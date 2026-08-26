from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

ALIASES = {
    "quantity": {"quantity", "qty", "count", "copies"},
    "name": {"name", "card", "card name", "product name"},
    "set_name": {"set", "set name", "expansion"},
    "set_code": {"set code", "setcode", "edition code"},
    "card_number": {"number", "card number", "collector number", "collector #", "#"},
    "condition": {"condition", "cond"},
    "finish": {"finish", "printing", "foil", "variant"},
    "market_price": {"market price", "price", "tcg market", "market", "value", "unit price"},
}

NORMALIZED_FIELDS = [
    "quantity",
    "name",
    "set_name",
    "set_code",
    "card_number",
    "condition",
    "finish",
    "market_price",
    "line_value",
]


def _canon(value: str) -> str:
    return " ".join(value.strip().casefold().replace("_", " ").replace("-", " ").split())


def _header_map(headers: Iterable[str]) -> dict[str, str]:
    lookup = {_canon(header): header for header in headers}
    result: dict[str, str] = {}
    for normalized, aliases in ALIASES.items():
        for alias in aliases:
            if _canon(alias) in lookup:
                result[normalized] = lookup[_canon(alias)]
                break
    return result


def _decimal(value: str) -> Decimal:
    clean = value.strip().replace("$", "").replace(",", "")
    if not clean:
        return Decimal(0)
    try:
        return Decimal(clean)
    except InvalidOperation:
        return Decimal(0)


def _quantity(value: str) -> int:
    try:
        return max(0, int(float(value.strip() or "1")))
    except ValueError:
        return 1


@dataclass(frozen=True, slots=True)
class InventorySummary:
    rows: int
    quantity: int
    market_value: Decimal


def normalize_inventory_csv(input_csv: Path, output_csv: Path) -> InventorySummary:
    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Inventory CSV has no header row.")
        mapping = _header_map(reader.fieldnames)
        if "name" not in mapping:
            raise ValueError("Inventory CSV must contain a recognizable card/name column.")

        normalized_rows: list[dict[str, str]] = []
        total_qty = 0
        total_value = Decimal(0)

        for source in reader:
            name = (source.get(mapping["name"], "") or "").strip()
            if not name:
                continue
            qty = _quantity(source.get(mapping.get("quantity", ""), "1") or "1")
            unit_price = _decimal(source.get(mapping.get("market_price", ""), "") or "")
            line_value = unit_price * qty
            total_qty += qty
            total_value += line_value

            row = {
                "quantity": str(qty),
                "name": name,
                "set_name": (source.get(mapping.get("set_name", ""), "") or "").strip(),
                "set_code": (source.get(mapping.get("set_code", ""), "") or "").strip(),
                "card_number": (source.get(mapping.get("card_number", ""), "") or "").strip(),
                "condition": (source.get(mapping.get("condition", ""), "") or "").strip(),
                "finish": (source.get(mapping.get("finish", ""), "") or "").strip(),
                "market_price": f"{unit_price:.2f}",
                "line_value": f"{line_value:.2f}",
            }
            normalized_rows.append(row)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=NORMALIZED_FIELDS)
        writer.writeheader()
        writer.writerows(normalized_rows)

    return InventorySummary(rows=len(normalized_rows), quantity=total_qty, market_value=total_value)


@dataclass(frozen=True, slots=True)
class BuylistColumn:
    header: str
    source: str = ""
    constant: str = ""


@dataclass(frozen=True, slots=True)
class BuylistProfile:
    name: str
    columns: tuple[BuylistColumn, ...]

    @classmethod
    def from_json(cls, path: Path) -> BuylistProfile:
        return cls.from_json_text(path.read_text(encoding="utf-8"))

    @classmethod
    def from_json_text(cls, text: str) -> BuylistProfile:
        payload = json.loads(text)
        return cls(
            name=payload["name"],
            columns=tuple(BuylistColumn(**column) for column in payload["columns"]),
        )


def export_buylist_csv(normalized_csv: Path, output_csv: Path, profile: BuylistProfile) -> None:
    with normalized_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = [column.header for column in profile.columns]
    with output_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for source_row in rows:
            output_row: dict[str, str] = {}
            for column in profile.columns:
                output_row[column.header] = (
                    column.constant if column.constant else source_row.get(column.source, "")
                )
            writer.writerow(output_row)
