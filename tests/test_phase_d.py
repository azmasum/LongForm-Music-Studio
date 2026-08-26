"""Tests for Phase D: FX engine, model, and integration."""
from __future__ import annotations

import numpy as np
import pytest

# ── Effect model ───────────────────────────────────────────────────────────

def test_effect_slot_roundtrip():
    from lfms.timeline.model import EffectSlot
    slot = EffectSlot(effect_type="eq", params={"low_gain_db": 3.0, "mid_gain_db": -2.0})
    d = slot.to_dict()
    slot2 = EffectSlot.from_dict(d)
    assert slot2.effect_type == "eq"
    assert slot2.params["low_gain_db"] == 3.0


def test_fx_chain_add_remove():
    from lfms.timeline.model import FxChain
    chain = FxChain(track_id="trk_1")
    s1 = chain.add("gain", {"gain_db": -6.0})
    s2 = chain.add("reverb", {"wet": 0.3})
    assert len(chain.slots) == 2
    chain.remove(s1.effect_id)
    assert len(chain.slots) == 1
    assert chain.slots[0].effect_id == s2.effect_id


def test_fx_chain_roundtrip():
    from lfms.timeline.model import FxChain
    chain = FxChain(track_id="trk_1")
    chain.add("gain", {"gain_db": -6.0})
    chain.add("compressor", {"threshold_db": -18.0, "ratio": 4.0})
    d = chain.to_dict()
    chain2 = FxChain.from_dict(d)
    assert len(chain2.slots) == 2
    assert chain2.slots[0].effect_type == "gain"
    assert chain2.slots[1].effect_type == "compressor"


def test_document_fx_chain():
    from lfms.timeline.model import TimelineDocument, TrackState
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="Track 1", kind="MUSIC"))
    chain = doc.fx_chain(track.track_id)
    chain.add("delay", {"delay_sec": 0.3})
    assert len(doc.fx_chain(track.track_id).slots) == 1
    # roundtrip
    doc2 = TimelineDocument.from_dict(doc.to_dict())
    assert len(doc2.fx_chain(track.track_id).slots) == 1


def test_document_fx_chain_cleanup_on_remove_track():
    from lfms.timeline.model import TimelineDocument, TrackState
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="Track 1", kind="MUSIC"))
    doc.fx_chain(track.track_id).add("reverb")
    doc.remove_track(track.track_id)
    assert len(doc.fx_chains) == 0


# ── GainEffect ─────────────────────────────────────────────────────────────

def test_gain_effect():
    from lfms.audio_engine.effects import GainEffect
    x = np.ones((2, 1024), dtype=np.float32) * 0.5
    fx = GainEffect(gain_db=6.0)
    out = fx.process(x)
    assert out.shape == (2, 1024)
    assert float(np.max(out)) > 0.9


# ── EQ ─────────────────────────────────────────────────────────────────────

def test_eq_effect():
    from lfms.audio_engine.studio_fx import EqEffect
    sr = 48000
    fx = EqEffect(sr, low_gain_db=6.0, mid_gain_db=-3.0, high_gain_db=6.0)
    x = np.random.randn(2, 4096).astype(np.float32) * 0.1
    out = fx.process(x)
    assert out.shape == x.shape
    # boost should increase energy
    boost = EqEffect(sr, low_gain_db=12.0)
    boosted = boost.process(x)
    assert float(np.sqrt(np.mean(boosted ** 2))) > float(np.sqrt(np.mean(x ** 2)))


def test_eq_to_dict():
    from lfms.audio_engine.studio_fx import EqEffect
    fx = EqEffect(48000, low_gain_db=3.0, mid_gain_db=-2.0, high_gain_db=1.0)
    d = fx.to_dict()
    assert d["type"] == "eq"
    assert d["low_gain_db"] == 3.0


# ── Compressor ─────────────────────────────────────────────────────────────

def test_compressor_effect():
    from lfms.audio_engine.studio_fx import CompressorEffect
    sr = 48000
    fx = CompressorEffect(sr, threshold_db=-20.0, ratio=4.0)
    x = np.random.randn(2, 4096).astype(np.float32) * 0.5
    out = fx.process(x)
    assert out.shape == x.shape
    # compressed output should have lower peak than input
    assert float(np.max(np.abs(out))) <= float(np.max(np.abs(x))) * 1.1


def test_compressor_makeup():
    from lfms.audio_engine.studio_fx import CompressorEffect
    sr = 48000
    fx = CompressorEffect(sr, threshold_db=-10.0, ratio=2.0, makeup_db=12.0)
    x = np.ones((2, 4096), dtype=np.float32) * 0.3
    out = fx.process(x)
    # makeup should boost the compressed signal above original level
    assert float(np.mean(np.abs(out))) > float(np.mean(np.abs(x)))


def test_compressor_to_dict():
    from lfms.audio_engine.studio_fx import CompressorEffect
    fx = CompressorEffect(48000, threshold_db=-18.0, ratio=6.0, makeup_db=3.0)
    d = fx.to_dict()
    assert d["type"] == "compressor"
    assert d["ratio"] == 6.0


# ── Delay ──────────────────────────────────────────────────────────────────

def test_delay_effect():
    from lfms.audio_engine.studio_fx import DelayEffect
    sr = 48000
    fx = DelayEffect(sr, delay_sec=0.05, feedback=0.3, wet=0.4)
    x = np.zeros((2, sr), dtype=np.float32)
    x[0, 0] = 1.0
    x[1, 0] = 1.0
    out = fx.process(x)
    assert out.shape == x.shape
    delay_idx = int(0.05 * sr)
    assert abs(float(out[0, delay_idx])) > 0.01


