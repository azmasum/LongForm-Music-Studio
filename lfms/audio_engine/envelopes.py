"""ADSR envelope with block-wise processing and retrigger support."""
from __future__ import annotations

import numpy as np


class ADSR:
    def __init__(
        self,
        sample_rate: int,
        *,
        attack: float = 0.01,
        decay: float = 0.1,
        sustain: float = 0.7,
        release: float = 0.4,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.attack = max(0.001, float(attack))
        self.decay = max(0.001, float(decay))
        self.sustain = min(1.0, max(0.0, float(sustain)))
        self.release = max(0.001, float(release))
        self.gate = False
        self._stage = "IDLE"
        self._pos = 0
        self._start_level = 0.0

    @property
    def finished(self) -> bool:
        return self._stage == "IDLE"

    def _seg_samples(self, stage: str) -> int:
        seconds = {"A": self.attack, "D": self.decay, "R": self.release}[stage]
        return max(1, int(seconds * self.sample_rate))

    def _current_value(self) -> float:
        if self._stage in ("A", "D"):
            targets = {"A": 1.0, "D": self.sustain}
            frac = min(1.0, self._pos / self._seg_samples(self._stage))
            return self._start_level + (targets[self._stage] - self._start_level) * frac
        if self._stage == "S":
            return self.sustain
        if self._stage == "R":
            frac = min(1.0, self._pos / self._seg_samples("R"))
            return self._start_level * (1.0 - frac)
        return 0.0

    def gate_on(self) -> None:
        if self._stage not in ("IDLE", "R"):
            return
        start = min(self._current_value(), 0.999)
        self.gate = True
        self._stage = "A"
        self._pos = 0
        self._start_level = start

    def gate_off(self) -> None:
        if self._stage in ("IDLE", "R"):
            return
        self._start_level = self._current_value()
        self.gate = False
        self._stage = "R"
        self._pos = 0

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        out = np.zeros(n, dtype=np.float64)
        filled = 0
        while filled < n and self._stage != "IDLE":
            remaining = n - filled
            stage = self._stage
            if stage == "S":
                out[filled:] = self.sustain
                filled = n
                break
            seg = self._seg_samples(stage)
            left = seg - self._pos
            take = min(left, remaining)
            idx = np.arange(self._pos + 1, self._pos + take + 1, dtype=np.float64) / seg
            if stage == "A":
                vals = self._start_level + (1.0 - self._start_level) * idx
                new_stage, new_start = ("D", 1.0) if take == left else (stage, None)
            elif stage == "D":
                vals = self._start_level + (self.sustain - self._start_level) * idx
                new_stage, new_start = ("S", self.sustain) if take == left else (stage, None)
            else:
                vals = self._start_level * (1.0 - idx)
                new_stage, new_start = ("IDLE", 0.0) if take == left else (stage, None)
            out[filled : filled + take] = vals
            self._pos += take
            filled += take
            if new_stage != stage:
                self._stage = new_stage
                self._start_level = new_start if new_start is not None else 0.0
                self._pos = 0
        return out.astype(np.float32)
