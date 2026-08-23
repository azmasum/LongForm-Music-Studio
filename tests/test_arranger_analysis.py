"""Repetition score analysis tests."""
from lfms.arranger.analysis import repetition_score
from lfms.generator.events import Composition, NoteEvent


def _composition(events: list[NoteEvent], duration: float, bpm: int = 90) -> Composition:
    composition = Composition(plan_fingerprint="TEST", duration_sec=duration)
    composition.bpm = bpm
    composition.roles = {"MELODY": events}
    return composition


def test_literal_repeat_scores_maximum():
    events = [
        NoteEvent(
            start_sec=window * 20.0 + (i % 4) * 5.0,
            duration_sec=1.0,
            midi=60 + (i % 3) * 4,
            velocity=70.0,
            role="MELODY",
            instrument="PLUCK",
        )
        for window in range(6)
        for i in range(12)
    ]
    score = repetition_score(_composition(events, 120.0))
    assert score >= 99.0


def test_progressively_varied_scores_low():
    events = []
    for window in range(6):
        count = 4 + window * 5
        for i in range(count):
            events.append(
                NoteEvent(
                    start_sec=window * 20.0 + i * (20.0 / count),
                    duration_sec=0.4 + 0.08 * window,
                    midi=((55 + window * 2 + i * 3) % 24) + 48,
                    velocity=float(35 + 9 * window),
                    role="MELODY",
                    instrument="PLUCK",
                )
            )
    score = repetition_score(_composition(events, 120.0))
    assert score <= 40.0


def test_short_compositions_score_zero():
    events = [NoteEvent(i * 0.5, 0.4, 60 + i, 70.0, "MELODY", "PLUCK") for i in range(6)]
    assert repetition_score(_composition(events, 3.0)) == 0.0


def test_empty_composition_scores_zero():
    composition = Composition(plan_fingerprint="EMPTY", duration_sec=120.0)
    composition.bpm = 90
    assert repetition_score(composition) == 0.0


def test_score_is_bounded_and_deterministic():
    events = [
        NoteEvent(i * 0.75, 0.5, 55 + (i * 7) % 12, 60.0, "MELODY", "PLUCK")
        for i in range(200)
    ]
    composition = _composition(events, 150.0)
    first = repetition_score(composition)
    second = repetition_score(composition)
    assert 0.0 <= first <= 100.0
    assert first == second
