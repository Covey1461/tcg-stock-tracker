from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import AppConfig


def configure_logging(config: AppConfig) -> None:
    """Configure one bounded application log under Data/logs."""
    log_dir = config.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(handler, "_tcg_resale_handler", False) for handler in root.handlers):
        return
    handler = RotatingFileHandler(
        log_dir / "tcg-resale-evaluator.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler._tcg_resale_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
