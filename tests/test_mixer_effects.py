"""Mixer effect DSP tests (EQ3, compressor, delay, reverb, chain, presets)."""
import numpy as np
import pytest

from lfms.audio_engine.dsp import band_energy, peak, rms
from lfms.audio_engine.effects import DriveEffect
from lfms.audio_engine.studio_fx import EqEffect
from lfms.core.errors import ValidationError
from lfms.mixer import (
    EFFECT_TYPES,
    CompressorEffect,
    DelayEffect,
    EffectChain,
    EQ3Effect,
    ReverbEffect,
    create_effect,
    known_chain_presets,
)

SR = 48000


def _sine(freq: float, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(SR * seconds), dtype=np.float64) / SR
    wave = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([wave, wave]).astype(np.float32)


def _energy_at(x: np.ndarray, lo: float, hi: float) -> float:
    return band_energy(x[0].astype(np.float64), SR, lo, hi)


def test_effect_param_validation():
    eq = EQ3Effect(SR)
    with pytest.raises(ValidationError):
        eq.set_param("low_gain_db", 40.0)
    with pytest.raises(ValidationError):
        eq.set_param("bogus", 1.0)
    comp = CompressorEffect(SR)
    with pytest.raises(ValidationError):
        CompressorEffect(SR, ratio=0.5)
    assert "ratio" in comp.params()


def test_create_effect_registry():
    assert set(EFFECT_TYPES) == {"EQ3", "COMPRESSOR", "DELAY", "REVERB"}
    for name in EFFECT_TYPES:
        effect = create_effect(name, SR)
        assert hasattr(effect, "process") and hasattr(effect, "reset")
    with pytest.raises(ValidationError):
        create_effect("FLANGER", SR)


def test_eq3_shapes_spectrum():
    eq = EQ3Effect(
        SR,
        low_hz=100.0,
        low_gain_db=-15.0,
        mid_gain_db=0.0,
        high_hz=6000.0,
        high_gain_db=6.0,
    )
    bass = _sine(80.0, 1.0)
    treble = _sine(9000.0, 1.0)
    out_bass = eq.process(bass)
    out_treble = eq.process(treble)
    in_bass = _energy_at(bass, 60.0, 120.0)
    in_treble = _energy_at(treble, 8000.0, 12000.0)
    assert _energy_at(out_bass, 60.0, 120.0) < in_bass * 0.35
    assert _energy_at(out_treble, 8000.0, 12000.0) > in_treble


def test_compressor_reduces_loud_peaks_and_leaves_quiet_alone():
    comp = CompressorEffect(
        SR, threshold_db=-20.0, ratio=4.0, attack_ms=2.0, release_ms=50.0, makeup_db=0.0
    )
    loud = _sine(440.0, 0.8, amp=0.9)
    quiet = _sine(440.0, 0.8, amp=0.05)
    out_loud = comp.process(loud)
    comp.reset()
    out_quiet = comp.process(quiet)
    # Measure steady-state (attack transient lives in the first ~10 ms).
    tail = slice(int(0.4 * SR), None)
    reduction = peak(out_loud[:, tail]) / peak(loud[:, tail])
    quiet_ratio = peak(out_quiet) / peak(quiet)
    assert 0.12 < reduction < 0.5
    assert quiet_ratio > 0.95


def test_compressor_makeup_boosts_output():
    comp = CompressorEffect(SR, threshold_db=-10.0, ratio=2.0, makeup_db=6.0)
    signal = _sine(330.0, 0.5, amp=0.05)
    assert peak(comp.process(signal)) > peak(signal)


def test_delay_adds_echo_tail():
    delay = DelayEffect(SR, time_ms=100.0, feedback=0.5, mix=0.6)
    burst = np.zeros((2, int(0.25 * SR)), dtype=np.float32)
    burst[:, : int(0.01 * SR)] = 0.8
    tail_start = int(0.12 * SR)
    dry_tail_before = float(np.sum(np.abs(burst[:, tail_start:])))
    wet = delay.process(burst)
    wet_tail = float(np.sum(np.abs(wet[:, tail_start:])))
    assert wet_tail > dry_tail_before + 0.01
    bounded = delay.process(_sine(220.0, 2.0, amp=0.45))
    assert peak(bounded) <= 1.0


