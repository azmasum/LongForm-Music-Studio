"""Procedural music generator (Phase 3): plan -> harmony -> events -> audio."""
from __future__ import annotations

from lfms.generator.composer import (
    BassGenerator,
    Composer,
    PadGenerator,
    PulseGenerator,
    SparkleGenerator,
)
from lfms.generator.events import ChordSegment, Composition, NoteEvent
from lfms.generator.harmony import HarmonyGenerator
from lfms.generator.melody import MelodyGenerator
from lfms.generator.plan import (
    GenerationParameters,
    MusicPlan,
    build_plan,
    known_genres,
    known_moods,
)
from lfms.generator.render import CompositionRenderer, quick_generate
from lfms.generator.scheduler import EventTrackSource

__all__ = [
    "BassGenerator",
    "ChordSegment",
    "Composer",
    "Composition",
    "CompositionRenderer",
    "EventTrackSource",
    "GenerationParameters",
    "HarmonyGenerator",
    "MelodyGenerator",
    "MusicPlan",
    "NoteEvent",
    "PadGenerator",
    "PulseGenerator",
    "SparkleGenerator",
    "build_plan",
    "known_genres",
    "known_moods",
    "quick_generate",
]
