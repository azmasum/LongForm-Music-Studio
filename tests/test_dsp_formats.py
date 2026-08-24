"""Tests for DSP helpers and export format mapping."""
from __future__ import annotations

import math

import numpy as np
import pytest

from lfms.audio_engine.dsp import (
    band_energy,
    clamp,
    db_to_gain,
    equal_power_pan,
    gain_to_db,
    peak,
    rms,
    soft_clip,
)
from lfms.audio_engine.formats import default_extension, resolve_sf_params


class TestGainMath:
    def test_db_gain_roundtrip(self) -> None:
        for db in (0.0, -6.0, -20.0, -60.0, 3.0):
            assert gain_to_db(db_to_gain(db)) == pytest.approx(db, abs=1e-9)

    def test_known_conversions(self) -> None:
        assert db_to_gain(0.0) == 1.0
        assert db_to_gain(-20.0) == pytest.approx(0.1, rel=1e-6)
        assert gain_to_db(0.0) == -math.inf

    def test_clamp(self) -> None:
        assert clamp(5, 0, 1) == 1
        assert clamp(-5, 0, 1) == 0
        assert clamp(0.5, 0, 1) == 0.5

    def test_peak_rms(self) -> None:
        x = np.array([0.5, -0.5, 0.5, -0.5])
        assert peak(x) == pytest.approx(0.5)
        assert rms(x) == pytest.approx(0.5)


class TestPanLaw:
    def test_center_is_unity(self) -> None:
        l_gain, r_gain = equal_power_pan(0.0)
        assert l_gain == pytest.approx(math.sqrt(2) / 2)
        assert r_gain == pytest.approx(math.sqrt(2) / 2)

    def test_hard_sides(self) -> None:
        assert equal_power_pan(-1.0) == (pytest.approx(1.0), pytest.approx(0.0))
        assert equal_power_pan(1.0) == (pytest.approx(0.0), pytest.approx(1.0))

    def test_constant_power(self) -> None:
        for pan in np.linspace(-1, 1, 9):
            l_gain, r_gain = equal_power_pan(float(pan))
            assert l_gain**2 + r_gain**2 == pytest.approx(1.0)


class TestSoftClip:
    def test_identity_below_threshold(self) -> None:
        x = np.array([0.0, 0.5, -0.9])
        assert np.allclose(soft_clip(x, 0.95), x)

    def test_bounded_above_threshold(self) -> None:
        x = np.linspace(-10, 10, 1001)
        y = soft_clip(x)
        assert np.max(np.abs(y)) <= 1.0 + 1e-12

    def test_continuous_at_threshold(self) -> None:
        t = 0.95
        inside = np.array([t - 1e-9])
        outside = np.array([t + 1e-9])
        assert abs(float(soft_clip(inside)[0]) - float(soft_clip(outside)[0])) < 1e-6


class TestBandEnergy:
    def test_energy_concentrated_at_tone(self) -> None:
        sr = 48000
        t = np.arange(sr) / sr
        x = np.sin(2 * np.pi * 100 * t)
        low = band_energy(x, sr, 80, 120)
        high = band_energy(x, sr, 5000, 15000)
        assert low > 1000 * max(high, 1e-12)


class TestFormatResolution:
    def test_wav_depths(self) -> None:
        assert resolve_sf_params("WAV", 16) == ("WAV", "PCM_16")
        assert resolve_sf_params("WAV", 24) == ("WAV", "PCM_24")
        assert resolve_sf_params("WAV", 32) == ("WAV", "FLOAT")
        assert resolve_sf_params("WAV") == ("WAV", "PCM_24")

    def test_flac_and_ogg(self) -> None:
        assert resolve_sf_params("FLAC", 16) == ("FLAC", "PCM_16")
        assert resolve_sf_params("FLAC", 24) == ("FLAC", "PCM_24")
        assert resolve_sf_params("FLAC", 32) == ("FLAC", "PCM_24")
        assert resolve_sf_params("OGG") == ("OGG", "VORBIS")

    def test_mp3_resolves_to_libsndfile_encoder(self) -> None:
        # libsndfile >= 1.1 can encode MP3 directly; no FFmpeg fallback needed.
        assert resolve_sf_params("MP3", 320) == ("MP3", "MPEG_LAYER_III")
        assert resolve_sf_params("MP3") == ("MP3", "MPEG_LAYER_III")

    def test_default_extension(self) -> None:
        assert default_extension("WAV") == "wav"
