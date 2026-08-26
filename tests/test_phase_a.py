"""Tests for Phase A editing features (model + engine + GUI smoke)."""
from __future__ import annotations

import os

import numpy as np
import pytest
import soundfile as sf

from lfms.core.errors import ValidationError
from lfms.timeline.commands import (
    AddClipCommand,
    CommandStack,
    SetClipPropertyCommand,
    SplitClipCommand,
)
from lfms.timeline.model import Clip, TimelineDocument, TrackState


def _doc_with_clip():
    doc = TimelineDocument(duration_sec=60.0)
    tr = doc.add_track(TrackState(name="M"))
    clip = doc.add_clip(
        Clip(track_id=tr.track_id, start_sec=2.0, duration_sec=5.0,
             label="A", source_kind="GENERATED", source_ref="fp1")
    )
    return doc, tr, clip


class TestClipModelFades:
    def test_split_at_middle(self):
        doc, tr, clip = _doc_with_clip()
        left, right = doc.split_clip(clip.clip_id, 4.5)
        assert left.start_sec == 2.0
        assert abs(left.duration_sec - 2.5) < 1e-9
        assert right.start_sec == 4.5
        assert abs(right.duration_sec - 2.5) < 1e-9
        assert left.clip_id != right.clip_id

    def test_split_too_close_raises(self):
        doc, _, clip = _doc_with_clip()
        with pytest.raises(ValidationError, match="inside the clip"):
            doc.split_clip(clip.clip_id, 2.0)
        with pytest.raises(ValidationError, match="inside the clip"):
            doc.split_clip(clip.clip_id, 7.0)

    def test_split_fade_redistribution(self):
        doc, _, clip = _doc_with_clip()
        # fade_in=3.0 spans the split at offset 2.5; carry_in = 3.0-2.5 = 0.5
        # fade_out=1.0 spans the split at offset 2.5 (right has 2.5s); carry_out=0
        doc.clips[0].fade_in_sec = 3.0
        doc.clips[0].fade_out_sec = 1.0
        left, right = doc.split_clip(clip.clip_id, 4.5)
        assert left.fade_in_sec == pytest.approx(2.5)  # min(3.0, offset=2.5)
        assert left.fade_out_sec == pytest.approx(0.0)
        assert right.fade_in_sec == pytest.approx(0.5)  # carry from cross-split
        assert right.fade_out_sec == pytest.approx(1.0)

    def test_split_cmd_undo_redo(self):
        doc, _, clip = _doc_with_clip()
        stack = CommandStack()
        original_id = clip.clip_id
        stack.execute(SplitClipCommand(clip.clip_id, 4.5), doc)
        assert len(doc.clips) == 2
        stack.undo(doc)
        assert len(doc.clips) == 1
        restored = doc.clip(original_id)
        assert abs(restored.duration_sec - 5.0) < 1e-9
        stack.redo(doc)
        assert len(doc.clips) == 2

    def test_clone_clip_has_new_id(self):
        doc, _, clip = _doc_with_clip()
        clone = doc.clone_clip(clip.clip_id)
        assert clone.clip_id != clip.clip_id
        assert abs(clone.start_sec - 7.0) < 1e-9
        assert clone.label == "A copy"

    def test_clip_property_cmd(self):
        doc, _, clip = _doc_with_clip()
        stack = CommandStack()
        stack.execute(SetClipPropertyCommand(clip.clip_id, "gain_db", -6.0), doc)
        assert doc.clip(clip.clip_id).gain_db == -6.0
        stack.undo(doc)
        assert doc.clip(clip.clip_id).gain_db == 0.0

    def test_clip_fade_validation(self):
        bad1 = Clip(track_id="x", start_sec=0, duration_sec=1.0,
                    fade_in_sec=-0.1, fade_out_sec=0.0)
        with pytest.raises(ValidationError, match="fades must be >= 0"):
            bad1.validate()
        bad2 = Clip(track_id="x", start_sec=0, duration_sec=1.0,
                    fade_in_sec=0.6, fade_out_sec=0.6)
        with pytest.raises(ValidationError, match="fades must not overlap"):
            bad2.validate()

    def test_roundtrip_persists_fades(self):
        doc, tr, _ = _doc_with_clip()
        doc.add_clip(Clip(track_id=tr.track_id, start_sec=10, duration_sec=2,
                          source_kind="GENERATED", source_ref="fp2",
                          fade_in_sec=0.3, fade_out_sec=0.2, gain_db=-3.0))
        data = doc.to_dict()
        doc2 = TimelineDocument.from_dict(data)
        c = [c for c in doc2.clips if c.source_ref == "fp2"][0]
        assert c.fade_in_sec == pytest.approx(0.3)
        assert c.fade_out_sec == pytest.approx(0.2)
        assert c.gain_db == pytest.approx(-3.0)

    def test_stems_produced(self, tmp_path):
        from lfms.generator.composer import Composer
        from lfms.generator.plan import GenerationParameters
        from lfms.library.service import LibraryService
        from lfms.studio.project import render_project_stems

        sr = 48000
        t = np.arange(int(sr * 1.5)) / sr
        sf.write(
            str(tmp_path / "tone.wav"),
            (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32),
            sr, subtype="PCM_16",
        )
        lib = LibraryService(":memory:")
        params = GenerationParameters(
            seed=42, duration_sec=2.0, genre="AMBIENT",
            moods=("CALM",), intensity=35.0,
        )
        params.validate()
        comp = Composer(params).compose()
        lib.register_composition(comp, params)
        doc = TimelineDocument(duration_sec=30.0)
        tr1 = doc.add_track(TrackState(name="Music"))
        tr2 = doc.add_track(TrackState(name="Audio"))
        doc.add_clip(Clip(track_id=tr1.track_id, start_sec=0.0, duration_sec=2.0,
                          source_kind="GENERATED", source_ref=comp.fingerprint))
        doc.add_clip(Clip(track_id=tr2.track_id, start_sec=0.5, duration_sec=1.5,
                          source_kind="AUDIO_FILE",
                          source_ref=str(tmp_path / "tone.wav")))
        outcome = render_project_stems(doc, lib, tmp_path / "stems")
        assert len(outcome.paths) == 2
        # stem 1: non-silent from 0..2s
        d1, _ = sf.read(str(outcome.paths[0]), always_2d=True, dtype="float32")
        body_rms = float(np.sqrt(np.mean(d1[int(0.5 * sr):int(1.5 * sr)] ** 2)))
        assert body_rms > 1e-3
        # stem 2: non-silent from 0.5..2.0s
        d2, _ = sf.read(str(outcome.paths[1]), always_2d=True, dtype="float32")
        gap_rms = float(np.sqrt(np.mean(d2[:int(0.4 * sr)] ** 2)))
        tone_rms = float(np.sqrt(np.mean(d2[int(0.7 * sr):int(1.8 * sr)] ** 2)))
        assert gap_rms < 1e-5 and tone_rms > 0.05

    def test_missing_fingerprint_raises(self, tmp_path):
        from lfms.library.service import LibraryService
        from lfms.studio.project import build_project_graph

        lib = LibraryService(":memory:")
        doc = TimelineDocument(duration_sec=10.0)
        tr = doc.add_track(TrackState(name="M"))
        doc.add_clip(Clip(track_id=tr.track_id, start_sec=0.0, duration_sec=1.0,
                          source_kind="GENERATED", source_ref="fp-missing"))
        with pytest.raises(ValidationError, match="no library item"):
            build_project_graph(doc, lib)


