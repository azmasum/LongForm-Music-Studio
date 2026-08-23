"""Mastering & QC tests: BS.1770 measurement, auto-master, QC gates."""
from __future__ import annotations

import numpy as np
import pytest

from lfms.core.errors import ValidationError
from lfms.mastering import (
    QCSpec,
    TruePeakLimiter,
    auto_master,
    known_target_presets,
    measure,
    resolve_target_preset,
    run_qc,
)

SR = 48000


def _sine(freq: float, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    tone = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([tone, tone])


# ----------------------------------------------------------- measurement

def test_reference_sine_loudness_matches_bs1770_anchor():
    # -20 dBFS 997 Hz stereo sine -> ~-20.0 LUFS: K-weighting is +0.69 dB at
    # 1 kHz, which cancels the standard's -0.691 offset (verified against the
    # published 48 kHz filter coefficients).
    m = measure(_sine(997.0, 3.0, amp=10 ** (-20 / 20)), SR)
    assert abs(m.integrated_lufs - (-20.0)) < 0.3
    assert abs(m.true_peak_dbtp - (-20.0)) < 0.3
    assert abs(m.sample_peak_dbfs - (-20.0)) < 0.01


def test_mono_sine_is_querier_than_stereo_by_3db():
    t = np.arange(int(SR * 3)) / SR
    mono = (0.1 * np.sin(2 * np.pi * 997 * t)).astype(np.float32)[None, :]
    stereo = np.stack([mono[0]] * 2)
    lm, ls = measure(mono, SR), measure(stereo, SR)
    assert abs((ls.integrated_lufs - lm.integrated_lufs) - 3.01) < 0.2


def test_relative_gate_ignores_quiet_tail():
    loud = _sine(997.0, 4.0, amp=10 ** (-16 / 20))
    tail = _sine(997.0, 4.0, amp=10 ** (-50 / 20))
    both = np.concatenate([loud, tail], axis=1)
    m = measure(both, SR)
    assert abs(m.integrated_lufs - (-16.0)) < 0.5
    assert m.duration_sec == pytest.approx(8.0)


def test_momentary_and_short_term_track_transients():
    # burst must outlast the 3 s short-term window for ST max to reach it
    burst = _sine(997.0, 3.5, amp=0.5)
    quiet = _sine(997.0, 2.5, amp=0.02)
    m = measure(np.concatenate([burst, quiet], axis=1), SR)
    assert m.momentary_max_lufs >= m.short_term_max_lufs - 0.1
    assert abs(m.short_term_max_lufs - (-6.72)) < 0.8
    assert m.integrated_lufs <= m.short_term_max_lufs + 0.15


def test_true_peak_exceeds_sample_peak_on_square_wave():
    t = np.arange(int(SR * 2)) / SR
    square = (0.9 * np.sign(np.sin(2 * np.pi * 997 * t))).astype(np.float32)
    audio = np.stack([square] * 2)
    m = measure(audio, SR)
    assert m.true_peak_dbtp > m.sample_peak_dbfs + 0.1


def test_measure_rejects_bad_input():
    with pytest.raises(ValidationError):
        measure(np.zeros(100), SR)
    with pytest.raises(ValidationError):
        measure(np.zeros((2, 0)), SR)
    with pytest.raises(ValidationError):
        measure(np.zeros((2, 100)), 0)


def test_measurement_is_deterministic():
    audio = _sine(440.0, 2.5) + _sine(1234.0, 2.5, amp=0.2)
    a, b = measure(audio, SR), measure(audio, SR)
    assert a.to_dict() == b.to_dict()


# ------------------------------------------------------------ auto-master

def test_preset_registry_resolves_case_insensitively():
    assert "YOUTUBE" in known_target_presets()
    p = resolve_target_preset("youtube")
    assert p.target_lufs == -14.0 and p.ceiling_dbtp == -1.0
    with pytest.raises(ValidationError):
        resolve_target_preset("NOPE")


def test_auto_master_raises_quiet_file_to_target():
    audio = _sine(220.0, 8.0, amp=10 ** (-30 / 20))
    result = auto_master(audio, SR, "YOUTUBE")
    assert abs(result.after.integrated_lufs - (-14.0)) < 0.6
    assert result.total_gain_db == pytest.approx(16.0, abs=1.0)
    assert not result.limiter_engaged
    assert result.hit_target()


def test_auto_master_limits_hot_peaky_material():
    # ~3% duty-cycle square bursts: quiet overall, peaks near full scale.
    # Gain-up alone would break the ceiling -> limiter must engage while the
    # secant search lands the integrated loudness on target.
    n = int(SR * 6)
    audio = np.zeros((2, n), dtype=np.float32)
    for start in range(0, n - int(0.01 * SR), SR // 3):
        idx = slice(start, start + int(0.01 * SR))
        audio[:, idx] = 0.95 * np.sign(
            np.sin(2 * np.pi * 997 * np.arange(idx.stop - idx.start) / SR)
        )
    result = auto_master(audio, SR, "YOUTUBE")
    assert result.limiter_engaged
    assert result.after.true_peak_dbtp <= -0.95
    assert abs(result.after.integrated_lufs - (-14.0)) < 1.2
    assert result.hit_target(tolerance=1.2)
    assert result.under_ceiling()


def test_auto_master_stops_honestly_at_the_loudness_ceiling():
    # 2% duty bursts: physically cannot reach -14 LUFS @ -1 dBTP; the
    # algorithm must protect the ceiling and stop instead of diverging.
    n = int(SR * 6)
    audio = np.zeros((2, n), dtype=np.float32)
    for start in range(0, n - int(0.01 * SR), int(0.5 * SR)):
        idx = slice(start, start + int(0.01 * SR))
        audio[:, idx] = 0.95 * np.sign(
            np.sin(2 * np.pi * 997 * np.arange(idx.stop - idx.start) / SR)
        )
    result = auto_master(audio, SR, "YOUTUBE")
    assert result.limiter_engaged
    assert result.after.true_peak_dbtp <= -0.95
    assert result.after.integrated_lufs <= -14.0  # never overshoots target
    assert result.after.integrated_lufs >= -16.5  # but gets close to ceiling


def test_auto_master_is_deterministic():
    audio = _sine(330.0, 5.0) + _sine(2000.0, 5.0, amp=0.3)
    r1 = auto_master(audio, SR, "PODCAST")
    r2 = auto_master(audio, SR, "PODCAST")
    assert np.array_equal(r1.output, r2.output)
    assert r1.total_gain_db == r2.total_gain_db


def test_auto_master_all_presets_hit_their_targets():
    audio = _sine(261.6, 8.0, amp=0.25)
    for name in known_target_presets():
        result = auto_master(audio, SR, name)
        target = resolve_target_preset(name)
        assert abs(result.after.integrated_lufs - target.target_lufs) < 0.8, name
        assert result.after.true_peak_dbtp <= target.ceiling_dbtp + 0.06, name


def test_auto_master_rejects_silence():
    with pytest.raises(ValidationError):
        auto_master(np.zeros((2, SR)), SR, "YOUTUBE")


def test_true_peak_limiter_caps_output_and_resets():
    limiter = TruePeakLimiter(SR, ceiling_dbtp=-1.0)
    hot = (_sine(997.0, 1.0, amp=1.4)).astype(np.float32)
    out = limiter.process(hot)
    from lfms.mastering.measure import measure as _m
    m = _m(out, SR)
    assert m.true_peak_dbtp <= -0.9
    limiter.reset()
    again = limiter.process(hot[: SR // 10])
    m2 = _m(again, SR)
    assert m2.true_peak_dbtp <= -0.85
    with pytest.raises(ValidationError):
        TruePeakLimiter(SR, ceiling_dbtp=5.0)


# ------------------------------------------------------------------- QC

def test_qc_passes_clean_mastered_audio():
    audio = _sine(440.0, 5.0, amp=0.28)
    mastered = auto_master(audio, SR, "YOUTUBE")
    report = run_qc(mastered.output, SR)
    assert report.status == "READY"
    assert report.passed
    d = report.to_dict()
    assert d["status"] == "READY" and len(d["checks"]) >= 6


def test_qc_flags_each_violation_type():
    good = _sine(440.0, 3.0, amp=0.28)

    hot = (good * 3.4).astype(np.float32)
    rep = run_qc(hot, SR, QCSpec(lufs_range=None))
    assert not rep.passed and any(c.name == "true_peak_dbtp" for c in rep.failed_checks())

    quiet = (good * 0.001).astype(np.float32)
    rep = run_qc(quiet, SR, QCSpec(max_true_peak_dbtp=-0.1))
    assert any(c.name == "integrated_lufs" for c in rep.failed_checks())

    dc = good.copy()
    dc[0] += 0.05
    rep = run_qc(dc.astype(np.float32), SR, QCSpec())
    assert any(c.name == "dc_offset" for c in rep.failed_checks())

    clipped = good.copy()
    clipped[:, :100] = 1.2
    rep = run_qc(clipped, SR, QCSpec(lufs_range=None))
    assert any(c.name == "clipped_samples" for c in rep.failed_checks())

    silent = np.zeros((2, SR), dtype=np.float32)
    rep = run_qc(silent, SR, QCSpec(lufs_range=None))
    assert any(c.name == "silence_fraction" for c in rep.failed_checks())

    lopsided = np.stack([good[0], np.zeros_like(good[0])])
    rep = run_qc(lopsided.astype(np.float32), SR, QCSpec(lufs_range=None))
    assert any(c.name == "stereo_balance_db" for c in rep.failed_checks())

    rep = run_qc(good[:, : SR // 4], SR, QCSpec(min_duration_sec=1.0, lufs_range=None))
    assert any(c.name == "duration_sec" for c in rep.failed_checks())


def test_qc_spec_validates_thresholds():
    with pytest.raises(ValidationError):
        QCSpec(max_true_peak_dbtp=1.0).validate()
    with pytest.raises(ValidationError):
        QCSpec(lufs_range=(-10.0, -20.0)).validate()
    with pytest.raises(ValidationError):
        QCSpec(clip_threshold=1.0).validate()
    QCSpec(lufs_range=None).validate()  # disabling range check is fine


def test_run_qc_rejects_empty_audio():
    with pytest.raises(ValidationError):
        run_qc(np.zeros((2, 0)), SR)
