from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from tcg_resale_evaluator.config import AppConfig
from tcg_resale_evaluator.index_store import DealIndex, DealIndexRow
from tcg_resale_evaluator.processor import (
    _pid_is_running,
    claim_next_lot,
    process_next_lot,
    recover_abandoned_claims,
)


def _image(path: Path, *, size: tuple[int, int] = (600, 900), variant: int = 0) -> None:
    image = Image.new("RGB", size, (30, 80, 140))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline=(240, 220, 80), width=10)
    draw.text((80, 100 + variant), "TCG CARD", fill=(255, 255, 255))
    image.save(path)


def _queue(config: AppConfig, lot_id: str = "LOT-TEST") -> Path:
    config.ensure_layout()
    lot = config.processing_dir / lot_id
    lot.mkdir()
    return lot


def test_worker_preserves_originals_and_creates_complete_artifact_set(tmp_path: Path) -> None:
    config = AppConfig(tmp_path, prepared_max_dimension=500)
    lot = _queue(config)
    source = lot / "phone upload.png"
    _image(source)
    original_bytes = source.read_bytes()
    DealIndex(config.index_csv).upsert(
        DealIndexRow(lot_id="LOT-TEST", created_at="2026-01-01", platform="Marketplace")
    )

    result = process_next_lot(config)

    assert result is not None
    assert result.status == "Completed"
    completed = config.completed_dir / "LOT-TEST"
    assert (completed / "Originals" / source.name).read_bytes() == original_bytes
    prepared = completed / "Prepared"
    expected = {
        "Images",
        "contact_sheet.jpg",
        "rename_manifest.csv",
        "listing_data.json",
        "listing_summary.md",
        "chatgpt_prompt.txt",
    }
    assert expected == {path.name for path in prepared.iterdir()}
    prepared_image = next((prepared / "Images").iterdir())
    with Image.open(prepared_image) as image:
        assert max(image.size) <= 500
        assert image.format == "JPEG"
    data = json.loads((prepared / "listing_data.json").read_text(encoding="utf-8"))
    assert data["image_count"] == 1
    assert data["lot_id"] == "LOT-TEST"
    with config.index_csv.open(newline="", encoding="utf-8-sig") as handle:
        index_rows = list(csv.DictReader(handle))
    assert [row["lot_id"] for row in index_rows] == ["LOT-TEST"]
    assert index_rows[0]["created_at"] == "2026-01-01"
    assert index_rows[0]["platform"] == "Marketplace"
    assert index_rows[0]["status"] == "Completed"


