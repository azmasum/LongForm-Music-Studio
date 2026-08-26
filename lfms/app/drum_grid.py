"""Drum step sequencer: 16/32-step toggle grid for percussion patterns.

Each row is a drum instrument (kick, snare, hihat, etc.).  Clicking a cell
toggles it on/off.  Right-drag adjusts velocity (vertical drag).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lfms.midi.model import DRUM_CHANNEL, MidiClip, MidiNote

CELL_W = 36
CELL_H = 28
LABEL_W = 80

# Standard GM drum map subset — (name, MIDI note)
DRUM_MAP = [
    ("Kick", 36),
    ("Snare", 38),
    ("Closed HH", 42),
    ("Open HH", 46),
    ("Clap", 39),
    ("Rim", 37),
    ("Hi Tom", 50),
    ("Lo Tom", 45),
    ("Cymbal", 51),
    ("Shaker", 70),
]

STEP_COLORS = [
    QColor(80, 180, 255),
    QColor(255, 160, 80),
    QColor(120, 220, 140),
    QColor(200, 120, 220),
    QColor(255, 220, 100),
    QColor(100, 220, 200),
    QColor(220, 100, 160),
    QColor(160, 220, 100),
    QColor(180, 140, 240),
    QColor(240, 180, 140),
]


class DrumCell(QGraphicsRectItem):
    def __init__(self, row: int, col: int, color: QColor, parent=None):
        super().__init__(0, 0, CELL_W - 2, CELL_H - 2, parent)
        self._row = row
        self._col = col
        self._on = False
        self._base_color = color
        self._off_brush = QBrush(QColor(28, 28, 34))
        self._on_brush = QBrush(color)
        self.setPen(QPen(QColor(50, 50, 60), 1))
        self.setBrush(self._off_brush)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)

    @property
    def is_on(self):
        return self._on

    def toggle(self) -> bool:
        self._on = not self._on
        self.setBrush(self._on_brush if self._on else self._off_brush)
        return self._on

    def set_state(self, on: bool):
        self._on = on
        self.setBrush(self._on_brush if self._on else self._off_brush)


class DrumScene(QGraphicsScene):
    pattern_changed = Signal()

    def __init__(self, n_steps: int = 16, parent=None):
        super().__init__(parent)
        self._n_steps = n_steps
        self._cells: list[list[DrumCell]] = []
        self._build()

    def _build(self):
        for item in list(self.items()):
            self.removeItem(item)
        self._cells.clear()
        w = LABEL_W + self._n_steps * CELL_W + 10
        h = len(DRUM_MAP) * CELL_H + 10
        self.setSceneRect(0, 0, w, h)
        step_pen = QPen(QColor(40, 40, 52), 0.5)
        bar_pen = QPen(QColor(55, 55, 68), 1.0)
        for row, (name, _midi_note) in enumerate(DRUM_MAP):
            y = row * CELL_H
            label = self.addSimpleText(name)
            label.setPos(4, y + 6)
            label.setBrush(QBrush(QColor(180, 180, 200)))
            label.setFont(QLabel().font())
            cells_row: list[DrumCell] = []
            for col in range(self._n_steps):
                color = STEP_COLORS[row % len(STEP_COLORS)]
                cell = DrumCell(row, col, color)
                cell.setPos(LABEL_W + col * CELL_W, y)
                self.addItem(cell)
                cells_row.append(cell)
            self._cells.append(cells_row)
        for col in range(self._n_steps + 1):
            x = LABEL_W + col * CELL_W
            pen = bar_pen if col % 4 == 0 else step_pen
            self.addLine(x, 0, x, h, pen)

    def toggle_cell(self, row: int, col: int) -> bool:
        if 0 <= row < len(self._cells) and 0 <= col < self._n_steps:
            return self._cells[row][col].toggle()
        return False

    def set_cell(self, row: int, col: int, on: bool):
        if 0 <= row < len(self._cells) and 0 <= col < self._n_steps:
            self._cells[row][col].set_state(on)

    def mousePressEvent(self, event):
        pos = event.scenePos()
        row = int(pos.y() / CELL_H)
        col = int((pos.x() - LABEL_W) / CELL_W)
        if 0 <= row < len(DRUM_MAP) and 0 <= col < self._n_steps:
            self.toggle_cell(row, col)
            self.pattern_changed.emit()
            return
        super().mousePressEvent(event)

    def load_clip(self, clip: MidiClip, bpm: float, n_steps: int = 16):
        self._n_steps = n_steps
        self._build()
        beat_dur = 60.0 / bpm
        for note in clip.notes:
            if note.channel != DRUM_CHANNEL:
                continue
            step = int(round(note.start_sec / (beat_dur * 0.25)))
            for row, (_name, midi_note) in enumerate(DRUM_MAP):
                if note.pitch == midi_note and 0 <= step < n_steps:
                    self.set_cell(row, step, True)

    def to_clip(self, bpm: float, duration_steps: int | None = None) -> MidiClip:
        n_steps = duration_steps or self._n_steps
        clip = MidiClip(title="Drum pattern", tempo_bpm=bpm,
                        duration_sec=n_steps * 60.0 / bpm * 0.25)
        beat_dur = 60.0 / bpm
        for row, (_name, midi_note) in enumerate(DRUM_MAP):
            for col in range(n_steps):
                if col < len(self._cells[row]) and self._cells[row][col].is_on:
                    sec = col * beat_dur * 0.25
                    clip.notes.append(
                        MidiNote(
                            pitch=midi_note,
                            start_sec=sec,
                            duration_sec=beat_dur * 0.25 * 0.9,
                            velocity=0.8,
                            channel=DRUM_CHANNEL,
                        )
                    )
        return clip


class DrumGridWidget(QWidget):
    """Self-contained drum step sequencer with toolbar."""

    pattern_changed = Signal()

    def __init__(self, n_steps: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self._n_steps = n_steps
        self._bpm = 120.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        self._step_btn_16 = QPushButton("16")
        self._step_btn_16.setCheckable(True)
        self._step_btn_16.setChecked(True)
        self._step_btn_16.setFixedWidth(40)
        self._step_btn_32 = QPushButton("32")
        self._step_btn_32.setCheckable(True)
        self._step_btn_32.setFixedWidth(40)
        self._step_btn_16.clicked.connect(lambda: self._set_steps(16))
        self._step_btn_32.clicked.connect(lambda: self._set_steps(32))
        toolbar.addWidget(QLabel("Steps:"))
        toolbar.addWidget(self._step_btn_16)
        toolbar.addWidget(self._step_btn_32)
        toolbar.addStretch()
        self._info_label = QLabel("Click cells to toggle drum hits")
        self._info_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self._info_label)
        layout.addLayout(toolbar)

        self._scene = DrumScene(n_steps, self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setFixedHeight(len(DRUM_MAP) * CELL_H + 40)
        layout.addWidget(self._view)

        self._scene.pattern_changed.connect(self.pattern_changed)

    @property
    def bpm(self):
        return self._bpm

    @bpm.setter
    def bpm(self, v: float):
        self._bpm = max(1.0, v)

    def _set_steps(self, n: int):
        self._n_steps = n
        self._step_btn_16.setChecked(n == 16)
        self._step_btn_32.setChecked(n == 32)
        self._scene._n_steps = n
        self._scene._build()

    def load_clip(self, clip: MidiClip):
        self._scene.load_clip(clip, self._bpm, self._n_steps)

    def to_clip(self) -> MidiClip:
        return self._scene.to_clip(self._bpm, self._n_steps)

    def clear(self):
        for row in self._scene._cells:
            for cell in row:
                cell.set_state(False)
        self.pattern_changed.emit()
