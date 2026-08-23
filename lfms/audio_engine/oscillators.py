"""Vectorized block-based oscillators with unison, FM, AM and sub voices."""
from __future__ import annotations

import numpy as np


def _sine(ph: np.ndarray) -> np.ndarray:
    return np.sin(2.0 * np.pi * ph)


def _saw(ph: np.ndarray) -> np.ndarray:
    return 2.0 * ph - 1.0


def _square(ph: np.ndarray) -> np.ndarray:
    return np.where(ph < 0.5, 1.0, -1.0)


def _triangle(ph: np.ndarray) -> np.ndarray:
    return 4.0 * np.abs(ph - 0.5) - 1.0


_WAVEFUNCS = {
    "SINE": _sine,
    "TRIANGLE": _triangle,
    "SAW": _saw,
    "SQUARE": _square,
}


class Oscillator:
    """PolyBLEP-free band-limited-enough for background use; stateful phase.

    All randomness is avoided here (phase offsets are deterministic), so an
    Oscillator with identical parameters always produces identical output.
    """

    __slots__ = (
        "sample_rate",
        "wave",
        "base_frequency",
        "unison_voices",
        "detune_cents",
        "sub_level",
        "sub_wave",
        "fm_ratio",
        "fm_index",
        "am_rate",
        "am_depth",
        "_ratios",
        "_phases",
        "_sub_phase",
        "_am_phase",
    )

    def __init__(
        self,
        sample_rate: int,
        *,
        wave: str = "SINE",
        frequency: float = 220.0,
        unison_voices: int = 1,
        detune_cents: float = 0.0,
        sub_level: float = 0.0,
        sub_wave: str = "SINE",
        fm_ratio: float = 0.0,
        fm_index: float = 0.0,
        am_rate: float = 0.0,
        am_depth: float = 0.0,
    ) -> None:
        if unison_voices < 1:
            raise ValueError("unison_voices must be >= 1")
        self.sample_rate = int(sample_rate)
        self.wave = wave.upper()
        if self.wave not in _WAVEFUNCS:
            raise ValueError(f"unknown wave {wave!r}")
        self.sub_wave = sub_wave.upper()
        if self.sub_wave not in _WAVEFUNCS:
            raise ValueError(f"unknown sub_wave {sub_wave!r}")
        self.base_frequency = float(frequency)
        self.unison_voices = int(unison_voices)
        self.detune_cents = float(detune_cents)
        self.sub_level = float(sub_level)
        self.fm_ratio = float(fm_ratio)
        self.fm_index = float(fm_index)
        self.am_rate = float(am_rate)
        self.am_depth = float(am_depth)
        voices = np.arange(self.unison_voices, dtype=np.float64)
        if self.unison_voices > 1:
            spread = np.linspace(-1.0, 1.0, self.unison_voices)
        else:
            spread = np.zeros(1)
        self._ratios = 2.0 ** (spread * self.detune_cents / 1200.0)
        self._phases = (voices * 0.618033988749895) % 1.0
        self._sub_phase = 0.25
        self._am_phase = 0.0

    @property
    def frequency(self) -> float:
        return self.base_frequency

    def set_frequency(self, hz: float) -> None:
        self.base_frequency = float(hz)

    def _advance(self, n: int) -> np.ndarray:
        inc = self._ratios * (self.base_frequency / self.sample_rate)
        step = np.arange(1, n + 1, dtype=np.float64)
        new = self._phases[:, None] + inc[:, None] * step[None, :]
        new %= 1.0
        self._phases = new[:, -1].copy()
        return new

    def _advance_scalar(self, phase: float, cycles_per_sample: float, n: int) -> tuple[np.ndarray, float]:
        step = np.arange(1, n + 1, dtype=np.float64)
        new = phase + cycles_per_sample * step
        wrapped = new % 1.0
        return wrapped, float(new[-1] % 1.0)

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        phases = self._advance(n)
        fun = _WAVEFUNCS[self.wave]
        if self.fm_index > 0.0 and self.fm_ratio > 0.0:
            pm = min(self.fm_index, 12.0) * np.sin(2.0 * np.pi * self.fm_ratio * phases[0])
            phases = phases + pm[None, :]
        out = np.zeros(n, dtype=np.float64)
        for v in range(self.unison_voices):
            out += fun(phases[v] % 1.0)
        out /= self.unison_voices

        if self.sub_level > 0.0:
            sub_phases, self._sub_phase = self._advance_scalar(
                self._sub_phase, self.base_frequency / self.sample_rate / 2.0, n
            )
            out += self.sub_level * _WAVEFUNCS[self.sub_wave](sub_phases)

        if self.am_depth > 0.0 and self.am_rate > 0.0:
            am_phases, self._am_phase = self._advance_scalar(
                self._am_phase, self.am_rate / self.sample_rate, n
            )
            tremolo = 1.0 - 0.5 * self.am_depth * (1.0 - np.cos(2.0 * np.pi * am_phases))
            out *= tremolo

        return out.astype(np.float32)[None, :]
