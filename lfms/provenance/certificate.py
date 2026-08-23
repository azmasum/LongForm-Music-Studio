"""Provenance certificates: machine-checkable lineage for generated music.

A certificate records who/what/how a piece was produced (versions, seed,
parameters, fingerprint), its measured loudness/QC status when available,
and the license note. It is plain data — exportable as JSON or formatted
TXT — so it can travel with the rendered audio.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lfms.core.version import APP_CODE, APP_NAME, GENERATOR_VERSION, VERSION

SCHEMA_VERSION = 1

DEFAULT_LICENSE_NOTE = (
    "Generated locally by LongForm Music Studio. No third-party samples, "
    "loops or stems were used; the creator holds royalty-free rights to "
    "the output under their LFMS license."
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ProvenanceRecord:
    """Complete lineage of one generated item."""

    created_at: str
    title: str
    schema_version: int = SCHEMA_VERSION
    app_name: str = APP_NAME
    app_version: str = VERSION
    generator_version: str = GENERATOR_VERSION
    item_id: int | None = None
    kind: str = "GENERATED"
    fingerprint: str | None = None
    duration_sec: float | None = None
    bpm: float | None = None
    key_name: str | None = None
    repetition_score: float | None = None
    parameters: dict = field(default_factory=dict)
    loudness: dict | None = None
    qc_status: str | None = None
    license_note: str = DEFAULT_LICENSE_NOTE
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_text(self) -> str:
        """Human-readable certificate suitable for printing."""
        bar = "=" * 64
        lines = [
            bar,
            f"{self.app_name} - PROVENANCE CERTIFICATE",
            bar,
            f"Certificate generated : {self.created_at}",
            f"Title                 : {self.title}",
            f"Library item          : {self.item_id if self.item_id is not None else '-'}",
            f"Kind                  : {self.kind}",
            "",
            "--- Provenance -------------------------------------------",
            f"Fingerprint           : {self.fingerprint or '-'}",
            f"Generator             : {self.generator_version}",
            f"App version           : {self.app_version} ({APP_CODE})",
            f"Duration              : "
            f"{format_duration(self.duration_sec)}",
            "",
            "--- Composition ------------------------------------------",
            f"BPM                   : {self.bpm if self.bpm is not None else '-'}",
            f"Key                   : {self.key_name or '-'}",
            f"Repetition score      : {self.repetition_score if self.repetition_score is not None else '-'}",
            "",
            "--- Parameters -------------------------------------------",
        ]
        if self.parameters:
            for name in sorted(self.parameters):
                value = self.parameters[name]
                lines.append(f"{name:<22}: {value}")
        else:
            lines.append("(none recorded)")
        lines.append("")
        lines.append("--- Quality ----------------------------------------------")
        if self.loudness:
            lines.append(
                "Loudness              : {integrated_lufs:.1f} LUFS, "
                "peak {true_peak_dbtp:.1f} dBTP".format(**self.loudness)
            )
        else:
            lines.append("Loudness              : not measured")
        lines.append(f"QC status             : {self.qc_status or 'not run'}")
        lines.append("")
        lines.append("--- License ----------------------------------------------")
        lines.append(self.license_note)
        if self.notes:
            lines.append("")
            lines.append(f"Notes: {self.notes}")
        lines.append(bar)
        lines.append(
            f"{APP_CODE} certificates are verifiable: recompose the recorded "
            "parameters and compare the fingerprint."
        )
        return "\n".join(lines)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    total = max(0, int(round(float(seconds))))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def build_record(
    *,
    title: str,
    item_id: int | None = None,
    kind: str = "GENERATED",
    fingerprint: str | None = None,
    duration_sec: float | None = None,
    bpm: float | None = None,
    key_name: str | None = None,
    parameters: dict | None = None,
    composition=None,
    measurement=None,
    qc_status: str | None = None,
    notes: str = "",
    license_note: str = DEFAULT_LICENSE_NOTE,
    created_at: str | None = None,
) -> ProvenanceRecord:
    """Assemble a record from whatever facts are available.

    ``composition`` enriches bpm/key/repetition/fingerprint;
    ``measurement`` fills the loudness block.
    """
    params = dict(parameters or {})
    if composition is not None:
        fingerprint = fingerprint or str(composition.fingerprint)
        bpm = float(composition.bpm) if composition.bpm is not None else bpm
        key_name = key_name or str(composition.key_name)
        repetition = getattr(composition, "repetition_score", None)
    else:
        repetition = None
    if measurement is not None:
        loudness = {
            "integrated_lufs": float(measurement.integrated_lufs),
            "true_peak_dbtp": float(measurement.true_peak_dbtp),
        }
    else:
        loudness = None
    return ProvenanceRecord(
        created_at=created_at or utc_now_iso(),
        title=title,
        item_id=item_id,
        kind=kind,
        fingerprint=fingerprint,
        duration_sec=duration_sec,
        bpm=bpm,
        key_name=key_name,
        repetition_score=repetition,
        parameters=params,
        loudness=loudness,
        qc_status=qc_status,
        license_note=license_note,
        notes=notes,
    )


def record_from_item(item, **enrichment) -> ProvenanceRecord:
    """Build a record from a library item's stored metadata."""
    parameters: dict = {}
    if item.params_json:
        try:
            parameters = json.loads(item.params_json)
        except json.JSONDecodeError:
            parameters = {}
    return build_record(
        title=item.title,
        item_id=item.id,
        kind=item.kind,
        fingerprint=item.fingerprint,
        duration_sec=item.duration_sec,
        bpm=item.bpm,
        key_name=item.key_name,
        parameters=parameters,
        notes=item.notes,
        **enrichment,
    )


def write_certificate(
    record: ProvenanceRecord, directory: str | Path, fmt: str = "txt"
) -> Path:
    """Write TXT or JSON certificate into ``directory`` and return its path."""
    clean = str(fmt).lower().lstrip(".")
    if clean not in ("txt", "json"):
        raise ValueError(f"unsupported certificate format {fmt!r}")
    token = (record.fingerprint or "UNCERTIFIED")[:12]
    safe_title = "".join(
        ch if ch.isalnum() else "-" for ch in record.title
    ).strip("-")[:24] or "item"
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{APP_CODE}-cert-{safe_title}-{token}.{clean}"
    path.write_text(
        record.to_text() if clean == "txt" else record.to_json(),
        encoding="utf-8",
    )
    return path
