from __future__ import annotations

from pathlib import Path

import pytest

from tcg_resale_evaluator.config import AppConfig
from tcg_resale_evaluator.intake import (
    SubmissionError,
    find_process_triggers,
    is_process_trigger,
    submit_current_lot,
)


def test_process_trigger_matches_base_name_case_insensitively(tmp_path: Path) -> None:
    accepted = ["process", "PROCESS.txt", "Process.md", "pRoCeSs.jpg"]
    rejected = ["process-now.txt", "process_1.txt", "reprocess.txt"]

    for name in accepted + rejected:
        (tmp_path / name).write_text("x", encoding="utf-8")

    for name in accepted:
        assert is_process_trigger(tmp_path / name)
    for name in rejected:
        assert not is_process_trigger(tmp_path / name)


def test_find_process_triggers_only_returns_matching_files(tmp_path: Path) -> None:
    (tmp_path / "PROCESS.txt").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "process-folder").mkdir()

    triggers = find_process_triggers(tmp_path)
    assert [path.name for path in triggers] == ["PROCESS.txt"]


def test_submit_moves_lot_recreates_new_folder_and_deletes_trigger(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    config.ensure_layout()
    (config.intake_dir / "photo.jpg").write_bytes(b"photo")
    trigger = tmp_path / "PrOcEsS.txt"
    trigger.write_text("go", encoding="utf-8")

    result = submit_current_lot(
        config,
        trigger_path=trigger,
        lot_id_factory=lambda: "LOT-TEST-001",
    )

    assert result.queued_path == config.processing_dir / "LOT-TEST-001"
    assert (result.queued_path / "photo.jpg").exists()
    assert config.intake_dir.exists()
    assert list(config.intake_dir.iterdir()) == []
    assert not trigger.exists()
    assert result.trigger_deleted is True


def test_empty_intake_does_not_delete_trigger(tmp_path: Path) -> None:
    config = AppConfig(tmp_path)
    config.ensure_layout()
    trigger = tmp_path / "process.txt"
    trigger.write_text("go", encoding="utf-8")

    with pytest.raises(SubmissionError):
        submit_current_lot(config, trigger_path=trigger, lot_id_factory=lambda: "LOT-TEST")

    assert trigger.exists()
    assert config.intake_dir.exists()
