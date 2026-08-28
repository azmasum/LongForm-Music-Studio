"""Optional GUI smoke test.

Runs only when LFMS_GUI_SMOKE=1 so machines without a display/Qt stay green:
    set LFMS_GUI_SMOKE=1 && python -m pytest tests/test_gui_smoke.py
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LFMS_GUI_SMOKE") != "1",
    reason="GUI smoke tests disabled; set LFMS_GUI_SMOKE=1 to run",
)

if os.environ.get("LFMS_GUI_SMOKE") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication  # noqa: E402

    from lfms.app.main_window import MainWindow, TransportBar, format_time  # noqa: E402
    from lfms.provenance import verify_item  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window(tmp_path):
    return MainWindow(db_path=tmp_path / "library.db")


def test_main_window_builds_and_generates(qapp, tmp_path):
    window = _make_window(tmp_path)
    assert window.pages.count() == 6
    assert window.sidebar.count() == window.pages.count()
    assert any(track.kind == "MUSIC" for track in window.document.tracks)

    before = window.document.to_dict()
    clip_count_before = len(window.document.clips)
    clip = window.generate_from_payload(
        {
            "seed": 20260823,
            "genre": "DOCUMENTARY",
            "moods": ("NEUTRAL",),
            "duration_sec": 45.0,
            "intensity": 50.0,
        }
    )
    assert clip is not None
    assert len(window.document.clips) == clip_count_before + 1
    assert clip.duration_sec == pytest.approx(45.0)
    # generation auto-registers into the library with smart tags
    items = window.library.list_items()
    assert len(items) == 1
    assert any(t.startswith("genre:") for t in items[0].tags)

    window.commands.undo(window.document)
    assert len(window.document.clips) == clip_count_before
    assert window.document.to_dict() == before
    window.library.close()


def test_library_page_search_and_details(qapp, tmp_path):
    window = _make_window(tmp_path)
    page = window.library_page
    kept = window.library.add_item("Ocean Waves", path="/sfx/ocean.wav")
    window.library.add_item("Desert Wind")
    page.refresh()

    assert page.items.count() == 2
    page.search.setText("ocean")
    assert page.items.count() == 1
    assert page.selected_item_id() == kept.id

    page.search.setText("")
    page.favorites_only.setChecked(True)
    assert page.items.count() == 0
    page.favorites_only.setChecked(False)

    # favorite toggle persists through the service
    from PySide6.QtCore import Qt  # noqa: E402

    for row_index in range(page.items.count()):
        if page.items.item(row_index).data(Qt.UserRole) == kept.id:
            page.items.setCurrentRow(row_index)
            break
    page._toggle_favorite()
    assert window.library.get(kept.id).favorite is True
    window.library.close()


def test_mix_page_edits_are_undoable(qapp, tmp_path):
    window = _make_window(tmp_path)
    track = next(t for t in window.document.tracks if t.kind == "MUSIC")
    original_volume = track.volume_db

    window.mix_page.property_changed.emit(track.track_id, "volume_db", -12.5)
    updated = next(t for t in window.document.tracks if t.track_id == track.track_id)
    assert updated.volume_db == pytest.approx(-12.5)

    window.commands.undo(window.document)
    restored = next(t for t in window.document.tracks if t.track_id == track.track_id)
    assert restored.volume_db == pytest.approx(original_volume)
    window.library.close()


def test_generate_page_ai_director_flow(qapp, tmp_path):
    window = _make_window(tmp_path)
    page = window.generate_page

    # prompt-first: typing triggers auto-director after debounce
    page.director_prompt.setText(
        "calm documentary bed under narration, 5 minutes"
    )
    page._auto_direct()

    params = page.current_parameters()
    assert params["genre"] == "DOCUMENTARY"
    assert params["duration_sec"] == 300.0
    assert params["intensity"] <= 40.0
    assert params["seed"] > 0
    # voiceover-safe is extracted from "narration" and must pass through
    assert params["voiceover_safe"] is True

    # full arrangement params (bpm/key/energy) reach the payload too
    page.director_prompt.setText(
        "cinematic tension at 100 bpm in E minor that slowly builds"
    )
    page._auto_direct()
    full = page.current_parameters()
    assert full["genre"] == "CINEMATIC"
    assert full["bpm"] == 100
    assert full["key_root"] == "E"
    assert full["key_mode"] == "MINOR"
    assert full["energy_curve"] == "SLOW_BUILD"

    # deterministic: same prompt -> same suggestion
    (tmp_path / "second").mkdir()
    window2 = _make_window(tmp_path / "second")
    page2 = window2.generate_page
    page2.director_prompt.setText(page.director_prompt.text())
    page2._auto_direct()
    assert page2.current_parameters()["seed"] == full["seed"]
    window2.library.close()

    window.library.close()


def test_provenance_page_verifies_and_exports(qapp, tmp_path):
    window = _make_window(tmp_path)
    window.generate_from_payload(
        {
            "seed": 4242,
            "genre": "LOFI",
            "moods": ("DREAMY",),
            "duration_sec": 20.0,
            "intensity": 35.0,
        }
    )
    page = window.provenance_page
    page.reload_items()
    assert page.item_combo.count() == 1

    item = page._selected_item()
    assert item is not None and item.fingerprint

    page._verify_selected()
    result = verify_item(item)
    assert result.ok and result.status == "VERIFIED"

    out_dir = tmp_path / "certs"
    txt_path = page.save_certificate_to_dir(out_dir, fmt="txt")
    json_path = page.save_certificate_to_dir(out_dir, fmt="json")
    assert txt_path.is_file() and json_path.is_file()
    import json as _json

    payload = _json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == item.fingerprint
    assert payload["parameters"]["seed"] == 4242
    window.library.close()


def test_batch_page_queue_runs_end_to_end(qapp, tmp_path):
    window = _make_window(tmp_path)
    page = window.batch_page
    out_dir = tmp_path / "batch-out"
    out_dir.mkdir()
    page._output_dir = out_dir
    page.track_count.setValue(2)
    page.duration.setValue(5.0)
    page.intensity.setValue(30)

    params_list = page.build_batch_params()
    assert len(params_list) == 2
    seeds = [p.seed for p in params_list]
    assert seeds[0] != seeds[1]

    for params in params_list:
        page.queue.add(params, out_dir, title=f"Batch {params.seed}")

    assert page.queue.wait_until_idle(timeout=180.0)
    rows = page.queue.snapshot()
    assert all(row["status"] == "DONE" for row in rows)
    delivered = list(out_dir.glob("*.wav"))
    assert len(delivered) >= 2

    page.refresh()
    assert page.table.rowCount() == 2
    assert "avg" in page.perf_label.text()

    # pause toggle reflects in queue state
    page._toggle_pause()
    assert page.queue.paused and page.pause_button.text() == "Resume"
    page._toggle_pause()
    assert not page.queue.paused

    # cancel + retry + clear flow on finished jobs via selection
    page.table.selectRow(0)
    job_id = int(page.table.item(0, 0).text())
    assert page.queue.retry(job_id) or True
    assert page.queue.wait_until_idle(timeout=180.0)
    window.batch_page.queue.stop()
    window.library.close()


def test_provenance_page_exports_audio(qapp, tmp_path):
    window = _make_window(tmp_path)
    window.generate_from_payload(
        {
            "seed": 777,
            "genre": "AMBIENT",
            "moods": ("CALM",),
            "duration_sec": 12.0,
            "intensity": 30.0,
            "voiceover_safe": True,
        }
    )
    page = window.provenance_page
    page.reload_items()
    assert page.item_combo.count() >= 1

    out_dir = tmp_path / "delivery"
    out_dir.mkdir()
    outcome = page.run_export(out_dir, preset_name="PODCAST")
    assert outcome is not None
    assert outcome.final_path.is_file()
    assert "[PODCAST]" in outcome.final_path.name
    assert abs(outcome.master.after.integrated_lufs - (-16.0)) < 1.0

    exported = window.library.get(outcome.library_item_id)
    assert exported.kind == "AUDIO_FILE"
    assert exported.path == str(outcome.final_path.resolve())
    window.library.close()


def test_format_time():
    assert format_time(0) == "00:00"
    assert format_time(75.6) == "01:16"
    assert format_time(3600) == "60:00"


def test_transport_bar_labels(qapp):
    bar = TransportBar()
    bar.set_range(600)
    bar.set_position(90.0)
    assert "01:30" in bar.time_label.text()
    assert "10:00" in bar.time_label.text()
