from pathlib import Path

from tcg_resale_evaluator.index_store import DealIndex, DealIndexRow


def test_index_upsert_replaces_same_lot(tmp_path: Path) -> None:
    path = tmp_path / "index.csv"
    index = DealIndex(path)
    index.upsert(DealIndexRow(lot_id="LOT-1", status="Queued"))
    index.upsert(DealIndexRow(lot_id="LOT-1", status="Reviewed", verdict="BUY"))

    text = path.read_text(encoding="utf-8-sig")
    assert text.count("LOT-1") == 1
    assert "Reviewed" in text
    assert "BUY" in text
