"""Lightweight MIDI model: pitch-first notes, absolute seconds, pure Python.

No dependency on mido at model level — mido is only used in lfms.midi.io
for file serialization. The model itself is a plain data structure that
the piano-roll, drum-grid and sampler all operate on directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lfms.core.errors import ValidationError
from lfms.core.ids import new_id

# MIDI pitch range supported by LFMS
MIN_NOTE = 21   # A0
MAX_NOTE = 108  # C8

# 16 standard MIDI drum channels; percussion uses channel 9 (zero-indexed)
DRUM_CHANNEL = 9

# Default ticks-per-quarter (resolution for import/export)
DEFAULT_TPQ = 480


@dataclass
class MidiNote:
    """A single note with absolute timing in seconds (not ticks)."""
    pitch: int          # MIDI note number (0-127)
    start_sec: float    # absolute start time in seconds
    duration_sec: float # length in seconds
    velocity: float = 0.8   # 0.0..1.0
    channel: int = 0    # MIDI channel (0-15)
    note_id: str = field(default_factory=lambda: new_id("MID"))

    def __post_init__(self) -> None:
        self.pitch = int(max(0, min(127, self.pitch)))
        self.start_sec = float(max(0.0, self.start_sec))
        self.duration_sec = float(max(0.0, self.duration_sec))
        self.velocity = float(max(0.0, min(1.0, self.velocity)))
        self.channel = int(max(0, min(15, self.channel)))

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec

    @property
    def midi_velocity(self) -> int:
        return int(round(self.velocity * 127))

    @midi_velocity.setter
    def midi_velocity(self, v: int) -> None:
        self.velocity = max(0.0, min(1.0, int(v) / 127.0))

    def validate(self) -> None:
        if self.pitch < MIN_NOTE or self.pitch > MAX_NOTE:
            raise ValidationError(
                f"pitch {self.pitch} outside supported range [{MIN_NOTE}, {MAX_NOTE}]"
            )
        if self.duration_sec <= 0.0:
            raise ValidationError("note duration must be positive")
        if self.velocity < 0.0 or self.velocity > 1.0:
            raise ValidationError("velocity must be in [0.0, 1.0]")


@dataclass
class MidiClip:
    """A collection of notes forming a MIDI clip on the timeline.

    Timing is always absolute (seconds) — conversion to/from ticks happens
    only at import/export time via lfms.midi.io.
    """
    clip_id: str = field(default_factory=lambda: new_id("MCL"))
    title: str = "Untitled MIDI"
    notes: list[MidiNote] = field(default_factory=list)
    tempo_bpm: float = 120.0
    duration_sec: float = 10.0
    tpq: int = DEFAULT_TPQ
    track_index: int = 0  # for multi-track import: which original track

    def validate(self) -> None:
        if self.duration_sec <= 0.0:
            raise ValidationError("clip duration must be positive")
        if self.tempo_bpm <= 0.0 or self.tempo_bpm > 300.0:
            raise ValidationError("tempo must be in (0, 300]")

    def notes_in_range(self, start_sec: float, end_sec: float) -> list[MidiNote]:
        return [
            n for n in self.notes
            if n.start_sec < end_sec and n.end_sec > start_sec
        ]

    def pitch_range(self) -> tuple[int, int] | None:
        if not self.notes:
            return None
        pitches = [n.pitch for n in self.notes]
        return min(pitches), max(pitches)

    def remove_note(self, note_id: str) -> MidiNote:
        for i, note in enumerate(self.notes):
            if note.note_id == note_id:
                return self.notes.pop(i)
        raise ValidationError(f"unknown note {note_id}")

    def add_note(self, note: MidiNote) -> None:
        note.validate()
        self.notes.append(note)

    # -- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "title": self.title,
            "tempo_bpm": self.tempo_bpm,
            "duration_sec": self.duration_sec,
            "tpq": self.tpq,
            "track_index": self.track_index,
            "notes": [
                {
                    "pitch": n.pitch,
                    "start_sec": n.start_sec,
                    "duration_sec": n.duration_sec,
                    "velocity": n.velocity,
                    "channel": n.channel,
                    "note_id": n.note_id,
                }
                for n in self.notes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> MidiClip:
        clip = cls(
            clip_id=data.get("clip_id", new_id("MCL")),
            title=data.get("title", "Untitled MIDI"),
            tempo_bpm=float(data.get("tempo_bpm", 120.0)),
            duration_sec=float(data.get("duration_sec", 10.0)),
            tpq=int(data.get("tpq", DEFAULT_TPQ)),
            track_index=int(data.get("track_index", 0)),
        )
        for raw in data.get("notes", []):
            clip.notes.append(
                MidiNote(
                    pitch=int(raw["pitch"]),
                    start_sec=float(raw["start_sec"]),
                    duration_sec=float(raw["duration_sec"]),
                    velocity=float(raw.get("velocity", 0.8)),
                    channel=int(raw.get("channel", 0)),
                    note_id=raw.get("note_id", new_id("MID")),
                )
            )
        return clip


def pitch_name(pitch: int) -> str:
    """Return 'C4', 'A#3' etc. for a MIDI note number."""
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (pitch // 12) - 1
    name = names[pitch % 12]
    return f"{name}{octave}"


def snap_to_grid(sec: float, bpm: float, subdivision: float = 0.25) -> float:
    """Snap a time in seconds to the nearest beat/subdivision boundary.

    subdivision: 1.0 = quarter note, 0.5 = eighth, 0.25 = sixteenth.
    """
    beat_sec = 60.0 / bpm
    grid_sec = beat_sec * subdivision
    return round(sec / grid_sec) * grid_sec
