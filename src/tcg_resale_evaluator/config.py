from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    root: Path
    intake_name: str = "New Folder"
    processing_name: str = "Processing"
    completed_name: str = "Completed"
    review_name: str = "Needs Review"
    data_name: str = "Data"
    poll_seconds: float = 1.0
    settle_seconds: float = 4.0
    worker_poll_seconds: float = 2.0
    max_file_bytes: int = 50 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    max_dimension: int = 20_000
    prepared_max_dimension: int = 2400
    duplicate_hash_distance: int = 4

    @property
    def intake_dir(self) -> Path:
        return self.root / self.intake_name

    @property
    def processing_dir(self) -> Path:
        return self.root / self.processing_name

    @property
    def completed_dir(self) -> Path:
        return self.root / self.completed_name

    @property
    def review_dir(self) -> Path:
        return self.root / self.review_name

    @property
    def data_dir(self) -> Path:
        return self.root / self.data_name

    @property
    def index_csv(self) -> Path:
        return self.data_dir / "TCG_Deal_Index.csv"

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.intake_dir.mkdir(parents=True, exist_ok=True)