def test_delay_feedback():
    from lfms.audio_engine.studio_fx import DelayEffect
    sr = 48000
    fx = DelayEffect(sr, delay_sec=0.05, feedback=0.5, wet=1.0)
    x = np.zeros((2, sr), dtype=np.float32)
    x[0, 0] = 1.0
    x[1, 0] = 1.0
    out = fx.process(x)
    idx2 = int(0.1 * sr)
    assert abs(float(out[0, idx2])) > 0.01


def test_delay_pingpong():
    from lfms.audio_engine.studio_fx import DelayEffect
    sr = 48000
    fx = DelayEffect(sr, delay_sec=0.05, feedback=0.4, wet=1.0, ping_pong=True)
    x = np.zeros((2, sr), dtype=np.float32)
    x[0, 0] = 1.0
    x[1, 0] = 0.0
    out = fx.process(x)
    delay_idx = int(0.05 * sr)
    assert abs(float(out[1, delay_idx])) > 0.01


def test_delay_to_dict():
    from lfms.audio_engine.studio_fx import DelayEffect
    fx = DelayEffect(48000, delay_sec=0.5, feedback=0.4, wet=0.3, ping_pong=True)
    d = fx.to_dict()
    assert d["type"] == "delay"
    assert d["ping_pong"] is True


# ── Reverb ─────────────────────────────────────────────────────────────────

def test_reverb_effect():
    from lfms.audio_engine.studio_fx import ReverbEffect
    sr = 48000
    fx = ReverbEffect(sr, room_size=0.7, damping=0.5, wet=0.3)
    x = np.zeros((2, 4800), dtype=np.float32)
    x[0, 100] = 1.0
    x[1, 100] = 1.0
    out = fx.process(x)
    assert out.shape == x.shape
    # reverb tail should have some energy
    assert float(np.sqrt(np.mean(out[:, 2000:] ** 2))) > 0.001


def test_reverb_to_dict():
    from lfms.audio_engine.studio_fx import ReverbEffect
    fx = ReverbEffect(48000, room_size=0.8, damping=0.6, wet=0.4)
    d = fx.to_dict()
    assert d["type"] == "reverb"
    assert d["room_size"] == 0.8


# ── build_effect_from_dict ─────────────────────────────────────────────────

def test_build_effect_from_dict():
    from lfms.audio_engine.effects import GainEffect
    from lfms.audio_engine.studio_fx import build_effect_from_dict
    fx = build_effect_from_dict({"type": "gain", "gain_db": -6.0}, 48000)
    assert isinstance(fx, GainEffect)

    fx2 = build_effect_from_dict({"type": "eq", "low_gain_db": 3.0}, 48000)
    assert hasattr(fx2, "process")

    fx3 = build_effect_from_dict({"type": "compressor", "ratio": 2.0}, 48000)
    assert hasattr(fx3, "process")


def test_build_effect_unknown_type():
    from lfms.audio_engine.studio_fx import build_effect_from_dict
    with pytest.raises(ValueError, match="unknown effect type"):
        build_effect_from_dict({"type": "flanger"}, 48000)


# ── serialize_effect ───────────────────────────────────────────────────────

def test_serialize_effect():
    from lfms.audio_engine.effects import GainEffect
    from lfms.audio_engine.studio_fx import CompressorEffect, serialize_effect
    d = serialize_effect(GainEffect(gain_db=-6.0))
    assert d["type"] == "gain"
    d2 = serialize_effect(CompressorEffect(48000, ratio=4.0))
    assert d2["type"] == "compressor"


# ── TrackStrip FX integration ──────────────────────────────────────────────

def test_trackstrip_with_fx():
    from lfms.audio_engine.context import RenderContext
    from lfms.audio_engine.effects import GainEffect
    from lfms.audio_engine.graph import TrackStrip
    from lfms.audio_engine.sources import ToneSource

    sr = 48000
    tone = ToneSource(sr, frequency=440.0)
    strip = TrackStrip("test", tone, volume_db=-10.0, effects=[GainEffect(gain_db=-6.0)])
    ctx = RenderContext(sample_rate=sr, channels=2)
    out = strip.process(ctx, 1024)
    assert out.shape == (2, 1024)
    assert float(np.max(np.abs(out))) > 0.0


def test_project_graph_fx_chain():
    from lfms.library.service import LibraryService
    from lfms.studio.project import build_project_graph
    from lfms.timeline.model import Clip, TimelineDocument, TrackState

    lib = LibraryService(":memory:")
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="FX Track", kind="MUSIC"))
    clip = Clip(
        track_id=track.track_id,
        start_sec=0.0,
        duration_sec=2.0,
        source_kind="MIDI",
        midi_data={
            "tempo_bpm": 120.0,
            "duration_sec": 2.0,
            "notes": [
                {"pitch": 60, "start_sec": 0.0, "duration_sec": 0.5, "velocity": 0.7},
            ],
        },
    )
    doc.add_clip(clip)
    chain = doc.fx_chain(track.track_id)
    chain.add("gain", {"gain_db": -6.0})
    chain.add("eq", {"mid_gain_db": 3.0})
    graph = build_project_graph(doc, lib)
    strip = graph.mixer.strips[0]
    assert len(strip.effects) == 2
