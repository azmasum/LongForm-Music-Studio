"""Energy curves: normalized intensity over track time (0..1 -> 0..1)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lfms.core.enums import EnergyCurvePreset
from lfms.core.errors import ValidationError
from lfms.core.seed import SeedSystem

_PRESET_POINTS: dict[str, tuple[tuple[float, float], ...]] = {
    "FLAT": ((0.0, 0.62), (1.0, 0.62)),
    "SLOW_BUILD": ((0.0, 0.22), (0.65, 0.5), (1.0, 0.85)),
    "CINEMATIC_BUILD": ((0.0, 0.18), (0.45, 0.42), (0.8, 0.9), (1.0, 0.72)),
    "EMOTIONAL_WAVE": (
        (0.0, 0.32), (0.25, 0.72), (0.5, 0.38),
        (0.75, 0.78), (1.0, 0.42),
    ),
    "DOCUMENTARY": ((0.0, 0.4), (0.15, 0.6), (0.85, 0.66), (1.0, 0.45)),
    "SUSPENSE": ((0.0, 0.48), (0.55, 0.52), (0.85, 0.82), (1.0, 0.58)),
    "RELAXATION": ((0.0, 0.52), (0.3, 0.3), (0.8, 0.28), (1.0, 0.34)),
    "INTRO_PEAK_OUTRO": ((0.0, 0.28), (0.12, 0.78), (0.88, 0.7), (1.0, 0.28)),
}


@dataclass(frozen=True)
class ControlPoint:
    t: float
    value: float


class EnergyCurve:
    """Piecewise-linear energy envelope over normalized time."""

    def __init__(
        self,
        points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
        *,
        name: str = "CUSTOM",
    ) -> None:
        if not points:
            raise ValidationError("energy curve needs at least one point")
        cleaned = sorted(((float(t), float(v)) for t, v in points), key=lambda p: p[0])
        for t, v in cleaned:
            if not -1e-9 <= t <= 1 + 1e-9:
                raise ValidationError(f"energy point time {t} outside [0, 1]")
            if not 0.0 <= v <= 1.0:
                raise ValidationError(f"energy value {v} outside [0, 1]")
        deduped: dict[float, float] = {}
        for t, v in cleaned:
            key = round(min(max(t, 0.0), 1.0), 9)
            deduped[key] = min(max(v, 0.0), 1.0)
        self.name = name
        self.points = tuple(ControlPoint(t, v) for t, v in sorted(deduped.items()))
        self._ts = np.array([p.t for p in self.points], dtype=np.float64)
        self._vs = np.array([p.value for p in self.points], dtype=np.float64)

    @classmethod
    def from_preset(
        cls,
        preset: str,
        *,
        seed: int = 0,
        user_points: tuple[tuple[float, float], ...] | None = None,
    ) -> EnergyCurve:
        if user_points:
            return cls(tuple(user_points), name="USER")
        if preset == EnergyCurvePreset.RANDOM_ORGANIC.value:
            return cls(_organic_points(seed), name=preset)
        if preset not in _PRESET_POINTS:
            raise ValidationError(f"unknown energy curve preset {preset!r}")
        return cls(_PRESET_POINTS[preset], name=preset)

    def evaluate(self, t: float) -> float:
        t_clamped = min(1.0, max(0.0, float(t)))
        return float(np.interp(t_clamped, self._ts, self._vs))

    def sample(self, n: int) -> list[float]:
        if n <= 0:
            return []
        return [self.evaluate(i / max(1, n - 1)) for i in range(n)]


def _organic_points(seed: int) -> tuple[tuple[float, float], ...]:
    rng = np.random.default_rng(SeedSystem(seed).derive("energy"))
    count = int(rng.integers(5, 9))
    inner_t = np.sort(rng.uniform(0.12, 0.88, size=count - 2))
    ts = [0.0, *inner_t.tolist(), 1.0]
    values = [float(rng.uniform(0.25, 0.45))]
    for _ in range(count - 2):
        previous = values[-1]
        target = float(np.clip(previous + rng.uniform(-0.28, 0.28), 0.15, 0.9))
        values.append(target)
    values.append(float(rng.uniform(0.2, 0.45)))
    return tuple(zip(ts, values, strict=True))


def known_energy_presets() -> tuple[str, ...]:
    return tuple(p.value for p in EnergyCurvePreset)
