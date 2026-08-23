"""Tests for portable-mode path resolution."""
from __future__ import annotations

from pathlib import Path

from lfms.core import paths


def test_env_var_override(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "custom-data"
    dirs = paths.resolve_data_dirs(env={paths.ENV_DATA_DIR: str(target)})
    assert dirs.root == target
    assert dirs.projects.exists()
    assert dirs.library.name == "MusicLibrary"
    assert dirs.settings_dir.name == "Settings"


def test_portable_flag_makes_app_root_the_data_root(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / paths.PORTABLE_FLAG_NAME).write_text("portable", encoding="utf-8")
    env = {"APPDATA": str(tmp_path / "appdata")}
    dirs = paths.resolve_data_dirs(app_root_override=tmp_path, env=env)
    assert dirs.root == tmp_path
    assert (tmp_path / "Projects").exists()


def test_appdata_default_when_not_portable(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    env = {"APPDATA": str(tmp_path / "appdata")}
    dirs = paths.resolve_data_dirs(app_root_override=app, env=env)
    expected = Path(env["APPDATA"]) / "LongFormMusicStudio"
    assert dirs.root == expected


def test_ensure_is_idempotent(tmp_path: Path) -> None:
    dirs = paths.resolve_data_dirs(data_root_override=tmp_path / "root")
    first = dirs.ensure()
    again = dirs.ensure()
    assert first.root == again.root
    assert dirs.logs.exists()
