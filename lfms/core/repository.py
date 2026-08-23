"""Repository: data-access layer between models and SQLite."""
from __future__ import annotations

from typing import Any, TypeVar

from lfms.core.db import Database
from lfms.core.errors import ValidationError
from lfms.core.models import (
    Asset,
    LibraryTrack,
    Preset,
    Project,
    ProjectVersion,
    ProvenanceRecord,
    RenderJob,
    RowModel,
    Track,
)

M = TypeVar("M", bound=RowModel)

_ORDER_WHITELIST = {
    "created_at",
    "updated_at",
    "name",
    "title",
    "duration_sec",
    "rating",
}


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------- generic
    def _insert(self, obj: M) -> None:
        row = obj.to_row()
        if not row:
            return
        columns = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        self.db.execute(
            f"INSERT INTO {obj.TABLE} ({columns}) VALUES ({placeholders})", row
        )

    def _update_fields(self, table: str, obj_id: str, fields: dict[str, Any]) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        params = dict(fields)
        params["obj_id"] = obj_id
        self.db.execute(
            f"UPDATE {table} SET {assignments} WHERE id = :obj_id", params
        )

    def _get(self, cls: type[M], obj_id: str) -> M | None:
        row = self.db.query_one(f"SELECT * FROM {cls.TABLE} WHERE id = ?", (obj_id,))
        return cls.from_row(row) if row else None

    def _delete(self, table: str, obj_id: str) -> None:
        self.db.execute(f"DELETE FROM {table} WHERE id = ?", (obj_id,))

    def _list(
        self,
        cls: type[M],
        where: str = "",
        params: tuple | dict = (),
        order_by: str = "",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[M]:
        sql = f"SELECT * FROM {cls.TABLE}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = self.db.query(sql, params)
        return [cls.from_row(r) for r in rows]

    @staticmethod
    def _check_order(order_by: str) -> str:
        if not order_by:
            return ""
        parts = [p.strip().split() for p in order_by.split(",")]
        for parts_ in parts:
            col = parts_[0]
            direction = parts_[1].upper() if len(parts_) > 1 else "ASC"
            if col not in _ORDER_WHITELIST or direction not in ("ASC", "DESC"):
                raise ValidationError(
                    f"Invalid sort expression: {order_by}",
                    suggestion="Use a whitelisted column with ASC or DESC.",
                )
        return order_by

    # ------------------------------------------------------------ projects
    def create_project(self, project: Project) -> Project:
        self._insert(project)
        return project

    def get_project(self, project_id: str) -> Project | None:
        return self._get(Project, project_id)

    def update_project(self, project_id: str, fields: dict[str, Any]) -> None:
        import json as _json

        from lfms.core.models import utc_now

        clean: dict[str, Any] = {}
        for key, value in fields.items():
            if key in Project._column_map and not isinstance(value, str):
                value = _json.dumps(value, ensure_ascii=False)
                key = Project._column_map[key]
            elif key in Project._bool_fields:
                value = int(bool(value))
            clean[key] = value
        clean["updated_at"] = utc_now()
        self._update_fields(Project.TABLE, project_id, clean)

    def delete_project(self, project_id: str) -> None:
        self._delete(Project.TABLE, project_id)

    def list_projects(
        self,
        *,
        order_by: str = "updated_at DESC",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Project]:
        return self._list(
            Project, order_by=self._check_order(order_by), limit=limit, offset=offset
        )

    def count_projects(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS c FROM projects")
        return int(row["c"]) if row else 0

    # -------------------------------------------------------------- tracks
    def add_track(self, track: Track) -> Track:
        self._insert(track)
        return track

    def get_track(self, track_id: str) -> Track | None:
        return self._get(Track, track_id)

    def update_track(self, track_id: str, fields: dict[str, Any]) -> None:
        self._update_fields(Track.TABLE, track_id, fields)

    def delete_track(self, track_id: str) -> None:
        self._delete(Track.TABLE, track_id)

    def list_tracks_for_project(self, project_id: str) -> list[Track]:
        rows = self.db.query(
            f"SELECT * FROM {Track.TABLE} WHERE project_id = ? ORDER BY position ASC",
            (project_id,),
        )
        return [Track.from_row(r) for r in rows]

    # -------------------------------------------------------------- assets
    def add_asset(self, asset: Asset) -> Asset:
        self._insert(asset)
        return asset

    def get_asset(self, asset_id: str) -> Asset | None:
        return self._get(Asset, asset_id)

    def update_asset(self, asset_id: str, fields: dict[str, Any]) -> None:
        self._update_fields(Asset.TABLE, asset_id, fields)

    def list_assets(self, limit: int | None = None) -> list[Asset]:
        return self._list(Asset, order_by="", limit=limit)

    # ------------------------------------------------------ library tracks
    def add_library_track(self, item: LibraryTrack) -> LibraryTrack:
        self._insert(item)
        return item

    def update_library_track(self, item_id: str, fields: dict[str, Any]) -> None:
        import json as _json

        clean: dict[str, Any] = {}
        for key, value in fields.items():
            if key in LibraryTrack._column_map and not isinstance(value, str):
                value = _json.dumps(value, ensure_ascii=False)
                key = LibraryTrack._column_map[key]
            elif key in LibraryTrack._bool_fields:
                value = int(bool(value))
            clean[key] = value
        self._update_fields(LibraryTrack.TABLE, item_id, clean)

    def delete_library_track(self, item_id: str) -> None:
        self._delete(LibraryTrack.TABLE, item_id)

    def search_library(
        self,
        *,
        q: str = "",
        genre: str = "",
        mood: str = "",
        collection: str = "",
        license_class: str = "",
        favorite: bool | None = None,
        min_duration: float | None = None,
        max_duration: float | None = None,
        order_by: str = "created_at DESC",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[LibraryTrack]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if q:
            clauses.append("(title LIKE :q OR file_path LIKE :q)")
            params["q"] = f"%{q}%"
        if genre:
            clauses.append("genre = :genre")
            params["genre"] = genre
        if mood:
            clauses.append("moods_json LIKE :mood")
            params["mood"] = f'%"{mood}"%'
        if collection:
            clauses.append("collection = :collection")
            params["collection"] = collection
        if license_class:
            clauses.append("license_class = :license_class")
            params["license_class"] = license_class
        if favorite is not None:
            clauses.append("favorite = :favorite")
            params["favorite"] = int(favorite)
        if min_duration is not None:
            clauses.append("duration_sec >= :min_dur")
            params["min_dur"] = min_duration
        if max_duration is not None:
            clauses.append("duration_sec <= :max_dur")
            params["max_dur"] = max_duration
        where = " AND ".join(clauses)
        items = self._list(
            LibraryTrack,
            where=where,
            params=params,
            order_by=self._check_order(order_by),
            limit=limit,
            offset=offset,
        )
        return items

    # ------------------------------------------------------------- presets
    def upsert_preset(self, preset: Preset) -> Preset:
        existing = self.db.query_one(
            "SELECT id FROM presets WHERE category = ? AND name = ?",
            (preset.category, preset.name),
        )
        if existing:
            import json as _json

            self._update_fields(
                Preset.TABLE,
                str(existing["id"]),
                {
                    "description": preset.description,
                    "data_json": _json.dumps(preset.data, ensure_ascii=False),
                    "builtin": int(preset.builtin),
                },
            )
            preset.id = str(existing["id"])
            return preset
        self._insert(preset)
        return preset

    def get_preset(self, preset_id: str) -> Preset | None:
        return self._get(Preset, preset_id)

    def list_presets(self, category: str | None = None) -> list[Preset]:
        if category:
            return self._list(
                Preset, where="category = :c", params={"c": category}, order_by="name"
            )
        return self._list(Preset, order_by="category, name")

    def delete_preset(self, preset_id: str) -> None:
        self._delete(Preset.TABLE, preset_id)

    # --------------------------------------------------------- render jobs
    def enqueue_render(self, job: RenderJob) -> RenderJob:
        self._insert(job)
        return job

    def update_render_job(self, job_id: str, fields: dict[str, Any] | None = None, **kwargs: Any) -> None:
        merged = dict(fields or {})
        merged.update(kwargs)
        self._update_fields(RenderJob.TABLE, job_id, merged)

    def get_render_job(self, job_id: str) -> RenderJob | None:
        return self._get(RenderJob, job_id)

    def list_render_jobs(self, status: str | None = None) -> list[RenderJob]:
        if status:
            return self._list(
                RenderJob,
                where="status = :s",
                params={"s": status},
                order_by="queued_at DESC",
            )
        return self._list(RenderJob, order_by="queued_at DESC")

    # --------------------------------------------------------- provenance
    def add_provenance(self, record: ProvenanceRecord) -> ProvenanceRecord:
        self._insert(record)
        return record

    def list_provenance(
        self, subject_type: str | None = None, subject_id: str | None = None
    ) -> list[ProvenanceRecord]:
        clauses: list[str] = []
        params: dict[str, str] = {}
        if subject_type:
            clauses.append("subject_type = :st")
            params["st"] = subject_type
        if subject_id:
            clauses.append("subject_id = :sid")
            params["sid"] = subject_id
        where = " AND ".join(clauses)
        return self._list(ProvenanceRecord, where=where, params=params, order_by="created_at DESC")

    # ----------------------------------------------------------- versions
    def add_project_version(self, version: ProjectVersion) -> ProjectVersion:
        self._insert(version)
        return version

    def list_versions(self, project_id: str) -> list[ProjectVersion]:
        return self._list(
            ProjectVersion,
            where="project_id = :pid",
            params={"pid": project_id},
            order_by="version_no DESC",
        )

    # ----------------------------------------------------------- settings
    def set_setting(self, key: str, value: Any) -> None:
        import json as _json

        payload = _json.dumps(value, ensure_ascii=False)
        self.db.execute(
            "INSERT INTO app_settings (key, value_json) VALUES (:k, :v) "
            "ON CONFLICT(key) DO UPDATE SET value_json = :v",
            {"k": key, "v": payload},
        )

    def get_setting(self, key: str, default: Any = None) -> Any:
        import json as _json

        row = self.db.query_one("SELECT value_json FROM app_settings WHERE key = ?", (key,))
        if not row:
            return default
        try:
            return _json.loads(row["value_json"])
        except _json.JSONDecodeError:
            return default

    # -------------------------------------------------------------- stats
    def dashboard_stats(self) -> dict[str, Any]:
        projects = self.count_projects()
        lib_row = self.db.query_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(duration_sec), 0) AS total FROM library_tracks"
        )
        fav_row = self.db.query_one(
            "SELECT COUNT(*) AS c FROM library_tracks WHERE favorite = 1"
        )
        renders_row = self.db.query_one("SELECT COUNT(*) AS c FROM render_jobs")
        return {
            "projects": projects,
            "library_tracks": int(lib_row["c"]) if lib_row else 0,
            "total_generated_seconds": float(lib_row["total"]) if lib_row else 0.0,
            "favorites": int(fav_row["c"]) if fav_row else 0,
            "renders": int(renders_row["c"]) if renders_row else 0,
        }
