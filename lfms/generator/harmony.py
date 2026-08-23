"""Harmony generation: seeded progression selection over the plan's mode."""
from __future__ import annotations

import numpy as np

from lfms.core.seed import SeedSystem
from lfms.generator.events import ChordSegment
from lfms.generator.plan import MusicPlan
from lfms.generator.theory import chord_pitch_classes, progression_pool_for_mode


class HarmonyGenerator:
    def __init__(self, plan: MusicPlan, *, rng_index: int = 0) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(
            SeedSystem(plan.seed).derive("harmony", rng_index)
        )

    def generate(self) -> list[ChordSegment]:
        pool = progression_pool_for_mode(self.plan.key_mode)
        progression = list(pool[int(self._rng.integers(0, len(pool)))])
        bar = self.plan.bar_sec
        segments: list[ChordSegment] = []
        time = 0.0
        step = 0
        while time < self.plan.duration_sec - 1e-9:
            degree = progression[step % len(progression)]
            duration = min(bar, self.plan.duration_sec - time)
            seventh = bool(self._rng.random() < 0.30)
            pcs = chord_pitch_classes(
                self.plan.key_root_pc,
                self.plan.key_mode,
                degree - 1,
                seventh=seventh,
            )
            segments.append(
                ChordSegment(
                    start_sec=time,
                    duration_sec=duration,
                    degree=degree,
                    pitch_classes=tuple(pcs),
                    seventh=seventh,
                )
            )
            time += duration
            step += 1
        return segments
