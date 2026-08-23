"""Music theory primitives: modes, diatonic chords, progression pools."""
from __future__ import annotations

import numpy as np

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

MODE_INTERVALS: dict[str, tuple[int, ...]] = {
    "MAJOR": (0, 2, 4, 5, 7, 9, 11),
    "MINOR": (0, 2, 3, 5, 7, 8, 10),
    "DORIAN": (0, 2, 3, 5, 7, 9, 10),
    "MIXOLYDIAN": (0, 2, 4, 5, 7, 9, 10),
    "PHRYGIAN": (0, 1, 3, 5, 7, 8, 10),
    "LYDIAN": (0, 2, 4, 6, 7, 9, 11),
}

PROGRESSION_POOL: dict[str, list[tuple[int, ...]]] = {
    "MINOR": [
        (1, 6, 7),
        (1, 6, 3, 7),
        (1, 4, 6, 5),
        (6, 7, 1, 1),
        (1, 7, 6, 7),
        (1, 5, 6, 4),
    ],
    "MAJOR": [
        (1, 5, 6, 4),
        (1, 4, 6, 5),
        (6, 4, 1, 5),
        (1, 6, 4, 5),
        (4, 5, 3, 6),
    ],
    "DORIAN": [
        (1, 4),
        (1, 2, 1, 4),
        (1, 4, 1, 5),
    ],
}


def note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_freq(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def freq_to_midi(freq: float) -> float:
    return 69.0 + 12.0 * float(np.log2(max(freq, 1e-6) / 440.0))


def scale_pitch_classes(root_pc: int, mode: str) -> list[int]:
    if mode not in MODE_INTERVALS:
        raise ValueError(f"unknown mode {mode!r}")
    return [(root_pc + iv) % 12 for iv in MODE_INTERVALS[mode]]


def chord_pitch_classes(
    root_pc: int,
    mode: str,
    degree_index: int,
    *,
    seventh: bool = False,
) -> list[int]:
    """Stack thirds within the mode; degree_index is 0-based."""
    scale = scale_pitch_classes(root_pc, mode)
    positions = (degree_index % 7, (degree_index + 2) % 7, (degree_index + 4) % 7)
    if seventh:
        positions += ((degree_index + 6) % 7,)
    return [scale[p] for p in positions]


def chord_quality_name(pcs: list[int]) -> str:
    intervals = {(pcs[1] - pcs[0]) % 12, (pcs[2] - pcs[0]) % 12}
    if intervals == {4, 7}:
        return "maj"
    if intervals == {3, 7}:
        return "min"
    if intervals == {3, 6}:
        return "dim"
    if intervals == {4, 8}:
        return "aug"
    if intervals == {2, 7}:
        return "sus2"
    if intervals == {5, 7}:
        return "sus4"
    return "other"


def voicing_for_chord(
    pcs: list[int],
    *,
    center_midi: int,
    bass_rotation: int = 0,
    spread_octaves: bool = False,
) -> list[int]:
    """Build an ascending voicing whose lowest note sits near center_midi."""
    rotation = bass_rotation % len(pcs)
    ordered = list(pcs[rotation:]) + list(pcs[:rotation])
    root = ordered[0]
    root_midi = root + 12 * int(round((center_midi - root) / 12.0))
    notes = [root_midi]
    for pc in ordered[1:]:
        candidate = pc + 12 * (notes[-1] // 12)
        while candidate <= notes[-1]:
            candidate += 12
        notes.append(candidate)
    if spread_octaves and len(notes) >= 3:
        notes[-1] += 12
    return notes


def nearest_scale_midi(target: int, root_pc: int, mode: str) -> int:
    """Snap target pitch to the closest member of the scale."""
    scale = scale_pitch_classes(root_pc, mode)

    def distance(candidate: int) -> int:
        best = 12
        for pc in scale:
            diff = abs(((candidate - pc) + 6) % 12 - 6)
            best = min(best, diff)
        return best

    best_target = target
    best_distance = 13
    for octave in (-1, 0, 1):
        candidate = target + 12 * octave
        dist = distance(candidate)
        if dist < best_distance:
            best_distance = dist
            snapped = min(scale, key=lambda pc: abs(((candidate - pc) + 6) % 12 - 6))
            best_target = 12 * round(candidate / 12) + snapped
    return best_target


PROGRESSION_FALLBACK = PROGRESSION_POOL["MINOR"]


def progression_pool_for_mode(mode: str) -> list[tuple[int, ...]]:
    return PROGRESSION_POOL.get(mode, PROGRESSION_FALLBACK)
