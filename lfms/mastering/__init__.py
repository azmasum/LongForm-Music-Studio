"""Mastering & QC (Phase 7): BS.1770 measurement, auto-master, QC gates."""
from lfms.mastering.master import (
    TARGET_PRESETS,
    MasterResult,
    TargetPreset,
    TruePeakLimiter,
    auto_master,
    known_target_presets,
    resolve_target_preset,
)
from lfms.mastering.measure import (
    LoudnessMeasurement,
    measure,
)
from lfms.mastering.qc import (
    CheckResult,
    QCReport,
    QCSpec,
    run_qc,
)

__all__ = [
    "CheckResult",
    "LoudnessMeasurement",
    "TARGET_PRESETS",
    "QCSpec",
    "QCReport",
    "TargetPreset",
    "TruePeakLimiter",
    "MasterResult",
    "auto_master",
    "known_target_presets",
    "measure",
    "resolve_target_preset",
    "run_qc",
]
