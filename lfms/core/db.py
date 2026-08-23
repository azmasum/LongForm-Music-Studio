"""SQLite access layer with migrations and thread-safe helpers."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from lfms.core.errors import DatabaseError

SCHEMA_VERSION = 1


def _migration_script(version: int) -> str:
    path = Path(__file__).resolve().parent / "schema.sql"
    return path.read_text(encoding="utf-8")


MIGRATIONS: dict[int, str] = {1: _migration_script(1)}


class Database:
    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = str(path)
        try:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._lock = threading.RLock()
            self._migrate()
        except sqlite3.Error as exc:
            raise DatabaseError(
                "Could not open the local database.",
                technical=str(exc),
                suggestion="Check that the data directory is writable.",
            ) from exc

    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY,"
                "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
            )
            row = self._conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
            current = row["v"] or 0 if row else 0
            for version in sorted(MIGRATIONS):
                if version <= current:
                    continue
                self._conn.executescript(MIGRATIONS[version])
                self._conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)", (version,)
                )
                self._conn.commit()

    @property
    def schema_version(self) -> int:
        row = self.query_one("SELECT MAX(version) AS v FROM schema_migrations")
        return int(row["v"]) if row and row["v"] is not None else 0

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur
            except sqlite3.Error as exc:
                raise DatabaseError(
                    "Database operation failed.", technical=str(exc)
                ) from exc

    def executemany(self, sql: str, seq_of_params: list[tuple] | list[dict]) -> None:
        with self._lock:
            try:
                self._conn.executemany(sql, seq_of_params)
                self._conn.commit()
            except sqlite3.Error as exc:
                raise DatabaseError(
                    "Database batch operation failed.", technical=str(exc)
                ) from exc

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                raise DatabaseError(
                    "Database query failed.", technical=str(exc)
                ) from exc
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
