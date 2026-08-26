from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .config import AppConfig
from .intake import SubmissionError, find_process_triggers, submit_current_lot
from .stability import FolderStabilityTracker

logger = logging.getLogger(__name__)


class IntakeWatcher:
    """Polling watcher chosen intentionally for Google Drive sync robustness."""

    def __init__(self, config: AppConfig, *, on_status: Callable[[str], None] | None = None) -> None:
        self.config = config
        self.on_status = on_status or (lambda _: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stability = FolderStabilityTracker(config.settle_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.config.ensure_layout()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="intake-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _emit(self, message: str) -> None:
        logger.info(message)
        self.on_status(message)

    def _run(self) -> None:
        while not self._stop.wait(self.config.poll_seconds):
            triggers = find_process_triggers(self.config.root)
            if not triggers:
                self._stability.reset()
                continue

            trigger = triggers[0]
            if not self._stability.observe(self.config.intake_dir):
                self._emit(f"Process trigger detected; waiting for uploads to settle: {trigger.name}")
                continue

            try:
                result = submit_current_lot(self.config, trigger_path=trigger)
            except SubmissionError as exc:
                self._emit(str(exc))
                continue

            self._stability.reset()
            self._emit(f"Queued {result.lot_id}; a fresh New Folder is ready.")
