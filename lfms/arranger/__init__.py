"""Long-form arranger (Phase 4): energy curves, sections, repetition control."""
from __future__ import annotations

from lfms.arranger.analysis import repetition_score
from lfms.arranger.arranger import Arranger
from lfms.arranger.energy import EnergyCurve, known_energy_presets
from lfms.arranger.sections import ROLE_GATES, SectionPlanner, SectionSpan

__all__ = [
    "Arranger",
    "EnergyCurve",
    "ROLE_GATES",
    "SectionPlanner",
    "SectionSpan",
    "known_energy_presets",
    "repetition_score",
]
