"""Tests for the mixer graph: strips, pan, mute/solo and master chain."""
from __future__ import annotations

import numpy as np
import pytest

from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.dsp import band_energy, db_to_gain, rms
from lfms.audio_engine.effects import StereoWidth
from lfms.audio_engine.graph import AudioGraph, TrackStrip
from lfms.audio_engine.sources import ToneSource

SR = 8000


def _collect(graph: AudioGraph, seconds: float) -> np.ndarray:
    ctx = RenderContext(sample_rate=graph.sample_rate)
    total = int(seconds * graph.sample_rate)
    parts = []
    done = 0
    while done < total:
        n = min(1024, total - done)
        parts.append(graph.process(ctx, n))
        done += n
    return np.concatenate(parts, axis=1)


def _stereo_tones_graph() -> AudioGraph:
    g = AudioGraph(SR)
    g.create_track("left", ToneSource(SR, frequency=330.0), pan=-1.0)
    g.create_track("right", ToneSource(SR, frequency=550.0), pan=1.0)
    return g


class TestTrackStrips:
    def test_pan_routes_frequencies(self) -> None:
        out = _collect(_stereo_tones_graph(), 0.5).astype(float)
        left_low = band_energy(out[0], SR, 300, 360)
        left_high = band_energy(out[0], SR, 520, 580)
        right_high = band_energy(out[1], SR, 520, 580)
        right_low = band_energy(out[1], SR, 300, 360)
        assert left_low > 50 * max(left_high, 1e-12)
        assert right_high > 50 * max(right_low, 1e-12)

    def test_mute_silences_strip(self) -> None:
        g = _stereo_tones_graph()
        for strip in g.mixer.strips:
            strip.mute = True
        out = _collect(g, 0.2)
        assert rms(out) < 1e-6

    def test_solo_isolates_strip(self) -> None:
        g = _stereo_tones_graph()
        g.mixer.strips[0].solo = True
        out = _collect(g, 0.3).astype(float)
        right_level = rms(out[1])
        assert right_level < 1e-6
        assert rms(out[0]) > 0.01

    def test_volume_db_applies(self) -> None:
        base = AudioGraph(SR)
        base.create_track("t", ToneSource(SR, frequency=220.0))
        quiet = AudioGraph(SR)
        quiet.create_track("t", ToneSource(SR, frequency=220.0), volume_db=-20.0)
        loud_rms = rms(_collect(base, 0.2).astype(float))
        quiet_rms = rms(_collect(quiet, 0.2).astype(float))
        expected = db_to_gain(-20.0)
        assert quiet_rms / loud_rms == pytest.approx(expected, rel=0.05)

    def test_master_volume_applies(self) -> None:
        g = AudioGraph(SR, )
        g.create_track("t", ToneSource(SR, frequency=220.0))
        full = _collect(g, 0.2)
        g.mixer.master_volume_db = -20.0
        reduced = _collect(g, 0.2)
        ratio = rms(reduced.astype(float)) / rms(full.astype(float))
        assert ratio == pytest.approx(db_to_gain(-20.0), rel=0.05)


class TestStereoWidthEffect:
    def test_width_zero_collapses_to_mono(self) -> None:
        g = AudioGraph(SR)
        g.create_track(
            "t",
            ToneSource(SR, frequency=440.0),
            effects=[StereoWidth(width=0.0)],
            pan=-0.8,
        )
        out = _collect(g, 0.2)
        assert np.allclose(out[0], out[1])


class TestGraphValidation:
    def test_sample_rate_mismatch_raises(self) -> None:
        g = AudioGraph(SR)
        with pytest.raises(ValueError):
            g.create_track("bad", ToneSource(44100, frequency=100.0))

    def test_mono_graph_shape(self) -> None:
        g = AudioGraph(SR, channels=1)
        g.create_track("t", ToneSource(SR, frequency=200.0))
        out = _collect(g, 0.1)
        assert out.shape[0] == 1

    def test_strip_defaults(self) -> None:
        strip = TrackStrip("x", ToneSource(SR))
        assert strip.volume_db == 0.0 and not strip.mute and not strip.solo
