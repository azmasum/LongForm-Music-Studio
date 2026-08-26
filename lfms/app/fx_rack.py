"""FX Rack panel: per-track effect chain editor with add/remove/reorder.

Displays the effect chain for a selected track. Each effect has a header
(type label, bypass toggle, delete button) and an expandable parameter area.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lfms.app.theme import TEXT_DIM
from lfms.timeline.model import EffectSlot, FxChain

EFFECT_TYPES = ["gain", "eq", "compressor", "delay", "reverb"]
EFFECT_LABELS = {
    "gain": "Gain",
    "eq": "EQ (3-band)",
    "compressor": "Compressor",
    "delay": "Delay",
    "reverb": "Reverb",
}

# Default parameter sets per effect type
EFFECT_DEFAULTS: dict[str, dict] = {
    "gain": {"gain_db": 0.0},
    "eq": {
        "low_cutoff": 200.0,
        "low_gain_db": 0.0,
        "mid_cutoff": 1000.0,
        "mid_q": 0.707,
        "mid_gain_db": 0.0,
        "high_cutoff": 4000.0,
        "high_gain_db": 0.0,
    },
    "compressor": {
        "threshold_db": -20.0,
        "ratio": 4.0,
        "attack_sec": 0.005,
        "release_sec": 0.05,
        "makeup_db": 0.0,
    },
    "delay": {
        "delay_sec": 0.25,
        "feedback": 0.3,
        "wet": 0.3,
        "ping_pong": False,
    },
    "reverb": {
        "room_size": 0.7,
        "damping": 0.5,
        "wet": 0.3,
    },
}

PARAM_LABELS: dict[str, dict[str, str]] = {
    "gain": {"gain_db": "Gain (dB)"},
    "eq": {
        "low_cutoff": "Low Freq (Hz)",
        "low_gain_db": "Low Gain (dB)",
        "mid_cutoff": "Mid Freq (Hz)",
        "mid_q": "Mid Q",
        "mid_gain_db": "Mid Gain (dB)",
        "high_cutoff": "High Freq (Hz)",
        "high_gain_db": "High Gain (dB)",
    },
    "compressor": {
        "threshold_db": "Threshold (dB)",
        "ratio": "Ratio",
        "attack_sec": "Attack (s)",
        "release_sec": "Release (s)",
        "makeup_db": "Makeup (dB)",
    },
    "delay": {
        "delay_sec": "Time (s)",
        "feedback": "Feedback",
        "wet": "Wet/Dry",
        "ping_pong": "Ping-Pong",
    },
    "reverb": {
        "room_size": "Room Size",
        "damping": "Damping",
        "wet": "Wet/Dry",
    },
}

# Spinbox ranges: (min, max, step, decimals)
PARAM_RANGES: dict[str, dict[str, tuple[float, float, float, int]]] = {
    "gain": {"gain_db": (-60, 24, 0.5, 1)},
    "eq": {
        "low_cutoff": (20, 500, 10, 0),
        "low_gain_db": (-24, 24, 0.5, 1),
        "mid_cutoff": (200, 8000, 50, 0),
        "mid_q": (0.1, 10.0, 0.1, 2),
        "mid_gain_db": (-24, 24, 0.5, 1),
        "high_cutoff": (1000, 20000, 100, 0),
        "high_gain_db": (-24, 24, 0.5, 1),
    },
    "compressor": {
        "threshold_db": (-80, 0, 1, 0),
        "ratio": (1.0, 30.0, 0.5, 1),
        "attack_sec": (0.0001, 0.1, 0.001, 4),
        "release_sec": (0.005, 1.0, 0.005, 3),
        "makeup_db": (-24, 24, 0.5, 1),
    },
    "delay": {
        "delay_sec": (0.01, 2.0, 0.01, 3),
        "feedback": (0.0, 0.95, 0.05, 2),
        "wet": (0.0, 1.0, 0.05, 2),
    },
    "reverb": {
        "room_size": (0.0, 1.0, 0.05, 2),
        "damping": (0.0, 1.0, 0.05, 2),
        "wet": (0.0, 1.0, 0.05, 2),
    },
}


class EffectWidget(QFrame):
    """Widget for a single effect slot with parameter editors."""

    params_changed = Signal(str)  # emits effect_id
    remove_clicked = Signal(str)  # emits effect_id
    bypass_toggled = Signal(str, bool)  # effect_id, enabled

    def __init__(self, slot: EffectSlot, parent: QWidget | None = None):
        super().__init__(parent)
        self._slot = slot
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "EffectWidget { border: 1px solid #333; border-radius: 4px; "
            "background: #1e1e26; margin: 2px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(4)
        self._bypass_cb = QCheckBox()
        self._bypass_cb.setChecked(slot.enabled)
        self._bypass_cb.setFixedWidth(16)
        self._bypass_cb.toggled.connect(
            lambda checked: self.bypass_toggled.emit(slot.effect_id, checked)
        )
        header.addWidget(self._bypass_cb)

        type_label = QLabel(EFFECT_LABELS.get(slot.effect_type, slot.effect_type))
        type_label.setStyleSheet(f"color: {TEXT_DIM}; font-weight: bold; border: none;")
        header.addWidget(type_label)
        header.addStretch()

        del_btn = QPushButton("\u00d7")
        del_btn.setFixedSize(20, 20)
        del_btn.setStyleSheet(
            "QPushButton { border: none; color: #888; font-size: 14px; }"
            "QPushButton:hover { color: #f44; }"
        )
        del_btn.clicked.connect(lambda: self.remove_clicked.emit(slot.effect_id))
        header.addWidget(del_btn)
        layout.addLayout(header)

        # Parameters
        param_layout = QFormLayout()
        param_layout.setSpacing(2)
        labels = PARAM_LABELS.get(slot.effect_type, {})
        ranges = PARAM_RANGES.get(slot.effect_type, {})
        self._param_widgets: dict[str, QWidget] = {}

        for param_name, label_text in labels.items():
            value = slot.params.get(param_name, EFFECT_DEFAULTS.get(slot.effect_type, {}).get(param_name, 0))
            if param_name == "ping_pong":
                cb = QCheckBox()
                cb.setChecked(bool(value))
                cb.stateChanged.connect(
                    lambda state, pn=param_name: self._on_param_changed(pn, bool(state))
                )
                self._param_widgets[param_name] = cb
                param_layout.addRow(label_text, cb)
            else:
                mn, mx, step, dec = ranges.get(param_name, (0, 100, 1, 1))
                spin = QDoubleSpinBox()
                spin.setRange(mn, mx)
                spin.setSingleStep(step)
                spin.setDecimals(dec)
                spin.setValue(float(value))
                spin.setFixedWidth(90)
                spin.valueChanged.connect(
                    lambda val, pn=param_name: self._on_param_changed(pn, float(val))
                )
                self._param_widgets[param_name] = spin
                param_layout.addRow(label_text, spin)
        layout.addLayout(param_layout)

    def _on_param_changed(self, param_name: str, value):
        self._slot.params[param_name] = value
        self.params_changed.emit(self._slot.effect_id)

    @property
    def slot(self) -> EffectSlot:
        return self._slot


class FxRackWidget(QWidget):
    """Complete FX rack: add/remove effects, edit parameters per effect."""

    chain_changed = Signal()  # emitted when any effect is added/removed/changed

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._chain: FxChain | None = None
        self._effect_widgets: dict[str, EffectWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 4)
        title = QLabel("FX Rack")
        title.setStyleSheet(f"color: {TEXT_DIM}; font-weight: bold; border: none;")
        header.addWidget(title)
        header.addStretch()
        self._add_combo = QComboBox()
        self._add_combo.setFixedWidth(110)
        for t in EFFECT_TYPES:
            self._add_combo.addItem(EFFECT_LABELS.get(t, t), t)
        header.addWidget(self._add_combo)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.clicked.connect(self._on_add_effect)
        header.addWidget(add_btn)
        layout.addLayout(header)

        # Scroll area for effects
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(400)
        self._effects_container = QWidget()
        self._effects_layout = QVBoxLayout(self._effects_container)
        self._effects_layout.setContentsMargins(0, 0, 0, 0)
        self._effects_layout.setSpacing(2)
        self._effects_layout.addStretch()
        scroll.setWidget(self._effects_container)
        layout.addWidget(scroll)

        self._empty_label = QLabel("No effects — click + to add")
        self._empty_label.setStyleSheet(f"color: {TEXT_DIM}; border: none; padding: 8px;")
        self._effects_layout.insertWidget(0, self._empty_label)

    def set_chain(self, chain: FxChain):
        self._chain = chain
        self._rebuild()

    @property
    def chain(self) -> FxChain | None:
        return self._chain

    def _rebuild(self):
        # Clear existing widgets
        for w in self._effect_widgets.values():
            w.setParent(None)
            w.deleteLater()
        self._effect_widgets.clear()

        if self._chain is None:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(len(self._chain.slots) == 0)
        for slot in self._chain.slots:
            self._add_effect_widget(slot)

    def _add_effect_widget(self, slot: EffectSlot):
        w = EffectWidget(slot)
        w.params_changed.connect(self._on_params_changed)
        w.remove_clicked.connect(self._on_remove_effect)
        w.bypass_toggled.connect(self._on_bypass_toggled)
        self._effect_widgets[slot.effect_id] = w
        self._effects_layout.insertWidget(self._effects_layout.count() - 1, w)
        self._empty_label.setVisible(False)

    def _on_add_effect(self):
        if self._chain is None:
            return
        effect_type = self._add_combo.currentData()
        params = dict(EFFECT_DEFAULTS.get(effect_type, {}))
        slot = self._chain.add(effect_type, params)
        self._add_effect_widget(slot)
        self.chain_changed.emit()

    def _on_remove_effect(self, effect_id: str):
        if self._chain is None:
            return
        self._chain.remove(effect_id)
        w = self._effect_widgets.pop(effect_id, None)
        if w:
            w.setParent(None)
            w.deleteLater()
        self._empty_label.setVisible(len(self._chain.slots) == 0)
        self.chain_changed.emit()

    def _on_params_changed(self, effect_id: str):
        self.chain_changed.emit()

    def _on_bypass_toggled(self, effect_id: str, enabled: bool):
        if self._chain is None:
            return
        for slot in self._chain.slots:
            if slot.effect_id == effect_id:
                slot.enabled = enabled
                break
        self.chain_changed.emit()
