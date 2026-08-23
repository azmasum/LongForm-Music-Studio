"""JSON-backed application settings with safe defaults and atomic writes."""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from lfms.core.paths import DataDirs, resolve_data_dirs, settings_file_path

DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "language": "en",
        "theme": "dark",
        "autosave_seconds": 120,
        "font_scale": 1.0,
    },
    "audio": {
        "sample_rate": 48000,
        "buffer_size": 1024,
        "device": None,
    },
    "generator": {
        "default_duration_minutes": 30,
        "default_genre": "AMBIENT",
        "default_intensity": 50,
        "preview_length_seconds": 30,
    },
    "rendering": {
        "cpu_threads": 0,
        "cache_dir": "",
        "temp_dir": "",
    },
    "storage": {
        "projects_dir": "",
        "library_dir": "",
        "backup_dir": "",
        "keep_backups": 20,
    },
    "ai": {
        "enabled": False,
        "provider": "none",
        "model": "",
        "api_key_env_var": "",
    },
    "privacy": {
        "local_only_mode": True,
        "telemetry": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self.path = Path(path) if path is not None else settings_file_path()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        self.load()

    @property
    def data(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                corrupt = self.path.with_suffix(self.path.suffix + ".corrupt")
                try:
                    if corrupt.exists():
                        corrupt.unlink()
                    os.replace(self.path, corrupt)
                except OSError:
                    pass
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
                return
            if not isinstance(raw, dict):
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
                return
            self._data = _deep_merge(DEFAULT_SETTINGS, raw)

    def save(self) -> None:
        with self._lock:
            payload = json.dumps(self._data, indent=2, ensure_ascii=False, sort_keys=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(payload + "\n", encoding="utf-8")
            os.replace(tmp, self.path)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any, *, save: bool = True) -> None:
        with self._lock:
            parts = dotted_key.split(".")
            node = self._data
            for part in parts[:-1]:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[part] = nxt
                node = nxt
            node[parts[-1]] = value
        if save:
            self.save()

    def update(self, values: dict[str, Any], *, save: bool = True) -> None:
        with self._lock:
            self._data = _deep_merge(self._data, values)
        if save:
            self.save()

    def reset_section(self, section: str, *, save: bool = True) -> None:
        with self._lock:
            if section in DEFAULT_SETTINGS:
                self._data[section] = copy.deepcopy(DEFAULT_SETTINGS[section])
        if save:
            self.save()


_instance: Config | None = None
_instance_lock = threading.Lock()


def get_config(dirs: DataDirs | None = None) -> Config:
    global _instance
    with _instance_lock:
        if _instance is None:
            resolved = dirs if dirs is not None else resolve_data_dirs()
            _instance = Config(settings_file_path(resolved))
        return _instance


def reset_config_singleton() -> None:
    global _instance
    with _instance_lock:
        _instance = None


def validate_settings(candidate: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    sample_rate = candidate.get("audio", {}).get("sample_rate")
    if sample_rate is not None and sample_rate not in (44100, 48000, 96000):
        problems.append("audio.sample_rate must be 44100, 48000 or 96000")
    duration = candidate.get("generator", {}).get("default_duration_minutes")
    if duration is not None and not (1 <= int(duration) <= 600):
        problems.append("generator.default_duration_minutes must be between 1 and 600")
    theme = candidate.get("general", {}).get("theme")
    if theme is not None and theme not in ("dark", "light", "system"):
        problems.append("general.theme must be dark, light or system")
    return problems
