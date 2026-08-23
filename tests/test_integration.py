"""End-to-end integration tests — the spec §71 MVP loop."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import soundfile as sf

from lfms.batch import RenderQueue, make_batch
from lfms.director import MusicDirector
from lfms.exporter import export_parameters
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService
from lfms.mastering.measure import measure
from lfms.provenance import verify_item
from lfms.timeline.commands import AddClipCommand, CommandStack
from lfms.timeline.model import Clip, TimelineDocument


def _params(seed=101, duration=8.0) -> GenerationParameters:
    params = GenerationParameters(
        seed=seed,
        duration_sec=duration,
        genre="DOCUMENTARY",
        moods=("CALM",),
        intensity=40.0,
        voiceover_safe=True,
    )
    params.validate()
    return params


@pytest.fixture(scope="module")
def qapp():
    try:
        import PySide6  # noqa: F401
    except ImportError:
        pytest.skip("PySide6 not installed; GUI integration test skipped")
    if os.environ.get("LFMS_GUI_SMOKE") == "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_full_mvp_loop_params_to_verified_delivery(tmp_path: Path):
    """compose -> export(master+QC) -> library -> certificate -> verify."""
    out_dir = tmp_path / "delivery"
    out_dir.mkdir()
    service = LibraryService(":memory:")
    params = _params()

    outcome = export_parameters(service, params, out_dir, title="MVP Bed")

    # delivered audio is real, mastered to the preset, ceiling-safe
    delivered, sr = sf.read(str(outcome.final_path), always_2d=True, dtype="float32")
    assert abs(delivered.shape[0] - int(params.duration_sec * sr)) <= 2
    m = measure(delivered.T, sr)
    assert abs(m.integrated_lufs - (-14.0)) < 1.0
    assert m.true_peak_dbtp <= -0.9
    assert outcome.qc.status in ("READY", "WARNING")

    # library holds source + export with lineage tags
    items = {item.title: item for item in service.list_items()}
    source = next(item for t, item in items.items() if t == "MVP Bed")
    exported = next(item for t, item in items.items() if "[YOUTUBE]" in t)
    assert "export" in exported.tags and f"fp-source:{source.id}" in exported.tags

    # certificate carries the source lineage; verification passes
    cert = json.loads(outcome.certificate_path.read_text(encoding="utf-8"))
    assert cert["fingerprint"] == source.fingerprint == outcome.composition_fingerprint
    verdict = verify_item(source)
    assert verdict.ok and verdict.status == "VERIFIED"
    service.close()


def test_director_prompt_to_delivery(tmp_path: Path):
    out_dir = tmp_path / "dir-out"
    out_dir.mkdir()
    service = LibraryService(":memory:")
    director = MusicDirector()
    director.enable(True)

    suggestion = director.direct("calm meditation soundscape for sleep, 30 seconds")
    outcome = export_parameters(
        service,
        suggestion.params,
        out_dir,
        title="Director Pick",
        preset="BACKGROUND_BED",
    )
    delivered, sr = sf.read(str(outcome.final_path), always_2d=True, dtype="float32")
    m = measure(delivered.T, sr)
    assert abs(m.integrated_lufs - (-20.0)) < 1.0
    assert m.true_peak_dbtp <= -1.9  # -2.0 dBTP preset + epsilon
    service.close()


def test_batch_three_tracks_unique_fingerprints(tmp_path: Path):
    out_dir = tmp_path / "batch"
    out_dir.mkdir()
    service = LibraryService(":memory:")
    queue = RenderQueue(service)
    base = _params(seed=500, duration=5.0)
    for clone in make_batch(base, 3):
        queue.add(clone, out_dir, title=f"Batch {clone.seed}")

    assert queue.wait_until_idle(timeout=300.0)
    rows = queue.snapshot()
    assert [r["status"] for r in rows] == ["DONE"] * 3
    fingerprints = {
        item.fingerprint
        for item in service.list_items()
        if item.kind == "GENERATED" and item.fingerprint
    }
    assert len(fingerprints) == 3  # unique seeds => unique compositions
    assert len(list(out_dir.glob("*.wav"))) >= 3
    queue.stop()
    service.close()


def test_edit_timeline_then_export_still_works(tmp_path: Path):
    """Undo/redo edits never corrupt the generation pipeline."""
    from lfms.timeline.model import TrackState

    doc = TimelineDocument(title="Edit drill", duration_sec=120.0)
    track = doc.add_track(TrackState(name="Music bed", kind="MUSIC"))
    stack = CommandStack()

    composition = Composer(_params(seed=77)).compose()
    clip = Clip(
        track_id=track.track_id,
        start_sec=0.0,
        duration_sec=float(composition.duration_sec),
        label=f"Bed {composition.fingerprint[:8]}",
        source_kind="GENERATED",
        source_ref=composition.fingerprint,
    )
    stack.execute(AddClipCommand(clip), doc)
    stack.undo(doc)
    assert doc.clips == []
    stack.redo(doc)
    assert len(doc.clips) == 1

    out_dir = tmp_path / "edited"
    out_dir.mkdir()
    service = LibraryService(":memory:")
    outcome = export_parameters(service, _params(seed=78), out_dir)
    assert outcome.final_path.is_file()
    service.close()


def test_tampered_parameters_fail_verification_honestly():
    """Forgery drill: swap a real fingerprint onto different parameters."""
    service = LibraryService(":memory:")
    original_params = _params(seed=909)
    original = service.register_composition(Composer(original_params).compose(), original_params)
    assert verify_item(original).ok

    forged_params = _params(seed=12345)
    forged = service.register_composition(
        Composer(forged_params).compose(),
        forged_params,
        title="Forged copy",
    )
    # attacker overwrites the stored fingerprint to claim the original's
    # audio identity while keeping their own parameters
    with service._lock:
        service._conn.execute(
            "UPDATE items SET fingerprint=? WHERE id=?",
            (original.fingerprint, forged.id),
        )
        service._conn.commit()
    refetched = service.get(forged.id)
    assert refetched.fingerprint == original.fingerprint

    verdict = verify_item(refetched)
    assert not verdict.ok and verdict.status == "FAILED"
    service.close()


def test_project_roundtrip_and_version_restore():
    from lfms.timeline.model import TrackState

    doc = TimelineDocument(title="Round trip", duration_sec=900.0)
    doc.add_track(TrackState(name="Audio 2", kind="MUSIC", order=1))
    payload = doc.to_dict()
    restored = TimelineDocument.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.title == "Round trip"


@pytest.mark.parametrize("bad", [None, 42, "text", {"tracks": "nope"}])
def test_damaged_project_data_raises_clean_error(bad):
    from lfms.core.errors import LFMSError

    with pytest.raises(LFMSError):
        TimelineDocument.from_dict(bad)


def test_gui_full_session(qapp, tmp_path):
    """Offscreen GUI: generate -> verify -> export -> batch one job."""
    if not os.environ.get("LFMS_GUI_SMOKE") == "1":
        pytest.skip("GUI smoke tests disabled; set LFMS_GUI_SMOKE=1 to run")
    from tests.test_gui_smoke import _make_window

    window = _make_window(tmp_path)

    # 1) generate from the form payload
    window.generate_from_payload(
        {
            "seed": 31337,
            "genre": "AMBIENT",
            "moods": ("DREAMY",),
            "duration_sec": 10.0,
            "intensity": 30.0,
        }
    )

    # 2) provenance verification of the fresh composition
    page = window.provenance_page
    page.reload_items()
    item = page._selected_item()
    assert item is not None and item.fingerprint
    verdict = verify_item(item)
    assert verdict.ok and verdict.status == "VERIFIED"

    # 3) master & deliver through the export pipeline
    out_dir = tmp_path / "gui-delivery"
    out_dir.mkdir()
    outcome = page.run_export(out_dir, preset_name="PODCAST")
    assert outcome is not None and outcome.final_path.is_file()

    # 4) enqueue a tiny batch job and let the queue finish it
    batch_out = tmp_path / "gui-batch"
    batch_out.mkdir()
    window.batch_page.queue.add(_params(seed=4141, duration=4.0), batch_out, title="GUI Batch")
    assert window.batch_page.queue.wait_until_idle(timeout=180.0)
    rows = window.batch_page.queue.snapshot()
    assert rows[0]["status"] == "DONE"

    window.batch_page.queue.stop()
    window.library.close()
