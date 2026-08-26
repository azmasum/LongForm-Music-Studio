"""Piano Roll editor: QGraphicsView for editing MidiClip notes visually.

Features:
- Piano keys on the left (C2-C7)
- Beat/bar grid with configurable zoom
- Click to add note, drag to move, drag right edge to resize
- Delete key removes selected notes
- Snap-to-grid toggle (off / 1/4 / 1/8 / 1/16 / 1/32)
- Horizontal zoom with Ctrl+scroll, vertical scroll for pitch
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from lfms.app.theme import TEXT_DIM
from lfms.midi.model import (
    MAX_NOTE,
    MIN_NOTE,
    MidiClip,
    MidiNote,
    snap_to_grid,
)

KEY_HEIGHT = 16
KEYBOARD_WIDTH = 64
DEFAULT_PX_PER_BEAT = 80
MIN_PX_PER_BEAT = 20
MAX_PX_PER_BEAT = 400
NOTE_HEIGHT = KEY_HEIGHT
NOTE_MIN_WIDTH = 4

SNAP_OPTIONS = {
    "Off": 0.0,
    "1/4": 1.0,
    "1/8": 0.5,
    "1/16": 0.25,
    "1/32": 0.125,
}

BLACK_KEYS = frozenset({1, 3, 6, 8, 10})

KEY_COLORS = {
    False: QColor(50, 50, 60),
    True: QColor(30, 30, 38),
}

NOTE_COLORS = [
    QColor(80, 180, 255),
    QColor(120, 220, 140),
    QColor(255, 160, 80),
    QColor(200, 120, 220),
]


class PianoKeyItem(QGraphicsRectItem):
    def __init__(self, pitch: int, parent=None):
        super().__init__(0, 0, KEYBOARD_WIDTH, KEY_HEIGHT, parent)
        self.pitch = pitch
        is_black = (pitch % 12) in BLACK_KEYS
        self.setBrush(QBrush(KEY_COLORS[is_black]))
        self.setPen(QPen(QColor(20, 20, 26), 0.5))
        self.setZValue(10)


class NoteItem(QGraphicsRectItem):
    """Visual representation of a MidiNote on the grid."""

    def __init__(self, note: MidiNote, color_idx: int = 0, parent=None):
        self._note = note
        self._color_idx = color_idx % len(NOTE_COLORS)
        super().__init__(0, 0, 10, NOTE_HEIGHT, parent)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self._refresh()

    @property
    def note(self) -> MidiNote:
        return self._note

    def _refresh(self):
        color = NOTE_COLORS[self._color_idx]
        if self.isSelected():
            color = color.lighter(140)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(20, 20, 30), 1))

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._refresh()
        return super().itemChange(change, value)


class PianoRollScene(QGraphicsScene):
    note_added = Signal(float, int, float)
    note_removed = Signal(str)
    note_moved = Signal(str, float, int)
    note_resized = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._px_per_beat = DEFAULT_PX_PER_BEAT
        self._bpm = 120.0
        self._duration_beats = 32
        self._snap = 0.0
        self._note_items: dict[str, NoteItem] = {}
        self._key_items: list[PianoKeyItem] = []
        self._drag_mode: str | None = None
        self._drag_note_id: str | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_orig_note: MidiNote | None = None
        self._build_key_items()
        self._rebuild_grid()

    @property
    def px_per_beat(self):
        return self._px_per_beat

    @px_per_beat.setter
    def px_per_beat(self, v: float):
        self._px_per_beat = max(MIN_PX_PER_BEAT, min(MAX_PX_PER_BEAT, v))
        self._rebuild_grid()

    @property
    def snap(self):
        return self._snap

    @snap.setter
    def snap(self, v: float):
        self._snap = v

    @property
    def bpm(self):
        return self._bpm

    @bpm.setter
    def bpm(self, v: float):
        self._bpm = max(1.0, v)

    def set_duration_beats(self, beats: float):
        self._duration_beats = max(4, beats)
        self._rebuild_grid()

    def _build_key_items(self):
        for item in self._key_items:
            self.removeItem(item)
        self._key_items.clear()
        for pitch in range(MAX_NOTE, MIN_NOTE - 1, -1):
            row = MAX_NOTE - pitch
            key = PianoKeyItem(pitch)
            key.setPos(0, row * KEY_HEIGHT)
            self._key_items.append(key)

    def _rebuild_grid(self):
        for item in list(self.items()):
            if isinstance(item, (PianoKeyItem, NoteItem)):
                continue
            self.removeItem(item)
        w = KEYBOARD_WIDTH + self._duration_beats * self._px_per_beat + 200
        h = (MAX_NOTE - MIN_NOTE + 1) * KEY_HEIGHT + 4
        self.setSceneRect(0, 0, w, h)
        beat_pen = QPen(QColor(55, 55, 68), 1.0)
        bar_pen = QPen(QColor(70, 70, 85), 1.5)
        for pitch in range(MAX_NOTE, MIN_NOTE - 1, -1):
            row = MAX_NOTE - pitch
            y = row * KEY_HEIGHT
            is_black = (pitch % 12) in BLACK_KEYS
            row_pen = QPen(QColor(28, 28, 36) if is_black else QColor(32, 32, 42), 0.5)
            line = self.addLine(KEYBOARD_WIDTH, y, w, y, row_pen)
            line.setZValue(-1)
        for beat in range(int(self._duration_beats) + 1):
            x = KEYBOARD_WIDTH + beat * self._px_per_beat
            is_bar = beat % 4 == 0
            pen = bar_pen if is_bar else beat_pen
            line = self.addLine(x, 0, x, h, pen)
            line.setZValue(-1)

    def load_clip(self, clip: MidiClip):
        for item in list(self._note_items.values()):
            self.removeItem(item)
        self._note_items.clear()
        self._bpm = clip.tempo_bpm
        self.set_duration_beats(max(32, int(clip.duration_sec * clip.tempo_bpm / 60.0) + 8))
        for i, note in enumerate(clip.notes):
            self._add_note_item(note, i)

    def _add_note_item(self, note: MidiNote, idx: int = 0):
        item = NoteItem(note, idx)
        self._place_note_item(item)
        self.addItem(item)
        self._note_items[note.note_id] = item

    def _place_note_item(self, item: NoteItem):
        note = item._note
        x = KEYBOARD_WIDTH + note.start_sec * self._bpm / 60.0 * self._px_per_beat
        w = max(NOTE_MIN_WIDTH, note.duration_sec * self._bpm / 60.0 * self._px_per_beat)
        y = (MAX_NOTE - note.pitch) * KEY_HEIGHT
        item.setPos(x, y)
        item.setRect(0, 0, w, NOTE_HEIGHT)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.scenePos()
            item = self.itemAt(pos)
            if isinstance(item, NoteItem):
                self._drag_mode = "move"
                self._drag_note_id = item.note.note_id
                self._drag_start_pos = pos
                self._drag_orig_note = MidiNote(
                    pitch=item.note.pitch,
                    start_sec=item.note.start_sec,
                    duration_sec=item.note.duration_sec,
                    velocity=item.note.velocity,
                    channel=item.note.channel,
                )
                super().mousePressEvent(event)
                return
            elif pos.x() > KEYBOARD_WIDTH:
                pitch = MAX_NOTE - int(pos.y() / KEY_HEIGHT)
                pitch = max(MIN_NOTE, min(MAX_NOTE, pitch))
                beat_pos = (pos.x() - KEYBOARD_WIDTH) / self._px_per_beat
                sec = beat_pos * 60.0 / self._bpm
                dur_beats = 0.25
                if self._snap > 0:
                    dur_beats = self._snap
                dur_sec = dur_beats * 60.0 / self._bpm
                self.note_added.emit(sec, pitch, dur_sec)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode == "move" and self._drag_start_pos and self._drag_note_id:
            item = self._note_items.get(self._drag_note_id)
            if item and self._drag_orig_note:
                dx = event.scenePos().x() - self._drag_start_pos.x()
                dy = event.scenePos().y() - self._drag_start_pos.y()
                orig = self._drag_orig_note
                new_sec = orig.start_sec + dx / self._px_per_beat * 60.0 / self._bpm
                new_pitch = orig.pitch - int(round(dy / KEY_HEIGHT))
                new_pitch = max(MIN_NOTE, min(MAX_NOTE, new_pitch))
                if self._snap > 0:
                    new_sec = snap_to_grid(new_sec, self._bpm, self._snap)
                item._note.start_sec = max(0.0, new_sec)
                item._note.pitch = new_pitch
                self._place_note_item(item)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_mode == "move" and self._drag_note_id:
            item = self._note_items.get(self._drag_note_id)
            if item:
                self.note_moved.emit(
                    item.note.note_id, item.note.start_sec, item.note.pitch
                )
        self._drag_mode = None
        self._drag_note_id = None
        self._drag_start_pos = None
        self._drag_orig_note = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            for item in self.selectedItems():
                if isinstance(item, NoteItem):
                    self.note_removed.emit(item.note.note_id)
                    self.removeItem(item)
                    self._note_items.pop(item.note.note_id, None)
            return
        super().keyPressEvent(event)


class PianoRollWidget(QWidget):
    """Self-contained piano roll editor with toolbar."""

    clip_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._clip: MidiClip | None = None
        self._color_idx = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        self._snap_combo = QComboBox()
        self._snap_combo.addItems(list(SNAP_OPTIONS.keys()))
        self._snap_combo.currentTextChanged.connect(self._on_snap_change)
        self._snap_combo.setFixedWidth(80)
        toolbar.addWidget(QLabel("Snap:"))
        toolbar.addWidget(self._snap_combo)
        toolbar.addStretch()
        self._info_label = QLabel("Click on the grid to add notes")
        self._info_label.setStyleSheet(f"color: {TEXT_DIM};")
        toolbar.addWidget(self._info_label)
        layout.addLayout(toolbar)

        self._scene = PianoRollScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        layout.addWidget(self._view)

        self._scene.note_added.connect(self._on_note_added)
        self._scene.note_removed.connect(self._on_note_removed)
        self._scene.note_moved.connect(self._on_note_moved)

    def set_clip(self, clip: MidiClip):
        self._clip = clip
        self._scene.load_clip(clip)
        self._info_label.setText(f"{clip.title} — {len(clip.notes)} notes")
        self._view.centerOn(KEYBOARD_WIDTH + 200, (MAX_NOTE - 72) * KEY_HEIGHT)

    @property
    def clip(self) -> MidiClip | None:
        return self._clip

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._scene.px_per_beat = self._scene.px_per_beat * factor
            event.accept()
        else:
            self._view.wheelEvent(event)

    def _on_snap_change(self, text: str):
        self._scene.snap = SNAP_OPTIONS.get(text, 0.0)

    def _on_note_added(self, sec: float, pitch: int, dur_sec: float):
        if self._clip is None:
            return
        note = MidiNote(pitch=pitch, start_sec=sec, duration_sec=dur_sec)
        self._clip.add_note(note)
        self._scene._add_note_item(note, len(self._clip.notes))
        self.clip_changed.emit()

    def _on_note_removed(self, note_id: str):
        if self._clip is None:
            return
        try:
            self._clip.remove_note(note_id)
            self.clip_changed.emit()
        except Exception:
            pass

    def _on_note_moved(self, note_id: str, new_sec: float, new_pitch: int):
        if self._clip is None:
            return
        for note in self._clip.notes:
            if note.note_id == note_id:
                note.start_sec = new_sec
                note.pitch = new_pitch
                self.clip_changed.emit()
                return
