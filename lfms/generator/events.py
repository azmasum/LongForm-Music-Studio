"""Event model shared by all generator layers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NoteEvent:
    start_sec: float
    duration_sec: float
    midi: int
    velocity: float
    role: str
    instrument: str

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


@dataclass(frozen=True)
class ChordSegment:
    start_sec: float
    duration_sec: float
    degree: int
    pitch_classes: tuple[int, ...]
    seventh: bool = False

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec


@dataclass
class Composition:
    plan_fingerprint: str
    duration_sec: float
    chords: list[ChordSegment] = field(default_factory=list)
    roles: dict[str, list[NoteEvent]] = field(default_factory=dict)
    fingerprint: str = field(default="")
    generator_version: str = ""
    seed: int = 0
    sample_rate: int = 48000
    brightness_hz: float = 1800.0
    voiceover_safe: bool = False
    crowd_chant: bool = False
    bpm: int = 90
    key_name: str = ""
    sections: list = field(default_factory=list)
    repetition_score: float | None = None
    energy_curve_name: str = ""

    def events(self) -> list[NoteEvent]:
        merged = [event for track in self.roles.values() for event in track]
        return sorted(merged, key=lambda e: (e.start_sec, e.instrument, e.midi))

    def total_events(self) -> int:
        return sum(len(track) for track in self.roles.values())

    def role_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.roles))
