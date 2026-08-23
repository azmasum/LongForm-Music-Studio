"""QC gates: verify a render/master is safe to export.

``run_qc`` checks loudness, true peak, DC offset, clipping, silence
fraction and stereo balance against a ``QCSpec`` and returns a serializable
report whose overall status is READY or WARNING.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from lfms.core.errors import ValidationError
from lfms.mastering.measure import measure


@dataclass(frozen=True)
class QCSpec:
    """Thresholds for every gate. ``None`` disables the loudness range check."""

    max_true_peak_dbtp: float = -1.0
    lufs_range: tuple[float, float] | None = (-24.0, -12.0)
    max_dc_offset: float = 1e-3
    max_clipped_samples: int = 0
    clip_threshold: float = 0.9995
    max_silence_fraction: float = 0.25
    silence_floor_dbfs: float = -60.0
    balance_db_max: float = 3.0
    min_duration_sec: float = 1.0

    def validate(self) -> None:
        if not -12.0 <= self.max_true_peak_dbtp <= 0.0:
            raise ValidationError("max_true_peak_dbtp must be within [-12, 0]")
        if self.lufs_range is not None and self.lufs_range[0] >= self.lufs_range[1]:
            raise ValidationError("lufs_range must be (lo, hi) with lo < hi")
        if not 0.0 < self.max_dc_offset < 0.5:
            raise ValidationError("max_dc_offset must be within (0, 0.5)")
        if self.max_clipped_samples < 0:
            raise ValidationError("max_clipped_samples must be >= 0")
        if not 0.9 <= self.clip_threshold < 1.0:
            raise ValidationError("clip_threshold must be within [0.9, 1)")
        if not 0.0 <= self.max_silence_fraction <= 1.0:
            raise ValidationError("max_silence_fraction must be within [0, 1]")
        if not -96.0 <= self.silence_floor_dbfs <= -20.0:
            raise ValidationError("silence_floor_dbfs must be within [-96, -20]")
        if self.balance_db_max < 0:
            raise ValidationError("balance_db_max must be >= 0")
        if self.min_duration_sec <= 0:
            raise ValidationError("min_duration_sec must be positive")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    value: float | str | None
    limit: str
    message: str


@dataclass(frozen=True)
class QCReport:
    sample_rate: int
    duration_sec: float
    integrated_lufs: float
    true_peak_dbtp: float
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def status(self) -> str:
        return "READY" if self.passed else "WARNING"

    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def summary(self) -> str:
        lines = [f"QC {self.status}: {len(self.failed_checks())} issue(s)"]
        for check in self.checks:
            mark = "PASS" if check.passed else "FAIL"
            value = f"{check.value:.2f}" if isinstance(check.value, float) else check.value
            lines.append(f"[{mark}] {check.name}: {value} (limit {check.limit})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "duration_sec": self.duration_sec,
            "integrated_lufs": self.integrated_lufs,
            "true_peak_dbtp": self.true_peak_dbtp,
            "status": self.status,
            "checks": [asdict(c) for c in self.checks],
        }


def run_qc(audio: np.ndarray, sample_rate: int, spec: QCSpec | None = None) -> QCReport:
    """Run all QC gates; never raises for bad audio — failures are reported."""
    spec = spec or QCSpec()
    spec.validate()
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] == 0:
        raise ValidationError("audio must be shaped (channels, frames)")

    m = measure(arr.astype(np.float32), sample_rate)
    channels, n = arr.shape
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            "duration_sec",
            m.duration_sec >= spec.min_duration_sec,
            round(m.duration_sec, 3),
            f">= {spec.min_duration_sec:g}",
            "render too short",
        )
    )
    checks.append(
        CheckResult(
            "true_peak_dbtp",
            m.true_peak_dbtp <= spec.max_true_peak_dbtp + 1e-6,
            round(m.true_peak_dbtp, 2),
            f"<= {spec.max_true_peak_dbtp:g}",
            "true peak above ceiling",
        )
    )
    if spec.lufs_range is not None:
        lo, hi = spec.lufs_range
        ok = lo <= m.integrated_lufs <= hi
        checks.append(
            CheckResult(
                "integrated_lufs",
                ok,
                round(m.integrated_lufs, 2),
                f"[{lo:g}, {hi:g}]",
                "integrated loudness out of target range",
            )
        )

    dc_max = float(np.max(np.abs(np.mean(arr, axis=1))))
    checks.append(
        CheckResult(
            "dc_offset",
            dc_max <= spec.max_dc_offset,
            round(dc_max, 6),
            f"<= {spec.max_dc_offset:g}",
            "DC offset detected",
        )
    )

    clipped = int(np.count_nonzero(np.abs(arr) >= spec.clip_threshold))
    checks.append(
        CheckResult(
            "clipped_samples",
            clipped <= spec.max_clipped_samples,
            clipped,
            f"<= {spec.max_clipped_samples}",
            "sample clipping detected",
        )
    )

    floor_lin = 10.0 ** (spec.silence_floor_dbfs / 20.0)
    silent_fraction = float(np.mean(np.abs(arr) < floor_lin))
    checks.append(
        CheckResult(
            "silence_fraction",
            silent_fraction <= spec.max_silence_fraction,
            round(silent_fraction, 4),
            f"<= {spec.max_silence_fraction:g}",
            "too much near-silent content",
        )
    )

    if channels >= 2:
        rms = np.sqrt(np.mean(arr[:2] ** 2, axis=1))
        diff_db = (
            abs(20.0 * np.log10(max(rms[0], 1e-9) / max(rms[1], 1e-9)))
            if min(rms[0], rms[1]) > 0
            else 120.0
        )
        checks.append(
            CheckResult(
                "stereo_balance_db",
                diff_db <= spec.balance_db_max,
                round(float(diff_db), 2),
                f"<= {spec.balance_db_max:g}",
                "left/right energy imbalance",
            )
        )

    return QCReport(
        sample_rate=sample_rate,
        duration_sec=m.duration_sec,
        integrated_lufs=m.integrated_lufs,
        true_peak_dbtp=m.true_peak_dbtp,
        checks=tuple(checks),
    )
