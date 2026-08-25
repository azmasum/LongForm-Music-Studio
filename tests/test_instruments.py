"""Instrument palette + seed-variety tests (v1.2 generator work)."""
from __future__ import annotations

import numpy as np
import pytest

from lfms.generator.events import NoteEvent
from lfms.generator.plan import GenerationParameters, build_plan, known_genres
from lfms.generator.voices import _VOICE_CLASSES, make_voice

_NEW_INSTRUMENTS = (
    "STRINGS", "CHOIR", "ORGAN", "EPIANO", "MARIMBA",
    "NYLON", "SAW_BASS", "SNARE",
)


@pytest.mark.parametrize("instrument", list(_VOICE_CLASSES))
def test_every_registered_voice_renders_non_silence(instrument) -> None:
    note = NoteEvent(
        start_sec=0.0, duration_sec=0.4, midi=60, velocity=90.0,
        role="TEST", instrument=instrument,
    )
    voice = make_voice(instrument, 22050, note, {"brightness_hz": 2000.0}, rng_seed=7)
    chunks = [voice.process(1024) for _ in range(12)]
    signal = np.concatenate(chunks)
    assert float(np.sqrt(np.mean(signal ** 2))) > 1e-3
    assert np.all(np.isfinite(signal))


def test_seeded_voices_are_deterministic() -> None:
    for instrument in ("HAT", "NYLON", "SNARE"):
        outputs = []
        for _ in range(2):
            note = NoteEvent(
                start_sec=0.0, duration_sec=0.3, midi=50, velocity=80.0,
                role="TEST", instrument=instrument,
            )
            voice = make_voice(instrument, 22050, note, {}, rng_seed=99)
            outputs.append(np.concatenate([voice.process(512) for _ in range(16)]))
        assert np.array_equal(outputs[0], outputs[1])


def test_nylon_uses_karplus_strong_cache() -> None:
    note = NoteEvent(
        start_sec=0.0, duration_sec=0.5, midi=64, velocity=85.0,
        role="MELODY", instrument="NYLON",
    )
    voice = make_voice("NYLON", 22050, note, {}, rng_seed=5)
    assert hasattr(voice, "_cache")
    first = voice.process(4096).copy()
    second = voice.process(4096)
    assert not np.array_equal(first, second)  # streaming forward through cache


def test_plan_instruments_vary_with_seed_within_genre() -> None:
    melodies: set[str] = set()
    pads: set[str] = set()
    basses: set[str] = set()
    for seed in range(1, 17):
        plan = build_plan(
            GenerationParameters(seed=seed, duration_sec=30.0, genre="AMBIENT",
                                 moods=("NEUTRAL",), intensity=45.0)
        )
        family_ok = {
            "melody": ("PLUCK", "BELL", "MARIMBA", "NYLON"),
            "pad": ("PAD", "STRINGS", "CHOIR"),
            "bass": ("BASS", "SAW_BASS"),
        }
        assert plan.melody_instrument in family_ok["melody"]
        assert plan.pad_instrument in family_ok["pad"]
        assert plan.bass_instrument in family_ok["bass"]
        melodies.add(plan.melody_instrument)
        pads.add(plan.pad_instrument)
        basses.add(plan.bass_instrument)
    # with 4/3/2 choices over 16 seeds, seeing only one value is ~impossible
    assert len(melodies) >= 2
    assert len(pads) >= 2
    assert len(basses) >= 2


def test_all_genres_have_complete_families() -> None:
    from lfms.generator.plan import _INSTRUMENT_FAMILIES

    for genre in known_genres():
        family = _INSTRUMENT_FAMILIES[genre]
        for key in ("melody", "pad", "bass"):
            choices = family[key]
            assert choices, f"{genre}.{key} empty"
            for name in choices:
                assert name in _VOICE_CLASSES, f"{genre}: unknown voice {name}"


def test_snare_flag_needs_pulse() -> None:
    loud = build_plan(
        GenerationParameters(seed=11, duration_sec=20.0, genre="ELECTRONIC",
                             moods=("ENERGETIC",), intensity=95.0)
    )
    quiet = build_plan(
        GenerationParameters(seed=11, duration_sec=20.0, genre="MEDITATION",
                             moods=("CALM",), intensity=10.0)
    )
    assert isinstance(loud.perc_snare, bool)
    assert quiet.perc_snare is False


def test_compositions_differ_across_seeds(tmp_path) -> None:

    fingerprints: set[str] = set()
    lead_instruments: set[str] = set()
    for seed in (101, 202):
        params = GenerationParameters(seed=seed, duration_sec=6.0,
                                      genre="CINEMATIC", moods=("WARM",),
                                      intensity=55.0)
        composition = build_plan(params) and __import__(
            "lfms.generator.composer", fromlist=["Composer"]
        ).Composer(params).compose()
        fingerprints.add(composition.fingerprint)
        melody_events = composition.roles.get("MELODY", [])
        if melody_events:
            lead_instruments.update(e.instrument for e in melody_events)
    assert len(fingerprints) == 2
