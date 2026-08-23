"""Low-frequency control oscillator producing values in [0, 1]."""
from __future__ import annotations

import numpy as np

_SHAPES = ("SINE", "TRIANGLE", "SAW", "RANDOM")


class LFO:
    """Deterministic control-rate LFO; RANDOM is a seeded sample-and-hold."""

    def __init__(
        self,
        sample_rate: int,
        *,
        shape: str = "SINE",
        rate_hz: float = 0.5,
        phase: float = 0.0,
        seed: int | None = None,
    ) -> None:
        shape = shape.upper()
        if shape not in _SHAPES:
            raise ValueError(f"unknown LFO shape {shape!r}")
        self.sample_rate = int(sample_rate)
        self.shape = shape
        self.rate_hz = max(0.001, float(rate_hz))
        self._abs_phase = float(phase) % 1.0
        self._last_hold = 0.0
        self._rng = np.random.default_rng(seed)

    def _advance(self, n: int) -> np.ndarray:
        step = self.rate_hz / self.sample_rate
        pos = self._abs_phase + step * np.arange(n, dtype=np.float64)
        self._abs_phase = float(pos[-1] + step)
        return pos

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        pos = self._advance(n)
        if self.shape == "SINE":
            vals = 0.5 + 0.5 * np.sin(2.0 * np.pi * (pos % 1.0))
        elif self.shape == "TRIANGLE":
            tri = 4.0 * np.abs((pos % 1.0) - 0.5) - 1.0
            vals = 0.5 - 0.5 * tri
        elif self.shape == "SAW":
            vals = pos % 1.0
        else:
            k = np.floor(pos).astype(np.int64)
            k_start = int(k[0])
            k_end = int(k[-1])
            n_draws = max(0, k_end - k_start)
            draws = self._rng.random(n_draws) if n_draws > 0 else np.zeros(0)
            rel = k - k_start
            idx = np.maximum(rel - 1, 0)
            vals = np.where(
                rel >= 1,
                draws[np.minimum(idx, max(n_draws - 1, 0))] if n_draws > 0 else self._last_hold,
                self._last_hold,
            )
            self._last_hold = float(vals[-1]) if vals.size else self._last_hold
        return vals.astype(np.float32)
