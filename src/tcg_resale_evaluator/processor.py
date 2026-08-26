from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import logging
import os
import shutil
import threading
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from .config import AppConfig
from .index_store import DealIndex, DealIndexRow

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
CLAIM_PREFIX = ".claimed__"
MANIFEST_FIELDS = [
    "original_name",
    "prepared_name",
    "sha256",
    "perceptual_hash",
    "duplicate_type",
    "duplicate_of",
    "category",
    "width",
    "height",
]


class LotProcessingError(RuntimeError):
    """A queued lot cannot be prepared safely."""


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    lot_id: str
    status: str
    destination: Path
    image_count: int = 0
    duplicate_count: int = 0


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _lot_id_from_claim(path: Path) -> str:
    if not path.name.startswith(CLAIM_PREFIX):
        raise LotProcessingError(f"Not a claimed lot: {path.name}")
    claim_parts = path.name[len(CLAIM_PREFIX) :].split("__", 1)
    if len(claim_parts) != 2 or not claim_parts[0].isdigit():
        raise LotProcessingError(f"Malformed claim name: {path.name}")
    lot_id = claim_parts[1]
    if not lot_id or lot_id in {".", ".."} or any(char in lot_id for char in "/\\"):
        raise LotProcessingError(f"Unsafe lot ID: {lot_id!r}")
    return lot_id


def claim_next_lot(config: AppConfig) -> Path | None:
    """Atomically rename one visible queue directory so only one worker can take it."""
    config.ensure_layout()
    for candidate in sorted(config.processing_dir.iterdir(), key=lambda path: path.name.casefold()):
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        if candidate.is_symlink():
            continue
        claimed = config.processing_dir / f"{CLAIM_PREFIX}{os.getpid()}__{candidate.name}"
        try:
            candidate.rename(claimed)
        except (FileExistsError, FileNotFoundError, PermissionError):
            continue
        logger.info("Claimed queued lot %s", candidate.name)
        return claimed
    return None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_limited_information = 0x1000
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5  # Access denied means the process exists.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def recover_abandoned_claims(config: AppConfig) -> int:
    """Return claims owned by dead processes to the visible queue."""
    recovered = 0
    for claimed in sorted(config.processing_dir.glob(f"{CLAIM_PREFIX}*")):
        parts = claimed.name[len(CLAIM_PREFIX) :].split("__", 1)
        if len(parts) != 2 or not parts[0].isdigit() or _pid_is_running(int(parts[0])):
            continue
        queued = config.processing_dir / parts[1]
        if queued.exists():
            continue
        try:
            claimed.rename(queued)
        except (FileExistsError, FileNotFoundError, PermissionError):
            continue
        recovered += 1
        logger.warning("Recovered abandoned claim for lot %s", parts[1])
    return recovered


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _difference_hash(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.get_flattened_data())
    value = 0
    for y_value in range(8):
        row = y_value * 9
        for x_value in range(8):
            value = (value << 1) | int(pixels[row + x_value] > pixels[row + x_value + 1])
    return f"{value:016x}"


def _hash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _category(width: int, height: int) -> str:
    ratio = width / height
    if 0.56 <= ratio <= 0.82:
        return "possible_card_image"
    if ratio >= 1.25:
        return "possible_collection_photo"
    return "possible_listing_screenshot"


