"""Arranger: section-aware composition with energy curves and anti-repetition.

Each section gets its own RNG namespace, density/energy treatment, role
gating (intros/breakdowns thin out), octave-shift variation and velocity
scaling — so long tracks never feel like a literal loop.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from lfms.arranger.analysis import repetition_score
from lfms.arranger.energy import EnergyCurve
from lfms.arranger.sections import SectionPlanner, SectionSpan, slice_chords
from lfms.core.ids import fingerprint
from lfms.core.seed import SeedSystem
from lfms.core.version import GENERATOR_VERSION
from lfms.generator.composer import (
    BassGenerator,
    PadGenerator,
    PulseGenerator,
    SparkleGenerator,
    _clip_events,
)
from lfms.generator.events import ChordSegment, Composition, NoteEvent
from lfms.generator.harmony import HarmonyGenerator
from lfms.generator.melody import MelodyGenerator
from lfms.generator.plan import GenerationParameters, MusicPlan

_DEFAULT_LONG_CURVE = "DOCUMENTARY"
_OCTAVE_SHIFT_CHOICES: dict[str, tuple[int, ...]] = {
    "VARIATION_A": (-12, 0, 12),
    "VARIATION_B": (-12, 0, 12),
    "DEVELOPMENT": (0, 12),
    "BREAKDOWN": (-12,),
}


class Arranger:
    def __init__(self, params: GenerationParameters, plan: MusicPlan) -> None:
        self.params = params
        self.plan = plan

    def arrange(self) -> Composition:
        plan = self.plan
        curve = self._energy_curve()
        spans = SectionPlanner(
            curve=curve,
            bar_sec=plan.bar_sec,
            duration_sec=plan.duration_sec,
            seed=plan.seed,
        ).plan()
        chords = HarmonyGenerator(plan).generate()

        # role -> list of (origin_offset_sec, event). Section-relative
        # generators emit times starting at 0 within their span; the pulse
        # generator works in absolute time (origin 0).
        collected: dict[str, list[tuple[float, NoteEvent]]] = {}

        for span in spans:
            section_chords = slice_chords(chords, span)
            if not section_chords:
                continue
            context = _section_plan(plan, span)
            index = span.index

            if span.allows("MELODY"):
                events = MelodyGenerator(context, rng_index=index).generate(section_chords)
                events = _thin(events, keep=0.55 + 0.45 * span.energy, seed=plan.seed, index=index)
                shift = _octave_shift(span, plan.seed)
                if shift:
                    events = [replace(event, midi=event.midi + shift) for event in events]
                collected.setdefault("MELODY", []).extend(
                    (span.start_sec, event) for event in events
                )
            if span.allows("PAD"):
                collected.setdefault("PAD", []).extend(
                    (span.start_sec, event)
                    for event in PadGenerator(context, rng_index=index).generate(section_chords)
                )
            if span.allows("BASS"):
                collected.setdefault("BASS", []).extend(
                    (span.start_sec, event)
                    for event in BassGenerator(context, rng_index=index).generate(section_chords)
                )
            if span.allows("SPARKLE"):
                collected.setdefault("SPARKLE", []).extend(
                    (span.start_sec, event)
                    for event in SparkleGenerator(context, rng_index=index).generate(section_chords)
                )
            if span.allows("PULSE") and context.pulse_level >= 0.03:
                collected.setdefault("PULSE", []).extend(
                    (0.0, event)
                    for event in PulseGenerator(context, rng_index=index).generate(
                        start_sec=span.start_sec, end_sec=span.end_sec
                    )
                )

        final_roles: dict[str, list[NoteEvent]] = {}
        for role, pairs in collected.items():
            placed: list[NoteEvent] = []
            for origin, event in pairs:
                absolute_start = event.start_sec + origin
                scale = _scale_for(absolute_start, spans)
                placed.append(_with_velocity(replace(event, start_sec=absolute_start), scale))
            final_roles[role] = placed

        return _assemble(plan, chords, spans, curve.name, final_roles)

    def _energy_curve(self) -> EnergyCurve:
        preset = self.params.energy_curve
        if preset is None:
            preset = _DEFAULT_LONG_CURVE if self.plan.duration_sec >= 600.0 else "FLAT"
        return EnergyCurve.from_preset(
            preset,
            seed=self.plan.seed,
            user_points=self.params.energy_points,
        )


def _section_plan(plan: MusicPlan, span: SectionSpan) -> MusicPlan:
    energy = span.energy
    return replace(
        plan,
        density=float(np.clip(plan.density * (0.6 + 0.8 * energy), 0.05, 1.0)),
        melody_probability=float(np.clip(plan.melody_probability * (0.5 + energy), 0.0, 1.0)),
        pulse_level=float(np.clip(plan.pulse_level * (0.25 + 1.1 * energy), 0.0, 1.0)),
        duration_sec=span.duration_sec,
    )


def _thin(
    events: list[NoteEvent], *, keep: float, seed: int, index: int
) -> list[NoteEvent]:
    rng = np.random.default_rng(SeedSystem(seed).derive("thin", index))
    return [event for event in events if float(rng.random()) < keep]


def _octave_shift(span: SectionSpan, seed: int) -> int:
    choices = _OCTAVE_SHIFT_CHOICES.get(span.section_type)
    if not choices:
        return 0
    rng = np.random.default_rng(SeedSystem(seed).derive("octaves", span.index))
    return int(choices[int(rng.integers(0, len(choices)))])


def _with_velocity(event: NoteEvent, scale: float) -> NoteEvent:
    if scale == 1.0:
        return event
    return replace(event, velocity=float(np.clip(event.velocity * scale, 5.0, 120.0)))


def _scale_for(absolute_start: float, spans: list[SectionSpan]) -> float:
    for span in spans:
        if span.start_sec <= absolute_start < span.end_sec:
            # cap at 1.0: velocity boosts above full scale push mixes into
            # the limiter and read as distortion
            return 0.70 + 0.30 * span.energy
    return 1.0


def _assemble(
    plan: MusicPlan,
    chords: list[ChordSegment],
    spans: list[SectionSpan],
    curve_name: str,
    roles: dict[str, list[NoteEvent]],
) -> Composition:
    composition = Composition(
        plan_fingerprint=plan.fingerprint,
        duration_sec=plan.duration_sec,
        chords=chords,
        roles={
            role: _clip_events(events, plan.duration_sec)
            for role, events in roles.items()
        },
        fingerprint=fingerprint(["CMP", GENERATOR_VERSION, "ARRANGED", plan.fingerprint]),
        generator_version=GENERATOR_VERSION,
        seed=plan.seed,
        sample_rate=plan.sample_rate,
        brightness_hz=plan.brightness_hz,
        voiceover_safe=plan.voiceover_safe,
        bpm=plan.bpm,
        key_name=plan.key_name,
        sections=list(spans),
        energy_curve_name=curve_name,
    )
    composition.repetition_score = repetition_score(composition)
    return composition
