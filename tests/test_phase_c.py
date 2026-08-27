"""Tests for Phase C: MIDI model, file I/O, sampler, drum grid."""
from __future__ import annotations

import os

import numpy as np
import pytest

# ── MIDI model ──────────────────────────────────────────────────────────────

def test_note_roundtrip_dict():
    from lfms.midi.model import MidiNote
    n = MidiNote(pitch=72, start_sec=1.5, duration_sec=0.5, velocity=0.9, channel=2)
    d = n.__dict__.copy()
    n2 = MidiNote(**d)
    assert n2.pitch == 72
    assert abs(n2.start_sec - 1.5) < 1e-9
    assert n2.channel == 2


def test_note_validation_bounds():
    from lfms.core.errors import ValidationError
    from lfms.midi.model import MAX_NOTE, MIN_NOTE, MidiNote
    n = MidiNote(pitch=MIN_NOTE - 1, start_sec=0, duration_sec=1)
    with pytest.raises(ValidationError, match="outside"):
        n.validate()
    n2 = MidiNote(pitch=MAX_NOTE + 1, start_sec=0, duration_sec=1)
    with pytest.raises(ValidationError, match="outside"):
        n2.validate()


def test_clip_roundtrip_dict():
    from lfms.midi.model import MidiClip, MidiNote
    clip = MidiClip(
        title="Test Clip",
        tempo_bpm=110.0,
        duration_sec=5.0,
        notes=[
            MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5),
            MidiNote(pitch=64, start_sec=0.5, duration_sec=0.5),
            MidiNote(pitch=67, start_sec=1.0, duration_sec=1.0),
        ],
    )
    d = clip.to_dict()
    clip2 = MidiClip.from_dict(d)
    assert clip2.title == "Test Clip"
    assert len(clip2.notes) == 3
    assert clip2.notes[1].pitch == 64


def test_clip_notes_in_range():
    from lfms.midi.model import MidiClip, MidiNote
    clip = MidiClip(duration_sec=10.0)
    clip.notes = [
        MidiNote(pitch=60, start_sec=1.0, duration_sec=0.5),
        MidiNote(pitch=64, start_sec=2.0, duration_sec=0.5),
        MidiNote(pitch=67, start_sec=4.0, duration_sec=0.5),
    ]
    in_range = clip.notes_in_range(0.5, 2.5)
    assert len(in_range) == 2


def test_pitch_name():
    from lfms.midi.model import pitch_name
    assert pitch_name(60) == "C4"
    assert pitch_name(69) == "A4"
    assert pitch_name(48) == "C3"


def test_snap_to_grid():
    from lfms.midi.model import snap_to_grid
    snapped = snap_to_grid(0.13, 120.0, 0.25)
    assert abs(snapped - 0.125) < 0.001


# ── MIDI file I/O ──────────────────────────────────────────────────────────

def test_read_write_midi_roundtrip(tmp_path):
    from lfms.midi.io import read_midi, write_midi
    from lfms.midi.model import MidiClip, MidiNote

    clip = MidiClip(
        title="Roundtrip",
        tempo_bpm=120.0,
        duration_sec=4.0,
        notes=[
            MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5, velocity=0.8, channel=0),
            MidiNote(pitch=64, start_sec=0.5, duration_sec=0.5, velocity=0.9, channel=0),
            MidiNote(pitch=67, start_sec=1.0, duration_sec=1.0, velocity=1.0, channel=0),
            MidiNote(pitch=48, start_sec=0.0, duration_sec=1.0, velocity=0.7, channel=9),
        ],
    )
    path = tmp_path / "test.mid"
    write_midi(clip, path)
    assert path.exists()
    clips = read_midi(path)
    assert len(clips) == 1
    assert len(clips[0].notes) == 4
    pitches = sorted(n.pitch for n in clips[0].notes)
    assert pitches == [48, 60, 64, 67]
    assert abs(clips[0].tempo_bpm - 120.0) < 1.0


