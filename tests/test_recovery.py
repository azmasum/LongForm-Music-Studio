"""Crash-recovery drills: damaged data, interrupted writes, queue failures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from lfms.batch import JobStatus, RenderQueue
from lfms.core.backup import BackupManager
from lfms.core.errors import ValidationError
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService
from lfms.provenance import verify_item
from lfms.timeline.model import TimelineDocument


def _params(seed=11, duration=5.0) -> GenerationParameters:
    params = GenerationParameters(
        seed=seed,
        duration_sec=duration,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=35.0,
    )
    params.validate()
    return params


# --------------------------------------------------------- damaged inputs


def test_corrupt_audio_file_rejected_cleanly(tmp_path: Path):
    bad = tmp_path / "broken.wav"
    bad.write_bytes(b"RIFF\x00\x00\x00\x00WAVEjunkjunkjunk")
    service = LibraryService(":memory:")
    with pytest.raises(ValidationError):
        service.import_audio_file(bad)
    truncated = tmp_path / "trunc.wav"
    truncated.write_bytes(b"RIFF\xff\xff\xff\x01WAVEfmt " + b"\x00" * 40)
    with pytest.raises(ValidationError):
        service.import_audio_file(truncated)
    service.close()


@pytest.mark.parametrize("garbage", [None, 42, "text", [1, 2], {"tracks": 7}])
def test_damaged_project_json_raises_lfms_error(garbage):
    from lfms.core.errors import LFMSError

    with pytest.raises(LFMSError):
        TimelineDocument.from_dict(garbage)


def test_partially_written_project_recovers_via_backup(tmp_path: Path):
    """A half-written project file is unusable; the backup restores work."""
    projects = tmp_path / "Projects"
    projects.mkdir()
    primary = projects / "session.json"
    doc = TimelineDocument(title="Session", duration_sec=600.0)
    primary.write_text(json.dumps(doc.to_dict()), encoding="utf-8")
    manager = BackupManager(tmp_path / "Backups", keep=3)
    backup_path = manager.backup_file(primary)

    # simulate a crash mid-write: truncated JSON on the primary file
    primary.write_text('{"title": "Sess', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(primary.read_text(encoding="utf-8"))

    # recovery path: load from the newest backup instead
    assert manager.backups_for("session")[0] == backup_path
    recovered = TimelineDocument.from_dict(json.loads(backup_path.read_text(encoding="utf-8")))
    assert recovered.title == "Session"


# ------------------------------------------------------ database recovery


def test_uncommitted_write_is_rolled_back_on_crash(tmp_path: Path):
    db_path = tmp_path / "library.db"
    service = LibraryService(db_path)
    committed = service.add_item("Committed item")
    service.close()

    # a second process/connection writes but "crashes" before commit
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(
            "INSERT INTO items (title, kind, notes, favorite, added_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("Ghost item", "AUDIO_FILE", "", 0, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        raise sqlite3.OperationalError("simulated crash mid-transaction")
    except sqlite3.OperationalError:
        pass
    finally:
        raw.close()  # implicit rollback of the uncommitted insert

    reopened = LibraryService(db_path)
    titles = [item.title for item in reopened.list_items()]
    assert "Committed item" in titles
    assert "Ghost item" not in titles
    assert reopened.get(committed.id).title == "Committed item"
    reopened.close()


def test_library_survives_corrupt_params_json(tmp_path: Path):
    service = LibraryService(":memory:")
    params = _params(seed=31)
    item = service.register_composition(Composer(params).compose(), params)

    # corrupt the stored parameters directly in the DB
    with service._lock:
        service._conn.execute(
            "UPDATE items SET params_json=? WHERE id=?",
            ("{not valid json", item.id),
        )
        service._conn.commit()
    damaged = service.get(item.id)

    # verification reports honestly instead of crashing
    verdict = verify_item(damaged)
    assert not verdict.ok and verdict.status in ("FAILED", "UNUSABLE")
    service.close()


# ------------------------------------------------------- queue resilience


def test_queue_continues_after_mid_batch_failure(tmp_path: Path):
    ghost = tmp_path / "ghost"  # job 2 target -> fails
    alive = tmp_path / "alive"
    alive.mkdir()
    queue = RenderQueue(LibraryService(":memory:"))
    first = queue.add(_params(51), alive, title="Job1 OK")
    second = queue.add(_params(52), ghost, title="Job2 doomed")
    third = queue.add(_params(53), alive, title="Job3 OK")

    assert queue.wait_until_idle(timeout=300.0)
    assert queue.get_job(first).status is JobStatus.DONE
    failed = queue.get_job(second)
    assert failed.status is JobStatus.FAILED and failed.error
    assert queue.get_job(third).status is JobStatus.DONE

    # operator fixes the problem afterwards; retry succeeds
    ghost.mkdir()
    assert queue.retry(second)
    assert queue.wait_until_idle(timeout=300.0)
    assert queue.get_job(second).status is JobStatus.DONE
    queue.stop()


def test_backup_rotation_keeps_only_recent_n(tmp_path: Path):
    manager = BackupManager(tmp_path / "Backups", keep=2)
    primary = tmp_path / "project.json"
    for round_index in range(5):
        primary.write_text(json.dumps({"take": round_index}), encoding="utf-8")
        manager.backup_file(primary)
    remaining = manager.backups_for("project")
    assert 1 <= len(remaining) <= 2