def test_reverb_wets_signal_deterministically():
    reverb = ReverbEffect(SR, room_size=0.7, damping=0.3, wet=0.5)
    impulse = np.zeros((2, int(0.8 * SR)), dtype=np.float32)
    impulse[0, 0] = impulse[1, 0] = 0.7
    wet_a = reverb.process(impulse)
    reverb.reset()
    wet_b = reverb.process(impulse)
    assert np.array_equal(wet_a, wet_b)
    late = wet_a[:, int(0.2 * SR) :]
    assert rms(late) > 0.0
    assert peak(wet_a) <= 1.0


def test_effects_reset_restores_neutral_state():
    delay = DelayEffect(SR, time_ms=50.0, feedback=0.4, mix=0.5)
    silence = np.zeros((2, SR // 4), dtype=np.float32)
    first = delay.process(silence)
    assert float(np.max(np.abs(first))) == 0.0
    delay.process(_sine(500.0, 0.2))
    dirty = delay.process(silence)
    assert float(np.max(np.abs(dirty))) > 0.0
    delay.reset()
    clean = delay.process(silence)
    assert float(np.max(np.abs(clean))) == 0.0


def test_chain_ordering_move_remove_and_process():
    chain = EffectChain()
    chain.append("DELAY", SR, time_ms=30.0, mix=0.5)
    chain.append("COMPRESSOR", SR, threshold_db=-40.0)
    assert len(chain) == 2 and chain.types() == ("DELAY", "COMPRESSOR")
    chain.move(1, 0)
    assert chain.types() == ("COMPRESSOR", "DELAY")
    chain.set_param(1, "mix", 0.0)
    assert chain.slot(1).effect.mix == pytest.approx(0.0)
    removed = chain.remove(0)
    assert removed.effect_type == "COMPRESSOR"
    assert len(chain) == 1
    with pytest.raises(ValidationError):
        chain.move(0, 5)


def test_chain_from_preset_and_serialization_roundtrip():
    for preset in known_chain_presets():
        chain = EffectChain.from_preset(preset, SR)
        recipe = chain.to_dict()
        rebuilt = EffectChain.from_recipe(
            tuple((slot["type"], slot["params"]) for slot in recipe), SR
        )
        assert rebuilt.types() == chain.types()
        signal = _sine(700.0, 0.4)
        a = chain.process(signal)
        b = rebuilt.process(signal)
        assert np.array_equal(a, b)
        chain.reset()


def test_unknown_preset_raises():
    from lfms.mixer import preset_recipe

    with pytest.raises(ValidationError):
        preset_recipe("NOPE")
    with pytest.raises(ValidationError):
        EffectChain.from_preset("NOPE", SR)


def test_drive_effect_zero_is_neutral_and_high_adds_harmonics():
    sine = _sine(220.0, 0.5, amp=0.4)
    neutral = DriveEffect(drive=0.0).process(sine)
    assert np.array_equal(neutral, sine)
    heavy = DriveEffect(drive=1.0).process(sine)
    # Tanh saturation reshapes the wave (adds warmth/harmonics), never exceeds 1.0.
    assert not np.array_equal(heavy, sine)
    assert peak(heavy) <= 1.0
    # More drive means more reshaping.
    mid = DriveEffect(drive=0.3).process(sine)
    assert not np.array_equal(mid, sine)
    # Drive keeps the signal bounded regardless of drive level.
    for d in (0.1, 0.5, 1.0):
        assert peak(DriveEffect(drive=d).process(_sine(110.0, 0.5, amp=0.9))) <= 1.0
    # mix=0 keeps signal untouched.
    assert np.array_equal(DriveEffect(drive=1.0, mix=0.0).process(sine), sine)


def test_eq_high_shelf_boosts_and_cuts_treble():
    treble = _sine(9000.0, 1.0)
    boost = 4.0 * _energy_at(treble, 8000.0, 12000.0)
    eq_boost = EqEffect(SR, high_cutoff=5200.0, high_gain_db=5.0)
    eq_cut = EqEffect(SR, high_cutoff=5200.0, high_gain_db=-5.0)
    out_boost = eq_boost.process(treble)
    out_cut = eq_cut.process(treble)
    in_e = _energy_at(treble, 8000.0, 12000.0)
    assert _energy_at(out_boost, 8000.0, 12000.0) > in_e * 1.5
    assert _energy_at(out_cut, 8000.0, 12000.0) < in_e * 0.7
    assert boost > 0
