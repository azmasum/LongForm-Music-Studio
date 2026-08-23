"""Melody generation: seeded motifs with bounded variation transforms.

Motifs are rhythm cells plus scale-degree walks. Repetitions of a motif get
one of a few deterministic transforms (shift, octave, erode) so long tracks
never feel like a literal loop, while staying recognisably thematic.
"""
from __future__ import annotations

import numpy as np

from lfms.core.seed import SeedSystem
from lfms.generator.events import ChordSegment, NoteEvent
from lfms.generator.plan import MusicPlan
from lfms.generator.theory import scale_pitch_classes

_RHYTHM_POOLS: dict[str, list[tuple[float, ...]]] = {
    "sparse": [
        (2.0, 2.0),
        (4.0,),
        (3.0, 1.0),
        (2.0, 1.0, 1.0),
    ],
    "mid": [
        (1.0, 1.0, 2.0),
        (0.5, 0.5, 1.0, 2.0),
        (1.0, 0.5, 0.5, 2.0),
        (2.0, 1.0, 1.0),
    ],
    "busy": [
        (0.5,) * 6 + (1.0,),
        (0.5, 0.5, 0.5, 0.5, 1.0, 1.0),
        (1.0, 0.5, 0.5, 0.5, 0.5, 1.0),
    ],
}

_STEPS = (-2, -1, -1, 0, 1, 1, 2)
_TRANSFORMS = ("NONE", "SHIFT_UP", "SHIFT_DOWN", "OCTAVE_UP", "ERODE")
_TRANSFORM_WEIGHTS = (0.45, 0.18, 0.15, 0.12, 0.10)


def rhythm_pool(density: float) -> list[tuple[float, ...]]:
    if density < 0.33:
        return _RHYTHM_POOLS["sparse"]
    if density < 0.66:
        return _RHYTHM_POOLS["mid"]
    return _RHYTHM_POOLS["busy"]


class MelodyGenerator:
    def __init__(self, plan: MusicPlan) -> None:
        self.plan = plan
        self._rng = np.random.default_rng(SeedSystem(plan.seed).derive("melody"))
        self._scale = scale_pitch_classes(plan.key_root_pc, plan.key_mode)

    def _scale_midi(self, degree: int) -> int:
        octave = degree // len(self._scale)
        pitch_class = self._scale[degree % len(self._scale)]
        return self.plan.register_center + 12 * (octave - 1) + pitch_class

    def _snap_to_chord(self, midi: int, chord_pcs: tuple[int, ...]) -> int:
        for delta in (0, 1, -1, 2, -2):
            candidate = midi + delta
            if candidate % 12 in chord_pcs:
                return candidate
        return midi

    def generate(
        self,
        chords: list[ChordSegment],
        instrument: str | None = None,
    ) -> list[NoteEvent]:
        """Generate melody events aligned to the chord segments."""
        if self.plan.melody_probability <= 0.02 or not chords:
            return []
        instrument = instrument or self.plan.melody_instrument
        beat = self.plan.beat_sec
        pool = rhythm_pool(self.plan.density)
        motifs = [self._make_motif(pool), self._make_motif(pool)]
        use_counts = [0, 0]
        events: list[NoteEvent] = []
        skip_first_bar = bool(self._rng.random() < 0.4)
        current_degree = int(self._rng.integers(-2, 3))

        for index, segment in enumerate(chords):
            if index == 0 and skip_first_bar:
                continue
            play_probability = self.plan.melody_probability * (
                1.0 if index % 2 == 0 else 0.55
            )
            if float(self._rng.random()) > play_probability:
                continue
            motif_index = int(self._rng.integers(0, 2)) if index % 2 == 0 else 0
            motif = motifs[motif_index]
            use_counts[motif_index] += 1
            degrees = list(motif["degrees"])
            if use_counts[motif_index] > 1:
                transform = str(self._rng.choice(_TRANSFORMS, p=_TRANSFORM_WEIGHTS))
            else:
                transform = "NONE"
            if transform == "SHIFT_UP":
                degrees = [d + 1 for d in degrees]
            elif transform == "SHIFT_DOWN":
                degrees = [d - 1 for d in degrees]
            elif transform == "OCTAVE_UP":
                degrees = [d + 7 for d in degrees]
            elif transform == "ERODE":
                degrees = degrees[:-1] if len(degrees) > 1 else degrees
            for note_pos, deg in enumerate(degrees):
                start = segment.start_sec + sum(motif["rhythm"][:note_pos]) * beat
                duration = motif["rhythm"][note_pos] * beat
                if start >= segment.end_sec:
                    break
                duration = min(duration, segment.end_sec - start)
                if float(self._rng.random()) < 0.25 * (1.0 - self.plan.density):
                    continue
                current_degree += int(deg)
                current_degree = int(np.clip(current_degree, -14, 21))
                midi = self._scale_midi(current_degree)
                beats_from_start = start / self.plan.beat_sec
                is_strong = abs(beats_from_start - round(beats_from_start)) < 0.05
                if is_strong:
                    midi = self._snap_to_chord(midi, segment.pitch_classes)
                velocity = 68.0 + float(self._rng.uniform(-9.0, 9.0))
                if abs(beats_from_start - round(beats_from_start)) < 0.02:
                    velocity += 8.0
                velocity = float(np.clip(velocity, 20.0, 110.0))
                events.append(
                    NoteEvent(
                        start_sec=start,
                        duration_sec=duration,
                        midi=int(midi),
                        velocity=velocity,
                        role="MELODY",
                        instrument=instrument,
                    )
                )
        return events

    def _make_motif(self, pool: list[tuple[float, ...]]) -> dict:
        rhythm = pool[int(self._rng.integers(0, len(pool)))]
        degrees = [int(self._rng.integers(-2, 3))]
        for _ in range(len(rhythm) - 1):
            step = int(self._rng.choice(_STEPS))
            degrees.append(int(np.clip(degrees[-1] + step, -6, 6)))
        return {"rhythm": rhythm, "degrees": degrees}