# --- GUI smoke tests ---

_gui = pytest.mark.skipif(
    os.environ.get("LFMS_GUI_SMOKE") != "1",
    reason="GUI tests need LFMS_GUI_SMOKE=1",
)

if os.environ.get("LFMS_GUI_SMOKE") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@_gui
def test_split_and_duplicate(qapp, tmp_path):
    from lfms.app.main_window import MainWindow
    window = MainWindow(db_path=tmp_path / "db.db")
    # generate a clip
    clip = window.generate_from_payload(
        {"seed": 8888, "genre": "AMBIENT", "moods": ("CALM",),
         "duration_sec": 3.0, "intensity": 30.0}
    )
    assert clip is not None
    assert len(window.document.clips) == 1
    original_id = clip.clip_id
    # split
    window.timeline_canvas.selected_clip_id = original_id
    window._on_clip_split(original_id, 1.5)
    assert len(window.document.clips) == 2
    # duplicate
    window.timeline_canvas.selected_clip_id = original_id
    window._on_clip_duplicate(original_id)
    assert len(window.document.clips) == 3


@_gui
def test_clip_gain_slider(qapp, tmp_path):
    from lfms.app.main_window import MainWindow
    window = MainWindow(db_path=tmp_path / "db.db")
    clip = window.generate_from_payload(
        {"seed": 7777, "genre": "AMBIENT", "moods": ("CALM",),
         "duration_sec": 2.0, "intensity": 30.0}
    )
    window.timeline_canvas.selected_clip_id = clip.clip_id
    window._on_clip_selection_changed(clip.clip_id)
    assert window.clip_props_box.isEnabled()
    window._clip_prop_refreshing = True
    window._clip_gain_slider.setValue(-6)
    window._clip_prop_refreshing = False
    window._commit_clip_property("gain_db", -6.0)
    assert window.document.clip(clip.clip_id).gain_db == -6.0
    # undo
    window.commands.undo(window.document)
    assert window.document.clip(clip.clip_id).gain_db == 0.0


