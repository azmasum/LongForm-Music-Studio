"""Composer: assembles a full Composition from plan + chord segments.

Layers: PAD (harmony bed), BASS, MELODY, SPARKLE (sparse bells), PULSE
(optional soft percussion). All randomness is seeded from the plan seed.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from lfms.core.ids import fingerprint
from lfms.core.seed import SeedSystem
from lfms.core.version import GENERATOR_VERSION
from lfms.generator.events import ChordSegment, Composition, NoteEvent
from lfms.generator.harmony import HarmonyGenerator
from lfms.generator.melody import MelodyGenerator
from lfms.generator.plan import GenerationParameters, MusicPlan, build_plan
from lfms.generator.theory import voicing_for_chord


class PadGenerator:
    def __init__(self, plan: MusicPlan) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(SeedSystem(plan.seed).derive("pad"))

    def generate(self, chords: list[ChordSegment]) -> list[NoteEvent]:
        events: list[NoteEvent] = []
        previous: list[int] = []
        for segment in chords:
            best_rotation = 0
            best_cost = float("inf")
            for rotation in range(len(segment.pitch_classes)):
                candidate = voicing_for_chord(
                    list(segment.pitch_classes),
                    center_midi=self.plan.register_center,
                    bass_rotation=rotation,
                )
                cost = (
                    float(np.mean(np.abs(np.array(candidate) - np.mean(previous))))
                    if previous
                    else 0.0
                )
                if cost < best_cost:
                    best_cost = cost
                    best_rotation = rotation
            voicing = voicing_for_chord(
                list(segment.pitch_classes),
                center_midi=self.plan.register_center,
                bass_rotation=best_rotation,
                spread_octaves=bool(self._rng.random() < 0.35),
            )
            previous = voicing
            velocity = float(np.clip(52.0 + self._rng.uniform(-4.0, 6.0), 30.0, 80.0))
            for midi in voicing:
                events.append(
                    NoteEvent(
                        start_sec=segment.start_sec,
                        duration_sec=segment.duration_sec,
                        midi=int(midi),
                        velocity=velocity,
                        role="PAD",
                        instrument="PAD",
                    )
                )
        return events


class BassGenerator:
    def __init__(self, plan: MusicPlan) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(SeedSystem(plan.seed).derive("bass"))

    def generate(self, chords: list[ChordSegment]) -> list[NoteEvent]:
        events: list[NoteEvent] = []
        for _index, segment in enumerate(chords):
            root_pc = segment.pitch_classes[0]
            target = 33 + (root_pc - self.plan.key_root_pc) % 12
            bass_midi = root_pc + 12 * ((target - root_pc) // 12)
            bass_midi = int(np.clip(bass_midi, 28, 47))
            bar_beats = segment.duration_sec / self.plan.beat_sec
            pattern: list[tuple[float, float]]
            if self.plan.density < 0.35 or bar_beats < 2.0:
                pattern = [(0.0, bar_beats)]
            elif float(self._rng.random()) < 0.45:
                half = bar_beats / 2.0
                pattern = [(0.0, half * 0.92), (half, half * 0.92)]
            else:
                pattern = [(0.0, bar_beats * 0.94)]
            velocity = float(np.clip(62.0 + self._rng.uniform(-5.0, 5.0), 30.0, 90.0))
            for beat_offset, beat_len in pattern:
                start = segment.start_sec + beat_offset * self.plan.beat_sec
                duration = min(beat_len * self.plan.beat_sec, segment.end_sec - start)
                if duration <= 0:
                    continue
                events.append(
                    NoteEvent(
                        start_sec=start,
                        duration_sec=duration,
                        midi=bass_midi,
                        velocity=velocity,
                        role="BASS",
                        instrument="BASS",
                    )
                )
        return events


class SparkleGenerator:
    """Rare high bells on chord tops; adds air without demanding attention."""

    def __init__(self, plan: MusicPlan) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(SeedSystem(plan.seed).derive("sparkle"))

    def generate(self, chords: list[ChordSegment]) -> list[NoteEvent]:
        probability = 0.18 * self.plan.density + 0.04
        events: list[NoteEvent] = []
        for segment in chords:
            if float(self._rng.random()) > probability:
                continue
            top_pc = max(segment.pitch_classes)
            sparkle_midi = top_pc + 12 * int(
                np.ceil((self.plan.register_center + 14 - top_pc) / 12.0)
            )
            sparkle_midi = int(np.clip(sparkle_midi, self.plan.register_center + 7, 96))
            offset = float(self._rng.uniform(0.1, 0.6)) * segment.duration_sec
            start = min(segment.start_sec + offset, segment.end_sec - 0.05)
            if start <= segment.start_sec:
                continue
            events.append(
                NoteEvent(
                    start_sec=start,
                    duration_sec=min(1.6, segment.end_sec - start),
                    midi=sparkle_midi,
                    velocity=float(np.clip(self._rng.uniform(32.0, 55.0), 15.0, 70.0)),
                    role="SPARKLE",
                    instrument="BELL",
                )
            )
        return events


class PulseGenerator:
    """Soft kick/hat pulse; only appears once intensity/pulse_level rises."""

    def __init__(self, plan: MusicPlan) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(SeedSystem(plan.seed).derive("pulse"))

    def generate(self) -> list[NoteEvent]:
        level = self.plan.pulse_level
        if level < 0.03:
            return []
        events: list[NoteEvent] = []
        jitter = 0.008
        beat = self.plan.beat_sec
        time = 0.0
        while time < self.plan.duration_sec - 1e-9:
            kick_times = [time]
            if level > 0.40 and time + 2 * beat < self.plan.duration_sec:
                kick_times.append(time + 2 * beat)
            for kick_start in kick_times:
                events.append(
                    NoteEvent(
                        start_sec=max(0.0, kick_start + float(self._rng.uniform(-jitter, jitter))),
                        duration_sec=0.42,
                        midi=36,
                        velocity=float(np.clip(38.0 + 34.0 * level, 10.0, 90.0)),
                        role="PULSE",
                        instrument="KICK",
                    )
                )
            if level > 0.10:
                hat_step = beat / 2.0
                hat_time = time
                while hat_time < time + 4 * beat - 1e-9:
                    if float(self._rng.random()) < 0.85 and hat_time < self.plan.duration_sec:
                        events.append(
                            NoteEvent(
                                start_sec=max(0.0, hat_time + float(self._rng.uniform(-jitter, jitter))),
                                duration_sec=0.09,
                                midi=42,
                                velocity=float(np.clip(16.0 + 22.0 * level, 8.0, 60.0)),
                                role="PULSE",
                                instrument="HAT",
                            )
                        )
                    hat_time += hat_step
            time += 4 * beat
        return [event for event in events if event.start_sec < self.plan.duration_sec]


def _clip_events(events: list[NoteEvent], duration_sec: float) -> list[NoteEvent]:
    clipped: list[NoteEvent] = []
    for event in events:
        if event.start_sec >= duration_sec:
            continue
        remaining = duration_sec - event.start_sec
        duration = min(event.duration_sec, remaining)
        if duration <= 1e-4:
            continue
        if duration < event.duration_sec:
            event = replace(event, duration_sec=duration)
        clipped.append(event)
    clipped.sort(key=lambda e: (e.start_sec, e.instrument, e.midi))
    return clipped


class Composer:
    def __init__(self, params: GenerationParameters, *, plan: MusicPlan | None = None) -> None:
        self.params = params
        self.plan = plan or build_plan(params)

    def compose(self) -> Composition:
        plan = self.plan
        chords = HarmonyGenerator(plan).generate()
        melody = MelodyGenerator(plan).generate(chords)
        pads = PadGenerator(plan).generate(chords)
        bass = BassGenerator(plan).generate(chords)
        sparkle = SparkleGenerator(plan).generate(chords)
        pulse = PulseGenerator(plan).generate()

        roles: dict[str, list[NoteEvent]] = {}
        for name, track_events in (
            ("MELODY", melody),
            ("PAD", pads),
            ("BASS", bass),
            ("SPARKLE", sparkle),
            ("PULSE", pulse),
        ):
            clipped = _clip_events(track_events, plan.duration_sec)
            if clipped:
                roles[name] = clipped

        composition_fingerprint = fingerprint(
            ["CMP", GENERATOR_VERSION, plan.fingerprint]
        )
        composition = Composition(
            plan_fingerprint=plan.fingerprint,
            duration_sec=plan.duration_sec,
            chords=chords,
            roles=roles,
            fingerprint=composition_fingerprint,
            generator_version=GENERATOR_VERSION,
        )
        return composition