def test_exif_orientation_is_applied_without_changing_original(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _queue(config)
    source = lot / "rotated.jpg"
    image = Image.new("RGB", (40, 80), "red")
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    original_bytes = source.read_bytes()

    result = process_next_lot(config)

    assert result is not None and result.status == "Completed"
    completed = result.destination
    assert (completed / "Originals" / "rotated.jpg").read_bytes() == original_bytes
    with Image.open(next((completed / "Prepared" / "Images").iterdir())) as prepared:
        assert prepared.size == (80, 40)


def test_exact_and_perceptual_duplicates_are_recorded(tmp_path: Path) -> None:
    config = AppConfig(tmp_path, duplicate_hash_distance=4)
    lot = _queue(config)
    _image(lot / "first.png")
    (lot / "exact.png").write_bytes((lot / "first.png").read_bytes())
    _image(lot / "near.png", variant=1)

    result = process_next_lot(config)

    assert result is not None and result.status == "Completed"
    with (result.destination / "Prepared" / "rename_manifest.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        rows = list(csv.DictReader(handle))
    duplicate_types = {row["duplicate_type"] for row in rows if row["duplicate_type"]}
    assert "exact" in duplicate_types
    assert "perceptual" in duplicate_types
    assert result.duplicate_count == 2


def test_conservative_content_filename_uses_possible_prefix(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _queue(config)
    _image(lot / "wide.webp", size=(1200, 600))

    result = process_next_lot(config)

    assert result is not None
    names = [path.name for path in (result.destination / "Prepared" / "Images").iterdir()]
    assert names == ["possible_collection_photo_001.jpg"]


@pytest.mark.parametrize(
    ("filename", "config_kwargs", "contents", "reason"),
    [
        ("broken.jpg", {}, b"not an image", "Malformed or unreadable"),
        ("notes.gif", {}, b"GIF89a", "Unsupported image extension"),
    ],
)
def test_malformed_and_unsupported_inputs_route_to_review(
    tmp_path: Path,
    filename: str,
    config_kwargs: dict[str, int],
    contents: bytes,
    reason: str,
) -> None:
    config = AppConfig(tmp_path, **config_kwargs)
    lot = _queue(config)
    (lot / filename).write_bytes(contents)

    result = process_next_lot(config)

    assert result is not None and result.status == "Needs Review"
    assert (result.destination / "Originals" / filename).read_bytes() == contents
    report = json.loads((result.destination / "error_report.json").read_text(encoding="utf-8"))
    assert reason in report["reason"]
    assert "Needs Review" in config.index_csv.read_text(encoding="utf-8-sig")


def test_file_size_limit_routes_to_review(tmp_path: Path) -> None:
    config = AppConfig(tmp_path, max_file_bytes=100)
    lot = _queue(config)
    _image(lot / "large.png")

    result = process_next_lot(config)

    assert result is not None and result.status == "Needs Review"
    report = json.loads((result.destination / "error_report.json").read_text(encoding="utf-8"))
    assert "file limit" in report["reason"]


@pytest.mark.parametrize(
    ("config_kwargs", "expected"),
    [
        ({"max_image_pixels": 1_000}, "pixel limit"),
        ({"max_dimension": 100}, "dimension limit"),
    ],
)
def test_pixel_and_dimension_limits_route_to_review(
    tmp_path: Path, config_kwargs: dict[str, int], expected: str
) -> None:
    config = AppConfig(tmp_path, **config_kwargs)
    lot = _queue(config)
    _image(lot / "too-big.png", size=(200, 200))

    result = process_next_lot(config)

    assert result is not None and result.status == "Needs Review"
    report = json.loads((result.destination / "error_report.json").read_text(encoding="utf-8"))
    assert expected in report["reason"]


def test_claim_is_atomic_and_completed_work_is_idempotent(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _queue(config)
    _image(lot / "one.jpg")

    claimed = claim_next_lot(config)
    assert claimed == config.processing_dir / f".claimed__{os.getpid()}__LOT-TEST"
    assert claim_next_lot(config) is None

    # Put it back to exercise the public worker path, then verify no second pass occurs.
    claimed.rename(lot)
    first = process_next_lot(config)
    second = process_next_lot(config)

    assert first is not None and first.status == "Completed"
    assert second is None
    assert [path.name for path in config.completed_dir.iterdir()] == ["LOT-TEST"]
    with config.index_csv.open(newline="", encoding="utf-8-sig") as handle:
        assert [row["lot_id"] for row in csv.DictReader(handle)] == ["LOT-TEST"]


def test_abandoned_claim_is_recovered(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    config.ensure_layout()
    abandoned = config.processing_dir / ".claimed__99999999__LOT-OLD"
    abandoned.mkdir()
    _image(abandoned / "one.jpg")

    assert recover_abandoned_claims(config) == 1
    assert (config.processing_dir / "LOT-OLD" / "one.jpg").exists()


def test_current_worker_process_is_detected_without_signalling_it() -> None:
    assert _pid_is_running(os.getpid())


def test_nested_input_failure_is_routed_and_existing_files_are_preserved(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    lot = _queue(config)
    _image(lot / "one.jpg")
    (lot / "nested").mkdir()

    result = process_next_lot(config)

    assert result is not None and result.status == "Needs Review"
    assert (result.destination / "Originals" / "one.jpg").exists()
    assert (result.destination / "nested").is_dir()
