"""Regression tests for the v1.1 UX fixes.

- Generate page writes a real WAV into the chosen output folder
  (defaults to ~/Downloads) and loads the playback buffer.
- Timeline canvas supports select / move / delete via signals.
- Mix page explains itself.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LFMS_GUI_SMOKE") != "1",
    reason="GUI tests need LFMS_GUI_SMOKE=1",
)

if os.environ.get("LFMS_GUI_SMOKE") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _window(tmp_path):
    from lfms.app.main_window import MainWindow

    return MainWindow(db_path=tmp_path / "library.db")


def test_generate_writes_wav_to_output_folder(qapp, tmp_path):
    window = _window(tmp_path)
    out_dir = tmp_path / "My Music"
    window.generate_page.set_output_dir(out_dir)
    clip = window.generate_from_payload(
        {"seed": 90210, "genre": "AMBIENT", "moods": ("CALM",),
         "duration_sec": 5.0, "intensity": 40.0}
    )
    assert clip is not None
    files = list(out_dir.glob("LFMS-*.wav"))
    assert len(files) == 1
    import soundfile as sf

    info = sf.info(str(files[0]))
    assert abs(info.duration - 5.0) < 0.5
    item = window.library.list_items()[0]
    assert item.path == str(files[0].resolve())
    # playback buffer is loaded so Play works immediately
    assert window._player.loaded
    assert abs(window._player.duration_sec - 5.0) < 0.5
    window.library.close()


def test_timeline_clip_move_and_delete_commands(qapp, tmp_path):
    window = _window(tmp_path)
    clip = window.generate_from_payload(
        {"seed": 77, "genre": "LOFI", "moods": ("DREAMY",),
         "duration_sec": 4.0, "intensity": 30.0}
    )
    out_dir = tmp_path / "wav-out"
    out_dir.mkdir()
    window.generate_page.set_output_dir(out_dir)

    window._on_clip_moved(clip.clip_id, 30.0)
    moved = window.document.clip(clip.clip_id)
    assert moved.start_sec == pytest.approx(30.0)

    window._undo()  # Ctrl+Z path works on timeline edits too
    assert window.document.clip(clip.clip_id).start_sec == pytest.approx(0.0)
    window._redo()

    before = len(window.document.clips)
    window._on_clip_delete(clip.clip_id)
    assert len(window.document.clips) == before - 1
    window._undo()
    assert len(window.document.clips) == before


def test_timeline_canvas_hit_testing_and_signals(qapp, tmp_path):
    from PySide6.QtCore import QPointF, Qt

    window = _window(tmp_path)
    out_dir = tmp_path / "hit-wav"
    out_dir.mkdir()
    window.generate_page.set_output_dir(out_dir)
    clip = window.generate_from_payload(
        {"seed": 555, "genre": "AMBIENT", "moods": ("NEUTRAL",),
         "duration_sec": 60.0, "intensity": 30.0}
    )
    canvas = window.timeline_canvas
    canvas.resize(1200, 600)
    canvas._recompute_rects()

    rx, ry, rw, rh = canvas._clip_rects[clip.clip_id]
    hit = canvas.clip_at(rx + rw * 0.5, ry + rh * 0.5)
    assert hit == clip.clip_id
    assert canvas.clip_at(-50.0, -50.0) is None

    received = []
    canvas.clip_moved.connect(lambda cid, start: received.append((cid, start)))
    canvas.selected_clip_id = clip.clip_id
    canvas._drag_clip_id = clip.clip_id
    canvas._drag_offset_sec = 0.0
    # simulate a drag preview of ~10 s then release at that x position
    canvas._drag_preview_start = 10.0
    scale, origin_x, _ = canvas._geometry()
    x = (10.0) * scale + origin_x
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    event = QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(x, ry + 5), Qt.LeftButton,
        Qt.LeftButton, Qt.NoModifier,
    )
    canvas.mouseReleaseEvent(event)
    assert received and received[0][0] == clip.clip_id
    assert received[0][1] == pytest.approx(10.0)


def test_mix_page_hint_and_strips(qapp, tmp_path):
    from PySide6.QtWidgets import QLabel

    window = _window(tmp_path)
    texts = [lbl.text() for lbl in window.mix_page.findChildren(QLabel)]
    assert any("mute" in t.lower() and "solo" in t.lower() for t in texts)


def test_auto_seed_rolls_fresh_seed_per_generate(qapp, tmp_path):
    window = _window(tmp_path)
    page = window.generate_page
    assert page.auto_seed.isChecked()
    first = page.current_parameters()["seed"]
    second = page.current_parameters()["seed"]
    assert first != second
    # uncheck -> seed becomes stable (repeat-the-same-track workflow)
    page.auto_seed.setChecked(False)
    fixed = page.current_parameters()["seed"]
    assert page.current_parameters()["seed"] == fixed
    assert page.current_parameters()["seed"] == int(page.seed.value())


def test_buffer_player_position_math_without_device():
    import numpy as np

    from lfms.audio_engine.playback import BufferPlayer
    from lfms.core.errors import AudioDeviceError

    player = BufferPlayer()
    assert not player.loaded
    player.load(np.zeros((2, 48000), dtype=np.float32), 48000)
    assert player.loaded
    assert player.duration_sec == pytest.approx(1.0)
    assert player.position_sec == pytest.approx(0.0)
    with pytest.raises(AudioDeviceError):
        BufferPlayer().play()  # nothing loaded