@_gui
def test_import_audio_file(qapp, tmp_path):
    from lfms.app.main_window import MainWindow
    sr = 48000
    t = np.arange(int(sr * 0.4)) / sr
    tone = (0.5 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
    wav = tmp_path / "import.wav"
    sf.write(str(wav), tone, sr, subtype="PCM_16")
    window = MainWindow(db_path=tmp_path / "db.db")
    window.library.import_audio_file(wav)
    # simulate import (skip dialog)
    item = window.library.list_items(query="import")[0]
    start = max((c.end_sec for c in window.document.clips), default=0.0)
    track = next(t for t in window.document.tracks if t.kind == "MUSIC")
    clip = Clip(
        track_id=track.track_id, start_sec=start,
        duration_sec=item.duration_sec, label=item.title,
        source_kind="AUDIO_FILE", source_ref=str(wav.resolve()),
    )
    window.commands.execute(AddClipCommand(clip), window.document)
    assert len(window.document.clips) == 1
    imported = window.document.clips[0]
    assert imported.source_kind == "AUDIO_FILE"
    assert abs(imported.duration_sec - 0.4) < 0.1


def test_render_mixdown_produces_file(tmp_path):
    from lfms.generator.composer import Composer
    from lfms.generator.plan import GenerationParameters
    from lfms.library.service import LibraryService
    from lfms.studio import render_project_mixdown
    from lfms.timeline.model import Clip, TimelineDocument, TrackState

    lib = LibraryService(":memory:")
    params = GenerationParameters(
        seed=6666, duration_sec=1.5, genre="AMBIENT",
        moods=("CALM",), intensity=30.0,
    )
    params.validate()
    comp = Composer(params).compose()
    lib.register_composition(comp, params)
    doc = TimelineDocument(duration_sec=10.0)
    tr = doc.add_track(TrackState(name="M"))
    doc.add_clip(Clip(track_id=tr.track_id, start_sec=0.0, duration_sec=1.5,
                      source_kind="GENERATED", source_ref=comp.fingerprint))
    out = render_project_mixdown(
        doc, lib, tmp_path / "mix_out",
        preset=None, filename="test-mix",
    )
    assert out.paths[0].exists()
    info = sf.info(str(out.paths[0]))
    assert info.duration > 1.0
