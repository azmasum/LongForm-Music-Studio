"""Tests for the SQLite layer and repository."""
from __future__ import annotations

from pathlib import Path

import pytest

from lfms.core.db import Database
from lfms.core.errors import ValidationError
from lfms.core.models import (
    Asset,
    LibraryTrack,
    Preset,
    Project,
    ProvenanceRecord,
    RenderJob,
    Track,
)
from lfms.core.repository import Repository


@pytest.fixture()
def repo(tmp_path: Path) -> Repository:
    db = Database(tmp_path / "test.lfmsdb")
    yield Repository(db)
    db.close()


def test_schema_version_recorded(repo: Repository) -> None:
    assert repo.db.schema_version >= 1


def test_project_roundtrip_all_fields(repo: Repository) -> None:
    project = Project(
        name="Dark Psychology 45m",
        duration_sec=2700.0,
        bpm=72.0,
        key_root="D",
        key_mode="MINOR",
        intensity=35.0,
        genre="PSYCHOLOGICAL",
        moods=["MYSTERIOUS", "DARK"],
        energy_curve="SLOW_BUILD",
        voiceover_safe=True,
        ducking_amount=70.0,
        speech_headroom_db=-15.0,
        seed=9384721,
        generator_version="lfms-gen-0.1.0",
        settings={"arrangement": {"sections": 10}},
        license_class="ORIGINAL",
        fingerprint="LFMS-AAAA-BBBB-CCCC",
    )
    repo.create_project(project)
    loaded = repo.get_project(project.id)
    assert loaded is not None
    assert loaded.name == "Dark Psychology 45m"
    assert loaded.moods == ["MYSTERIOUS", "DARK"]
    assert loaded.voiceover_safe is True
    assert loaded.settings["arrangement"]["sections"] == 10
    assert loaded.speech_headroom_db == -15.0


def test_project_cascade_deletes_tracks(repo: Repository) -> None:
    project = repo.create_project(Project(name="P"))
    repo.add_track(Track(project_id=project.id, name="Melody"))
    repo.add_track(Track(project_id=project.id, name="Bass"))
    assert len(repo.list_tracks_for_project(project.id)) == 2
    repo.delete_project(project.id)
    assert repo.list_tracks_for_project(project.id) == []


def test_update_project_touches_updated_at_and_fields(repo: Repository) -> None:
    project = repo.create_project(Project(name="Before"))
    before = repo.get_project(project.id)
    assert before is not None
    repo.update_project(project.id, {"name": "After", "intensity": 80, "moods": ["EPIC"]})
    after = repo.get_project(project.id)
    assert after is not None
    assert after.name == "After"
    assert after.intensity == 80
    assert after.moods == ["EPIC"]
    assert after.updated_at >= before.updated_at


def test_library_search_filters(repo: Repository) -> None:
    items = [
        LibraryTrack(
            title="Dark Ambient 60min",
            file_path="x/Dark_60.wav",
            genre="DOCUMENTARY",
            moods=["DARK", "MYSTERIOUS"],
            duration_sec=3600,
            favorite=True,
            collection="Psychology",
            license_class="ORIGINAL",
        ),
        LibraryTrack(
            title="Calm Piano 30min",
            file_path="x/Calm_30.wav",
            genre="PIANO",
            moods=["CALM"],
            duration_sec=1800,
        ),
        LibraryTrack(
            title="Imported Song",
            file_path="y/song.mp3",
            license_class="UNKNOWN",
            duration_sec=200,
        ),
    ]
    for item in items:
        repo.add_library_track(item)

    dark = repo.search_library(mood="DARK")
    assert len(dark) == 1 and dark[0].title.startswith("Dark Ambient")

    favs = repo.search_library(favorite=True)
    assert len(favs) == 1

    unknown = repo.search_library(license_class="UNKNOWN")
    assert len(unknown) == 1 and unknown[0].title == "Imported Song"

    long = repo.search_library(min_duration=1000)
    assert {t.title for t in long} == {"Dark Ambient 60min", "Calm Piano 30min"}

    text = repo.search_library(q="piano")
    assert len(text) == 1

    ordered = repo.search_library(order_by="duration_sec DESC")
    assert ordered[0].duration_sec == 3600


def test_search_rejects_bad_order(repo: Repository) -> None:
    with pytest.raises(ValidationError):
        repo.search_library(order_by="id; DROP TABLE users")


def test_preset_upsert_by_category_name(repo: Repository) -> None:
    first = repo.upsert_preset(
        Preset(category="GENERATOR", name="Doc Dark", data={"intensity": 30})
    )
    second = Preset(category="GENERATOR", name="Doc Dark", data={"intensity": 45})
    saved = repo.upsert_preset(second)
    assert saved.id == first.id
    listed = repo.list_presets("GENERATOR")
    assert len(listed) == 1
    assert listed[0].data["intensity"] == 45


def test_render_job_lifecycle(repo: Repository) -> None:
    job = repo.enqueue_render(RenderJob(output_path="out/a.wav"))
    repo.update_render_job(job.id, status="RUNNING", progress=0.5)
    running = repo.list_render_jobs("RUNNING")
    assert len(running) == 1 and running[0].progress == 0.5
    repo.update_render_job(job.id, status="DONE", progress=1.0)
    assert repo.list_render_jobs("RUNNING") == []
    assert len(repo.list_render_jobs()) == 1


def test_provenance_and_versions(repo: Repository) -> None:
    project = repo.create_project(Project(name="Prov"))
    record = repo.add_provenance(
        ProvenanceRecord(subject_type="PROJECT", subject_id=project.id, certificate={"license": "ORIGINAL"})
    )
    found = repo.list_provenance("PROJECT", project.id)
    assert found[0].id == record.id
    assert found[0].certificate["license"] == "ORIGINAL"


def test_settings_kv(repo: Repository) -> None:
    repo.set_setting("last_open_project", "prj-123")
    assert repo.get_setting("last_open_project") == "prj-123"
    assert repo.get_setting("missing", default=7) == 7


def test_asset_license_defaults_to_unknown_with_flag() -> None:
    asset = Asset(path="C:/music/mystery.mp3")
    from lfms.core.enums import LicenseClass

    assert LicenseClass(asset.license_class).needs_warning is True


def test_dashboard_stats(repo: Repository) -> None:
    repo.create_project(Project(name="S1"))
    repo.add_library_track(LibraryTrack(title="T", file_path="a.wav", duration_sec=600, favorite=True))
    stats = repo.dashboard_stats()
    assert stats["projects"] == 1
    assert stats["library_tracks"] == 1
    assert stats["total_generated_seconds"] == 600
    assert stats["favorites"] == 1