def test_read_midi_multi_track(tmp_path):
    import mido

    from lfms.midi.io import read_midi
    from lfms.midi.model import MidiClip, MidiNote

    clip1 = MidiClip(
        title="Track1", tempo_bpm=120.0, duration_sec=2.0, track_index=0,
        notes=[MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5)],
    )
    clip2 = MidiClip(
        title="Track2", tempo_bpm=120.0, duration_sec=2.0, track_index=1,
        notes=[MidiNote(pitch=72, start_sec=0.0, duration_sec=0.5, channel=1)],
    )
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    for clip in [clip1, clip2]:
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(clip.tempo_bpm)))
        for note in clip.notes:
            off_tick = int(note.end_sec * clip.tempo_bpm / 60.0 * 480)
            track.append(mido.Message("note_on", note=note.pitch,
                                      velocity=note.midi_velocity, channel=note.channel, time=0))
            track.append(mido.Message("note_off", note=note.pitch,
                                      velocity=0, channel=note.channel, time=off_tick))
        track.append(mido.MetaMessage("end_of_track", time=0))
    path = tmp_path / "multi.mid"
    mid.save(str(path))
    clips = read_midi(path)
    assert len(clips) == 2
    assert clips[0].track_index == 0
    assert clips[1].track_index == 1


def test_read_midi_filter_track(tmp_path):
    import mido

    from lfms.midi.io import read_midi

    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    for idx in range(3):
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120)))
        track.append(mido.Message("note_on", note=60 + idx, velocity=80, time=0))
        track.append(mido.Message("note_off", note=60 + idx, velocity=0, time=480))
        track.append(mido.MetaMessage("end_of_track", time=0))
    path = tmp_path / "filter.mid"
    mid.save(str(path))
    clips = read_midi(path, track_index=1)
    assert len(clips) == 1
    assert clips[0].notes[0].pitch == 61


def test_write_midi_invalid_file(tmp_path):
    from lfms.core.errors import ValidationError
    from lfms.midi.io import read_midi
    bad = tmp_path / "bad.mid"
    bad.write_text("not a midi file")
    with pytest.raises(ValidationError, match="cannot read"):
        read_midi(bad)


# ── Sampler ────────────────────────────────────────────────────────────────

