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


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window(tmp_path):
    return MainWindow(db_path=tmp_path / "library.db")


def test_main_window_builds_and_generates(qapp, tmp_path):
    window = _make_window(tmp_path)
    assert window.pages.count() == 5
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
