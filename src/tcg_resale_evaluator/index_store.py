from __future__ import annotations

import csv
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

INDEX_FIELDS = [
    "lot_id",
    "created_at",
    "platform",
    "tcg",
    "asking_price",
    "location",
    "status",
    "folder",
    "inventory_rows",
    "inventory_quantity",
    "inventory_market_value",
    "verdict",
    "max_buy",
    "expected_resale",
    "expected_profit",
    "roi_percent",
    "notes",
]

_INDEX_LOCK = threading.Lock()


@dataclass(slots=True)
class DealIndexRow:
    lot_id: str
    created_at: str = ""
    platform: str = ""
    tcg: str = ""
    asking_price: str = ""
    location: str = ""
    status: str = "Queued"
    folder: str = ""
    inventory_rows: str = ""
    inventory_quantity: str = ""
    inventory_market_value: str = ""
    verdict: str = ""
    max_buy: str = ""
    expected_resale: str = ""
    expected_profit: str = ""
    roi_percent: str = ""
    notes: str = ""


class DealIndex:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path

    def _read_all(self) -> list[dict[str, str]]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def find(self, lot_id: str) -> dict[str, str] | None:
        with _INDEX_LOCK:
            return next((row for row in self._read_all() if row.get("lot_id") == lot_id), None)

    def upsert(self, row: DealIndexRow, *, preserve_existing: bool = False) -> None:
        with _INDEX_LOCK:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            rows = self._read_all()
            payload = {field: str(asdict(row).get(field, "")) for field in INDEX_FIELDS}
            replaced = False
            for index, existing in enumerate(rows):
                if existing.get("lot_id") == row.lot_id:
                    merged = {field: existing.get(field, "") for field in INDEX_FIELDS}
                    if preserve_existing:
                        for field, value in payload.items():
                            if field in {"lot_id", "status", "folder", "notes"} or not merged.get(
                                field
                            ):
                                merged[field] = value
                    else:
                        merged.update(payload)
                    rows[index] = merged
                    replaced = True
                    break
            if not replaced:
                rows.append(payload)

            temp = self.csv_path.with_suffix(".tmp")
            with temp.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            temp.replace(self.csv_path)
