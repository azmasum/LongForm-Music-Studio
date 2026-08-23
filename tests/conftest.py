"""Shared pytest fixtures."""
from __future__ import annotations

import logging
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
