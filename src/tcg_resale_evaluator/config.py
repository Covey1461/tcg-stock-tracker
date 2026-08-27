from __future__ import annotations

import os
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
    ai_enabled: bool = False
    openai_model: str = "gpt-5.6-terra"
    evaluation_poll_seconds: float = 10.0
    evaluation_max_images: int = 8
    evaluation_max_image_bytes: int = 8 * 1024 * 1024
    evaluation_max_total_image_bytes: int = 32 * 1024 * 1024
    evaluation_max_output_tokens: int = 12000
    evaluation_max_tool_calls: int = 6
    platform_fee_rate: float = 0.13
    default_shipping_cost: float = 10.0
    max_buy_fraction: float = 0.55

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


def config_from_environment(root: Path) -> AppConfig:
    enabled = os.getenv("TCG_AI_ENABLED", "").strip().casefold() in {"1", "true", "yes", "on"}
    model = os.getenv("TCG_OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
    return AppConfig(root=root, ai_enabled=enabled, openai_model=model)
