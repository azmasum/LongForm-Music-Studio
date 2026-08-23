"""Auto-mastering: loudness targets, true-peak limiting, two-pass normalize.

``auto_master`` measures the source, applies static gain toward the preset
target, engages an oversampled true-peak limiter when needed and iterates
(up to two passes) until the integrated loudness lands near target without
exceeding the ceiling. Everything is deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import resample_poly

from lfms.audio_engine.dsp import db_to_gain
from lfms.core.errors import ValidationError
from lfms.mastering.measure import LoudnessMeasurement, measure


@dataclass(frozen=True)
class TargetPreset:
    """A named loudness/ceiling combination (e.g. YouTube -14 LUFS / -1 dBTP)."""

    name: str
    description: str
    target_lufs: float
    ceiling_dbtp: float


TARGET_PRESETS: dict[str, TargetPreset] = {
    "YOUTUBE": TargetPreset("YOUTUBE", "YouTube / general streaming", -14.0, -1.0),
    "PODCAST": TargetPreset("PODCAST", "Podcast platforms (Spotify etc.)", -16.0, -1.0),
    "EBU_R128": TargetPreset("EBU_R128", "EBU R128 broadcast", -23.0, -1.0),
    "BACKGROUND_BED": TargetPreset(
        "BACKGROUND_BED", "Quiet bed under voiceover", -20.0, -2.0
    ),
}


def known_target_presets() -> tuple[str, ...]:
    return tuple(sorted(TARGET_PRESETS))


def resolve_target_preset(preset: str | TargetPreset) -> TargetPreset:
    if isinstance(preset, TargetPreset):
        return preset
    key = str(preset).upper()
    if key not in TARGET_PRESETS:
        raise ValidationError(
            f"unknown mastering preset {preset!r}; known: "
            f"{', '.join(known_target_presets())}"
        )
    return TARGET_PRESETS[key]


class TruePeakLimiter:
    """Oversampled look-ahead peak limiter.

    The gain curve is derived at 4x rate (sliding minimum over the
    look-ahead window, one-pole release), then applied at base rate.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        ceiling_dbtp: float = -1.0,
        lookahead_ms: float = 5.0,
        release_ms: float = 60.0,
    ) -> None:
        sr = int(sample_rate)
        if sr <= 0:
            raise ValidationError("sample_rate must be positive")
        self.sample_rate = sr
        if not -12.0 <= ceiling_dbtp <= 0.0:
            raise ValidationError("ceiling_dbtp must be within [-12, 0]")
        self.ceiling_dbtp = float(ceiling_dbtp)
        if not 0.5 <= lookahead_ms <= 50.0:
            raise ValidationError("lookahead_ms must be within [0.5, 50]")
        if not 1.0 <= release_ms <= 1000.0:
            raise ValidationError("release_ms must be within [1, 1000]")
        self._oversample = 4
        self._window_os = max(2, int(sr * self._oversample * lookahead_ms / 1000.0))
        self._release_coef = float(
            np.exp(-1.0 / (release_ms * 0.001 * sr * self._oversample))
        )
        self._last_gain = 1.0
        self.last_min_gain = 1.0

    def process(self, block: np.ndarray) -> np.ndarray:
        x = block.astype(np.float64)
        os_x = resample_poly(x, self._oversample, 1, axis=1)
        ceiling = db_to_gain(self.ceiling_dbtp)

        needed = np.minimum(
            ceiling / np.maximum(np.abs(os_x), 1e-9), 1.0
        ).min(axis=0)

        w = min(self._window_os, needed.shape[0])
        if w >= 2:
            padded = np.concatenate((needed, np.full(w - 1, 1.0)))
            windows = np.lib.stride_tricks.sliding_window_view(padded, w)
            looked_ahead = windows.min(axis=1)[: needed.shape[0]]
        else:
            looked_ahead = needed

        g = self._last_gain
        out_gain = np.empty_like(looked_ahead)
        for i, target in enumerate(looked_ahead):
            if target < g:
                g = target
            else:
                g += self._release_coef * (target - g)
            out_gain[i] = g
        self._last_gain = float(g)
        self.last_min_gain = float(np.min(out_gain))

        base_gain = out_gain[:: self._oversample]
        if base_gain.shape[0] < x.shape[1]:
            base_gain = np.concatenate(
                (base_gain, np.full(x.shape[1] - base_gain.shape[0], base_gain[-1]))
            )
        return (x * base_gain[None, :]).astype(np.float32)

    def reset(self) -> None:
        self._last_gain = 1.0
        self.last_min_gain = 1.0


