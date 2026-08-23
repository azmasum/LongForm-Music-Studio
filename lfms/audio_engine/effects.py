"""Effect nodes operating on (channels, n) float blocks."""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.dsp import db_to_gain, soft_clip
from lfms.audio_engine.filters import DCBlocker


class Effect:
    """Base class for in-place-capable stereo effects."""

    def process(self, block: np.ndarray) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class GainEffect(Effect):
    def __init__(self, gain_db: float = 0.0) -> None:
        self.gain_db = float(gain_db)

    def process(self, block: np.ndarray) -> np.ndarray:
        return block * np.float32(db_to_gain(self.gain_db))


class SoftLimiter(Effect):
    def __init__(self, threshold: float = 0.95) -> None:
        self.threshold = float(threshold)

    def process(self, block: np.ndarray) -> np.ndarray:
        peak = float(np.max(np.abs(block))) if block.size else 0.0
        if peak <= self.threshold:
            return block
        return soft_clip(block.astype(np.float64), self.threshold).astype(np.float32)


class DCBlockEffect(Effect):
    def __init__(self, sample_rate: int, channels: int = 2, cutoff: float = 5.0) -> None:
        self._blocker = DCBlocker(sample_rate, channels=channels, cutoff=cutoff)

    def process(self, block: np.ndarray) -> np.ndarray:
        return self._blocker.process(block).astype(np.float32)


class StereoWidth(Effect):
    """width 0 = mono, 1 = original, up to ~2 = widened."""

    def __init__(self, width: float = 1.0) -> None:
        self.width = max(0.0, float(width))

    def process(self, block: np.ndarray) -> np.ndarray:
        if block.shape[0] != 2 or self.width == 1.0:
            return block
        mid = 0.5 * (block[0] + block[1])
        side = 0.5 * (block[0] - block[1])
        side = side * self.width
        return np.stack([mid + side, mid - side]).astype(np.float32)
