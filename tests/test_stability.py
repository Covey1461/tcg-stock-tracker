from __future__ import annotations

from pathlib import Path

from tcg_resale_evaluator.stability import FolderStabilityTracker


def test_stability_requires_unchanged_folder_for_window(tmp_path: Path) -> None:
    folder = tmp_path / "New Folder"
    folder.mkdir()
    photo = folder / "a.jpg"
    photo.write_bytes(b"a")

    tracker = FolderStabilityTracker(required_seconds=4)
    assert tracker.observe(folder, now=0) is False
    assert tracker.observe(folder, now=3) is False
    assert tracker.observe(folder, now=4) is True

    photo.write_bytes(b"changed")
    assert tracker.observe(folder, now=5) is False
    assert tracker.observe(folder, now=9) is True