@dataclass(frozen=True)
class MasterResult:
    """Outcome of ``auto_master`` with before/after measurements."""

    output: np.ndarray
    before: LoudnessMeasurement
    after: LoudnessMeasurement
    preset: str
    total_gain_db: float
    limiter_engaged: bool
    passes: int

    def hit_target(self, tolerance: float = 0.5) -> bool:
        target = resolve_target_preset(self.preset)
        return abs(self.after.integrated_lufs - target.target_lufs) <= tolerance

    def under_ceiling(self, tolerance: float = 0.05) -> bool:
        target = resolve_target_preset(self.preset)
        return self.after.true_peak_dbtp <= target.ceiling_dbtp + tolerance


def _apply_gain(audio: np.ndarray, gain_db: float) -> np.ndarray:
    return (audio.astype(np.float64) * db_to_gain(gain_db)).astype(np.float32)


def auto_master(
    audio: np.ndarray,
    sample_rate: int,
    preset: str | TargetPreset,
    *,
    max_passes: int = 4,
) -> MasterResult:
    """Normalize to the preset's integrated loudness and cap true peak.

    Candidates are always built fresh from the source (normalize gain +
    trial offset, then limit), never by re-processing an already limited
    signal — this keeps the search stable for sparse, peaky material. The
    trial offset converges via secant steps on the measured integrated
    loudness; ``passes`` counts candidate evaluations.
    """
    target = resolve_target_preset(preset)
    arr = np.asarray(audio)
    if arr.ndim != 2 or arr.shape[1] == 0:
        raise ValidationError("audio must be shaped (channels, frames)")

    before = measure(arr, sample_rate)
    if before.integrated_lufs <= -90.0:
        raise ValidationError(
            "input is too quiet to master (no measurable loudness)"
        )

    def evaluate(total_db: float) -> tuple[np.ndarray, LoudnessMeasurement, bool]:
        scaled = (arr.astype(np.float64) * db_to_gain(total_db)).astype(np.float32)
        limiter = TruePeakLimiter(sample_rate, ceiling_dbtp=target.ceiling_dbtp)
        limited = limiter.process(scaled)
        engaged = limiter.last_min_gain < 0.999
        final_audio = limited if engaged else scaled
        return final_audio, measure(final_audio, sample_rate), engaged

    base_gain_db = target.target_lufs - before.integrated_lufs

    best_audio, best_m, engaged = evaluate(base_gain_db)
    best_offset_db = 0.0
    best_err = abs(best_m.integrated_lufs - target.target_lufs)
    passes = 1
    trials: list[tuple[float, float]] = [(0.0, best_m.integrated_lufs)]

    for _ in range(max(1, max_passes) - 1):
        if best_err <= 0.3:
            break
        if len(trials) >= 2:
            (x1, l1), (x2, l2) = trials[-2], trials[-1]
            slope = (l2 - l1) / (x2 - x1)
            if abs(slope) < 0.05:
                break  # limiter absorbs all added gain; cannot get louder
            step = float(np.clip((target.target_lufs - l2) / slope, -6.0, 6.0))
        else:
            step = target.target_lufs - best_m.integrated_lufs
        x_new = trials[-1][0] + step
        if any(abs(x_new - x) < 1e-6 for x, _ in trials):
            break  # stalled: repeating the same candidate
        cand_audio, cand_m, cand_engaged = evaluate(base_gain_db + x_new)
        engaged = engaged or cand_engaged
        passes += 1
        trials.append((x_new, cand_m.integrated_lufs))
        cand_err = abs(cand_m.integrated_lufs - target.target_lufs)
        if cand_err < best_err:
            best_audio, best_m = cand_audio, cand_m
            best_offset_db, best_err = x_new, cand_err
        if cand_err <= 0.2:
            break

    final = measure(best_audio, sample_rate)
    if final.true_peak_dbtp > target.ceiling_dbtp + 0.06:
        trim = target.ceiling_dbtp - final.true_peak_dbtp
        best_audio = (best_audio.astype(np.float64) * db_to_gain(trim)).astype(
            np.float32
        )
        final = measure(best_audio, sample_rate)

    return MasterResult(
        output=best_audio.astype(np.float32),
        before=before,
        after=final,
        preset=target.name,
        total_gain_db=base_gain_db + best_offset_db,
        limiter_engaged=bool(engaged),
        passes=passes,
    )
