"""Full export pipeline: library item -> rendered audio -> mastered -> QC.

One call turns a generated library item into a delivered audio file:
recompose from stored parameters, render offline, auto-master to the chosen
loudness preset, run QC gates, register the result in the library and write
a provenance certificate next to it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.audio_engine.formats import resolve_sf_params
from lfms.core.errors import ValidationError
from lfms.generator.composer import Composer
from lfms.generator.render import CompositionRenderer
from lfms.generator.scheduler import EventTrackSource  # noqa: F401 (graph source)
from lfms.library import LibraryService
from lfms.mastering.master import (
    MasterResult,
    TargetPreset,
    auto_master,
    resolve_target_preset,
)
from lfms.mastering.qc import QCReport, run_qc
from lfms.provenance.certificate import build_record, write_certificate
from lfms.provenance.verify import params_from_payload


@dataclass(frozen=True)
class ExportOutcome:
    """Everything one export produced."""

    source_item_id: int
    composition_fingerprint: str
    final_path: Path
    certificate_path: Path
    library_item_id: int
    master: MasterResult
    qc: QCReport
    target_name: str


def _safe_stem(title: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "- " else "-" for ch in title)
    return stem.strip().replace(" ", "-")[:48] or "lfms-export"


def export_item(
    service: LibraryService,
    item_id: int,
    output_dir: str | Path,
    *,
    preset: str | TargetPreset = "YOUTUBE",
    container: str = "WAV",
    bit_depth: int = 24,
    on_progress=None,
) -> ExportOutcome:
    """Render, master, QC and archive one generated library item."""
    item = service.get(item_id)
    if not item.params_json:
        raise ValidationError(
            f"library item #{item_id} has no generation parameters to render"
        )
    try:
        payload = json.loads(item.params_json)
        params = params_from_payload(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("stored parameters are not valid JSON") from exc

    target = resolve_target_preset(preset)
    out_dir = Path(output_dir)
    if not out_dir.exists():
        raise ValidationError(f"output directory does not exist: {out_dir}")

    def report(fraction: float) -> None:
        if on_progress is not None:
            on_progress(max(0.0, min(1.0, float(fraction))))

    report(0.0)
    composition = Composer(params).compose()

    # 1) offline render of the raw mix (0 .. 60% of total progress)
    raw_path = out_dir / f"{_safe_stem(item.title)}-raw.wav"
    renderer = CompositionRenderer(composition)

    def render_progress(inner: float) -> None:
        report(0.6 * inner)

    renderer.render(raw_path, container="WAV", bit_depth=24, on_progress=render_progress)
    if not raw_path.is_file():
        raise ValidationError("render did not produce a file")

    # 2) load, master, write final delivery file (60 .. 85%)
    data, sr = sf.read(str(raw_path), always_2d=True, dtype="float32")
    audio = np.ascontiguousarray(data.T.astype(np.float32))
    report(0.65)
    master = auto_master(audio, sr, target)
    report(0.8)

    fmt, subtype = resolve_sf_params(container, bit_depth)
    extension = {"WAV": ".wav", "FLAC": ".flac"}.get(fmt.upper(), ".wav")
    final_path = out_dir / f"{_safe_stem(item.title)} [{target.name}]{extension}"
    sf.write(
        str(final_path),
        master.output.T,
        sr,
        format=fmt,
        subtype=subtype,
    )
    raw_path.unlink(missing_ok=True)
    report(0.9)

    # 3) QC gates on the delivered file's numbers
    qc = run_qc(master.output, sr)

    # 4) register the export in the library
    exported = service.add_item(
        f"{item.title} [{target.name}]",
        kind="AUDIO_FILE",
        path=str(final_path.resolve()),
        duration_sec=float(master.after.duration_sec),
        sample_rate=int(sr),
        channels=int(master.output.shape[0]),
        integrated_lufs=float(master.after.integrated_lufs),
        true_peak_dbtp=float(master.after.true_peak_dbtp),
    )
    for tag in ("export", f"target:{target.name.lower()}"):
        exported = service.add_tag(exported.id, tag)
    if item.fingerprint:
        exported = service.add_tag(exported.id, f"fp-source:{item.id}")

    # 5) provenance certificate next to the delivery file
    record = build_record(
        title=item.title,
        item_id=item.id,
        fingerprint=item.fingerprint,
        duration_sec=float(params.duration_sec),
        parameters=payload,
        composition=composition,
        measurement=master.after,
        qc_status=qc.status,
        notes=(
            f"Exported from library item #{item.id} with mastering preset "
            f"{target.name}; delivered as {final_path.name}."
        ),
    )
    cert_path = write_certificate(record, out_dir, fmt="json")
    report(1.0)

    return ExportOutcome(
        source_item_id=item.id,
        composition_fingerprint=str(composition.fingerprint),
        final_path=final_path,
        certificate_path=cert_path,
        library_item_id=exported.id,
        master=master,
        qc=qc,
        target_name=target.name,
    )
