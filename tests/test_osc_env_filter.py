"""Tests for oscillators, envelopes, filters and LFOs."""
from __future__ import annotations

import numpy as np
import pytest

from lfms.audio_engine.envelopes import ADSR
from lfms.audio_engine.filters import BiquadFilter, DCBlocker, rbj_biquad
from lfms.audio_engine.lfo import LFO
from lfms.audio_engine.oscillators import Oscillator

SR = 48000


def _estimate_frequency(x: np.ndarray, sr: int) -> float:
    crossings = int(np.sum(np.diff(np.signbit(x)) != 0))
    seconds = x.size / sr
    return (crossings / 2.0) / seconds


class TestOscillator:
    def test_sine_frequency_and_bounds(self) -> None:
        osc = Oscillator(SR, frequency=440.0)
        data = osc.process(SR)[0]
        assert not np.any(np.isnan(data))
        assert float(np.max(np.abs(data))) <= 1.001
        assert _estimate_frequency(data.astype(float), SR) == pytest.approx(440.0, rel=0.01)

    def test_waves_bounded(self) -> None:
        for wave in ("SINE", "TRIANGLE", "SAW", "SQUARE"):
            osc = Oscillator(SR, wave=wave, frequency=220.0)
            data = osc.process(4096)[0]
            assert float(np.max(np.abs(data))) <= 1.0001

    def test_unison_detune_changes_signal(self) -> None:
        plain = Oscillator(SR, frequency=110.0, unison_voices=3).process(SR // 2)
        detuned = Oscillator(SR, frequency=110.0, unison_voices=3, detune_cents=25.0).process(SR // 2)
        assert not np.allclose(plain, detuned)

    def test_fm_changes_signal(self) -> None:
        plain = Oscillator(SR, frequency=110.0).process(SR // 2)
        fm = Oscillator(SR, frequency=110.0, fm_ratio=2.0, fm_index=3.0).process(SR // 2)
        assert not np.allclose(plain, fm)

    def test_am_tremolo_varies_amplitude(self) -> None:
        osc = Oscillator(SR, frequency=220.0, am_rate=2.0, am_depth=1.0)
        data = osc.process(SR * 2)[0].astype(float)
        envelope = np.abs(data).reshape(-1, 4800).max(axis=1)
        assert envelope.max() - envelope.min() > 0.3

    def test_sub_oscillator_adds_content(self) -> None:
        without_sub = Oscillator(SR, frequency=110.0).process(SR)
        with_sub = Oscillator(SR, frequency=110.0, sub_level=0.8).process(SR)
        assert not np.allclose(without_sub, with_sub)

    def test_phase_continues_across_blocks(self) -> None:
        whole = Oscillator(SR, frequency=100.0).process(SR)[0]
        osc = Oscillator(SR, frequency=100.0)
        chunked_parts = [osc.process(1000)[0] for _ in range(SR // 1000)]
        assert np.allclose(whole, np.concatenate(chunked_parts), atol=1e-5)


    def test_invalid_wave_rejected(self) -> None:
        with pytest.raises(ValueError):
            Oscillator(SR, wave="CUBIC")


class TestADSR:
    def _run(self, env: ADSR, seconds: float, block: int = 1024) -> np.ndarray:
        chunks = []
        remaining = int(seconds * SR)
        while remaining > 0:
            n = min(block, remaining)
            chunks.append(env.process(n))
            remaining -= n
        return np.concatenate(chunks).astype(float)

    def test_sustain_reached(self) -> None:
        env = ADSR(SR, attack=0.01, decay=0.05, sustain=0.5, release=0.1)
        env.gate_on()
        out = self._run(env, 0.5)
        assert out.min() >= -0.001 and out.max() <= 1.001
        assert abs(out[-100:].mean() - 0.5) < 0.02

    def test_release_falls_to_zero(self) -> None:
        env = ADSR(SR, attack=0.005, decay=0.02, sustain=0.8, release=0.05)
        env.gate_on()
        self._run(env, 0.2)
        env.gate_off()
        tail = self._run(env, 0.3)
        assert abs(tail[-100:].mean()) < 0.001

    def test_retrigger_from_release_is_softer(self) -> None:
        env = ADSR(SR, attack=0.05, decay=0.05, sustain=0.9, release=0.2)
        env.gate_on()
        self._run(env, 0.12)
        env.gate_off()
        partial = self._run(env, 0.04)
        level_before = float(partial[-1])
        assert 0.0 < level_before < 0.9
        env.gate_on()
        first_after = float(env.process(64)[0])
        assert first_after <= level_before + 0.01


class TestFilters:
    def _noise(self, seconds: float) -> np.ndarray:
        rng = np.random.default_rng(7)
        return rng.standard_normal(int(seconds * SR)) * 0.5

    def test_lowpass_attenuates_highs(self) -> None:
        from lfms.audio_engine.dsp import band_energy

        x = self._noise(0.5)
        f = BiquadFilter(SR, kind="lowpass", cutoff=800.0)
        y = f.process(x)
        in_high = band_energy(x, SR, 4000, 20000)
        out_high = band_energy(y.astype(float), SR, 4000, 20000)
        assert out_high < 0.05 * in_high

    def test_highpass_attenuates_lows(self) -> None:
        from lfms.audio_engine.dsp import band_energy

        x = self._noise(0.5)
        f = BiquadFilter(SR, kind="highpass", cutoff=4000.0)
        y = f.process(x)
        in_low = band_energy(x, SR, 20, 500)
        out_low = band_energy(y.astype(float), SR, 20, 500)
        assert out_low < 0.05 * in_low

    def test_state_continues_across_blocks(self) -> None:
        x = self._noise(0.4)
        f_whole = BiquadFilter(SR, kind="lowpass", cutoff=800.0)
        whole = f_whole.process(x)
        f_chunks = BiquadFilter(SR, kind="lowpass", cutoff=800.0)
        parts = [f_chunks.process(seg) for seg in np.array_split(x, 16)]
        assert np.allclose(whole, np.concatenate(parts), atol=1e-6)

    def test_rbj_biquad_stable(self) -> None:
        for kind in ("lowpass", "highpass", "bandpass", "notch", "peaking", "lowshelf", "highshelf"):
            b, a = rbj_biquad(kind, SR, 1000.0)
            poles = np.roots(a)
            assert np.all(np.abs(poles) < 1.0)

    def test_dc_blocker_removes_offset(self) -> None:
        blocker = DCBlocker(SR)
        out = blocker.process(np.ones(SR))
        assert abs(float(out[-1000:].mean())) < 1e-3


class TestLFO:
    def test_sine_range_and_period(self) -> None:
        lfo = LFO(SR, shape="SINE", rate_hz=1.0)
        vals = lfo.process(SR * 2).astype(float)
        assert vals.min() >= -1e-6 and vals.max() <= 1 + 1e-6
        crossings = int(np.sum(np.diff(vals >= 0.5).astype(bool)))
        assert crossings == pytest.approx(4, abs=1)

    def test_random_deterministic_and_bounded(self) -> None:
        a = LFO(SR, shape="RANDOM", rate_hz=4.0, seed=11).process(24000)
        b = LFO(SR, shape="RANDOM", rate_hz=4.0, seed=11).process(24000)
        assert np.array_equal(a, b)
        assert a.min() >= 0.0 and a.max() < 1.0

    def test_unknown_shape_raises(self) -> None:
        with pytest.raises(ValueError):
            LFO(SR, shape="WAVE")