def _validate_and_normalize(
    source: Path,
    output: Path,
    config: AppConfig,
) -> tuple[int, int, str]:
    if source.suffix.casefold() not in SUPPORTED_SUFFIXES:
        raise LotProcessingError(
            f"Unsupported image extension for {source.name}; supported: JPEG, PNG, WebP."
        )
    size = source.stat().st_size
    if size <= 0:
        raise LotProcessingError(f"Image is empty: {source.name}")
    if size > config.max_file_bytes:
        raise LotProcessingError(
            f"Image exceeds the {config.max_file_bytes}-byte file limit: {source.name}"
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                if opened.format not in SUPPORTED_FORMATS:
                    raise LotProcessingError(
                        f"Unsupported image format for {source.name}: {opened.format or 'unknown'}"
                    )
                opened.verify()
            with Image.open(source) as reopened:
                raw_width, raw_height = reopened.size
                if raw_width <= 0 or raw_height <= 0:
                    raise LotProcessingError(f"Image has invalid dimensions: {source.name}")
                if raw_width > config.max_dimension or raw_height > config.max_dimension:
                    raise LotProcessingError(
                        f"Image exceeds the {config.max_dimension}-pixel dimension limit: {source.name}"
                    )
                if raw_width * raw_height > config.max_image_pixels:
                    raise LotProcessingError(
                        f"Image exceeds the {config.max_image_pixels}-pixel limit: {source.name}"
                    )
                oriented = ImageOps.exif_transpose(reopened)
                oriented.load()
                width, height = oriented.size
                normalized = oriented.convert("RGB")
                normalized.thumbnail(
                    (config.prepared_max_dimension, config.prepared_max_dimension),
                    Image.Resampling.LANCZOS,
                )
                perceptual_hash = _difference_hash(normalized)
                output.parent.mkdir(parents=True, exist_ok=True)
                normalized.save(output, "JPEG", quality=90, optimize=True)
                return width, height, perceptual_hash
    except LotProcessingError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise LotProcessingError(
            f"Image triggered decompression-bomb protection: {source.name}"
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise LotProcessingError(f"Malformed or unreadable image {source.name}: {exc}") from exc


def _make_contact_sheet(images: list[tuple[Path, str]], output: Path) -> None:
    thumb_width, thumb_height, label_height = 320, 240, 36
    columns = min(3, max(1, len(images)))
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (path, label) in enumerate(images):
        with Image.open(path) as opened:
            thumb = opened.convert("RGB")
            thumb.thumbnail((thumb_width - 16, thumb_height - 16), Image.Resampling.LANCZOS)
            x_value = (index % columns) * thumb_width + (thumb_width - thumb.width) // 2
            y_base = (index // columns) * (thumb_height + label_height)
            y_value = y_base + (thumb_height - thumb.height) // 2
            sheet.paste(thumb, (x_value, y_value))
            draw.text(
                (index % columns * thumb_width + 8, y_base + thumb_height + 8), label, fill="black"
            )
    sheet.save(output, "JPEG", quality=88, optimize=True)


def _preserve_originals(claimed: Path) -> Path:
    originals = claimed / "Originals"
    originals.mkdir(exist_ok=True)
    children = sorted(claimed.iterdir(), key=lambda path: path.name.casefold())
    inputs = [
        child
        for child in children
        if child != originals
        and not child.name.startswith("Prepared")
        and child.name != "error_report.json"
    ]
    invalid = next((child for child in inputs if child.is_symlink() or not child.is_file()), None)
    for child in inputs:
        if child.is_symlink() or not child.is_file():
            continue
        destination = originals / child.name
        if destination.exists():
            raise LotProcessingError(f"Original filename collision: {child.name}")
        child.rename(destination)
    if invalid is not None:
        raise LotProcessingError(f"Unsupported nested item in queued lot: {invalid.name}")
    return originals


def _write_review_report(claimed: Path, lot_id: str, message: str) -> None:
    payload = {
        "lot_id": lot_id,
        "status": "Needs Review",
        "failed_at": _utc_now(),
        "reason": message,
        "originals_preserved": (claimed / "Originals").is_dir(),
    }
    (claimed / "error_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _destination(config: AppConfig, lot_id: str, status: str) -> Path:
    parent = config.completed_dir if status == "Completed" else config.review_dir
    return parent / lot_id


def _finalize(config: AppConfig, claimed: Path, lot_id: str, status: str) -> Path:
    destination = _destination(config, lot_id, status)
    if destination.exists():
        raise LotProcessingError(f"Destination already exists: {destination}")
    claimed.rename(destination)
    return destination


def _index_result(
    config: AppConfig,
    lot_id: str,
    status: str,
    destination: Path,
    notes: str = "",
) -> None:
    try:
        DealIndex(config.index_csv).upsert(
            DealIndexRow(
                lot_id=lot_id,
                created_at=_utc_now(),
                status=status,
                folder=str(destination),
                notes=notes,
            ),
            preserve_existing=True,
        )
    except OSError:
        logger.exception("Could not update master deal index for %s", lot_id)


def process_claimed_lot(config: AppConfig, claimed: Path) -> ProcessingResult:
    """Preserve, validate, prepare, index, and route one atomically claimed lot."""
    lot_id = _lot_id_from_claim(claimed)
    prepared = claimed / "Prepared"
    marker = prepared / "listing_data.json"
    if marker.exists():
        payload = json.loads(marker.read_text(encoding="utf-8"))
        destination = _finalize(config, claimed, lot_id, "Completed")
        _index_result(config, lot_id, "Completed", destination)
        return ProcessingResult(
            lot_id,
            "Completed",
            destination,
            int(payload.get("image_count", 0)),
            int(payload.get("duplicate_count", 0)),
        )

    try:
        originals = _preserve_originals(claimed)
        source_files = sorted(
            (path for path in originals.iterdir() if path.is_file()),
            key=lambda path: path.name.casefold(),
        )
        if not source_files:
            raise LotProcessingError("Queued lot contains no images.")

        building = claimed / "Prepared.__building__"
        if building.exists():
            shutil.rmtree(building)
        images_dir = building / "Images"
        images_dir.mkdir(parents=True)

        exact_seen: dict[str, str] = {}
        perceptual_seen: list[tuple[str, str]] = []
        rows: list[dict[str, str | int]] = []
        sheet_images: list[tuple[Path, str]] = []
        duplicate_count = 0

        for sequence, source in enumerate(source_files, start=1):
            temporary = images_dir / f".__normalize__{sequence:03d}.jpg"
            width, height, perceptual_hash = _validate_and_normalize(source, temporary, config)
            exact_hash = _sha256(source)
            duplicate_type = ""
            duplicate_of = ""
            if exact_hash in exact_seen:
                duplicate_type = "exact"
                duplicate_of = exact_seen[exact_hash]
            else:
                for known_hash, known_name in perceptual_seen:
                    if (
                        _hash_distance(perceptual_hash, known_hash)
                        <= config.duplicate_hash_distance
                    ):
                        duplicate_type = "perceptual"
                        duplicate_of = known_name
                        break

            category = _category(width, height)
            if duplicate_type:
                final_name = f"possible_duplicate_{sequence:03d}.jpg"
                duplicate_count += 1
            else:
                final_name = f"{category}_{sequence:03d}.jpg"
            temporary.rename(images_dir / final_name)
            exact_seen.setdefault(exact_hash, final_name)
            if not duplicate_type:
                perceptual_seen.append((perceptual_hash, final_name))
            rows.append(
                {
                    "original_name": source.name,
                    "prepared_name": final_name,
                    "sha256": exact_hash,
                    "perceptual_hash": perceptual_hash,
                    "duplicate_type": duplicate_type,
                    "duplicate_of": duplicate_of,
                    "category": category,
                    "width": width,
                    "height": height,
                }
            )
            sheet_images.append((images_dir / final_name, final_name))

        with (building / "rename_manifest.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        _make_contact_sheet(sheet_images, building / "contact_sheet.jpg")
        payload = {
            "schema_version": 1,
            "lot_id": lot_id,
            "status": "Prepared",
            "prepared_at": _utc_now(),
            "image_count": len(rows),
            "duplicate_count": duplicate_count,
            "originals_folder": "../Originals",
            "prepared_images_folder": "Images",
            "images": rows,
        }
        (building / "listing_data.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary = (
            f"# Listing summary: {lot_id}\n\n"
            f"- Images received: {len(rows)}\n"
            f"- Possible duplicates: {duplicate_count}\n"
            "- Originals: preserved byte-for-byte in `Originals/`\n"
            "- Prepared images: normalized JPEGs in `Prepared/Images/`\n\n"
            "Filenames and categories are conservative local heuristics. Names beginning with "
            "`possible_` require human confirmation.\n"
        )
        (building / "listing_summary.md").write_text(summary, encoding="utf-8")
        prompt = (
            "Evaluate this TCG resale listing using the attached contact sheet and prepared images. "
            "Treat all possible_ filenames as uncertain hints, check the duplicate annotations in "
            "listing_data.json, identify visible games/products/sets and condition risks, then provide "
            "a conservative resale range, fees/shipping assumptions, maximum buy price, expected profit, "
            "ROI, key uncertainties, and a BUY/PASS/REVIEW verdict. Do not invent unreadable card details.\n"
        )
        (building / "chatgpt_prompt.txt").write_text(prompt, encoding="utf-8")
        building.rename(prepared)

        destination = _finalize(config, claimed, lot_id, "Completed")
        _index_result(config, lot_id, "Completed", destination)
        logger.info("Completed lot %s with %d images", lot_id, len(rows))
        return ProcessingResult(lot_id, "Completed", destination, len(rows), duplicate_count)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        logger.exception("Lot %s requires review: %s", lot_id, message)
        try:
            building = claimed / "Prepared.__building__"
            if building.exists():
                shutil.rmtree(building)
            _write_review_report(claimed, lot_id, message)
            destination = _finalize(config, claimed, lot_id, "Needs Review")
            _index_result(config, lot_id, "Needs Review", destination, message)
            return ProcessingResult(lot_id, "Needs Review", destination)
        except Exception:
            logger.exception("Failed to route lot %s to Needs Review", lot_id)
            raise


def process_next_lot(config: AppConfig) -> ProcessingResult | None:
    config.ensure_layout()
    recover_abandoned_claims(config)
    claimed = claim_next_lot(config)
    if claimed is None:
        return None
    return process_claimed_lot(config, claimed)


class ProcessingWorker:
    """Background queue consumer for the desktop app."""

    def __init__(
        self, config: AppConfig, *, on_status: Callable[[str], None] | None = None
    ) -> None:
        self.config = config
        self.on_status = on_status or (lambda _: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.config.ensure_layout()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="processing-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _emit(self, message: str) -> None:
        logger.info(message)
        self.on_status(message)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = process_next_lot(self.config)
            except Exception as exc:
                logger.exception("Processing worker error")
                self._emit(f"Processing worker error: {exc}")
                self._stop.wait(self.config.worker_poll_seconds)
                continue
            if result is None:
                self._stop.wait(self.config.worker_poll_seconds)
                continue
            self._emit(f"{result.lot_id}: {result.status}")
