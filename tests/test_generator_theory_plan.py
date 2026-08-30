"""Theory + plan builder tests."""
import pytest

from lfms.core.errors import ValidationError
from lfms.generator.plan import GenerationParameters, build_plan, known_genres
from lfms.generator.theory import (
    chord_pitch_classes,
    chord_quality_name,
    midi_to_freq,
    progression_pool_for_mode,
    scale_pitch_classes,
    voicing_for_chord,
)


def test_scale_pitch_classes_c_major():
    assert scale_pitch_classes(0, "MAJOR") == [0, 2, 4, 5, 7, 9, 11]


def test_scale_pitch_classes_a_minor():
    assert scale_pitch_classes(9, "MINOR") == [9, 11, 0, 2, 4, 5, 7]


def test_chord_degree_qualities_major_scale():
    c_major_triads = [chord_pitch_classes(0, "MAJOR", d) for d in range(7)]
    qualities = [chord_quality_name(chord) for chord in c_major_triads]
    assert qualities == ["maj", "min", "min", "maj", "maj", "min", "dim"]


def test_chord_with_seventh_has_four_notes():
    chord = chord_pitch_classes(0, "MAJOR", 0, seventh=True)
    assert len(chord) == 4


def test_midi_to_freq_a4():
    assert midi_to_freq(69) == pytest.approx(440.0, rel=1e-9)


def test_voicing_ascends_and_centers():
    voicing = voicing_for_chord([0, 4, 7], center_midi=60)
    assert voicing == sorted(voicing)
    assert abs(voicing[0] - 60) <= 12


def test_voicing_rotation_changes_bass():
    root_pos = voicing_for_chord([0, 4, 7], center_midi=60, bass_rotation=0)
    first_inv = voicing_for_chord([0, 4, 7], center_midi=60, bass_rotation=1)
    assert root_pos[0] % 12 == 0
    assert first_inv[0] % 12 == 4


def test_progression_pool_known_and_fallback():
    assert progression_pool_for_mode("MINOR")
    assert progression_pool_for_mode("LYDIAN") == progression_pool_for_mode("MINOR")


def _params(**overrides):
    defaults = dict(
        seed=123456789,
        duration_sec=300.0,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=50.0,
    )
    defaults.update(overrides)
    return GenerationParameters(**defaults)


def test_build_plan_is_deterministic():
    a = build_plan(_params())
    b = build_plan(_params())
    assert a.fingerprint == b.fingerprint
    assert a.bpm == b.bpm
    assert a.key_root_pc == b.key_root_pc
    assert a.key_mode == b.key_mode


def test_explicit_bpm_and_key_respected():
    plan = build_plan(_params(bpm=101, key_root="F#", key_mode="DORIAN"))
    assert plan.bpm == 101
    assert plan.key_name == "F# Dorian"


def test_higher_intensity_raises_density():
    low = build_plan(_params(intensity=10.0))
    high = build_plan(_params(intensity=90.0))
    assert high.density > low.density
    assert high.pulse_level >= low.pulse_level


def test_horror_is_darker_than_ambient():
    horror = build_plan(_params(genre="HORROR", moods=("NEUTRAL",)))
    ambient = build_plan(_params(genre="AMBIENT", moods=("NEUTRAL",)))
    assert horror.register_center < ambient.register_center
    assert horror.brightness_hz < ambient.brightness_hz


def test_dark_mood_lowers_register_and_brightness():
    neutral = build_plan(_params(moods=("NEUTRAL",)))
    dark = build_plan(_params(moods=("DARK",)))
    assert dark.register_center < neutral.register_center
    assert dark.brightness_hz < neutral.brightness_hz


def test_invalid_inputs_raise_validation_error():
    with pytest.raises(ValidationError):
        build_plan(_params(genre="NOT_A_GENRE"))
    with pytest.raises(ValidationError):
        build_plan(_params(intensity=150.0))
    with pytest.raises(ValidationError):
        build_plan(_params(duration_sec=0.0))
    with pytest.raises(ValidationError):
        build_plan(_params(moods=("NOPE",)))


def test_all_genres_have_profiles():
    for genre in known_genres():
        plan = build_plan(_params(genre=genre, duration_sec=30.0))
        assert plan.bar_sec > 0


def test_new_style_controls_defaults_and_wiring():
    plan = build_plan(_params())
    assert plan.drop_intensity == 50.0
    assert plan.bass_distortion == 0.0
    assert plan.supersaw_brightness == 50.0
    assert plan.sidechain_amount == 100.0
    custom = build_plan(
        _params(
            drop_intensity=80.0,
            bass_distortion=60.0,
            supersaw_brightness=20.0,
            sidechain_amount=40.0,
        )
    )
    assert custom.drop_intensity == 80.0
    assert custom.bass_distortion == 60.0
    assert custom.supersaw_brightness == 20.0
    assert custom.sidechain_amount == 40.0


def test_new_style_controls_range_validation():
    for name, bad in (
        ("drop_intensity", 101.0),
        ("bass_distortion", -1.0),
        ("supersaw_brightness", 150.0),
        ("sidechain_amount", -5.0),
    ):
        with pytest.raises(ValidationError):
            build_plan(_params(**{name: bad}))
