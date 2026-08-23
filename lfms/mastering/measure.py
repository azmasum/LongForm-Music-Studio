"""ITU-R BS.1770-4 loudness & true-peak measurement.

Implements K-weighting (pre-filter shelf + RLB high-pass), gated integrated
loudness, momentary/short-term maxima, oversampled true peak, sample peak
and plain RMS. Deterministic, works on ``(channels, n)`` float arrays at any
sample rate (biquad coefficients are recomputed per fs).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.signal import resample_poly

from lfms.core.errors import ValidationError

BLOCK_SEC = 0.400
HOP_SEC = 0.100
SHORT_TERM_SEC = 3.000
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = 10.0
UNMEASURABLE_LUFS = -120.0
TRUE_PEAK_OVERSAMPLE = 4

_CHANNEL_GAINS = (1.0, 1.0, 1.0, 1.41, 1.41)


def _validate_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    sr = int(sample_rate)
    if sr <= 0:
        raise ValidationError("sample_rate must be positive")
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim != 2:
        raise ValidationError("audio must be shaped (channels, frames)")
    return arr


def _k_weight_coeffs(sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Stage-1 high shelf + stage-2 RLB high-pass coefficients (BS.1770)."""
    fs = float(sample_rate)

    f0 = 1681.9744509555319
    gain_db = 3.999843853973347
    q = 0.7071752369554196
    k = float(np.tan(np.pi * f0 / fs))
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf_b = np.array(
        [
            (vh + vb * k / q + k * k) / a0,
            2.0 * (k * k - vh) / a0,
            (vh - vb * k / q + k * k) / a0,
        ]
    )
    shelf_a = np.array(
        [1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0]
    )

    f0 = 38.13547087602444
    q = 0.5003270373238773
    k = float(np.tan(np.pi * f0 / fs))
    denom = 1.0 + k / q + k * k
    hpf_b = np.array([1.0, -2.0, 1.0])
    hpf_a = np.array([denom, 2.0 * (k * k - 1.0), (1.0 - k / q + k * k)]) / denom

    return shelf_b, shelf_a, hpf_b, hpf_a


def _k_weight(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    from scipy.signal import lfilter

    sb, sa, hb, ha = _k_weight_coeffs(sample_rate)
    out = np.empty_like(audio)
    for ch in range(audio.shape[0]):
        stage1 = lfilter(sb, sa, audio[ch])
        out[ch] = lfilter(hb, ha, stage1)
    return out


def _block_mean_squares(
    weighted: np.ndarray, block_len: int, hop: int
) -> np.ndarray:
    """Mean square per channel per block, computed with cumulative sums."""
    n = weighted.shape[1]
    if n < block_len:
        return np.zeros((0, weighted.shape[0]))
    sq = np.concatenate(
        (np.zeros((weighted.shape[0], 1)), np.cumsum(weighted**2, axis=1)),
        axis=1,
    )
    starts = np.arange(0, n - block_len + 1, hop)
    ends = starts + block_len
    ms = (sq[:, ends] - sq[:, starts]) / block_len
    return ms.T


def _gains_for(channels: int) -> np.ndarray:
    gains = [
        _CHANNEL_GAINS[ch] if ch < len(_CHANNEL_GAINS) else 1.0
        for ch in range(channels)
    ]
    return np.array(gains)


def _loudness_from_power(power: np.ndarray) -> float:
    return -0.691 + 10.0 * float(np.log10(power))


def _gated_integrated(power_per_block: np.ndarray) -> float:
    if power_per_block.size == 0:
        return UNMEASURABLE_LUFS
    abs_gate = 10.0 ** ((ABSOLUTE_GATE_LUFS + 0.691) / 10.0)
    kept = power_per_block[power_per_block > abs_gate]
    if kept.size == 0:
        return UNMEASURABLE_LUFS
    relative_gate = float(np.mean(kept)) * 10.0 ** (-RELATIVE_GATE_LU / 10.0)
    kept = kept[kept > relative_gate]
    if kept.size == 0:
        return UNMEASURABLE_LUFS
    return _loudness_from_power(float(np.mean(kept)))


@dataclass(frozen=True)
class LoudnessMeasurement:
    """Complete loudness/level fingerprint of one render."""

    integrated_lufs: float
    short_term_max_lufs: float
    momentary_max_lufs: float
    true_peak_dbtp: float
    sample_peak_dbfs: float
    rms_dbfs: float
    duration_sec: float

    def to_dict(self) -> dict:
        return asdict(self)


def measure(audio: np.ndarray, sample_rate: int) -> LoudnessMeasurement:
    """Measure BS.1770 loudness and level statistics of ``audio``."""
    arr = _validate_audio(audio, sample_rate)
    channels, n = arr.shape
    if n == 0:
        raise ValidationError("cannot measure empty audio")

    weighted = _k_weight(arr, sample_rate)
    gains = _gains_for(channels)

    block_len = max(1, int(BLOCK_SEC * sample_rate))
    hop = max(1, int(HOP_SEC * sample_rate))
    st_len = max(1, int(SHORT_TERM_SEC * sample_rate))

    block_ms = _block_mean_squares(weighted, block_len, hop)
    momentary_loudness = (
        -0.691 + 10.0 * np.log10(np.maximum(block_ms @ gains, 1e-30))
        if block_ms.shape[0]
        else np.zeros(0)
    )
    momentary_max = (
        float(np.max(momentary_loudness)) if momentary_loudness.size
        else UNMEASURABLE_LUFS
    )

    st_ms = _block_mean_squares(weighted, st_len, hop)
    short_term_max = (
        float(np.max(-0.691 + 10.0 * np.log10(np.maximum(st_ms @ gains, 1e-30))))
        if st_ms.shape[0]
        else UNMEASURABLE_LUFS
    )

    integrated = _gated_integrated(block_ms @ gains)

    os_audio = resample_poly(arr, TRUE_PEAK_OVERSAMPLE, 1, axis=1)
    true_peak = float(np.max(np.abs(os_audio)))
    sample_peak = float(np.max(np.abs(arr)))
    rms = float(np.sqrt(np.mean(arr**2)))

    return LoudnessMeasurement(
        integrated_lufs=integrated,
        short_term_max_lufs=short_term_max,
        momentary_max_lufs=momentary_max,
        true_peak_dbtp=20.0 * np.log10(max(true_peak, 1e-9)),
        sample_peak_dbfs=20.0 * np.log10(max(sample_peak, 1e-9)),
        rms_dbfs=20.0 * np.log10(max(rms, 1e-9)),
        duration_sec=n / float(sample_rate),
    )
