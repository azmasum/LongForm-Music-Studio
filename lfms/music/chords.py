"""Music theory primitives: notes, intervals, chords, scales, progressions.

Pure math, no audio, no Qt — fully unit-testable.
All note numbers are MIDI (C4 = 60, A4 = 69).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lfms.midi.model import MidiClip

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_MAP = {name: i for i, name in enumerate(NOTE_NAMES)}
FLAT_MAP = {
    "Db": 1, "Eb": 3, "Fb": 4, "Gb": 6, "Ab": 8, "Bb": 10, "Cb": 11,
}


def parse_note(name: str) -> int:
    """Parse 'C4', 'A#3', 'Bb5' etc. to MIDI note number."""
    name = name.strip()
    if len(name) < 2:
        raise ValueError(f"invalid note name: {name!r}")
    letter = name[0].upper()
    rest = name[1:]
    sharp = rest.startswith("#")
    flat = rest.startswith("b") and not rest.startswith("bb")
    if sharp:
        rest = rest[1:]
    elif flat:
        rest = rest[1:]
    if not rest.isdigit():
        raise ValueError(f"invalid octave in: {name!r}")
    octave = int(rest)
    chroma = NOTE_MAP.get(letter, -1)
    if chroma < 0:
        raise ValueError(f"unknown note letter: {letter!r}")
    if sharp:
        chroma = (chroma + 1) % 12
    elif flat:
        chroma = (chroma - 1) % 12
    return (octave + 1) * 12 + chroma


def note_name(pitch: int) -> str:
    """MIDI note number to name, e.g. 60 -> 'C4'."""
    octave = (pitch // 12) - 1
    return f"{NOTE_NAMES[pitch % 12]}{octave}"


# ── Intervals ──────────────────────────────────────────────────────────────

INTERVALS = {
    "P1": 0, "m2": 1, "M2": 2, "m3": 3, "M3": 4,
    "P4": 5, "TT": 6, "P5": 7, "m6": 8, "M6": 9,
    "m7": 10, "M7": 11, "P8": 12,
}


# ── Scales ─────────────────────────────────────────────────────────────────

SCALE_INTERVALS: dict[str, list[int]] = {
    "major":             [0, 2, 4, 5, 7, 9, 11],
    "minor":             [0, 2, 3, 5, 7, 8, 10],
    "natural_minor":     [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":    [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor":     [0, 2, 3, 5, 7, 9, 11],
    "dorian":            [0, 2, 3, 5, 7, 9, 10],
    "mixolydian":        [0, 2, 4, 5, 7, 9, 10],
    "phrygian":          [0, 1, 3, 5, 7, 8, 10],
    "lydian":            [0, 2, 4, 6, 7, 9, 11],
    "locrian":           [0, 1, 3, 5, 6, 8, 10],
    "major_pentatonic":  [0, 2, 4, 7, 9],
    "minor_pentatonic":  [0, 3, 5, 7, 10],
    "blues":             [0, 3, 5, 6, 7, 10],
    "whole_tone":        [0, 2, 4, 6, 8, 10],
    "chromatic":         list(range(12)),
}


@dataclass
class Scale:
    root: int  # MIDI note number of root
    mode: str  # key into SCALE_INTERVALS

    def __post_init__(self):
        if self.mode not in SCALE_INTERVALS:
            raise ValueError(f"unknown scale mode: {self.mode!r}")

    @property
    def intervals(self) -> list[int]:
        return SCALE_INTERVALS[self.mode]

    def notes(self, octave_range: tuple[int, int] = (3, 5)) -> list[int]:
        """Return scale degrees across the given octave range."""
        result = []
        for octave in range(octave_range[0], octave_range[1] + 1):
            base = (octave + 1) * 12
            for interval in self.intervals:
                pitch = self.root + interval + (base - ((self.root % 12) + base % 12))
                # simpler: just stack from root
                pitch = base + (self.root % 12) + interval
                if 0 <= pitch <= 127:
                    result.append(pitch)
        return sorted(set(result))

    def contains(self, pitch: int) -> bool:
        return (pitch - self.root) % 12 in set(self.intervals)

    def degree(self, degree_num: int, octave: int = 4) -> int:
        """Return the Nth degree (0-indexed) of the scale in the given octave."""
        base = (octave + 1) * 12 + (self.root % 12)
        idx = degree_num % len(self.intervals)
        oct_offset = degree_num // len(self.intervals)
        return base + self.intervals[idx] + oct_offset * 12


# ── Chords ─────────────────────────────────────────────────────────────────

CHORD_TYPES: dict[str, list[int]] = {
    "major":            [0, 4, 7],
    "minor":            [0, 3, 7],
    "diminished":       [0, 3, 6],
    "augmented":        [0, 4, 8],
    "major7":           [0, 4, 7, 11],
    "minor7":           [0, 3, 7, 10],
    "dom7":             [0, 4, 7, 10],
    "dim7":             [0, 3, 6, 9],
    "half_dim7":        [0, 3, 6, 10],
    "sus2":             [0, 2, 7],
    "sus4":             [0, 5, 7],
    "add9":             [0, 4, 7, 14],
    "minor_add9":       [0, 3, 7, 14],
    "major6":           [0, 4, 7, 9],
    "minor6":           [0, 3, 7, 9],
    "major9":           [0, 4, 7, 11, 14],
    "minor9":           [0, 3, 7, 10, 14],
    "dom9":             [0, 4, 7, 10, 14],
    "power":            [0, 7],
}

CHORD_ALIASES: dict[str, str] = {
    "maj": "major", "min": "minor", "dim": "diminished", "aug": "augmented",
    "M7": "major7", "m7": "minor7", "7": "dom7", "hdim7": "half_dim7",
    "sus4": "sus4", "sus2": "sus2",
}


@dataclass
class Chord:
    root: int          # MIDI note number
    chord_type: str    # key into CHORD_TYPES
    inversion: int = 0  # 0 = root position, 1 = first inversion, etc.

    def __post_init__(self):
        ct = CHORD_ALIASES.get(self.chord_type, self.chord_type)
        if ct not in CHORD_TYPES:
            raise ValueError(f"unknown chord type: {self.chord_type!r}")
        self.chord_type = ct

    @property
    def intervals(self) -> list[int]:
        return CHORD_TYPES[self.chord_type]

    def voicing(self, octave: int = 4, max_notes: int | None = None) -> list[int]:
        """Return MIDI note numbers for this chord in the given octave.

        inversion 0 = root position; higher inversions rotate the lowest note up.
        """
        base = (octave + 1) * 12
        pitches = sorted(base + self.root % 12 + iv for iv in self.intervals)
        inv = self.inversion % len(pitches)
        if inv > 0:
            pitches = pitches[inv:] + [p + 12 for p in pitches[:inv]]
        if max_notes is not None:
            pitches = pitches[:max_notes]
        return pitches

    @property
    def symbol(self) -> str:
        name = NOTE_NAMES[self.root % 12]
        symbols = {
            "major": "", "minor": "m", "diminished": "dim", "augmented": "aug",
            "major7": "maj7", "minor7": "m7", "dom7": "7",
            "dim7": "dim7", "half_dim7": "m7b5",
            "sus2": "sus2", "sus4": "sus4",
            "add9": "add9", "minor_add9": "m(add9)",
            "major6": "6", "minor6": "m6",
            "major9": "maj9", "minor9": "m9", "dom9": "9",
            "power": "5",
        }
        return name + symbols.get(self.chord_type, self.chord_type)

    @classmethod
    def from_symbol(cls, symbol: str, octave: int = 4) -> Chord:
        """Parse 'Cmaj7', 'Am', 'F#dim', 'G7', 'Bsus4' etc."""
        s = symbol.strip()
        root_str = s[0]
        rest = s[1:]
        if rest.startswith("#"):
            root_str += "#"
            rest = rest[1:]
        elif rest.startswith("b"):
            root_str += "b"
            rest = rest[1:]
        root = parse_note(root_str + str(octave))
        if not rest:
            return cls(root=root, chord_type="major")
        ct = CHORD_ALIASES.get(rest, rest)
        if ct not in CHORD_TYPES:
            # try common short forms
            mapping = {
                "m": "minor", "min": "minor",
                "dim": "diminished", "aug": "augmented",
                "7": "dom7", "maj7": "major7", "M7": "major7",
                "m7": "minor7", "hdim7": "half_dim7",
            }
            ct = mapping.get(rest, "major")
        return cls(root=root, chord_type=ct)


# ── Progressions ───────────────────────────────────────────────────────────

# Roman numeral patterns (scale-degree based, 1-indexed)
# Positive = major chord on that degree, negative = minor chord
PROGRESSION_PRESETS: dict[str, list[tuple[int, str]]] = {
    "I-IV-V-I":           [(1, ""), (4, ""), (5, ""), (1, "")],
    "I-V-vi-IV":          [(1, ""), (5, ""), (6, "m"), (4, "")],
    "ii-V-I":             [(2, "m"), (5, ""), (1, "")],
    "I-vi-IV-V":          [(1, ""), (6, "m"), (4, ""), (5, "")],
    "12-bar-blues":        [(1, ""), (1, ""), (1, ""), (1, ""),
                           (4, ""), (4, ""), (1, ""), (1, ""),
                           (5, ""), (4, ""), (1, ""), (5, "")],
    "i-iv-v-i (minor)":   [(1, "m"), (4, "m"), (5, ""), (1, "m")],
    "i-VI-III-VII":       [(1, "m"), (6, ""), (3, ""), (7, "")],
    "I-IV-vi-V":          [(1, ""), (4, ""), (6, "m"), (5, "")],
    "vi-IV-I-V":          [(6, "m"), (4, ""), (1, ""), (5, "")],
    "I-V-vi-iii-IV-I-IV-V": [(1, ""), (5, ""), (6, "m"), (3, "m"),
                              (4, ""), (1, ""), (4, ""), (5, "")],
    "Canon":              [(1, ""), (5, ""), (6, "m"), (3, "m"),
                           (4, ""), (1, ""), (4, ""), (5, "")],
}


@dataclass
class ProgressionChord:
    """One chord in a progression, scale-degree based."""
    degree: int       # 1-indexed scale degree
    suffix: str       # "" for major, "m" for minor, "dim", "aug", "7", etc.
    beats: float = 4.0  # duration in beats (4 = one bar in 4/4)


@dataclass
class Progression:
    name: str
    chords: list[ProgressionChord]
    key_root: int = 0       # MIDI note of key (0 = C)
    key_mode: str = "major"
    bpm: float = 120.0
    time_sig: tuple[int, int] = (4, 4)

    def chord_symbols(self) -> list[str]:
        """Return human-readable chord symbols for the current key."""
        scale = Scale(self.key_root, self.key_mode)
        result = []
        for pc in self.chords:
            pitch = scale.degree(pc.degree - 1, octave=4)
            ct = _suffix_to_type(pc.suffix)
            chord = Chord(root=pitch, chord_type=ct)
            result.append(chord.symbol)
        return result

    @classmethod
    def from_preset(cls, name: str, key_root: int = 0,
                    key_mode: str = "major", bpm: float = 120.0) -> Progression:
        if name not in PROGRESSION_PRESETS:
            raise ValueError(f"unknown progression: {name!r}")
        chords = [
            ProgressionChord(degree=deg, suffix=suf)
            for deg, suf in PROGRESSION_PRESETS[name]
        ]
        return cls(name=name, chords=chords, key_root=key_root,
                   key_mode=key_mode, bpm=bpm)


def _suffix_to_type(suffix: str) -> str:
    mapping = {
        "": "major", "m": "minor", "dim": "diminished",
        "aug": "augmented", "7": "dom7", "maj7": "major7",
        "m7": "minor7", "dim7": "dim7", "hdim7": "half_dim7",
        "sus2": "sus2", "sus4": "sus4",
    }
    return mapping.get(suffix, "major")


# ── Progression → MidiClip ─────────────────────────────────────────────────

def progression_to_midi_clip(
    progression: Progression,
    bars: int = 4,
    voicing_octave: int = 4,
    rhythm: str = "whole",
) -> MidiClip:
    """Convert a Progression to a MidiClip with chord voicings.

    rhythm: "whole" = one chord per bar, "half" = two per bar,
            "quarter" = four per bar, "arpeggio" = broken chords.
    """
    from lfms.midi.model import MidiClip, MidiNote

    scale = Scale(progression.key_root, progression.key_mode)
    beat_dur = 60.0 / progression.bpm
    beats_per_bar = progression.time_sig[0]
    total_beats = bars * beats_per_bar

    notes: list[MidiNote] = []
    beat_pos = 0.0

    # cycle through chords to fill bars
    idx = 0
    while beat_pos < total_beats:
        pc = progression.chords[idx % len(progression.chords)]
        pitch = scale.degree(pc.degree - 1, octave=voicing_octave)
        ct = _suffix_to_type(pc.suffix)
        chord = Chord(root=pitch, chord_type=ct)
        voicing = chord.voicing(octave=voicing_octave)

        chord_beats = min(pc.beats, total_beats - beat_pos)

        if rhythm == "arpeggio":
            step_beats = 0.25
            note_dur = step_beats * 0.8
            t = beat_pos
            vi = 0
            while t < beat_pos + chord_beats and vi < len(voicing) * 2:
                pitch_idx = vi % len(voicing)
                notes.append(MidiNote(
                    pitch=voicing[pitch_idx],
                    start_sec=t * beat_dur,
                    duration_sec=note_dur * beat_dur,
                    velocity=0.7,
                ))
                t += step_beats
                vi += 1
        else:
            if rhythm == "whole":
                note_beats = chord_beats
            elif rhythm == "half":
                note_beats = min(2.0, chord_beats)
            elif rhythm == "quarter":
                note_beats = min(1.0, chord_beats)
            else:
                note_beats = chord_beats

            t = beat_pos
            while t < beat_pos + chord_beats:
                dur = min(note_beats, beat_pos + chord_beats - t)
                for p in voicing:
                    notes.append(MidiNote(
                        pitch=p,
                        start_sec=t * beat_dur,
                        duration_sec=dur * beat_dur * 0.95,
                        velocity=0.7,
                    ))
                t += note_beats

        beat_pos += chord_beats
        idx += 1

    total_sec = total_beats * beat_dur
    title = f"{progression.name} in {note_name(progression.key_root)} " \
            f"{'maj' if progression.key_mode == 'major' else 'min'}"

    return MidiClip(
        title=title,
        notes=notes,
        tempo_bpm=progression.bpm,
        duration_sec=total_sec + 0.1,
    )