def test_sampler_source_produces_audio():
    from lfms.audio_engine.sampler import SamplerSource
    sr = 48000
    dur_samples = sr
    t = np.linspace(0, 1.0, dur_samples, dtype=np.float32)
    sample = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
    events = [
        {"pitch": 60, "start_sec": 0.0, "duration_sec": 0.5, "velocity": 0.8},
        {"pitch": 64, "start_sec": 0.5, "duration_sec": 0.5, "velocity": 0.6},
    ]
    src = SamplerSource(sr, sample, base_note=60, events=events)
    total = np.zeros((1, sr), dtype=np.float32)
    pos = 0
    while pos < sr and not src.finished:
        n = min(2048, sr - pos)
        block = src.process(n)
        total[:, pos:pos + n] = block[:, :n]
        pos += n
    rms = float(np.sqrt(np.mean(total[:, :sr // 2] ** 2)))
    assert rms > 0.001, "sampler produced silence"
    assert not src.finished or pos >= sr


def test_sampler_voice_pitch_shift():
    from lfms.audio_engine.sampler import SamplerVoice
    sr = 48000
    dur_samples = sr
    t = np.linspace(0, 1.0, dur_samples, dtype=np.float32)
    sample = (np.sin(2 * np.pi * 440 * t) * 0.8).astype(np.float32)
    voice = SamplerVoice(sr, sample, base_note=69, target_note=81, velocity=1.0)
    out = voice.process(sr // 2)
    rms = float(np.sqrt(np.mean(out[0] ** 2)))
    assert rms > 0.001, "sampler voice produced silence"


# ── DefaultSineSource ──────────────────────────────────────────────────────

def test_default_sine_source():
    from lfms.audio_engine.midi_source import DefaultSineSource
    from lfms.midi.model import MidiClip, MidiNote
    clip = MidiClip(
        duration_sec=2.0,
        notes=[MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5)],
    )
    src = DefaultSineSource(48000, clip)
    total_frames = 0
    all_audio = []
    while not src.finished and total_frames < 48000:
        block = src.process(2048)
        all_audio.append(block)
        total_frames += block.shape[1]
    audio = np.concatenate(all_audio, axis=1)
    rms = float(np.sqrt(np.mean(audio[0] ** 2)))
    assert rms > 0.001


# ── Piano roll scene (needs QApplication) ──────────────────────────────────


_GUI_SMOKE = os.environ.get("LFMS_GUI_SMOKE") == "1"


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_piano_roll_scene_load_clip():
    from lfms.app.piano_roll import PianoRollScene
    from lfms.midi.model import MidiClip, MidiNote
    clip = MidiClip(
        tempo_bpm=120.0,
        duration_sec=4.0,
        notes=[
            MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5),
            MidiNote(pitch=67, start_sec=1.0, duration_sec=0.5),
        ],
    )
    scene = PianoRollScene()
    scene.load_clip(clip)
    note_items = [i for i in scene.items() if hasattr(i, 'note')]
    assert len(note_items) == 2


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_piano_roll_scene_add_note():
    from lfms.app.piano_roll import PianoRollWidget
    from lfms.midi.model import MidiClip
    clip = MidiClip(duration_sec=8.0)
    widget = PianoRollWidget()
    widget.set_clip(clip)
    widget._scene.note_added.emit(1.0, 72, 0.25)
    assert len(clip.notes) == 1
    assert clip.notes[0].pitch == 72


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_piano_roll_scene_remove_note():
    from lfms.app.piano_roll import PianoRollWidget
    from lfms.midi.model import MidiClip, MidiNote
    clip = MidiClip(
        duration_sec=4.0,
        notes=[MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5)],
    )
    widget = PianoRollWidget()
    widget.set_clip(clip)
    note_id = clip.notes[0].note_id
    widget._scene.note_removed.emit(note_id)
    assert len(clip.notes) == 0


# ── Drum grid (needs QApplication) ─────────────────────────────────────────

@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_drum_scene_toggle():
    from lfms.app.drum_grid import DrumScene
    scene = DrumScene(16)
    assert not scene._cells[0][0].is_on
    scene.toggle_cell(0, 0)
    assert scene._cells[0][0].is_on
    scene.toggle_cell(0, 0)
    assert not scene._cells[0][0].is_on


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_drum_scene_to_clip():
    from lfms.app.drum_grid import DrumScene
    from lfms.midi.model import DRUM_CHANNEL
    scene = DrumScene(16)
    scene.toggle_cell(0, 0)
    scene.toggle_cell(0, 4)
    clip = scene.to_clip(bpm=120.0)
    assert len(clip.notes) == 2
    assert all(n.channel == DRUM_CHANNEL for n in clip.notes)
    assert clip.notes[0].pitch == 36  # kick


@pytest.mark.skipif(not _GUI_SMOKE, reason="set LFMS_GUI_SMOKE=1 to run GUI tests")
def test_drum_scene_load_clip():
    from lfms.app.drum_grid import DrumScene
    from lfms.midi.model import DRUM_CHANNEL, MidiClip, MidiNote
    clip = MidiClip(
        tempo_bpm=120.0,
        duration_sec=4.0,
        notes=[
            MidiNote(pitch=36, start_sec=0.0, duration_sec=0.1, channel=DRUM_CHANNEL),
            MidiNote(pitch=38, start_sec=0.5, duration_sec=0.1, channel=DRUM_CHANNEL),
        ],
    )
    scene = DrumScene(16)
    scene.load_clip(clip, bpm=120.0)
    assert scene._cells[0][0].is_on  # kick at step 0
    assert scene._cells[1][4].is_on  # snare at step 4 (0.5s at 120bpm = 4 × 16th notes)


# ── Integration: build_project_graph with MIDI clip ────────────────────────

def test_project_graph_midi_clip(tmp_path):
    from lfms.library.service import LibraryService
    from lfms.midi.model import MidiClip, MidiNote
    from lfms.studio.project import build_project_graph
    from lfms.timeline.model import Clip, TimelineDocument, TrackState

    lib = LibraryService(":memory:")
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="MIDI Track", kind="MUSIC"))

    midi_clip = MidiClip(
        tempo_bpm=120.0,
        duration_sec=2.0,
        notes=[
            MidiNote(pitch=60, start_sec=0.0, duration_sec=0.5, velocity=0.7),
            MidiNote(pitch=64, start_sec=0.5, duration_sec=0.5, velocity=0.8),
        ],
    )
    clip = Clip(
        track_id=track.track_id,
        start_sec=0.0,
        duration_sec=2.0,
        source_kind="MIDI",
        midi_data=midi_clip.to_dict(),
    )
    doc.add_clip(clip)
    graph = build_project_graph(doc, lib)
    assert len(graph.mixer.strips) == 1


def test_project_graph_midi_no_data_fails():
    from lfms.core.errors import ValidationError
    from lfms.library.service import LibraryService
    from lfms.studio.project import build_project_graph
    from lfms.timeline.model import Clip, TimelineDocument, TrackState

    lib = LibraryService(":memory:")
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="Track", kind="MUSIC"))
    clip = Clip(
        track_id=track.track_id,
        start_sec=0.0,
        duration_sec=2.0,
        source_kind="MIDI",
        midi_data=None,
    )
    doc.add_clip(clip)
    with pytest.raises(ValidationError, match="no embedded note data"):
        build_project_graph(doc, lib)
