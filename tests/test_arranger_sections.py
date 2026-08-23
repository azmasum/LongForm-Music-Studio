"""Section planner tests."""
import pytest

from lfms.arranger.energy import EnergyCurve
from lfms.arranger.sections import ROLE_GATES, SectionPlanner, slice_chords
from lfms.generator.events import ChordSegment


def _planner(duration: float, bar_sec: float = 2.0, seed: int = 7) -> SectionPlanner:
    return SectionPlanner(
        curve=EnergyCurve.from_preset("DOCUMENTARY"),
        bar_sec=bar_sec,
        duration_sec=duration,
        seed=seed,
    )


def test_short_track_is_single_section():
    spans = _planner(45.0).plan()
    assert len(spans) == 1
    assert spans[0].section_type == "THEME_A"
    assert spans[0].start_sec == 0.0
    assert spans[0].end_sec == pytest.approx(45.0)


def test_long_track_covers_duration_with_intro_outro():
    duration = 1200.0
    spans = _planner(duration, bar_sec=2.0, seed=11).plan()
    assert spans[0].section_type == "INTRO"
    assert spans[-1].section_type in ("OUTRO", "THEME_A", "VARIATION_A", "THEME_B", "DEVELOPMENT")
    assert spans[0].start_sec == 0.0
    assert spans[-1].end_sec == pytest.approx(duration, abs=1e-6)
    for a, b in zip(spans, spans[1:], strict=False):
        assert a.end_sec == pytest.approx(b.start_sec, abs=1e-6)


def test_sections_are_bar_aligned():
    bar = 2.0
    spans = _planner(900.0, bar_sec=bar).plan()
    for span in spans[:-1]:
        remainder = span.duration_sec / bar
        assert abs(remainder - round(remainder)) < 1e-6 or span is spans[-1]


def test_middle_cycles_contain_theme_and_contrast():
    duration = 1500.0
    spans = _planner(duration).plan()
    middle = [s.section_type for s in spans[1:-1]]
    assert len(middle) >= 3
    assert any(t.startswith("THEME") for t in middle)
    assert any(not t.startswith("THEME") for t in middle)


def test_role_gates_thin_breakdown_and_intro():
    assert "PULSE" not in ROLE_GATES["BREAKDOWN"]
    assert "BASS" not in ROLE_GATES["BREAKDOWN"]
    assert "MELODY" not in ROLE_GATES["INTRO"]
    assert "PULSE" not in ROLE_GATES["OUTRO"]
    assert "MELODY" in ROLE_GATES["THEME_A"]


def test_slice_chords_trims_and_offsets():
    chords = [
        ChordSegment(start_sec=0.0, duration_sec=10.0, degree=1, pitch_classes=(0, 3, 7)),
        ChordSegment(start_sec=10.0, duration_sec=10.0, degree=5, pitch_classes=(7, 11, 2)),
    ]
    from lfms.arranger.sections import SectionSpan

    span = SectionSpan("THEME_A", start_sec=5.0, duration_sec=8.0, energy=0.5, index=1)
    sliced = slice_chords(chords, span)
    assert len(sliced) == 2
    assert sliced[0].start_sec == pytest.approx(0.0)
    assert sliced[0].duration_sec == pytest.approx(5.0)
    assert sliced[1].start_sec == pytest.approx(5.0)
    assert sliced[-1].end_sec == pytest.approx(8.0)


def test_planner_deterministic():
    first = _planner(800.0, seed=99).plan()
    second = _planner(800.0, seed=99).plan()
    assert first == second
