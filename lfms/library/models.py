"""Library data model: a persisted sound/composition record."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Item:
    """One library entry: generated composition or imported audio file."""

    id: int
    title: str
    kind: str = "GENERATED"
    path: str | None = None
    duration_sec: float = 0.0
    sample_rate: int | None = None
    channels: int | None = None
    integrated_lufs: float | None = None
    true_peak_dbtp: float | None = None
    bpm: float | None = None
    key_name: str | None = None
    seed: int | None = None
    fingerprint: str | None = None
    params_json: str | None = None
    notes: str = ""
    favorite: bool = False
    added_at: str = ""
    updated_at: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["favorite"] = bool(self.favorite)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_row(cls, row: dict) -> Item:
        known = set(cls.__dataclass_fields__)
        return cls(
            **{key: value for key, value in row.items() if key in known}
        )
