from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .csv_tools import BuylistProfile, InventorySummary, export_buylist_csv, normalize_inventory_csv


@dataclass(frozen=True, slots=True)
class InventoryImportResult:
    raw_copy: Path
    normalized_csv: Path
    buylist_csv: Path
    summary: InventorySummary


def import_inventory_for_lot(
    lot_folder: Path,
    input_csv: Path,
    profile_path: Path | None = None,
) -> InventoryImportResult:
    inventory_dir = lot_folder / "Inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)

    raw_copy = inventory_dir / f"source_{input_csv.name}"
    shutil.copy2(input_csv, raw_copy)

    normalized_csv = inventory_dir / "inventory_normalized.csv"
    summary = normalize_inventory_csv(raw_copy, normalized_csv)

    if profile_path is None:
        profile_text = (
            resources.files("tcg_resale_evaluator.resources")
            .joinpath("default-buylist.json")
            .read_text(encoding="utf-8")
        )
        profile = BuylistProfile.from_json_text(profile_text)
    else:
        profile = BuylistProfile.from_json(profile_path)
    buylist_csv = inventory_dir / "buylist_export.csv"
    export_buylist_csv(normalized_csv, buylist_csv, profile)

    return InventoryImportResult(
        raw_copy=raw_copy,
        normalized_csv=normalized_csv,
        buylist_csv=buylist_csv,
        summary=summary,
    )
