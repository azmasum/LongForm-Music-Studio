"""SQLite-backed sound library: items, tags, collections, smart tagging.

The service is the single access point used by tests and the GUI. All
mutating methods validate input and raise ``ValidationError``; reads are
forgiving. The database is created on first open (parents auto-created).
"""
from __future__ import annotations

import functools
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.core.errors import ValidationError
from lfms.library.models import Item
from lfms.mastering.measure import measure

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'GENERATED',
  duration_sec REAL NOT NULL DEFAULT 0,
  sample_rate INTEGER,
  channels INTEGER,
  integrated_lufs REAL,
  true_peak_dbtp REAL,
  bpm REAL,
  key_name TEXT,
  seed INTEGER,
  fingerprint TEXT,
  params_json TEXT,
  notes TEXT NOT NULL DEFAULT '',
  favorite INTEGER NOT NULL DEFAULT 0,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags(
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  tag TEXT NOT NULL,
  PRIMARY KEY(item_id, tag)
);
CREATE TABLE IF NOT EXISTS collections(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS collection_items(
  collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  PRIMARY KEY(collection_id, item_id)
);
"""

_MAX_TITLE = 200
_LOUDNESS_MEASURE_LIMIT_SEC = 900.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_tag(tag: str) -> str:
    cleaned = " ".join(str(tag).split()).strip().lower()
    if not cleaned:
        raise ValidationError("tag must not be empty")
    if len(cleaned) > 60:
        raise ValidationError("tag must be at most 60 characters")
    return cleaned


def smart_tags_for_generation(params_json: str | None, bpm: float | None) -> tuple[str, ...]:
    """Derive search tags from a stored generation payload."""
    tags: list[str] = []
    if params_json:
        try:
            payload = json.loads(params_json)
        except json.JSONDecodeError:
            payload = {}
        if genre := payload.get("genre"):
            tags.append(f"genre:{str(genre).lower()}")
        for mood in payload.get("moods") or ():
            tags.append(f"mood:{str(mood).lower()}")
        if payload.get("voiceover_safe"):
            tags.append("voiceover-safe")
        intensity = payload.get("intensity")
        if isinstance(intensity, (int, float)):
            if intensity >= 70:
                tags.append("energy:high")
            elif intensity <= 30:
                tags.append("energy:low")
            else:
                tags.append("energy:mid")
    if bpm:
        bucket = int(round(bpm / 5.0) * 5)
        tags.append(f"bpm:{bucket}")
    return tuple(dict.fromkeys(tags))


def smart_tags_for_measurement(
    integrated_lufs: float | None,
    channels: int | None,
    duration_sec: float,
) -> tuple[str, ...]:
    """Derive search tags from measured audio properties."""
    tags: list[str] = []
    if integrated_lufs is not None:
        if integrated_lufs <= -24.0:
            tags.append("level:quiet")
        elif integrated_lufs >= -14.0:
            tags.append("level:loud")
        else:
            tags.append("level:moderate")
    if channels == 1:
        tags.append("mono")
    elif channels and channels >= 2:
        tags.append("stereo")
    if duration_sec >= 300.0:
        tags.append("long-form")
    elif duration_sec <= 30.0:
        tags.append("sting")
    return tuple(tags)


class LibraryService:
    """Persistent library backed by SQLite.

    Thread-safe: the render queue's worker thread shares this service
    with the GUI, so every public call runs under one reentrant lock.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = Path(db_path) if db_path != ":memory:" else None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        target = str(self.db_path) if self.db_path is not None else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._wrap_public_methods()

    def _wrap_public_methods(self) -> None:
        """Serialize every public call through ``self._lock`` so the
        render-queue worker thread can share this service safely."""
        lock = self._lock

        def guarded(bound):
            @functools.wraps(bound)
            def call(*args, **kwargs):
                with lock:
                    return bound(*args, **kwargs)

            return call

        for name in dir(type(self)):
            if name.startswith("_"):
                continue
            attr = getattr(self, name)
            if callable(attr):
                try:
                    object.__setattr__(self, name, guarded(attr))
                except (AttributeError, TypeError):  # pragma: no cover
                    pass

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- helpers

    def _row_to_item(self, row: sqlite3.Row) -> Item:
        data = dict(row)
        data["favorite"] = bool(data["favorite"])
        tag_rows = self._conn.execute(
            "SELECT tag FROM tags WHERE item_id=? ORDER BY tag", (data["id"],)
        ).fetchall()
        data["tags"] = tuple(r["tag"] for r in tag_rows)
        return Item.from_row(data)

    @staticmethod
    def _validate_title(title: str) -> str:
        cleaned = str(title).strip()
        if not cleaned:
            raise ValidationError("title must not be empty")
        if len(cleaned) > _MAX_TITLE:
            raise ValidationError(f"title must be at most {_MAX_TITLE} characters")
        return cleaned

    def _insert_item(self, fields: dict) -> Item:
        stamp = _now()
        cursor = self._conn.execute(
            """
            INSERT INTO items(path, title, kind, duration_sec, sample_rate,
                              channels, integrated_lufs, true_peak_dbtp, bpm,
                              key_name, seed, fingerprint, params_json,
                              added_at, updated_at)
            VALUES(:path,:title,:kind,:duration_sec,:sample_rate,:channels,
                   :integrated_lufs,:true_peak_dbtp,:bpm,:key_name,:seed,
                   :fingerprint,:params_json,:added_at,:updated_at)
            """,
            {**fields, "added_at": stamp, "updated_at": stamp},
        )
        self._conn.commit()
        return self.get(cursor.lastrowid)

    def _touch(self, item_id: int) -> None:
        self._conn.execute(
            "UPDATE items SET updated_at=? WHERE id=?", (_now(), item_id)
        )

    # ------------------------------------------------------------ mutations

    def add_item(
        self,
        title: str,
        *,
        kind: str = "GENERATED",
        path: str | None = None,
        **metadata,
    ) -> Item:
        clean = self._validate_title(title)
        if path is not None:
            existing = self._conn.execute(
                "SELECT id FROM items WHERE path=?", (path,)
            ).fetchone()
            if existing is not None:
                raise ValidationError(f"path already in library: {path}")
        fields = {
            "path": path,
            "title": clean,
            "kind": kind,
            "duration_sec": 0.0,
            "sample_rate": None,
            "channels": None,
            "integrated_lufs": None,
            "true_peak_dbtp": None,
            "bpm": None,
            "key_name": None,
            "seed": None,
            "fingerprint": None,
            "params_json": None,
        }
        for key, value in metadata.items():
            if key not in fields:
                raise ValidationError(f"unknown item field {key!r}")
            fields[key] = value
        item = self._insert_item(fields)
        return item

    def register_composition(
        self,
        composition,
        params,
        *,
        title: str | None = None,
        audio_path: str | None = None,
        extra_tags: tuple[str, ...] = (),
    ) -> Item:
        """Store a generated composition with its parameters and smart tags."""
        params_json = json.dumps(
            {
                "seed": params.seed,
                "duration_sec": params.duration_sec,
                "genre": str(params.genre),
                "moods": [str(m) for m in params.moods],
                "intensity": params.intensity,
                "voiceover_safe": bool(params.voiceover_safe),
            }
        )
        display = title or f"{str(params.genre).title()} {composition.fingerprint}"
        item = self.add_item(
            display,
            kind="GENERATED",
            path=audio_path,
            duration_sec=float(params.duration_sec),
            sample_rate=int(params.sample_rate),
            bpm=float(composition.bpm),
            key_name=str(composition.key_name),
            seed=int(params.seed),
            fingerprint=str(composition.fingerprint),
            params_json=params_json,
        )
        for tag in smart_tags_for_generation(params_json, composition.bpm):
            self.add_tag(item.id, tag)
        for tag in extra_tags:
            self.add_tag(item.id, tag)
        return self.get(item.id)

    def import_audio_file(self, path: str | Path, *, title: str | None = None) -> Item:
        """Analyze an audio file (duration/format/loudness) and register it."""
        file_path = Path(path)
        if not file_path.is_file():
            raise ValidationError(f"audio file not found: {file_path}")
        info = sf.info(str(file_path))
        integrated: float | None = None
        peak: float | None = None
        if info.duration <= _LOUDNESS_MEASURE_LIMIT_SEC:
            data, sr = sf.read(str(file_path), always_2d=True, dtype="float32")
            measurement = measure(data.T.astype(np.float32), int(info.samplerate))
            integrated = measurement.integrated_lufs
            peak = measurement.true_peak_dbtp
        display = title or humanized_stem(file_path.name)
        item = self.add_item(
            display,
            kind="AUDIO_FILE",
            path=str(file_path.resolve()),
            duration_sec=float(info.duration),
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            integrated_lufs=integrated,
            true_peak_dbtp=peak,
        )
        for tag in smart_tags_for_measurement(
            integrated, int(info.channels), float(info.duration)
        ):
            self.add_tag(item.id, tag)
        return self.get(item.id)

    def delete_item(self, item_id: int) -> None:
        cursor = self._conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self._conn.commit()
        if cursor.rowcount == 0:
            raise ValidationError(f"no library item with id {item_id}")

    def set_favorite(self, item_id: int, favorite: bool) -> Item:
        self._require(item_id)
        self._conn.execute(
            "UPDATE items SET favorite=?, updated_at=? WHERE id=?",
            (1 if favorite else 0, _now(), item_id),
        )
        self._conn.commit()
        return self.get(item_id)

    def update_notes(self, item_id: int, notes: str) -> Item:
        self._require(item_id)
        self._conn.execute(
            "UPDATE items SET notes=?, updated_at=? WHERE id=?",
            (str(notes), _now(), item_id),
        )
        self._conn.commit()
        return self.get(item_id)

    def add_tag(self, item_id: int, tag: str) -> Item:
        self._require(item_id)
        clean = normalize_tag(tag)
        self._conn.execute(
            "INSERT OR IGNORE INTO tags(item_id, tag) VALUES(?, ?)",
            (item_id, clean),
        )
        self._touch(item_id)
        self._conn.commit()
        return self.get(item_id)

    def remove_tag(self, item_id: int, tag: str) -> Item:
        self._require(item_id)
        self._conn.execute(
            "DELETE FROM tags WHERE item_id=? AND tag=?",
            (item_id, normalize_tag(tag)),
        )
        self._touch(item_id)
        self._conn.commit()
        return self.get(item_id)

    def create_collection(self, name: str) -> int:
        clean = str(name).strip()
        if not clean:
            raise ValidationError("collection name must not be empty")
        exists = self._conn.execute(
            "SELECT id FROM collections WHERE name=?", (clean,)
        ).fetchone()
        if exists is not None:
            raise ValidationError(f"collection already exists: {clean}")
        cursor = self._conn.execute(
            "INSERT INTO collections(name) VALUES(?)", (clean,)
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def delete_collection(self, name: str) -> None:
        cursor = self._conn.execute(
            "DELETE FROM collections WHERE name=?", (str(name).strip(),)
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise ValidationError(f"no collection named {name!r}")

    def add_to_collection(self, collection: str, item_id: int) -> None:
        cid = self._collection_id(collection)
        self._require(item_id)
        self._conn.execute(
            "INSERT OR IGNORE INTO collection_items(collection_id, item_id)"
            " VALUES(?, ?)",
            (cid, item_id),
        )
        self._conn.commit()

    def remove_from_collection(self, collection: str, item_id: int) -> None:
        cid = self._collection_id(collection)
        self._conn.execute(
            "DELETE FROM collection_items WHERE collection_id=? AND item_id=?",
            (cid, item_id),
        )
        self._conn.commit()

    # --------------------------------------------------------------- queries

    def get(self, item_id: int) -> Item:
        row = self._conn.execute(
            "SELECT * FROM items WHERE id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValidationError(f"no library item with id {item_id}")
        return self._row_to_item(row)

    def all_tags(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT DISTINCT tag FROM tags ORDER BY tag"
        ).fetchall()
        return tuple(r["tag"] for r in rows)

    def list_collections(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT name FROM collections ORDER BY name"
        ).fetchall()
        return tuple(r["name"] for r in rows)

    def collection_items(self, collection: str) -> tuple[Item, ...]:
        cid = self._collection_id(collection)
        rows = self._conn.execute(
            "SELECT i.* FROM items i JOIN collection_items ci"
            " ON ci.item_id=i.id WHERE ci.collection_id=?"
            " ORDER BY i.title COLLATE NOCASE",
            (cid,),
        ).fetchall()
        return tuple(self._row_to_item(r) for r in rows)

    def list_items(
        self,
        query: str = "",
        *,
        tag: str | None = None,
        favorite_only: bool = False,
        collection: str | None = None,
        sort: str = "added_desc",
    ) -> tuple[Item, ...]:
        clauses: list[str] = []
        args: list[object] = []
        text = query.strip().lower()
        if text:
            like = f"%{text}%"
            clauses.append(
                "(lower(i.title) LIKE ? OR lower(COALESCE(i.path,'')) LIKE ?"
                " OR lower(COALESCE(i.fingerprint,'')) LIKE ?"
                " OR i.id IN (SELECT item_id FROM tags WHERE tag LIKE ?))"
            )
            args.extend([like, like, like, like])
        if tag is not None:
            clean = normalize_tag(tag)
            clauses.append("i.id IN (SELECT item_id FROM tags WHERE tag=?)")
            args.append(clean)
        if favorite_only:
            clauses.append("i.favorite=1")
        if collection is not None:
            clauses.append(
                "i.id IN (SELECT ci.item_id FROM collection_items ci"
                " JOIN collections c ON c.id=ci.collection_id WHERE c.name=?)"
            )
            args.append(str(collection).strip())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order = {
            "added_desc": "i.id DESC",
            "added_asc": "i.id ASC",
            "title_asc": "i.title COLLATE NOCASE ASC",
            "duration_desc": "i.duration_sec DESC",
        }.get(sort)
        if order is None:
            raise ValidationError(f"unknown sort {sort!r}")
        rows = self._conn.execute(
            f"SELECT DISTINCT i.* FROM items i{where} ORDER BY {order}", args
        ).fetchall()
        return tuple(self._row_to_item(r) for r in rows)

    # ------------------------------------------------------------- internal

    def _require(self, item_id: int) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM items WHERE id=?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValidationError(f"no library item with id {item_id}")

    def _collection_id(self, name: str) -> int:
        row = self._conn.execute(
            "SELECT id FROM collections WHERE name=?", (str(name).strip(),)
        ).fetchone()
        if row is None:
            raise ValidationError(f"no collection named {name!r}")
        return int(row["id"])


def humanized_stem(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else filename
