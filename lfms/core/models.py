"""Domain models persisted in the LFMS database.

Models map 1:1 onto the SQLite schema. JSON-backed columns are exposed as
parsed Python objects; boolean columns as real booleans.
"""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from lfms.core import ids


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class RowModel:
    TABLE: ClassVar[str] = ""
    _json_fields: ClassVar[tuple[str, ...]] = ()
    _bool_fields: ClassVar[tuple[str, ...]] = ()
    _column_map: ClassVar[dict[str, str]] = {}

    def to_row(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if value is None:
                continue
            if f.name in self._json_fields:
                value = json.dumps(value, ensure_ascii=False)
            elif f.name in self._bool_fields:
                value = int(bool(value))
            out[self._column_map.get(f.name, f.name)] = value
        return out

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> RowModel:
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):  # type: ignore[arg-type]
            column = cls._column_map.get(f.name, f.name)
            if column not in row:
                continue
            value = row[column]
            if f.name in cls._json_fields:
                value = json.loads(value) if isinstance(value, str) and value else []
            elif f.name in cls._bool_fields:
                value = bool(value)
            kwargs[f.name] = value
        return cls(**kwargs)  # type: ignore[return-value]


def _id(prefix: str) -> str:
    return ids.new_id(prefix)


@dataclass
class Project(RowModel):
    TABLE = "projects"
    _json_fields = ("moods", "settings")
    _bool_fields = ("voiceover_safe",)
    _column_map = {"moods": "moods_json", "settings": "settings_json"}

    id: str = field(default_factory=lambda: _id("prj"))
    name: str = "Untitled Project"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    duration_sec: float = 1800.0
    bpm: float = 80.0
    key_root: str = "C"
    key_mode: str = "MINOR"
    intensity: float = 50.0
    genre: str = "AMBIENT"
    moods: list[str] = field(default_factory=lambda: ["CALM"])
    energy_curve: str = "FLAT"
    voiceover_safe: bool = False
    ducking_amount: float = 60.0
    speech_headroom_db: float = -12.0
    seed: int = 0
    generator_version: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    license_class: str = "ORIGINAL"
    fingerprint: str = ""


@dataclass
class Track(RowModel):
    TABLE = "tracks"
    _json_fields = ("effects", "automation")
    _bool_fields = ("mute", "solo")
    _column_map = {"effects": "effects_json", "automation": "automation_json"}

    id: str = field(default_factory=lambda: _id("trk"))
    project_id: str = ""
    name: str = "Track"
    kind: str = "GENERATED"
    position: int = 0
    volume_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    effects: list[dict[str, Any]] = field(default_factory=list)
    automation: dict[str, Any] = field(default_factory=dict)
    source_asset_id: str | None = None
    start_sec: float = 0.0
    offset_sec: float = 0.0
    duration_sec: float | None = None
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0


@dataclass
class Asset(RowModel):
    TABLE = "assets"
    _json_fields = ("tags",)
    _bool_fields = ("attribution_required",)
    _column_map = {"tags": "tags_json"}

    id: str = field(default_factory=lambda: _id("ast"))
    path: str = ""
    title: str = ""
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    license_class: str = "UNKNOWN"
    source: str = ""
    author: str = ""
    attribution_url: str = ""
    commercial_use: int | None = None
    attribution_required: bool = False
    notes: str = ""
    imported_at: str = field(default_factory=utc_now)
    fingerprint: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class LibraryTrack(RowModel):
    TABLE = "library_tracks"
    _json_fields = ("moods", "tags")
    _bool_fields = ("favorite",)
    _column_map = {"moods": "moods_json", "tags": "tags_json"}

    id: str = field(default_factory=lambda: _id("lib"))
    project_id: str | None = None
    file_path: str = ""
    title: str = ""
    format: str = "WAV"
    duration_sec: float = 0.0
    bpm: float | None = None
    key_root: str | None = None
    key_mode: str | None = None
    genre: str = ""
    moods: list[str] = field(default_factory=list)
    intensity: float | None = None
    seed: int | None = None
    generator_version: str | None = None
    license_class: str = "ORIGINAL"
    fingerprint: str = ""
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    collection: str = ""
    rating: int = 0
    created_at: str = field(default_factory=utc_now)
    render_job_id: str | None = None


@dataclass
class Preset(RowModel):
    TABLE = "presets"
    _json_fields = ("data",)
    _bool_fields = ("builtin",)
    _column_map = {"data": "data_json"}

    id: str = field(default_factory=lambda: _id("pre"))
    category: str = "GENERATOR"
    name: str = ""
    description: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    builtin: bool = False
    created_at: str = field(default_factory=utc_now)


@dataclass
class RenderJob(RowModel):
    TABLE = "render_jobs"

    id: str = field(default_factory=lambda: _id("rnd"))
    project_id: str | None = None
    output_path: str = ""
    container: str = "WAV"
    bit_depth: int = 24
    bitrate_kbps: int | None = None
    sample_rate: int = 48000
    channels: int = 2
    status: str = "PENDING"
    progress: float = 0.0
    error_text: str = ""
    queued_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class ProvenanceRecord(RowModel):
    TABLE = "provenance_records"
    _json_fields = ("certificate",)
    _column_map = {"certificate": "certificate_json"}

    id: str = field(default_factory=lambda: _id("prv"))
    subject_type: str = "LIBRARY_TRACK"
    subject_id: str = ""
    certificate: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass
class ProjectVersion(RowModel):
    TABLE = "project_versions"

    id: str = field(default_factory=lambda: _id("ver"))
    project_id: str = ""
    version_no: int = 1
    label: str = ""
    snapshot_path: str = ""
    created_at: str = field(default_factory=utc_now)
