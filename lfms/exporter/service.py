"""Full export pipeline: composition -> rendered audio -> mastered -> QC.

Two entry points share one core:

- :func:`export_item` re-renders a generated library item from its stored
  parameters (provenance-safe).
- :func:`export_parameters` renders fresh ``GenerationParameters`` and
  registers the source item in the library first (used by the batch queue).

One call turns music into a delivered audio file: recompose, render
offline, auto-master to the chosen loudness preset, run QC gates, register
the result in the library and write a provenance certificate next to it.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.audio_engine.formats import default_extension, resolve_sf_params
from lfms.core.errors import RenderCancelled, ValidationError
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters, params_from_payload
from lfms.generator.render import CompositionRenderer
from lfms.library import LibraryService
from lfms.mastering.master import (
    MasterResult,
    TargetPreset,
    auto_master,
    resolve_target_preset,
)
from lfms.mastering.qc import QCReport, run_qc
from lfms.provenance.certificate import build_record, write_certificate


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


class _CancelJobControl:
    """Adapts a cancel predicate to the RenderJobControl protocol."""

    def __init__(self, should_cancel: Callable[[], bool]) -> None:
        self._should_cancel = should_cancel

    def checkpoint(self) -> bool:
        return not self._should_cancel()


def _check_cancel(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise RenderCancelled("export cancelled by user")


def _export_core(
    service: LibraryService,
    item,
    payload: dict,
    composition,
    out_dir: Path,
    target: TargetPreset,
    container: str,
    bit_depth: int,
    on_progress: Callable[[float], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> ExportOutcome:
    def report(fraction: float) -> None:
        if on_progress is not None:
            on_progress(max(0.0, min(1.0, float(fraction))))

    report(0.0)
    _check_cancel(should_cancel)

    # 1) offline render of the raw mix (0 .. 60% of total progress)
    raw_path = out_dir / f"{_safe_stem(item.title)}-raw.wav"
    renderer = CompositionRenderer(composition)

    def render_progress(inner: float) -> None:
        report(0.6 * inner)

    job_control = (
        _CancelJobControl(should_cancel) if should_cancel is not None else None
    )
    try:
        renderer.render(
            raw_path,
            container="WAV",
            bit_depth=24,
            on_progress=render_progress,
            job_control=job_control,
        )
        _check_cancel(should_cancel)
        if not raw_path.is_file():
            raise ValidationError("render did not produce a file")

        # 2) load, master, write final delivery file (60 .. 85%)
        data, sr = sf.read(str(raw_path), always_2d=True, dtype="float32")
        audio = np.ascontiguousarray(data.T.astype(np.float32))
        report(0.65)
        master = auto_master(audio, sr, target)
        _check_cancel(should_cancel)
        report(0.8)

        fmt, subtype = resolve_sf_params(container, bit_depth)
        extension = f".{default_extension(container)}"
        final_path = out_dir / f"{_safe_stem(item.title)} [{target.name}]{extension}"
        sf.write(
            str(final_path),
            master.output.T,
            sr,
            format=fmt,
            subtype=subtype,
        )
    finally:
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
        duration_sec=float(payload.get("duration_sec", 0.0)),
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


def export_item(
    service: LibraryService,
    item_id: int,
    output_dir: str | Path,
    *,
    preset: str | TargetPreset = "YOUTUBE",
    container: str = "WAV",
    bit_depth: int = 24,
    on_progress=None,
    should_cancel=None,
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

    composition = Composer(params).compose()
    return _export_core(
        service,
        item,
        payload,
        composition,
        out_dir,
        target,
        container,
        bit_depth,
        on_progress,
        should_cancel,
    )


def export_parameters(
    service: LibraryService,
    params: GenerationParameters,
    output_dir: str | Path,
    *,
    title: str | None = None,
    preset: str | TargetPreset = "YOUTUBE",
    container: str = "WAV",
    bit_depth: int = 24,
    on_progress=None,
    should_cancel=None,
) -> ExportOutcome:
    """Compose fresh parameters, archive them and run the full pipeline."""
    params.validate()
    out_dir = Path(output_dir)
    if not out_dir.exists():
        raise ValidationError(f"output directory does not exist: {out_dir}")

    payload = asdict(params)
    payload["moods"] = tuple(params.moods)
    composition = Composer(params).compose()
    display_title = title or f"Track {params.seed}"
    item = service.register_composition(
        composition,
        params,
        title=display_title,
    )
    return _export_core(
        service,
        item,
        payload,
        composition,
        out_dir,
        resolve_target_preset(preset),
        container,
        bit_depth,
        on_progress,
        should_cancel,
    )
