# Mastering & QC

Status: Phase 7 implemented and tested (240 tests passing overall).

## Package layout (`lfms.mastering`)

| Module | Contents |
| --- | --- |
| `measure.py` | ITU-R BS.1770-4 measurement (`measure`, `LoudnessMeasurement`) |
| `master.py` | Loudness target presets, `TruePeakLimiter`, `auto_master` |
| `qc.py` | Export gates (`QCSpec`, `run_qc`, `QCReport` with READY/WARNING) |

All processing is deterministic and operates on `(channels, n)` float arrays.

## Measurement (BS.1770-4)

- **K-weighting**: parametric shelf + RLB high-pass biquads recomputed for
  any sample rate; verified to match the published fixed 48 kHz
  coefficients exactly.
- **Integrated loudness**: 400 ms blocks / 100 ms hop, absolute (-70 LUFS)
  plus relative (-10 LU) gating. Below-measurable input reports -120.
- **Momentary** (400 ms max), **short-term** (3 s window max), true peak via
  4x oversampling (`resample_poly`), sample peak, RMS.

Reference anchor: a -20 dBFS 997 Hz stereo sine measures ≈ -20.0 LUFS,
because K-weighting is +0.69 dB at 1 kHz and cancels the standard's -0.691
offset.

## Auto-mastering

Presets (`resolve_target_preset`, case-insensitive): YOUTUBE -14/-1.0 dBTP,
PODCAST -16/-1.0, EBU_R128 -23/-1.0, BACKGROUND_BED -20/-2.0.

`auto_master(audio, sr, preset)`:

1. Static-normalize toward the target integrated loudness.
2. Run the look-ahead true-peak limiter (no-op below ceiling).
3. If still off-target, retry from fresh source with secant-estimated extra
   gain (candidates are never re-limited iteratively — that compounds
   distortion and can diverge on peaky material).
4. Stops honestly when the limiter absorbs all added gain (slope < 0.05
   LU/dB): some sparse material physically cannot reach the target at the
   ceiling without heavier compression; the result then under-shoots while
   never exceeding the ceiling.

`MasterResult` carries before/after `LoudnessMeasurement`, total applied
gain, whether the limiter engaged, pass count, plus `hit_target()` /
`under_ceiling()` helpers. Hot spot: the limiter's release smoothing runs
per-sample at 4x rate (~5x realtime overall for 60 s program).

## QC gates

`run_qc(audio, sr, spec)` checks duration, true peak vs ceiling, integrated
loudness range (optional), DC offset, sample clipping, silence fraction and
stereo balance. Every failure is reported as a named check with value +
limit; `report.status` is READY or WARNING, `summary()` is human-readable,
`to_dict()` feeds export certificates (Phase 9). Bad audio never raises —
failures are data.

## GUI note

Export page wiring (auto-master preset picker + QC panel) lands with the
Phase 8 UI work; everything here is usable from scripts today.
