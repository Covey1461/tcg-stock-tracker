from pathlib import Path

from tcg_resale_evaluator.config import AppConfig
from tcg_resale_evaluator.diagnostics import diagnostics_ok, run_diagnostics


def test_diagnostics_create_and_validate_layout(tmp_path: Path) -> None:
    config = AppConfig(tmp_path / "TCG Resale Evaluator")
    checks = run_diagnostics(config)

    assert diagnostics_ok(checks)
    assert config.intake_dir.is_dir()
    assert config.processing_dir.is_dir()
    assert config.completed_dir.is_dir()
    assert config.review_dir.is_dir()
    assert config.data_dir.is_dir()


def test_diagnostics_fail_when_root_is_a_file(tmp_path: Path) -> None:
    root = tmp_path / "not-a-folder"
    root.write_text("x", encoding="utf-8")

    checks = run_diagnostics(AppConfig(root))

    assert not diagnostics_ok(checks)
    assert any(not check.passed for check in checks)


def test_diagnostics_require_key_only_when_ai_is_enabled(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    disabled = run_diagnostics(AppConfig(tmp_path / "disabled"))
    enabled = run_diagnostics(AppConfig(tmp_path / "enabled", ai_enabled=True))

    assert diagnostics_ok(disabled)
    assert not diagnostics_ok(enabled)
    assert any("OPENAI_API_KEY" in check.detail for check in enabled)
