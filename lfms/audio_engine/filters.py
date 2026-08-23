"""Streaming biquad filters (RBJ cookbook) built on scipy.signal.lfilter."""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

_FILTER_KINDS = (
    "lowpass",
    "highpass",
    "bandpass",
    "notch",
    "peaking",
    "lowshelf",
    "highshelf",
)


def rbj_biquad(kind: str, sample_rate: int, cutoff: float, q: float = 0.707, gain_db: float = 0.0):
    """Return normalized (b, a) coefficients for the requested design."""
    kind = kind.lower()
    if kind not in _FILTER_KINDS:
        raise ValueError(f"unknown filter kind {kind!r}")
    fs = float(sample_rate)
    f0 = min(max(float(cutoff), 1.0), fs * 0.49)
    q = max(0.05, float(q))
    w0 = 2.0 * math.pi * f0 / fs
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * q)

    if kind == "lowpass":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = b0
        a0, a1, a2 = 1.0 + alpha, -2.0 * cos_w0, 1.0 - alpha
    elif kind == "highpass":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = b0
        a0, a1, a2 = 1.0 + alpha, -2.0 * cos_w0, 1.0 - alpha
    elif kind == "bandpass":
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
        a0, a1, a2 = 1.0 + alpha, -2.0 * cos_w0, 1.0 - alpha
    elif kind == "notch":
        b0, b1, b2 = 1.0, -2.0 * cos_w0, 1.0
        a0, a1, a2 = 1.0 + alpha, -2.0 * cos_w0, 1.0 - alpha
    else:
        A = 10.0 ** (float(gain_db) / 40.0)
        if kind == "peaking":
            b0 = 1.0 + alpha * A
            b1 = -2.0 * cos_w0
            b2 = 1.0 - alpha * A
            a0 = 1.0 + alpha / A
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha / A
        elif kind == "lowshelf":
            sqrt_a = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + sqrt_a)
            b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - sqrt_a)
            a0 = (A + 1.0) + (A - 1.0) * cos_w0 + sqrt_a
            a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
            a2 = (A + 1.0) + (A - 1.0) * cos_w0 - sqrt_a
        else:
            sqrt_a = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + sqrt_a)
            b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - sqrt_a)
            a0 = (A + 1.0) - (A - 1.0) * cos_w0 + sqrt_a
            a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
            a2 = (A + 1.0) - (A - 1.0) * cos_w0 - sqrt_a

    b = np.array([b0, b1, b2], dtype=np.float64) / a0
    a = np.array([a0, a1, a2], dtype=np.float64) / a0
    return b, a


class BiquadFilter:
    """Stateful per-channel biquad; parameters may change between blocks."""

    def __init__(
        self,
        sample_rate: int,
        *,
        kind: str = "lowpass",
        cutoff: float,
        q: float = 0.707,
        gain_db: float = 0.0,
        channels: int = 1,
    ) -> None:
        if channels < 1:
            raise ValueError("channels must be >= 1")
        self.sample_rate = int(sample_rate)
        self.kind = kind.lower()
        self.cutoff = float(cutoff)
        self.q = float(q)
        self.gain_db = float(gain_db)
        self.channels = channels
        self._b, self._a = rbj_biquad(self.kind, sample_rate, self.cutoff, self.q, self.gain_db)
        self._zi = [np.zeros(2) for _ in range(channels)]

    def set_params(
        self,
        *,
        cutoff: float | None = None,
        q: float | None = None,
        gain_db: float | None = None,
        reset_state: bool = False,
    ) -> None:
        if cutoff is not None:
            self.cutoff = float(cutoff)
        if q is not None:
            self.q = float(q)
        if gain_db is not None:
            self.gain_db = float(gain_db)
        self._b, self._a = rbj_biquad(self.kind, self.sample_rate, self.cutoff, self.q, self.gain_db)
        if reset_state:
            self.reset()

    def reset(self) -> None:
        self._zi = [np.zeros(2) for _ in range(self.channels)]

    def process(self, block: np.ndarray) -> np.ndarray:
        """block shape (channels, n) or (n,) for mono; returns same layout."""
        single = block.ndim == 1
        data = block[None, :] if single else block
        if data.shape[0] != self.channels:
            raise ValueError(f"expected {self.channels} channels, got {data.shape[0]}")
        out = np.empty_like(data, dtype=np.float64)
        for ch in range(self.channels):
            y, self._zi[ch] = lfilter(self._b, self._a, data[ch].astype(np.float64), zi=self._zi[ch])
            out[ch] = y
        return out[0] if single else out


class DCBlocker(BiquadFilter):
    def __init__(self, sample_rate: int, *, channels: int = 1, cutoff: float = 5.0) -> None:
        super().__init__(
            sample_rate,
            kind="highpass",
            cutoff=cutoff,
            q=0.5,
            channels=channels,
        )
