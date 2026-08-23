"""Tests for procedural sources: noise colors, ambiences and drones."""
from __future__ import annotations

import numpy as np
import pytest

from lfms.audio_engine.dsp import peak, rms
from lfms.audio_engine.sources import AmbienceSource, DroneSource, NoiseSource, ToneSource

SR = 48000


def _render(source, seconds: float) -> np.ndarray:
    total = int(seconds * SR)
    parts = []
    done = 0
    while done < total:
        n = min(4096, total - done)
        parts.append(source.process(n)[0])
        done += n
    return np.concatenate(parts)


class TestNoiseSource:
    def test_white_bounds(self) -> None:
        data = _render(NoiseSource(SR, color="WHITE", seed=1), 0.2)
        assert data.shape == (0.2 * SR,)
        assert float(np.max(np.abs(data))) < 1.5

    @pytest.mark.parametrize("color", ["PINK", "BROWN"])
    def test_colored_noise_hits_target_rms(self, color: str) -> None:
        src = NoiseSource(SR, color=color, seed=5, target_rms=0.12)
        data = _render(src, 0.5).astype(float)
        assert rms(data) == pytest.approx(0.12, rel=0.9)

    def test_pink_has_more_low_energy_than_white(self) -> None:
        from lfms.audio_engine.dsp import band_energy

        seconds = 0.5
        white = _render(NoiseSource(SR, color="WHITE", seed=3), seconds).astype(float)
        pink = _render(NoiseSource(SR, color="PINK", seed=3), seconds).astype(float)
        ratio = lambda x: band_energy(x, SR, 100, 400) / max(band_energy(x, SR, 4000, 16000), 1e-12)  # noqa: E731
        assert ratio(pink) > ratio(white)

    def test_deterministic(self) -> None:
        a = _render(NoiseSource(SR, color="PINK", seed=8), 0.1)
        b = _render(NoiseSource(SR, color="PINK", seed=8), 0.1)
        c = _render(NoiseSource(SR, color="PINK", seed=9), 0.1)
        assert np.array_equal(a, b)
        assert not np.array_equal(a, c)

    def test_invalid_color(self) -> None:
        with pytest.raises(ValueError):
            NoiseSource(SR, color="AQUA")


class TestAmbienceSource:
    @pytest.mark.parametrize(
        "kind",
        ["RAIN", "WIND", "OCEAN", "ROOM_TONE", "NIGHT", "CITY"],
    )
    def test_kinds_produce_sane_audio(self, kind: str) -> None:
        src = AmbienceSource(SR, kind=kind, seed=21)
        data = _render(src, 0.4).astype(float)
        assert np.all(np.isfinite(data))
        level = rms(data)
        assert 1e-5 < level < 0.6
        assert peak(data) < 2.0

    def test_rain_deterministic_by_seed(self) -> None:
        a = _render(AmbienceSource(SR, kind="RAIN", seed=33), 0.2)
        b = _render(AmbienceSource(SR, kind="RAIN", seed=33), 0.2)
        assert np.array_equal(a, b)

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError):
            AmbienceSource(SR, kind="VOLCANO")


class TestDroneAndTone:
    def test_drone_sane_output(self) -> None:
        drone = DroneSource(SR, frequency=110.0, seed=17)
        data = _render(drone, 0.6).astype(float)
        assert np.all(np.isfinite(data))
        assert rms(data) > 1e-3
        assert peak(data) < 1.2

    def test_tone_frequency_setter(self) -> None:
        tone = ToneSource(SR, frequency=220.0)
        tone.set_frequency(440.0)
        data = _render(tone, 1.0).astype(float)
        crossings = int(np.sum(np.diff(np.signbit(data)) != 0)) / 2.0
        assert crossings == pytest.approx(440.0, rel=0.01)
