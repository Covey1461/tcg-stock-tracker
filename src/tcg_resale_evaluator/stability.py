from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time


def folder_signature(folder: Path) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    if not folder.exists():
        return tuple()
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        rows.append((str(path.relative_to(folder)), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(rows))


@dataclass(slots=True)
class FolderStabilityTracker:
    required_seconds: float = 4.0
    _signature: tuple[tuple[str, int, int], ...] | None = None
    _stable_since: float | None = None

    def observe(self, folder: Path, *, now: float | None = None) -> bool:
        current_time = time.monotonic() if now is None else now
        signature = folder_signature(folder)

        if not signature:
            self._signature = signature
            self._stable_since = current_time
            return False

        if signature != self._signature:
            self._signature = signature
            self._stable_since = current_time
            return False

        if self._stable_since is None:
            self._stable_since = current_time
            return False

        return (current_time - self._stable_since) >= self.required_seconds

    def reset(self) -> None:
        self._signature = None
        self._stable_since = None
