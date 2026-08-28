"""Composer: assembles a full Composition from plan + chord segments.

Layers: PAD (harmony bed), BASS, MELODY, SPARKLE (sparse bells), PULSE
(optional soft percussion). All randomness is seeded from the plan seed.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from lfms.core.seed import SeedSystem
from lfms.generator.events import ChordSegment, Composition, NoteEvent
from lfms.generator.plan import GenerationParameters, MusicPlan, build_plan
from lfms.generator.theory import voicing_for_chord


class PadGenerator:
    def __init__(self, plan: MusicPlan, *, rng_index: int = 0) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(
            SeedSystem(plan.seed).derive("pad", rng_index)
        )

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
                        instrument=getattr(self.plan, "pad_instrument", "PAD"),
                    )
                )
        return events


class BassGenerator:
    def __init__(self, plan: MusicPlan, *, rng_index: int = 0) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(
            SeedSystem(plan.seed).derive("bass", rng_index)
        )

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
                        instrument=getattr(self.plan, "bass_instrument", "BASS"),
                    )
                )
        return events


class SparkleGenerator:
    """Rare high bells on chord tops; adds air without demanding attention."""

    def __init__(self, plan: MusicPlan, *, rng_index: int = 0) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(
            SeedSystem(plan.seed).derive("sparkle", rng_index)
        )

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

    def __init__(self, plan: MusicPlan, *, rng_index: int = 0) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(
            SeedSystem(plan.seed).derive("pulse", rng_index)
        )

    def generate(
        self,
        *,
        start_sec: float = 0.0,
        end_sec: float | None = None,
    ) -> list[NoteEvent]:
        level = self.plan.pulse_level
        if level < 0.03:
            return []
        limit = self.plan.duration_sec if end_sec is None else end_sec
        events: list[NoteEvent] = []
        jitter = 0.008
        beat = self.plan.beat_sec
        bar_sec = 4 * beat
        first_bar = int(np.floor(start_sec / bar_sec + 1e-9))
        time = first_bar * bar_sec
        while time < limit - 1e-9:
            drum_mode = getattr(self.plan, "drums", "NONE")
            kick_times = [time]
            if drum_mode in ("TRIBAL", "FOUR_FLOOR"):
                # four-on-the-floor: a kick on every beat for a massive,
                # driving festival / club drop
                kick_times = [time, time + beat, time + 2 * beat, time + 3 * beat]
            elif level > 0.40 and time + 2 * beat < limit:
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
                while hat_time < time + bar_sec - 1e-9:
                    if float(self._rng.random()) < 0.85 and hat_time < limit:
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
            if getattr(self.plan, "perc_snare", False) and level > 0.30:
                for backbeat in (time + beat, time + 3 * beat):
                    if backbeat < limit - 1e-9:
                        events.append(
                            NoteEvent(
                                start_sec=max(0.0, backbeat + float(self._rng.uniform(-jitter, jitter))),
                                duration_sec=0.22,
                                midi=38,
                                velocity=float(np.clip(26.0 + 30.0 * level, 12.0, 80.0)),
                                role="PULSE",
                                instrument="SNARE",
                            )
                        )
            # Explicitly requested drums produce a full, driving kit. This
            # is what answers prompts like "epic tribal drums" / "drop":
            # hard backbeat snare on 2 & 4 and a crash accent where asked.
            if drum_mode in ("FULL", "TRIBAL", "FOUR_FLOOR"):
                # heavy backbeats (2 & 4) at high velocity
                for backbeat in (time + beat, time + 3 * beat):
                    if backbeat < limit - 1e-9:
                        events.append(
                            NoteEvent(
                                start_sec=max(0.0, backbeat + float(self._rng.uniform(-jitter, jitter))),
                                duration_sec=0.22,
                                midi=38,
                                velocity=float(np.clip(50.0 + 30.0 * min(1.0, level), 40.0, 92.0)),
                                role="PULSE",
                                instrument="SNARE",
                            )
                        )
            if drum_mode == "TRIBAL" and level >= 0.05:
                # extra ghost snare + open stomp on the offbeats for a
                # bigger, tribal step
                for t in (time + 2 * beat,):
                    if t < limit - 1e-9:
                        events.append(
                            NoteEvent(
                                start_sec=max(0.0, t + float(self._rng.uniform(-jitter, jitter))),
                                duration_sec=0.3,
                                midi=38,
                                velocity=float(np.clip(20.0 + 24.0 * level, 16.0, 70.0)),
                                role="PULSE",
                                instrument="SNARE",
                            )
                        )
            time += bar_sec
        return [
            event
            for event in events
            if event.start_sec >= start_sec and event.start_sec < limit
        ]


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
        from lfms.arranger.arranger import Arranger

        return Arranger(self.params, self.plan).arrange()
