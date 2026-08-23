"""Parametric mixing effects operating on (channels, n) float32 blocks.

Every effect is stateful/streaming-safe (call ``process`` sequentially),
exposes ``params()``/``set_param``/``reset()`` and validates its ranges so
presets stay inside sane bounds. Processing is deterministic.

Implementation notes:
- EQ3 chains three biquads from the audio engine.
- Compressor uses an O(n) scalar envelope/gain smoother.
- Delay/reverb recursions use fixed-lag window vectorization (numpy),
  so there are no per-sample Python loops in the hot path.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from lfms.audio_engine.dsp import db_to_gain
from lfms.audio_engine.filters import BiquadFilter
from lfms.core.errors import ValidationError


def _check_range(name: str, value: float, lo: float, hi: float) -> float:
    value = float(value)
    if not lo <= value <= hi:
        raise ValidationError(f"{name} must be within [{lo}, {hi}]")
    return value


class ParametricEffect:
    """Contract shared by all mixer effects."""

    PARAM_SPECS: dict[str, tuple[float, float]] = {}

    def params(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self.PARAM_SPECS}

    def set_param(self, name: str, value: float) -> None:
        if name not in self.PARAM_SPECS:
            raise ValidationError(f"unknown parameter {name!r}")
        lo, hi = self.PARAM_SPECS[name]
        setattr(self, name, _check_range(name, value, lo, hi))

    def _apply(self, name: str, value: float) -> float:
        lo, hi = self.PARAM_SPECS[name]
        return _check_range(name, value, lo, hi)


class EQ3Effect(ParametricEffect):
    """Low-shelf / peaking-mid / high-shelf three-band EQ."""

    PARAM_SPECS = {
        "low_hz": (10.0, 500.0),
        "low_gain_db": (-18.0, 18.0),
        "mid_hz": (150.0, 8000.0),
        "mid_gain_db": (-18.0, 18.0),
        "mid_q": (0.1, 8.0),
        "high_hz": (1500.0, 18000.0),
        "high_gain_db": (-18.0, 18.0),
    }

    def __init__(
        self,
        sample_rate: int,
        *,
        low_hz: float = 90.0,
        low_gain_db: float = 0.0,
        mid_hz: float = 1200.0,
        mid_gain_db: float = 0.0,
        mid_q: float = 0.9,
        high_hz: float = 7500.0,
        high_gain_db: float = 0.0,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.low_hz = self._apply("low_hz", low_hz)
        self.low_gain_db = self._apply("low_gain_db", low_gain_db)
        self.mid_hz = self._apply("mid_hz", mid_hz)
        self.mid_gain_db = self._apply("mid_gain_db", mid_gain_db)
        self.mid_q = self._apply("mid_q", mid_q)
        self.high_hz = self._apply("high_hz", high_hz)
        self.high_gain_db = self._apply("high_gain_db", high_gain_db)
        self._bands = (
            BiquadFilter(
                self.sample_rate,
                kind="lowshelf",
                cutoff=self.low_hz,
                q=self.mid_q,
                gain_db=self.low_gain_db,
                channels=2,
            ),
            BiquadFilter(
                self.sample_rate,
                kind="peaking",
                cutoff=self.mid_hz,
                q=self.mid_q,
                gain_db=self.mid_gain_db,
                channels=2,
            ),
            BiquadFilter(
                self.sample_rate,
                kind="highshelf",
                cutoff=self.high_hz,
                q=self.mid_q,
                gain_db=self.high_gain_db,
                channels=2,
            ),
        )

    def set_param(self, name: str, value: float) -> None:
        super().set_param(name, value)
        self._redesign()

    def _redesign(self) -> None:
        self._bands[0].set_params(cutoff=self.low_hz, gain_db=self.low_gain_db)
        self._bands[1].set_params(
            cutoff=self.mid_hz, q=self.mid_q, gain_db=self.mid_gain_db
        )
        self._bands[2].set_params(cutoff=self.high_hz, gain_db=self.high_gain_db)

    def process(self, block: np.ndarray) -> np.ndarray:
        out = block.astype(np.float32)
        for band in self._bands:
            out = band.process(out).astype(np.float32)
        return out

    def reset(self) -> None:
        for band in self._bands:
            band.reset()


class CompressorEffect(ParametricEffect):
    """Feed-forward compressor with linked mono envelope and smooth gain."""

    PARAM_SPECS = {
        "threshold_db": (-60.0, 0.0),
        "ratio": (1.0, 20.0),
        "attack_ms": (0.5, 200.0),
        "release_ms": (10.0, 2000.0),
        "makeup_db": (-12.0, 24.0),
    }

    def __init__(
        self,
        sample_rate: int,
        *,
        threshold_db: float = -26.0,
        ratio: float = 3.0,
        attack_ms: float = 12.0,
        release_ms: float = 150.0,
        makeup_db: float = 0.0,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.threshold_db = self._apply("threshold_db", threshold_db)
        self.ratio = self._apply("ratio", ratio)
        self.attack_ms = self._apply("attack_ms", attack_ms)
        self.release_ms = self._apply("release_ms", release_ms)
        self.makeup_db = self._apply("makeup_db", makeup_db)
        self._attack_coef = float(
            np.exp(-1.0 / (self.attack_ms * 0.001 * self.sample_rate))
        )
        self._release_coef = float(
            np.exp(-1.0 / (self.release_ms * 0.001 * self.sample_rate))
        )
        self._env = 0.0
        self._gain = 1.0

    def process(self, block: np.ndarray) -> np.ndarray:
        if block.size == 0:
            return block
        mono = np.max(np.abs(block.astype(np.float64)), axis=0)
        env = self._env
        coef_up = self._attack_coef
        coef_dn = self._release_coef
        env_arr = np.empty_like(mono)
        for i, target in enumerate(mono):
            coef = coef_up if target > env else coef_dn
            env = target + coef * (env - target)
            env_arr[i] = env
        self._env = float(env)

        level_db = 20.0 * np.log10(np.maximum(env_arr, 1e-9))
        excess = np.maximum(level_db - self.threshold_db, 0.0)
        target_gain = db_to_gain(-excess * (1.0 - 1.0 / self.ratio))

        gain = self._gain
        gain_arr = np.empty_like(target_gain)
        for i, tgt in enumerate(target_gain):
            coef = coef_up if tgt < gain else coef_dn
            gain = tgt + coef * (gain - tgt)
            gain_arr[i] = gain
        self._gain = float(gain)

        makeup = db_to_gain(self.makeup_db)
        return (block * (gain_arr * makeup).astype(np.float32)).astype(np.float32)

    def reset(self) -> None:
        self._env = 0.0
        self._gain = 1.0


class _FeedbackComb:
    """Pure feedback comb y[i] = x[i-D] + fb*y[i-D], window-vectorized."""

    def __init__(self, delay: int) -> None:
        self.d = max(1, int(delay))
        self.xh = np.zeros(self.d, dtype=np.float64)
        self.yh = np.zeros(self.d, dtype=np.float64)

    def process(self, x: np.ndarray, fb: float) -> np.ndarray:
        xv = x.astype(np.float64)
        m = xv.shape[0]
        ext = np.concatenate((self.xh, xv))
        y = np.empty(m, dtype=np.float64)
        first = min(self.d, m)
        y[:first] = ext[:first] + fb * self.yh[:first]
        written = first
        while written < m:
            lo, hi = written, min(written + self.d, m)
            y[lo:hi] = ext[lo:hi] + fb * y[lo - self.d : hi - self.d]
            written = hi
        if m >= self.d:
            self.xh = ext[-self.d :].copy()
            self.yh = y[-self.d :].copy()
        else:
            self.xh = np.concatenate((self.xh[m:], xv))
            self.yh = np.concatenate((self.yh[m:], y))
        return y

    def reset(self) -> None:
        self.xh.fill(0.0)
        self.yh.fill(0.0)


class DelayEffect(ParametricEffect):
    """Stereo feedback delay with dry/wet crossfade."""

    PARAM_SPECS = {
        "time_ms": (5.0, 2000.0),
        "feedback": (0.0, 0.95),
        "mix": (0.0, 1.0),
    }

    MAX_DELAY_SEC = 2.0

    def __init__(
        self,
        sample_rate: int,
        *,
        time_ms: float = 240.0,
        feedback: float = 0.35,
        mix: float = 0.25,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.time_ms = self._apply("time_ms", time_ms)
        self.feedback = self._apply("feedback", feedback)
        self.mix = self._apply("mix", mix)
        self._length = min(
            int(self.sample_rate * self.time_ms / 1000.0),
            int(self.sample_rate * self.MAX_DELAY_SEC),
        )
        self._dry_gain = 1.0 - self.mix * 0.5
        self._lines = [_FeedbackComb(self._length), _FeedbackComb(self._length)]

    def process(self, block: np.ndarray) -> np.ndarray:
        x = block.astype(np.float64)
        out = np.empty_like(x)
        for ch in range(min(x.shape[0], 2)):
            delayed = self._lines[ch].process(x[ch], self.feedback)
            out[ch] = x[ch] * self._dry_gain + delayed * self.mix
        return out.astype(np.float32)

    def reset(self) -> None:
        for line in self._lines:
            line.reset()


class ReverbEffect(ParametricEffect):
    """Schroeder reverb: 4 parallel feedback combs + 2 series allpasses.

    Damping softens the comb input with a one-pole lowpass and slightly
    reduces feedback (Freeverb-style), all vectorized exactly.
    """

    PARAM_SPECS = {
        "room_size": (0.05, 1.0),
        "damping": (0.0, 1.0),
        "wet": (0.0, 1.0),
    }

    _COMB_BASE = (1116, 1188, 1277, 1356)
    _ALLPASS_BASE = (556, 441)

    def __init__(
        self,
        sample_rate: int,
        *,
        room_size: float = 0.5,
        damping: float = 0.4,
        wet: float = 0.3,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.room_size = self._apply("room_size", room_size)
        self.damping = self._apply("damping", damping)
        self.wet = self._apply("wet", wet)
        scale = 0.4 + 0.9 * self.room_size
        self._fb_base = 0.72 + 0.18 * self.room_size
        comb_lengths = [max(8, int(n * scale)) for n in self._COMB_BASE]
        ap_lengths = [max(4, int(n * scale)) for n in self._ALLPASS_BASE]
        self._combs = [
            [_FeedbackComb(length), _FeedbackComb(length)] for length in comb_lengths
        ]
        self._aps = [
            [_ChunkAllpass(length), _ChunkAllpass(length)] for length in ap_lengths
        ]
        self._lp_zi = [np.zeros(1, dtype=np.float64), np.zeros(1, dtype=np.float64)]

    def process(self, block: np.ndarray) -> np.ndarray:
        x = block.astype(np.float64)
        channels = min(x.shape[0], 2)
        dmp = self.damping
        fb_eff = self._fb_base * (1.0 - 0.15 * dmp)
        a_lp = 0.85 * dmp
        verb = np.zeros_like(x)
        for ch in range(channels):
            sig = x[ch]
            if dmp > 0.0:
                soft, self._lp_zi[ch] = lfilter(
                    np.array([1.0 - a_lp]),
                    np.array([1.0, -a_lp]),
                    sig,
                    zi=self._lp_zi[ch],
                )
                sig = (1.0 - dmp) * x[ch] + dmp * soft
            for pair in self._combs:
                verb[ch] += pair[ch].process(sig, fb_eff)
            for ap_pair in self._aps:
                verb[ch] = ap_pair[ch].process(verb[ch])
        out = x * (1.0 - self.wet) + verb * self.wet * 0.6
        return out.astype(np.float32)

    def reset(self) -> None:
        for pair in self._combs:
            for comb in pair:
                comb.reset()
        for pair in self._aps:
            for ap in pair:
                ap.reset()
        for zi in self._lp_zi:
            zi.fill(0.0)


class _ChunkAllpass:
    """M-tap Schroeder allpass processed in lag-sized vector chunks.

    out[n] = -g*x[n] + x[n-M] + g*out[n-M]; chunk row k depends only on
    rows k-1, so each row is a single vectorized expression.
    """

    def __init__(self, length_m: int, g: float = 0.5) -> None:
        self.m = max(1, int(length_m))
        self.g = float(g)
        self.xb = np.zeros(self.m, dtype=np.float64)
        self.ob = np.zeros(self.m, dtype=np.float64)

    def process(self, x: np.ndarray) -> np.ndarray:
        n = x.shape[0]
        if n == 0:
            return x.astype(np.float64)[:0]
        pad = (-n) % self.m
        xp = np.concatenate((x.astype(np.float64), np.zeros(pad))).reshape(
            -1, self.m
        )
        op = -self.g * xp + self.xb + self.g * self.ob
        self.xb = xp[-1].copy()
        self.ob = op[-1].copy()
        return op.reshape(-1)[:n]

    def reset(self) -> None:
        self.xb.fill(0.0)
        self.ob.fill(0.0)


EFFECT_TYPES: dict[str, type[ParametricEffect]] = {
    "EQ3": EQ3Effect,
    "COMPRESSOR": CompressorEffect,
    "DELAY": DelayEffect,
    "REVERB": ReverbEffect,
}


def create_effect(effect_type: str, sample_rate: int, **overrides) -> ParametricEffect:
    try:
        cls = EFFECT_TYPES[effect_type.upper()]
    except KeyError as exc:
        raise ValidationError(f"unknown effect type {effect_type!r}") from exc
    return cls(sample_rate, **overrides)
