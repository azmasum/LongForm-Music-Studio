"""Harmony, melody and composer structure tests."""
import pytest

from lfms.generator.composer import Composer, PulseGenerator
from lfms.generator.harmony import HarmonyGenerator
from lfms.generator.melody import MelodyGenerator
from lfms.generator.plan import GenerationParameters, build_plan
from lfms.generator.theory import scale_pitch_classes


def _params(**overrides):
    defaults = dict(
        seed=987654321,
        duration_sec=120.0,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=50.0,
    )
    defaults.update(overrides)
    return GenerationParameters(**defaults)


def test_chords_cover_duration_exactly():
    plan = build_plan(_params(duration_sec=97.3))
    chords = HarmonyGenerator(plan).generate()
    assert chords[0].start_sec == 0.0
    assert chords[-1].end_sec == pytest.approx(97.3, abs=1e-6)
    for a, b in zip(chords, chords[1:], strict=False):
        assert a.end_sec == pytest.approx(b.start_sec, abs=1e-6)


def test_chord_tones_stay_in_scale():
    plan = build_plan(_params())
    scale = set(scale_pitch_classes(plan.key_root_pc, plan.key_mode))
    for chord in HarmonyGenerator(plan).generate():
        assert set(chord.pitch_classes) <= scale


def test_harmony_is_deterministic():
    plan = build_plan(_params())
    first = HarmonyGenerator(plan).generate()
    second = HarmonyGenerator(plan).generate()
    assert [(c.start_sec, c.degree) for c in first] == [
        (c.start_sec, c.degree) for c in second
    ]


def test_melody_pitches_stay_in_scale():
    plan = build_plan(_params(genre="PIANO", intensity=70.0, duration_sec=90.0))
    scale = set(scale_pitch_classes(plan.key_root_pc, plan.key_mode))
    chords = HarmonyGenerator(plan).generate()
    events = MelodyGenerator(plan).generate(chords)
    assert events
    for event in events:
        assert event.midi % 12 in scale
        assert 15.0 <= event.velocity <= 115.0
        assert 0.0 <= event.start_sec
        assert event.end_sec <= plan.duration_sec + 1e-6


def test_melody_empty_when_probability_zero():
    plan = build_plan(_params())
    plan.melody_probability = 0.0
    chords = HarmonyGenerator(plan).generate()
    assert MelodyGenerator(plan).generate(chords) == []


def test_melody_is_deterministic():
    plan = build_plan(_params(genre="PIANO", intensity=60.0))
    chords = HarmonyGenerator(plan).generate()
    first = MelodyGenerator(plan).generate(chords)
    second = MelodyGenerator(plan).generate(chords)
    assert first == second


def test_pulse_generator_silent_at_low_level():
    plan = build_plan(_params(genre="AMBIENT", intensity=5.0))
    if plan.pulse_level >= 0.03:
        plan.pulse_level = 0.0
    assert PulseGenerator(plan).generate() == []


def test_composer_produces_core_roles():
    composition = Composer(_params(genre="CINEMATIC", intensity=55.0)).compose()
    roles = composition.role_names()
    assert "PAD" in roles
    assert "BASS" in roles
    assert "MELODY" in roles
    assert composition.total_events() > 0


def test_composer_events_sorted_and_clipped():
    duration = 61.7
    composition = Composer(_params(genre="ELECTRONIC", intensity=85.0, duration_sec=duration)).compose()
    for role in composition.role_names():
        events = composition.roles[role]
        starts = [e.start_sec for e in events]
        assert starts == sorted(starts)
        for event in events:
            assert 0.0 <= event.start_sec < duration
            assert event.duration_sec > 0
            assert event.end_sec <= duration + 1e-6


def test_composer_fingerprint_format_and_stability():
    first = Composer(_params()).compose()
    second = Composer(_params()).compose()
    assert first.fingerprint.startswith("LFMS-")
    assert len(first.fingerprint) == len("LFMS-XXXX-XXXX-XXXX")
    assert first.fingerprint == second.fingerprint


def test_different_seed_changes_events():
    first = Composer(_params(seed=1)).compose()
    second = Composer(_params(seed=2)).compose()
    differs = any(
        first.roles.get(role) != second.roles.get(role)
        for role in ("MELODY", "BASS", "SPARKLE")
    )
    assert differs


@pytest.mark.parametrize("genre", ["AMBIENT", "CALM", "MEDITATION", "RELAXATION", "NATURE"])
def test_calm_genres_never_go_shrill(genre):
    """Lead ≤ G5 and sparkle ≤ C6 for calm genres across seeds (no piercing)."""
    from lfms.generator.melody import CALM_MELODY_CEILING, CALM_SPARKLE_CEILING

    for seed in (1, 7, 42, 99, 2024, 20260911):
        composition = Composer(
            _params(seed=seed, genre=genre, duration_sec=600.0)
        ).compose()
        for event in composition.roles.get("MELODY", []):
            assert event.midi <= CALM_MELODY_CEILING, (genre, seed, event.midi)
        for event in composition.roles.get("SPARKLE", []):
            assert event.midi <= CALM_SPARKLE_CEILING, (genre, seed, event.midi)


def test_energetic_genres_keep_full_register():
    """The calm cap must not dull energetic genres; cap helper is a no-op."""
    from lfms.generator.melody import cap_register

    assert cap_register(96, "ELECTRONIC", 79) == 96
    assert cap_register(96, "MEDITATION", 79) == 79
    highs = []
    for seed in (1, 7, 42, 99, 2024, 20260911):
        composition = Composer(
            _params(seed=seed, genre="ELECTRONIC", duration_sec=600.0)
        ).compose()
        highs.extend(e.midi for e in composition.roles.get("MELODY", []))
    assert max(highs) > 79
