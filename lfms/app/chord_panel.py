"""Chord progression panel: select key, pick progression, preview, generate MIDI.

Includes a chord chart display showing symbols per bar.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lfms.app.theme import TEXT_DIM
from lfms.music.chords import (
    NOTE_NAMES,
    PROGRESSION_PRESETS,
    Progression,
    progression_to_midi_clip,
)


class ChordChartWidget(QWidget):
    """Displays chord symbols per bar as colored boxes."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._symbols: list[str] = []
        self._bars: int = 0
        self.setMinimumHeight(48)
        self.setMaximumHeight(64)

    def set_chords(self, symbols: list[str], bars: int):
        self._symbols = symbols
        self._bars = bars
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, QColor(22, 22, 28))
        if not self._symbols or self._bars == 0:
            p.end()
            return
        bar_w = w / max(1, self._bars)
        colors = [
            QColor(80, 180, 255), QColor(120, 220, 140),
            QColor(255, 160, 80), QColor(200, 120, 220),
        ]
        font = QFont("Consolas", 11)
        p.setFont(font)
        fm = QFontMetrics(font)
        for bar in range(self._bars):
            x = int(bar * bar_w)
            color = colors[bar % len(colors)]
            p.setPen(QPen(color, 1))
            p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 30)))
            p.drawRoundedRect(x + 2, 2, int(bar_w) - 4, h - 4, 4, 4)
            idx = bar % len(self._symbols)
            text = self._symbols[idx]
            tw = fm.horizontalAdvance(text)
            p.setPen(QPen(color))
            p.drawText(x + int((bar_w - tw) / 2), h - 12, text)
        p.end()


class ProgressionWidget(QWidget):
    """Self-contained progression selector with chord chart and generate button."""

    midi_generated = Signal(object)  # emits MidiClip

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Controls
        controls = QHBoxLayout()
        controls.setContentsMargins(4, 4, 4, 4)

        # Key selector
        key_group = QHBoxLayout()
        key_group.setSpacing(2)
        self._key_combo = QComboBox()
        self._key_combo.setFixedWidth(50)
        for name in NOTE_NAMES:
            self._key_combo.addItem(name)
        self._key_combo.setCurrentIndex(0)
        self._mode_combo = QComboBox()
        self._mode_combo.setFixedWidth(70)
        self._mode_combo.addItems(["major", "minor"])
        key_group.addWidget(QLabel("Key:"))
        key_group.addWidget(self._key_combo)
        key_group.addWidget(self._mode_combo)
        controls.addLayout(key_group)

        # Progression selector
        self._prog_combo = QComboBox()
        self._prog_combo.setMinimumWidth(180)
        for name in sorted(PROGRESSION_PRESETS.keys()):
            self._prog_combo.addItem(name)
        controls.addWidget(QLabel("Progression:"))
        controls.addWidget(self._prog_combo)

        # BPM
        self._bpm_spin = QSpinBox()
        self._bpm_spin.setRange(40, 300)
        self._bpm_spin.setValue(120)
        self._bpm_spin.setFixedWidth(55)
        controls.addWidget(QLabel("BPM:"))
        controls.addWidget(self._bpm_spin)

        # Bars
        self._bars_spin = QSpinBox()
        self._bars_spin.setRange(1, 64)
        self._bars_spin.setValue(4)
        self._bars_spin.setFixedWidth(45)
        controls.addWidget(QLabel("Bars:"))
        controls.addWidget(self._bars_spin)

        controls.addStretch()

        # Generate button
        self._gen_btn = QPushButton("Generate MIDI")
        self._gen_btn.setStyleSheet(
            "QPushButton { padding: 4px 12px; }"
            "QPushButton:hover { background: #2a5a9a; }"
        )
        self._gen_btn.clicked.connect(self._on_generate)
        controls.addWidget(self._gen_btn)
        layout.addLayout(controls)

        # Chord chart
        self._chart = ChordChartWidget()
        layout.addWidget(self._chart)

        # Info
        self._info_label = QLabel("Select a progression and click Generate")
        self._info_label.setStyleSheet(f"color: {TEXT_DIM}; border: none;")
        layout.addWidget(self._info_label)

        # Wire up previews
        self._prog_combo.currentTextChanged.connect(self._update_preview)
        self._key_combo.currentIndexChanged.connect(self._update_preview)
        self._mode_combo.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

    def _get_progression(self) -> Progression:
        key_idx = self._key_combo.currentIndex()
        key_root = key_idx  # C=0, C#=1, etc.
        mode = self._mode_combo.currentText()
        prog_name = self._prog_combo.currentText()
        bpm = float(self._bpm_spin.value())
        return Progression.from_preset(prog_name, key_root=key_root,
                                       key_mode=mode, bpm=bpm)

    def _update_preview(self):
        try:
            prog = self._get_progression()
            symbols = prog.chord_symbols()
            bars = self._bars_spin.value()
            self._chart.set_chords(symbols, bars)
            sym_str = " - ".join(symbols)
            self._info_label.setText(
                f"{prog.name} in {NOTE_NAMES[self._key_combo.currentIndex()]} "
                f"{self._mode_combo.currentText()}: {sym_str}"
            )
        except Exception as e:
            self._info_label.setText(f"Error: {e}")

    def _on_generate(self):
        prog = self._get_progression()
        bars = self._bars_spin.value()
        clip = progression_to_midi_clip(prog, bars=bars)
        self.midi_generated.emit(clip)
        self._info_label.setText(
            f"Generated: {clip.title} — {len(clip.notes)} notes, "
            f"{clip.duration_sec:.1f}s"
        )
