"""Tests for backup manager, autosave timer, logging and crash reports."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from lfms.core.backup import AutosaveTimer, BackupManager, safe_filename_stem
from lfms.core.errors import StorageError
from lfms.core.logging_setup import setup_logging, write_crash_report


class TestBackupManager:
    def test_backup_creates_timestamped_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "My Project.lfms"
        src.write_text("{}", encoding="utf-8")
        mgr = BackupManager(tmp_path / "Backups", keep=3)
        backup = mgr.backup_file(src)
        assert backup.exists() and backup.read_text(encoding="utf-8") == "{}"
        assert "My_Project" in backup.name

    def test_backup_missing_file_raises(self, tmp_path: Path) -> None:
        mgr = BackupManager(tmp_path / "Backups")
        with pytest.raises(StorageError):
            mgr.backup_file(tmp_path / "nope.lfms")

    def test_prune_keeps_only_n(self, tmp_path: Path) -> None:
        src = tmp_path / "proj.lfms"
        src.write_text("{}", encoding="utf-8")
        mgr = BackupManager(tmp_path / "Backups", keep=2)
        for _ in range(4):
            mgr.backup_file(src)
        remaining = mgr.backups_for("proj")
        assert len(remaining) == 2
        assert remaining[0] == max(remaining, key=lambda p: p.name)

    def test_safe_filename_stem(self) -> None:
        assert safe_filename_stem("Dark // Psychology: 60min?") == "Dark_Psychology_60min"
        assert safe_filename_stem("***") == "untitled"


class TestAutosaveTimer:
    def test_due_after_interval(self) -> None:
        timer = AutosaveTimer(interval_seconds=5)
        assert not timer.due()

    def test_mark_saved_resets(self) -> None:
        timer = AutosaveTimer(interval_seconds=5)
        timer.mark_saved()
        assert not timer.due()


class TestLoggingAndCrash:
    def test_setup_writes_log_file(self, tmp_path: Path, clean_logging) -> None:
        logs = tmp_path / "Logs"
        setup_logging(logs, console=False)
        logging.getLogger("test").info("hello-lfms")
        for handler in logging.getLogger().handlers:
            handler.flush()
        log_file = logs / "lfms.log"
        assert log_file.exists()
        assert "hello-lfms" in log_file.read_text(encoding="utf-8")

    def test_setup_is_idempotent(self, tmp_path: Path, clean_logging) -> None:
        logs = tmp_path / "Logs"
        setup_logging(logs, console=False)
        count_first = len(logging.getLogger().handlers)
        setup_logging(logs, console=False)
        assert len(logging.getLogger().handlers) == count_first

    def test_crash_report_written(self, tmp_path: Path) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            report = write_crash_report(tmp_path, *sys.exc_info())
        text = report.read_text(encoding="utf-8")
        assert "crash report" in text
        assert "ValueError" in text and "boom" in text
