"""Section planning: bar-aligned spans with energy values and role gates."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lfms.arranger.energy import EnergyCurve
from lfms.core.seed import SeedSystem

ROLE_GATES: dict[str, frozenset[str]] = {
    "INTRO": frozenset({"PAD", "SPARKLE", "BASS"}),
    "THEME_A": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "VARIATION_A": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "TRANSITION": frozenset({"PAD", "BASS"}),
    "THEME_B": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "VARIATION_B": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "BREAKDOWN": frozenset({"PAD", "SPARKLE"}),
    "DEVELOPMENT": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "RETURN": frozenset({"PAD", "BASS", "MELODY", "SPARKLE", "PULSE"}),
    "OUTRO": frozenset({"PAD", "BASS", "SPARKLE"}),
}

_MIDDLE_CYCLES: tuple[tuple[str, ...], ...] = (
    ("THEME_A", "VARIATION_A", "THEME_B", "DEVELOPMENT"),
    ("THEME_A", "THEME_B", "VARIATION_B", "BREAKDOWN"),
    ("THEME_A", "VARIATION_A", "THEME_B", "TRANSITION"),
    ("THEME_A", "THEME_B", "DEVELOPMENT", "VARIATION_A"),
)


@dataclass(frozen=True)
class SectionSpan:
    section_type: str
    start_sec: float
    duration_sec: float
    energy: float
    index: int

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec

    def allows(self, role: str) -> bool:
        return role in ROLE_GATES.get(self.section_type, ROLE_GATES["THEME_A"])


class SectionPlanner:
    """Splits the timeline into bar-aligned sections driven by an energy curve."""

    def __init__(
        self,
        *,
        curve: EnergyCurve,
        bar_sec: float,
        duration_sec: float,
        seed: int,
    ) -> None:
        self.curve = curve
        self.bar_sec = max(1e-6, float(bar_sec))
        self.duration_sec = float(duration_sec)
        self._rng = np.random.default_rng(SeedSystem(seed).derive("sections"))

    def plan(self) -> list[SectionSpan]:
        if self.duration_sec < 60.0:
            return [
                SectionSpan(
                    section_type="THEME_A",
                    start_sec=0.0,
                    duration_sec=self.duration_sec,
                    energy=self.curve.evaluate(0.5),
                    index=0,
                )
            ]
        intro_bars = int(np.clip(round(0.04 * self.duration_sec / self.bar_sec), 4, 16))
        outro_bars = int(np.clip(round(0.05 * self.duration_sec / self.bar_sec), 4, 16))
        intro_sec = intro_bars * self.bar_sec
        outro_sec = outro_bars * self.bar_sec
        middle_sec = self.duration_sec - intro_sec - outro_sec

        slot_bars = int(self._rng.integers(16, 33))
        slot_sec = slot_bars * self.bar_sec
        slot_count = max(1, int(round(middle_sec / slot_sec)))
        base_slot = middle_sec / slot_count
        slot_bars_aligned = max(4, int(round(base_slot / self.bar_sec)))
        aligned_slot = min(slot_bars_aligned * self.bar_sec, middle_sec)

        cycle = _MIDDLE_CYCLES[int(self._rng.integers(0, len(_MIDDLE_CYCLES)))]
        sections: list[SectionSpan] = []

        time = 0.0
        sections.append(
            SectionSpan("INTRO", 0.0, intro_sec, self.curve.evaluate(intro_sec * 0.5 / self.duration_sec), 0)
        )
        time += intro_sec

        span_index = 1
        remaining_middle = middle_sec - aligned_slot * (slot_count - 1)
        for slot in range(slot_count):
            duration = aligned_slot if slot < slot_count - 1 else max(aligned_slot, remaining_middle)
            duration = min(duration, self.duration_sec - time - outro_sec)
            if duration < self.bar_sec:
                break
            section_type = cycle[slot % len(cycle)]
            mid_energy_t = (time + duration * 0.5) / self.duration_sec
            sections.append(
                SectionSpan(section_type, time, duration, self.curve.evaluate(mid_energy_t), span_index)
            )
            time += duration
            span_index += 1

        if self.duration_sec - time > self.bar_sec // 2:
            outro_duration = self.duration_sec - time
            sections.append(
                SectionSpan("OUTRO", time, outro_duration, self.curve.evaluate((time + outro_duration * 0.5) / self.duration_sec), span_index)
            )
        elif sections:
            last = sections[-1]
            extended = self.duration_sec - last.start_sec
            sections[-1] = SectionSpan(last.section_type, last.start_sec, extended, last.energy, last.index)
        return sections


def slice_chords(chords, span: SectionSpan):  # noqa: ANN001 - list[ChordSegment]
    """Trim global chord segments to a section window; returns new segments."""
    from dataclasses import replace

    from lfms.generator.events import ChordSegment

    out: list[ChordSegment] = []
    for chord in chords:
        start = max(chord.start_sec, span.start_sec)
        end = min(chord.end_sec, span.end_sec)
        if end - start <= 1e-6:
            continue
        out.append(
            replace(
                chord,
                start_sec=start - span.start_sec,
                duration_sec=end - start,
            )
        )
    return out
