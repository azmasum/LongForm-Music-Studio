"""Backup and autosave helpers.

Backups are timestamped copies; the original project file is never destroyed.
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
from pathlib import Path

from lfms.core.errors import StorageError

_SAFE_STEM = re.compile(r"[^A-Za-z0-9_\-]+")


def safe_filename_stem(name: str) -> str:
    stem = _SAFE_STEM.sub("_", name).strip("_")
    return stem or "untitled"


class BackupManager:
    def __init__(self, backup_dir: Path | str, keep: int = 20) -> None:
        self.backup_dir = Path(backup_dir)
        self.keep = max(1, int(keep))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_file(self, source: Path | str, label: str = "") -> Path:
        source = Path(source)
        if not source.is_file():
            raise StorageError(
                f"Cannot back up missing file: {source.name}",
                technical=str(source),
                suggestion="Save the project before creating a backup.",
            )
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        stem = safe_filename_stem(source.stem)
        target = self.backup_dir / f"{stem}_{stamp}{suffix}{source.suffix}"
        counter = 1
        while target.exists():
            target = self.backup_dir / f"{stem}_{stamp}{suffix}_{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, target)
        self.prune(source.stem)
        return target

    def backups_for(self, stem: str) -> list[Path]:
        prefix = f"{safe_filename_stem(stem)}_"
        found = [p for p in self.backup_dir.glob(f"{prefix}*") if p.is_file()]
        return sorted(found, key=lambda p: p.name, reverse=True)

    def prune(self, stem: str) -> list[Path]:
        existing = self.backups_for(stem)
        removed = []
        for old in existing[self.keep :]:
            try:
                old.unlink()
                removed.append(old)
            except OSError:
                continue
        return removed


class AutosaveTimer:
    """Tracks elapsed time and signals when an autosave is due."""

    def __init__(self, interval_seconds: float = 120.0) -> None:
        self.interval = max(5.0, float(interval_seconds))
        self._last_save: float | None = None
        import time

        self._time = time.monotonic
        self.mark_saved()

    def mark_saved(self) -> None:
        self._last_save = self._time()

    def due(self) -> bool:
        if self._last_save is None:
            return True
        return (self._time() - self._last_save) >= self.interval
