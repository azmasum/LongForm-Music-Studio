"""Low-level DSP helpers shared across the audio engine."""
from __future__ import annotations

import math

import numpy as np

_EPS = 1e-12


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def gain_to_db(gain: float) -> float:
    if gain <= _EPS:
        return -math.inf
    return 20.0 * math.log10(gain)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def equal_power_pan(pan: float) -> tuple[float, float]:
    """pan in [-1, 1]; returns (left_gain, right_gain), unity at center."""
    p = clamp(pan, -1.0, 1.0)
    theta = (p + 1.0) * (math.pi / 4.0)
    return math.cos(theta), math.sin(theta)


def soft_clip(x: np.ndarray, threshold: float = 0.95) -> np.ndarray:
    """Continuous soft limiter above `threshold`; asymptotic ceiling 1.0."""
    t = clamp(threshold, 0.1, 0.999)
    ax = np.abs(x)
    over = ax > t
    if not np.any(over):
        return x
    out = x.astype(np.float64, copy=True)
    mag = ax[over]
    shaped = t + (1.0 - t) * np.tanh((mag - t) / (1.0 - t))
    out[over] = np.sign(out[over]) * shaped
    return out


class Limiter:
    """Stateful streaming brickwall-ish limiter for offline rendering.

    Tracks a smoothed gain across blocks (fast attack, slow release) so the
    ceiling is respected *continuously* — unlike block-wise soft_clip, which
    produces discontinuities at block boundaries (audible as clicks/buzz).
    A final soft_clip pass catches any residual intra-block transient.
    """

    def __init__(self, sample_rate: int, *, ceiling: float = 0.97,
                 attack_ms: float = 2.0, release_ms: float = 90.0) -> None:
        self.ceiling = clamp(float(ceiling), 0.5, 0.999)
        self._attack_coef = math.exp(-1000.0 / (max(0.01, attack_ms) * sample_rate))
        self._release_coef = math.exp(-1000.0 / (max(1.0, release_ms) * sample_rate))
        self._gain = 1.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x
        block_peak = float(np.max(np.abs(x)))
        needed = self.ceiling / max(block_peak, self.ceiling)
        target = min(1.0, needed)
        coef = self._attack_coef if target < self._gain else self._release_coef
        self._gain = target + (self._gain - target) * coef
        out = x * self._gain
        # continuous asymptotic safety net; maps everything above the
        # ceiling into [ceiling, ceiling] so the output NEVER exceeds it
        ax = np.abs(out)
        if float(np.max(ax)) > self.ceiling:
            t = self.ceiling
            span = max(1e-6, 1.0 - t)
            over = ax > t
            mag = ax[over]
            shaped = t + (self.ceiling - t) * np.tanh((mag - t) / span)
            out[over] = np.sign(out[over]) * np.minimum(shaped, self.ceiling)
        return out


def peak(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.max(np.abs(x)))


def rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def band_energy(x: np.ndarray, sample_rate: int, f_lo: float, f_hi: float) -> float:
    """Energy of x within [f_lo, f_hi] Hz via rfft (x is mono)."""
    spectrum = np.fft.rfft(x.astype(np.float64))
    freqs = np.fft.rfftfreq(x.shape[-1], d=1.0 / sample_rate)
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not np.any(mask):
        return 0.0
    power = np.square(np.abs(spectrum[mask]))
    return float(np.sum(power))
