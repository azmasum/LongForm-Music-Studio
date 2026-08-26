"""Tests for Phase E: music theory, chord progressions, and GUI."""
from __future__ import annotations

import os

import pytest

# ── Note parsing ───────────────────────────────────────────────────────────

def test_parse_note():
    from lfms.music.chords import parse_note
    assert parse_note("C4") == 60
    assert parse_note("A4") == 69
    assert parse_note("A#4") == 70
    assert parse_note("Bb4") == 70
    assert parse_note("C3") == 48


def test_note_name():
    from lfms.music.chords import note_name
    assert note_name(60) == "C4"
    assert note_name(69) == "A4"
    assert note_name(70) == "A#4"


# ── Scales ─────────────────────────────────────────────────────────────────

def test_scale_notes():
    from lfms.music.chords import Scale
    s = Scale(60, "major")  # C major
    notes = s.notes((4, 4))
    assert 60 in notes  # C4
    assert 64 in notes  # E4
    assert 67 in notes  # G4
    assert 61 not in notes  # C# not in C major


def test_scale_contains():
    from lfms.music.chords import Scale
    s = Scale(60, "major")
    assert s.contains(60)  # C
    assert s.contains(64)  # E
    assert not s.contains(61)  # C#


def test_scale_degree():
    from lfms.music.chords import Scale
    s = Scale(60, "major")
    assert s.degree(0, 4) == 60  # C4
    assert s.degree(2, 4) == 64  # E4
    assert s.degree(4, 4) == 67  # G4


# ── Chords ─────────────────────────────────────────────────────────────────

def test_chord_voicing():
    from lfms.music.chords import Chord
    c = Chord(root=60, chord_type="major")
    v = c.voicing(octave=4)
    assert v == [60, 64, 67]  # C E G


def test_chord_voicing_inversion():
    from lfms.music.chords import Chord
    c = Chord(root=60, chord_type="major", inversion=1)
    v = c.voicing(octave=4)
    assert v[0] == 64  # E is lowest (first inversion)
    assert 72 in v  # C moved up octave


def test_chord_symbol():
    from lfms.music.chords import Chord
    assert Chord(root=60, chord_type="major").symbol == "C"
    assert Chord(root=60, chord_type="minor").symbol == "Cm"
    assert Chord(root=60, chord_type="major7").symbol == "Cmaj7"
    assert Chord(root=60, chord_type="dom7").symbol == "C7"
    assert Chord(root=60, chord_type="sus4").symbol == "Csus4"


def test_chord_from_symbol():
    from lfms.music.chords import Chord
    c = Chord.from_symbol("Am", octave=4)
    assert c.root == 69  # A4
    assert c.chord_type == "minor"

    c2 = Chord.from_symbol("Cmaj7", octave=4)
    assert c2.root == 60
    assert c2.chord_type == "major7"

    c3 = Chord.from_symbol("G7", octave=4)
    assert c3.root == 67
    assert c3.chord_type == "dom7"


def test_chord_types_all_valid():
    from lfms.music.chords import CHORD_TYPES, Chord
    for ct in CHORD_TYPES:
        c = Chord(root=60, chord_type=ct)
        v = c.voicing()
        assert len(v) >= 2


# ── Progressions ───────────────────────────────────────────────────────────

def test_progression_preset():
    from lfms.music.chords import Progression
    p = Progression.from_preset("I-IV-V-I", key_root=0, key_mode="major")
    symbols = p.chord_symbols()
    assert len(symbols) == 4
    assert symbols[0] == "C"  # I in C major
    assert symbols[1] == "F"  # IV in C major
    assert symbols[2] == "G"  # V in C major
    assert symbols[3] == "C"  # I in C major


def test_progression_minor_key():
    from lfms.music.chords import Progression
    p = Progression.from_preset("i-iv-v-i (minor)", key_root=57, key_mode="minor")
    symbols = p.chord_symbols()
    assert symbols[0] == "Am"  # i in A minor


def test_progression_all_presets():
    from lfms.music.chords import Progression
    for name in ["I-IV-V-I", "I-V-vi-IV", "ii-V-I", "12-bar-blues",
                 "Canon", "vi-IV-I-V"]:
        p = Progression.from_preset(name, key_root=0)
        symbols = p.chord_symbols()
        assert len(symbols) > 0


# ── Progression → MidiClip ─────────────────────────────────────────────────

def test_progression_to_midi_clip():
    from lfms.music.chords import Progression, progression_to_midi_clip
    p = Progression.from_preset("I-IV-V-I", key_root=0, bpm=120.0)
    clip = progression_to_midi_clip(p, bars=4, rhythm="whole")
    assert clip.tempo_bpm == 120.0
    assert clip.duration_sec > 0
    assert len(clip.notes) > 0
    # all notes should be in reasonable range
    for n in clip.notes:
        assert 36 <= n.pitch <= 96


def test_progression_to_midi_arpeggio():
    from lfms.music.chords import Progression, progression_to_midi_clip
    p = Progression.from_preset("I-V-vi-IV", key_root=0, bpm=100.0)
    clip = progression_to_midi_clip(p, bars=2, rhythm="arpeggio")
    assert len(clip.notes) > 10  # arpeggio should produce many notes


def test_progression_to_midi_chord_symbols():
    from lfms.music.chords import Progression
    p = Progression.from_preset("I-V-vi-IV", key_root=0)
    symbols = p.chord_symbols()
    assert symbols == ["C", "G", "Am", "F"]


# ── GUI (needs QApplication) ──────────────────────────────────────────────

_GUI_SMOKE = os.environ.get("LFMS_GUI_SMOKE") == "1"


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_chord_chart_widget():
    from lfms.app.chord_panel import ChordChartWidget
    w = ChordChartWidget()
    w.set_chords(["C", "G", "Am", "F"], 4)
    assert w._symbols == ["C", "G", "Am", "F"]
    assert w._bars == 4


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_progression_widget_generate():
    from lfms.app.chord_panel import ProgressionWidget
    from lfms.midi.model import MidiClip
    w = ProgressionWidget()
    results = []
    w.midi_generated.connect(lambda clip: results.append(clip))
    w._on_generate()
    assert len(results) == 1
    assert isinstance(results[0], MidiClip)
    assert len(results[0].notes) > 0
