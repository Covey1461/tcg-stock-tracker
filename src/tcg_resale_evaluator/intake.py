from __future__ import annotations

import logging
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppConfig
from .index_store import DealIndex, DealIndexRow

logger = logging.getLogger(__name__)

LOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SubmissionError(RuntimeError):
    """Raised when the current intake folder cannot be submitted safely."""


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    lot_id: str
    queued_path: Path
    trigger_deleted: bool


def is_process_trigger(path: Path) -> bool:
    """Return True when a file's base name is exactly 'process', case-insensitive."""
    return path.is_file() and path.stem.casefold() == "process"


def find_process_triggers(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir() if is_process_trigger(path)),
        key=lambda path: path.name.casefold(),
    )


def intake_has_content(intake_dir: Path) -> bool:
    return intake_dir.exists() and any(intake_dir.iterdir())


def _validate_lot_id(lot_id: str) -> str:
    if lot_id in {".", ".."} or not LOT_ID_RE.fullmatch(lot_id):
        raise SubmissionError(
            "Lot ID contains unsafe characters. Allowed: letters, numbers, dot, dash, underscore."
        )
    return lot_id


def _validate_trigger(config: AppConfig, trigger_path: Path) -> Path:
    try:
        root = config.root.resolve(strict=True)
        trigger = trigger_path.resolve(strict=True)
    except OSError as exc:
        raise SubmissionError(f"Process trigger is not accessible: {trigger_path}") from exc

    if trigger.parent != root or not is_process_trigger(trigger_path):
        raise SubmissionError("Process trigger must be a file named 'process' in the app root.")
    return trigger_path


def _default_lot_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC).astimezone()).strftime("%Y%m%d-%H%M%S")
    return f"LOT-{stamp}-{uuid.uuid4().hex[:6].upper()}"


def submit_current_lot(
    config: AppConfig,
    *,
    trigger_path: Path | None = None,
    lot_id_factory: Callable[[], str] = _default_lot_id,
) -> SubmissionResult:
    """Submit the reusable intake folder safely.

    The optional trigger is deleted only after the lot has moved and a fresh intake folder exists.
    """
    config.ensure_layout()
    intake = config.intake_dir

    if trigger_path is not None:
        trigger_path = _validate_trigger(config, trigger_path)

    if not intake_has_content(intake):
        raise SubmissionError("The intake folder is empty; nothing was submitted.")

    lot_id = _validate_lot_id(lot_id_factory())
    destination = config.processing_dir / lot_id
    if destination.exists():
        raise SubmissionError(f"Processing destination already exists: {destination}")

    staging = config.root / f".__intake_staging__{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)

    moved = False
    try:
        shutil.move(str(intake), str(destination))
        moved = True
        staging.rename(intake)
    except Exception as exc:
        if moved and destination.exists() and not intake.exists():
            try:
                shutil.move(str(destination), str(intake))
            except Exception:
                logger.exception("Failed to roll back lot after submission error")
        if staging.exists():
            try:
                staging.rmdir()
            except OSError:
                pass
        raise SubmissionError(f"Failed to submit current lot safely: {exc}") from exc

    trigger_deleted = False
    if trigger_path is not None and trigger_path.exists():
        try:
            trigger_path.unlink()
            trigger_deleted = True
        except OSError as exc:
            raise SubmissionError(
                f"Lot was queued, but trigger cleanup failed: {trigger_path}: {exc}"
            ) from exc

    try:
        DealIndex(config.index_csv).upsert(
            DealIndexRow(
                lot_id=lot_id,
                created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                status="Queued",
                folder=str(destination),
            )
        )
    except OSError:
        logger.exception("Lot queued, but master deal index update failed for %s", lot_id)

    return SubmissionResult(lot_id=lot_id, queued_path=destination, trigger_deleted=trigger_deleted)
