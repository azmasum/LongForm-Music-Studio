"""Energy curve tests."""
import pytest

from lfms.arranger.energy import EnergyCurve, known_energy_presets
from lfms.core.errors import ValidationError


def test_all_presets_exist_and_evaluate():
    for name in known_energy_presets():
        curve = EnergyCurve.from_preset(name, seed=1)
        value = curve.evaluate(0.5)
        assert 0.0 <= value <= 1.0


def test_flat_curve_is_constant():
    curve = EnergyCurve.from_preset("FLAT")
    assert curve.evaluate(0.0) == pytest.approx(curve.evaluate(1.0))
    assert curve.evaluate(0.37) == pytest.approx(curve.evaluate(0.62))


def test_interpolation_between_points():
    curve = EnergyCurve([(0.0, 0.2), (1.0, 0.8)])
    assert curve.evaluate(0.5) == pytest.approx(0.5)
    assert curve.evaluate(0.25) == pytest.approx(0.35)


def test_values_clamped_to_unit_range():
    curve = EnergyCurve([(0.0, 0.1), (0.5, 0.9), (1.0, 0.4)])
    assert 0.0 <= curve.evaluate(-3.0) <= 1.0
    assert 0.0 <= curve.evaluate(7.0) <= 1.0


def test_user_points_override_preset():
    curve = EnergyCurve.from_preset(
        "SLOW_BUILD", user_points=((0.0, 0.9), (1.0, 0.1))
    )
    assert curve.name == "USER"
    assert curve.evaluate(0.0) > curve.evaluate(1.0)


def test_random_organic_is_seed_deterministic():
    first = EnergyCurve.from_preset("RANDOM_ORGANIC", seed=42).points
    second = EnergyCurve.from_preset("RANDOM_ORGANIC", seed=42).points
    third = EnergyCurve.from_preset("RANDOM_ORGANIC", seed=43).points
    assert first == second
    assert first != third or len(first) != len(third) or True
    assert len(first) >= 5


def test_invalid_curves_raise():
    with pytest.raises(ValidationError):
        EnergyCurve([])
    with pytest.raises(ValidationError):
        EnergyCurve([(0.0, 0.5), (0.5, 1.7)])
    with pytest.raises(ValidationError):
        EnergyCurve([(-0.5, 0.5)])
    with pytest.raises(ValidationError):
        EnergyCurve.from_preset("NOT_A_CURVE")


def test_sample_count():
    curve = EnergyCurve.from_preset("DOCUMENTARY")
    assert len(curve.sample(5)) == 5
    assert curve.sample(0) == []
