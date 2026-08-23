"""Arranger integration tests (composition level, no audio rendering)."""
import pytest

from lfms.arranger import Arranger, repetition_score
from lfms.core.errors import ValidationError
from lfms.generator.plan import GenerationParameters, build_plan


def _params(**overrides):
    defaults = dict(
        seed=31337,
        duration_sec=600.0,
        genre="CINEMATIC",
        moods=("HOPEFUL",),
        intensity=55.0,
    )
    defaults.update(overrides)
    return GenerationParameters(**defaults)


def test_arranged_composition_has_sections_and_score():
    composition = Arranger(_params(), build_plan(_params())).arrange()
    assert len(composition.sections) >= 5
    assert composition.repetition_score is not None
    assert 0.0 <= composition.repetition_score <= 100.0
    assert composition.energy_curve_name == "DOCUMENTARY"


def test_energy_curve_preset_respected():
    params = _params(energy_curve="SLOW_BUILD")
    composition = Arranger(params, build_plan(params)).arrange()
    assert composition.energy_curve_name == "SLOW_BUILD"
    energies = [section.energy for section in composition.sections]
    assert energies[-1] > energies[0]


def test_invalid_curve_rejected_at_validation():
    with pytest.raises(ValidationError):
        _params(energy_curve="WAVEY").validate()


def test_intro_has_no_melody_outro_has_no_pulse():
    composition = Arranger(_params(), build_plan(_params())).arrange()
    intro = composition.sections[0]
    outro = composition.sections[-1]
    for event in composition.roles.get("MELODY", []):
        assert not (intro.start_sec <= event.start_sec < intro.end_sec)
    for event in composition.roles.get("PULSE", []):
        assert not (outro.start_sec <= event.start_sec < outro.end_sec)


def test_events_stay_within_duration_and_sorted():
    duration = 450.0
    params = _params(duration_sec=duration)
    composition = Arranger(params, build_plan(params)).arrange()
    for role in composition.role_names():
        events = composition.roles[role]
        starts = [event.start_sec for event in events]
        assert starts == sorted(starts)
        for event in events:
            assert 0.0 <= event.start_sec < duration
            assert event.end_sec <= duration + 1e-6


def test_arrangement_is_deterministic():
    params = _params()
    first = Arranger(params, build_plan(params)).arrange()
    second = Arranger(params, build_plan(params)).arrange()
    assert first.roles == second.roles
    assert first.sections == second.sections
    assert first.fingerprint == second.fingerprint


def test_arranged_scores_below_literal_repeat_threshold():
    for genre, mood in (("CINEMATIC", ("HOPEFUL",)), ("LOFI", ("CALM",))):
        params = _params(genre=genre, moods=mood, duration_sec=900.0)
        composition = Arranger(params, build_plan(params)).arrange()
        assert composition.repetition_score < 96.0, f"{genre}: {composition.repetition_score}"


def test_long_horizon_score_bounded():
    params = _params(seed=777000, duration_sec=3600.0, genre="DOCUMENTARY", intensity=50.0)
    composition = Arranger(params, build_plan(params)).arrange()
    assert 0.0 <= composition.repetition_score < 96.0
    assert len(composition.sections) >= 10


def test_custom_energy_points_flow_through():
    points = ((0.0, 0.9), (0.5, 0.1), (1.0, 0.9))
    params = _params(energy_points=points)
    composition = Arranger(params, build_plan(params)).arrange()
    assert composition.energy_curve_name == "USER"


def test_repetition_score_function_matches_composition_value():
    params = _params()
    composition = Arranger(params, build_plan(params)).arrange()
    recomputed = repetition_score(composition)
    assert recomputed == composition.repetition_score
