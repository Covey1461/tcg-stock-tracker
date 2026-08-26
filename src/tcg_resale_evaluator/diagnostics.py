from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    passed: bool
    detail: str


def _check_python() -> DiagnosticCheck:
    version = sys.version_info
    passed = version >= (3, 11)
    return DiagnosticCheck(
        "Python version",
        passed,
        f"{version.major}.{version.minor}.{version.micro}",
    )


def _check_layout(config: AppConfig) -> DiagnosticCheck:
    try:
        config.ensure_layout()
    except OSError as exc:
        return DiagnosticCheck("Folder layout", False, str(exc))

    required = [
        config.intake_dir,
        config.processing_dir,
        config.completed_dir,
        config.review_dir,
        config.data_dir,
    ]
    missing = [str(path) for path in required if not path.is_dir()]
    if missing:
        return DiagnosticCheck("Folder layout", False, f"Missing: {', '.join(missing)}")
    return DiagnosticCheck("Folder layout", True, str(config.root))


def _check_writable(config: AppConfig) -> DiagnosticCheck:
    try:
        config.ensure_layout()
        fd, name = tempfile.mkstemp(prefix=".__tcg_write_test__", dir=config.root)
        os.close(fd)
        Path(name).unlink()
    except OSError as exc:
        return DiagnosticCheck("Root writable", False, str(exc))
    return DiagnosticCheck("Root writable", True, str(config.root))


def run_diagnostics(config: AppConfig) -> list[DiagnosticCheck]:
    return [_check_python(), _check_layout(config), _check_writable(config)]


def diagnostics_ok(checks: list[DiagnosticCheck]) -> bool:
    return all(check.passed for check in checks)


def main() -> int:
    from .app import choose_root

    config = AppConfig(root=choose_root())
    checks = run_diagnostics(config)
    print("TCG Resale Evaluator - system check")
    print(f"Root: {config.root}")
    print()
    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    return 0 if diagnostics_ok(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
