"""Voiceover sidechain ducking: music ducks while the VO bus is active.

Envelope detection works on 256-sample hops (fast); gains are held per hop,
which at 48 kHz gives ~5 ms resolution — smooth enough for background-music
ducking without zipper noise. Fully deterministic.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.dsp import db_to_gain
from lfms.core.errors import ValidationError


def _check(name: str, value: float, lo: float, hi: float) -> float:
    value = float(value)
    if not lo <= value <= hi:
        raise ValidationError(f"{name} must be within [{lo}, {hi}]")
    return value


class DuckingSettings:
    """Sidechain response configuration."""

    HOP = 256

    def __init__(
        self,
        *,
        threshold_db: float = -38.0,
        floor_db: float = -12.0,
        attack_ms: float = 40.0,
        release_ms: float = 600.0,
        range_db: float = 18.0,
    ) -> None:
        self.threshold_db = _check("threshold_db", threshold_db, -80.0, 0.0)
        self.floor_db = _check("floor_db", floor_db, -48.0, 0.0)
        self.attack_ms = _check("attack_ms", attack_ms, 1.0, 500.0)
        self.release_ms = _check("release_ms", release_ms, 10.0, 5000.0)
        self.range_db = _check("range_db", range_db, 3.0, 60.0)

    def validate(self) -> None:  # kept for API symmetry
        return None


class SidechainDucker:
    """Streaming music-bus processor driven by the voiceover signal."""

    def __init__(self, sample_rate: int, settings: DuckingSettings | None = None) -> None:
        self.sample_rate = int(sample_rate)
        self.settings = settings or DuckingSettings()
        hop_sec = DuckingSettings.HOP / self.sample_rate
        self._attack_coef = float(
            np.exp(-hop_sec / max(1e-4, self.settings.attack_ms * 0.001))
        )
        self._release_coef = float(
            np.exp(-hop_sec / max(1e-3, self.settings.release_ms * 0.001))
        )
        self._env_db = -120.0

    def reset(self) -> None:
        self._env_db = -120.0

    @property
    def current_gain(self) -> float:
        return db_to_gain(self._reduction_for(self._env_db))

    def vo_level_db(self, vo_segment: np.ndarray) -> float:
        if vo_segment.size == 0:
            return -120.0
        mono = np.mean(vo_segment.astype(np.float64), axis=0)
        rms = float(np.sqrt(np.mean(mono * mono)))
        if rms <= 1e-9:
            return -120.0
        return 20.0 * float(np.log10(rms))

    def _reduction_for(self, env_db: float) -> float:
        s = self.settings
        excess = env_db - s.threshold_db
        amount = min(max(excess / s.range_db, 0.0), 1.0) * (-s.floor_db)
        return -amount

    def gain_curve_for(self, n: int, vo_block: np.ndarray) -> np.ndarray:
        """Per-sample ducking gain curve of shape (n,)."""
        hop = DuckingSettings.HOP
        n_hops = max(1, int(np.ceil(n / hop)))
        env = self._env_db
        gains = np.empty(n_hops, dtype=np.float32)
        for h in range(n_hops):
            start = h * hop
            stop = min(n, start + hop)
            level_db = (
                self.vo_level_db(vo_block[..., start:stop])
                if stop > start
                else -120.0
            )
            coef = self._attack_coef if level_db > env else self._release_coef
            env = level_db + coef * (env - level_db)
            gains[h] = np.float32(db_to_gain(self._reduction_for(env)))
        self._env_db = env
        positions = np.clip(np.arange(n) // hop, 0, n_hops - 1)
        return gains[positions]

    def process(self, music_block: np.ndarray, vo_block: np.ndarray) -> np.ndarray:
        n = music_block.shape[-1]
        curve = self.gain_curve_for(n, vo_block)
        shaped = curve[None, :] if music_block.ndim == 2 else curve
        return (music_block.astype(np.float32) * shaped).astype(np.float32)
