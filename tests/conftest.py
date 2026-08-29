"""Shared pytest fixtures."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from lfms.core import paths


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "data"))
    paths.reset_cached_data_dirs()
    yield tmp_path / "data"
    paths.reset_cached_data_dirs()


@pytest.fixture()
def clean_logging():
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def qapp():
    """A single Qt application instance for GUI tests.

    Creating Qt widgets without a QApplication instance is a native crash
    (Windows fatal exception: access violation). This guards every GUI test
    file that instantiates widgets/scenes.
    """
    if os.environ.get("LFMS_GUI_SMOKE") != "1":
        pytest.skip("set LFMS_GUI_SMOKE=1 to run GUI tests")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
