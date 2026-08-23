"""Anti-repetition analysis: windowed self-similarity -> Repetition Score.

The metric intentionally looks at the *foreground* (melody, sparkle bells,
pulse) — steady pads and bass drones are supposed to repeat in background
music and must not dominate the measurement.
"""
from __future__ import annotations

import numpy as np

from lfms.generator.events import Composition, NoteEvent

_FOREGROUND_ROLES = ("MELODY", "SPARKLE", "PULSE")
_ROLE_WEIGHTS = np.array([2.0, 1.0, 0.35], dtype=np.float64)


def _feature_vector(events: list[NoteEvent], lo: float, hi: float) -> np.ndarray:
    """Bounded descriptor of one time window's foreground activity."""
    window_events = [
        e for e in events if lo <= e.start_sec < hi and e.role in _FOREGROUND_ROLES
    ]
    count = float(len(window_events))
    if count == 0:
        return np.zeros(len(_FOREGROUND_ROLES) + 4 + 12 + 4, dtype=np.float64)

    role_counts = np.array(
        [sum(1 for e in window_events if e.role == role) for role in _FOREGROUND_ROLES],
        dtype=np.float64,
    )
    role_shape = role_counts / count * _ROLE_WEIGHTS

    melodic = [e for e in window_events if e.role in ("MELODY", "SPARKLE")]
    mean_velocity = float(np.mean([e.velocity for e in melodic or window_events]))
    mean_midi = float(np.mean([e.midi for e in melodic or window_events]))
    mean_duration = float(np.mean([e.duration_sec for e in melodic or window_events]))
    scalars = np.array(
        [
            min(1.0, count / 24.0),
            mean_velocity / 127.0,
            (mean_midi - 24.0) / 84.0,
            min(1.0, mean_duration / 4.0),
        ],
        dtype=np.float64,
    )

    pitch_histogram = np.zeros(12, dtype=np.float64)
    for event in melodic or window_events:
        pitch_histogram[event.midi % 12] += 1.0
    pitch_histogram /= count

    gap_histogram = np.zeros(4, dtype=np.float64)
    melodic_starts = sorted(e.start_sec for e in melodic)
    onset_gaps = np.diff(melodic_starts)
    for gap in onset_gaps:
        gap_histogram[min(3, int(gap / 0.5))] += 1.0
    gap_total = float(gap_histogram.sum())
    if gap_total > 0:
        gap_histogram /= gap_total

    return np.concatenate([role_shape, scalars, pitch_histogram, gap_histogram])


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 1e-12 else vector


def repetition_score(composition: Composition, *, window_bars: int = 8) -> float:
    """0 = fully varied foreground, 100 = literal repetition. Deterministic.

    Windows are always ``window_bars`` bars long so resolution stays musical
    regardless of track length. Pairwise similarities are computed on
    *deviations from the track's mean window*, so the shared key/scale/role
    baseline cancels out and only genuine pattern repeats score high.
    """
    bar_sec = 60.0 / 90.0 if composition.bpm == 0 else 240.0 / composition.bpm
    duration = max(composition.duration_sec, 1e-6)
    window_sec = max(window_bars * bar_sec, 1.0)
    n_windows = int(np.ceil(duration / window_sec))
    if n_windows < 4:
        return 0.0

    events = composition.events()
    if not events:
        return 0.0
    vectors = [
        _normalize(_feature_vector(events, i * window_sec, (i + 1) * window_sec))
        for i in range(n_windows)
    ]
    mean_vector = np.mean(vectors, axis=0)
    deviations = [vector - mean_vector for vector in vectors]

    similarities: list[float] = []
    for i in range(n_windows):
        norm_i = float(np.linalg.norm(deviations[i]))
        for j in range(i + 2, n_windows):
            norm_j = float(np.linalg.norm(deviations[j]))
            if norm_i < 1e-9 and norm_j < 1e-9:
                similarity = 1.0
            elif norm_i < 1e-9 or norm_j < 1e-9:
                similarity = 0.0
            else:
                similarity = float(
                    np.dot(deviations[i], deviations[j]) / (norm_i * norm_j)
                )
            similarities.append(similarity)

    if not similarities:
        return 0.0
    top_fraction = max(1, int(round(0.15 * len(similarities))))
    top = sorted(similarities, reverse=True)[:top_fraction]
    score = float(np.clip(np.mean(top), -1.0, 1.0))
    return round(max(0.0, score) * 100.0, 2)
