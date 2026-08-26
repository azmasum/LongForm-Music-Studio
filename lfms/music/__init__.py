"""Music theory primitives: notes, chords, scales, progressions."""
from lfms.music.chords import (
    CHORD_TYPES,
    PROGRESSION_PRESETS,
    SCALE_INTERVALS,
    Chord,
    Progression,
    ProgressionChord,
    Scale,
    note_name,
    parse_note,
    progression_to_midi_clip,
)

__all__ = [
    "CHORD_TYPES",
    "SCALE_INTERVALS",
    "Chord",
    "Progression",
    "ProgressionChord",
    "Scale",
    "parse_note",
    "progression_to_midi_clip",
    "note_name",
    "PROGRESSION_PRESETS",
]
