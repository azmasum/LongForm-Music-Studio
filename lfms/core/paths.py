"""Path resolution with portable-mode support.

Data locations are resolved in this priority order:
1. ``LFMS_DATA_DIR`` environment variable (useful for tests and advanced users).
2. Portable mode: a ``portable.flag`` file inside the application root makes all
   data live next to the executable/package (external-drive friendly).
3. Default per-user directory: ``%APPDATA%\\LongFormMusicStudio``.

No absolute paths are ever hardcoded; everything derives from these roots.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PORTABLE_FLAG_NAME = "portable.flag"
ENV_DATA_DIR = "LFMS_DATA_DIR"


@dataclass(frozen=True)
class DataDirs:
    root: Path
    projects: Path
    library: Path
    presets: Path
    exports: Path
    cache: Path
    backups: Path
    logs: Path
    settings_dir: Path

    def ensure(self) -> DataDirs:
        for path in (
            self.root,
            self.projects,
            self.library,
            self.presets,
            self.exports,
            self.cache,
            self.backups,
            self.logs,
            self.settings_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


def app_root() -> Path:
    """Directory of the running app (frozen exe dir or repo/package parent)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_data_root(
    *,
    app_root_override: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    env_map = env if env is not None else os.environ
    override = env_map.get(ENV_DATA_DIR, "").strip()
    if override:
        return Path(override).expanduser()
    root = app_root_override if app_root_override is not None else app_root()
    if (root / PORTABLE_FLAG_NAME).exists():
        return root
    base = env_map.get("APPDATA", "")
    if base:
        return Path(base) / "LongFormMusicStudio"
    return root / "Settings"


def resolve_data_dirs(
    *,
    data_root_override: Path | None = None,
    app_root_override: Path | None = None,
    env: dict[str, str] | None = None,
) -> DataDirs:
    root = (
        data_root_override
        if data_root_override is not None
        else default_data_root(app_root_override=app_root_override, env=env)
    )
    dirs = DataDirs(
        root=root,
        projects=root / "Projects",
        library=root / "MusicLibrary",
        presets=root / "Presets",
        exports=root / "Exports",
        cache=root / "Cache",
        backups=root / "Backups",
        logs=root / "Logs",
        settings_dir=root / "Settings",
    )
    return dirs.ensure()


def settings_file_path(dirs: DataDirs | None = None) -> Path:
    resolved = dirs if dirs is not None else resolve_data_dirs()
    return resolved.settings_dir / "settings.json"


@lru_cache(maxsize=1)
def cached_data_dirs() -> DataDirs:
    return resolve_data_dirs()


def reset_cached_data_dirs() -> None:
    cached_data_dirs.cache_clear()
