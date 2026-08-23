"""Tests for the settings/config layer."""
from __future__ import annotations

import json
from pathlib import Path

from lfms.core.config import (
    DEFAULT_SETTINGS,
    Config,
    validate_settings,
)


def test_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json")
    assert cfg.get("general.theme") == "dark"
    assert cfg.get("privacy.telemetry") is False
    assert cfg.get("audio.sample_rate") == 48000


def test_set_and_persist_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    cfg = Config(path)
    cfg.set("generator.default_duration_minutes", 45)
    again = Config(path)
    assert again.get("generator.default_duration_minutes") == 45


def test_corrupt_file_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ not valid json !!", encoding="utf-8")
    cfg = Config(path)
    assert cfg.get("general.language") == "en"
    corrupt = path.with_suffix(".json.corrupt")
    assert corrupt.exists()


def test_partial_override_keeps_other_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"general": {"theme": "light"}}), encoding="utf-8")
    cfg = Config(path)
    assert cfg.get("general.theme") == "light"
    assert cfg.get("general.language") == "en"


def test_reset_section(tmp_path: Path) -> None:
    cfg = Config(tmp_path / "settings.json")
    cfg.set("general.autosave_seconds", 30, save=False)
    cfg.reset_section("general", save=False)
    assert cfg.get("general.autosave_seconds") == DEFAULT_SETTINGS["general"]["autosave_seconds"]


def test_validate_settings_rejects_bad_values() -> None:
    problems = validate_settings({"audio": {"sample_rate": 12345}})
    assert problems
    ok = validate_settings({"audio": {"sample_rate": 48000}, "general": {"theme": "dark"}})
    assert ok == []
