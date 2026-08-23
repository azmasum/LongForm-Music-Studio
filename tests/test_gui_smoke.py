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

    from lfms.app.main_window import MainWindow, format_time  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds_and_generates(qapp):
    window = MainWindow()
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

    window.commands.undo(window.document)
    assert len(window.document.clips) == clip_count_before
    assert window.document.to_dict() == before


def test_format_time():
    assert format_time(0) == "00:00"
    assert format_time(75.6) == "01:16"
    assert format_time(3600) == "60:00"


def test_transport_bar_labels(qapp):
    from lfms.app.main_window import TransportBar

    bar = TransportBar()
    bar.set_range(600)
    bar.set_position(90.0)
    assert "01:30" in bar.time_label.text()
    assert "10:00" in bar.time_label.text()
