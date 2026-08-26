from __future__ import annotations

import csv
from pathlib import Path

from tcg_resale_evaluator.csv_tools import (
    BuylistProfile,
    export_buylist_csv,
    normalize_inventory_csv,
)
from tcg_resale_evaluator.inventory_flow import import_inventory_for_lot


def test_normalize_inventory_and_calculate_value(tmp_path: Path) -> None:
    source = tmp_path / "cards.csv"
    source.write_text(
        "Qty,Card Name,Set,Collector Number,Condition,Price\n"
        "2,Charizard,Base Set,4/102,NM,$25.00\n"
        "1,Pikachu,Jungle,60/64,LP,5.50\n",
        encoding="utf-8",
    )
    normalized = tmp_path / "normalized.csv"

    summary = normalize_inventory_csv(source, normalized)

    assert summary.rows == 2
    assert summary.quantity == 3
    assert str(summary.market_value) == "55.50"

    with normalized.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["name"] == "Charizard"
    assert rows[0]["line_value"] == "50.00"


def test_profile_driven_buylist_export(tmp_path: Path) -> None:
    normalized = tmp_path / "normalized.csv"
    normalized.write_text(
        "quantity,name,set_name,set_code,card_number,condition,finish,market_price,line_value\n"
        "2,Charizard,Base Set,BS,4/102,NM,Normal,25.00,50.00\n",
        encoding="utf-8",
    )
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        '{"name":"Test","columns":['
        '{"header":"Card","source":"name"},'
        '{"header":"Qty","source":"quantity"},'
        '{"header":"Language","constant":"English"}'
        "]}",
        encoding="utf-8",
    )
    output = tmp_path / "buylist.csv"

    profile = BuylistProfile.from_json(profile_file)
    export_buylist_csv(normalized, output, profile)

    with output.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"Card": "Charizard", "Qty": "2", "Language": "English"}]


def test_packaged_default_buylist_profile_is_available(tmp_path: Path) -> None:
    lot = tmp_path / "lot"
    source = tmp_path / "cards.csv"
    source.write_text("Name,Qty\nPikachu,2\n", encoding="utf-8")

    result = import_inventory_for_lot(lot, source)

    assert result.buylist_csv.exists()
    assert "Quantity,Name,Set" in result.buylist_csv.read_text(encoding="utf-8-sig")
