"""PySide6 application shell: sidebar navigation, dark theme, transport bar,
timeline canvas, functional Generate/Library/Mix pages."""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from lfms.app.theme import ACCENT, BORDER, POSITIVE, TEXT_DIM
from lfms.core.enums import Genre, Mood
from lfms.core.errors import ValidationError
from lfms.core.version import APP_NAME, VERSION
from lfms.exporter import export_item
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import Item, LibraryService
from lfms.mastering import known_target_presets
from lfms.provenance import (
    ProvenanceRecord,
    format_duration,
    record_from_item,
    verify_item,
    write_certificate,
)
from lfms.timeline import (
    AddClipCommand,
    AddTrackCommand,
    Clip,
    CommandStack,
    SetTrackPropertyCommand,
    TimelineDocument,
    TrackState,
)

SIDEBAR_ITEMS = ("Library", "Generate", "Timeline", "Mix", "Export")

DEFAULT_DB_PATH = Path.home() / ".lfms" / "library.db"


def format_time(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 60:02d}:{total % 60:02d}"


def humanize(value: str) -> str:
    return value.replace("_", " ").title()


class TransportBar(QFrame):
    play_toggled = Signal(bool)
    stopped = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("transport")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)
        self.stop_button = QPushButton("Stop")
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("muted")

        self.position = QSlider(Qt.Horizontal)
        self.position.setRange(0, 1)
        self.position.setEnabled(False)

        layout.addWidget(self.play_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.position, stretch=1)
        layout.addWidget(self.time_label)

        self.play_button.toggled.connect(self.play_toggled.emit)
        self.stop_button.clicked.connect(self._on_stop)

    def _on_stop(self) -> None:
        self.play_button.setChecked(False)
        self.set_position(0.0)
        self.stopped.emit()

    def set_range(self, duration_sec: float) -> None:
        self.position.setMaximum(max(1, int(duration_sec)))

    def set_position(self, seconds: float) -> None:
        if not self.position.isSliderDown():
            self.position.setValue(int(seconds))
        duration = self.position.maximum()
        self.time_label.setText(f"{format_time(seconds)} / {format_time(duration)}")


class TimelineCanvas(QWidget):
    RULER_HEIGHT = 24
    LANE_HEIGHT = 38
    LANE_GAP = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document: TimelineDocument | None = None
        self.setMinimumHeight(240)

    def set_document(self, document: TimelineDocument) -> None:
        self.document = document
        rows = len(document.tracks)
        self.setMinimumHeight(
            self.RULER_HEIGHT + rows * (self.LANE_HEIGHT + self.LANE_GAP) + 40
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#14141c"))
        if self.document is None or not self.document.tracks:
            painter.setPen(QPen(QColor(TEXT_DIM)))
            painter.drawText(self.rect(), Qt.AlignCenter, "No timeline loaded")
            return

        document = self.document
        width = max(1.0, float(self.width()) - 24.0)
        scale = width / max(1.0, document.duration_sec)
        origin_x, y = 12.0, float(self.RULER_HEIGHT)

        tick_step = 30.0
        while document.duration_sec / tick_step > 40:
            tick_step *= 2
        t = 0.0
        while t <= document.duration_sec:
            x = origin_x + t * scale
            painter.setPen(QPen(QColor(BORDER)))
            painter.drawLine(int(x), 4, int(x), int(y))
            painter.drawText(int(x) + 3, 16, format_time(t))
            t += tick_step

        for marker in document.markers:
            x = origin_x + marker.time_sec * scale
            color = QColor(ACCENT) if marker.kind == "SECTION" else QColor("#e0af68")
            painter.setPen(QPen(color, 1, Qt.DashLine))
            painter.drawLine(int(x), self.RULER_HEIGHT, int(x), self.height() - 8)
            painter.drawText(int(x) + 3, self.RULER_HEIGHT + 12, marker.label[:18])

        for index, track in enumerate(document.tracks):
            lane_y = y + index * (self.LANE_HEIGHT + self.LANE_GAP)
            painter.setBrush(QColor("#191a24"))
            painter.setPen(QPen(QColor(BORDER)))
            painter.drawRect(int(origin_x), int(lane_y), int(width), self.LANE_HEIGHT)
            painter.drawText(
                int(origin_x) + 6, int(lane_y) + 14, f"{track.name} ({humanize(track.kind)})"
            )
            for clip in document.clips_on_track(track.track_id):
                x0 = origin_x + clip.start_sec * scale
                rect_w = max(3, int(max(3.0, clip.duration_sec * scale)) - 2)
                rect_y = int(lane_y) + 16
                fill = QColor(ACCENT if clip.source_kind == "GENERATED" else POSITIVE)
                fill.setAlpha(150)
                painter.setBrush(fill)
                painter.drawRoundedRect(int(x0) + 1, rect_y, rect_w, self.LANE_HEIGHT - 20, 5, 5)
                if rect_w > 40:
                    painter.drawText(
                        int(x0) + 6,
                        rect_y + self.LANE_HEIGHT - 24,
                        (clip.label or clip.clip_id)[: rect_w // 8],
                    )


class GeneratePage(QWidget):
    generate_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)

        heading = QLabel("Generate music")
        heading.setObjectName("page-title")
        outer.addWidget(heading)
        outer.addSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)

        self.seed = QDoubleSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setDecimals(0)
        self.seed.setValue(float(random.randrange(1, 1_000_000)))
        self.randomize = QPushButton("Random seed")
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.seed, stretch=1)
        seed_row.addWidget(self.randomize)

        self.genre = QComboBox()
        for genre in Genre:
            self.genre.addItem(humanize(genre.value), genre.value)
        self.genre.setCurrentIndex(list(Genre).index(Genre.DOCUMENTARY))

        self.mood = QComboBox()
        for mood in Mood:
            self.mood.addItem(humanize(mood.value), mood.value)
        self.mood.setCurrentIndex(list(Mood).index(Mood.NEUTRAL))

        self.duration = QDoubleSpinBox()
        self.duration.setRange(10.0, 4 * 3600.0)
        self.duration.setDecimals(0)
        self.duration.setSuffix(" s")
        self.duration.setValue(600.0)
        self.duration.setSingleStep(30.0)

        self.intensity = QSlider(Qt.Horizontal)
        self.intensity.setRange(0, 100)
        self.intensity.setValue(50)
        self.intensity_value = QLabel("50")
        intensity_row = QHBoxLayout()
        intensity_row.addWidget(self.intensity, stretch=1)
        intensity_row.addWidget(self.intensity_value)

        form.addRow("Seed", seed_row)
        form.addRow("Genre", self.genre)
        form.addRow("Mood", self.mood)
        form.addRow("Duration", self.duration)
        form.addRow("Intensity", intensity_row)
        outer.addWidget(card)

        # ------------------------------------------------ AI Music Director
        director_box = QGroupBox("AI Music Director (optional — off by default)")
        director_layout = QVBoxLayout(director_box)
        self.director_enabled = QCheckBox(
            "Enable AI director (I understand where my prompt is sent)"
        )
        director_layout.addWidget(self.director_enabled)
        self.director_consent = QLabel(
            "Offline interpreter: runs entirely on this machine.\n"
            "Ollama provider: your prompt text is sent to your own "
            "Ollama server (localhost by default). Nothing else leaves "
            "the app."
        )
        self.director_consent.setWordWrap(True)
        self.director_consent.setVisible(False)
        director_layout.addWidget(self.director_consent)
        self.director_provider = QComboBox()
        from lfms.director import known_providers

        for name in known_providers():
            self.director_provider.addItem(name.capitalize(), name)
        self.director_prompt = QLineEdit()
        self.director_prompt.setPlaceholderText(
            'Describe the music, e.g. "calm 5 minute documentary bed '
            'under narration, slowly builds"'
        )
        self.suggest_button = QPushButton("Suggest parameters")
        suggest_button_row = QHBoxLayout()
        suggest_button_row.addWidget(self.director_provider)
        suggest_button_row.addWidget(self.suggest_button)
        director_layout.addWidget(self.director_prompt)
        director_layout.addLayout(suggest_button_row)
        outer.addWidget(director_box)

        self.generate_button = QPushButton("Generate into timeline")
        self.generate_button.setObjectName("primary")
        outer.addWidget(self.generate_button, alignment=Qt.AlignLeft)
        outer.addStretch(1)

        self.randomize.clicked.connect(
            lambda: self.seed.setValue(float(random.randrange(1, 1_000_000)))
        )
        self.intensity.valueChanged.connect(self.intensity_value.setNum)
        self.generate_button.clicked.connect(self._emit_request)

        from lfms.director import MusicDirector

        self.director = MusicDirector()
        self.director_provider.setEnabled(False)
        self.director_prompt.setEnabled(False)
        self.suggest_button.setEnabled(False)
        self.director_enabled.toggled.connect(self._on_director_toggled)
        self.suggest_button.clicked.connect(self._on_suggest_clicked)

    # ------------------------------------------------------- AI director

    def _on_director_toggled(self, checked: bool) -> None:
        if checked:
            self.director.enable(True)
        else:
            self.director.disable()
        self.director_consent.setVisible(checked)
        for widget in (
            self.director_provider,
            self.director_prompt,
            self.suggest_button,
        ):
            widget.setEnabled(checked)

    def _on_suggest_clicked(self) -> None:
        status = self.window().statusBar()
        try:
            self.director.use(self.director_provider.currentData())
            suggestion = self.director.direct(self.director_prompt.text())
        except ValidationError as exc:
            status.showMessage(f"AI director: {exc}", 6000)
            return
        params = suggestion.params
        self.seed.setValue(float(params.seed))
        genre_index = self.genre.findData(params.genre)
        if genre_index >= 0:
            self.genre.setCurrentIndex(genre_index)
        mood = params.moods[0] if params.moods else "NEUTRAL"
        mood_index = self.mood.findData(mood)
        if mood_index >= 0:
            self.mood.setCurrentIndex(mood_index)
        self.duration.setValue(float(params.duration_sec))
        self.intensity.setValue(int(round(params.intensity)))
        message = f"Applied ({suggestion.provider}): {suggestion.rationale}"
        if suggestion.warnings:
            message += " | " + "; ".join(suggestion.warnings)
        status.showMessage(message[:180], 12000)

    def current_parameters(self) -> dict:
        return {
            "seed": int(self.seed.value()),
            "genre": self.genre.currentData(),
            "moods": (self.mood.currentData(),),
            "duration_sec": float(self.duration.value()),
            "intensity": float(self.intensity.value()),
        }

    def _emit_request(self) -> None:
        self.generate_requested.emit(self.current_parameters())


class LibraryPage(QWidget):
    """Browser for the SQLite sound library with search/filter/collections."""

    def __init__(self, library: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)

        heading = QLabel("Library")
        heading.setObjectName("page-title")
        outer.addWidget(heading)
        outer.addSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, path, fingerprint or tag…")
        self.search.textChanged.connect(self.refresh)
        self.tag_filter = QComboBox()
        self.tag_filter.currentIndexChanged.connect(self.refresh)
        self.favorites_only = QCheckBox("Favorites only")
        self.favorites_only.toggled.connect(self.refresh)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.search, stretch=1)
        filter_row.addWidget(QLabel("Tag:"))
        filter_row.addWidget(self.tag_filter)
        filter_row.addWidget(self.favorites_only)
        outer.addLayout(filter_row)

        self.items = QListWidget()
        self.items.currentItemChanged.connect(self._show_details)
        self.items.itemDoubleClicked.connect(lambda _: self._toggle_favorite())
        outer.addWidget(self.items, stretch=1)

        self.details = QTextBrowser()
        self.details.setObjectName("card")
        self.details.setMaximumHeight(150)
        outer.addWidget(self.details)

        buttons = QHBoxLayout()
        self.favorite_button = QPushButton("Favorite")
        self.delete_button = QPushButton("Delete")
        self.to_collection_button = QPushButton("Add to collection…")
        self.new_collection_button = QPushButton("New collection…")
        for btn in (
            self.favorite_button,
            self.delete_button,
            self.to_collection_button,
            self.new_collection_button,
        ):
            buttons.addWidget(btn)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.delete_button.clicked.connect(self._delete_selected)
        self.to_collection_button.clicked.connect(self._add_to_collection)
        self.new_collection_button.clicked.connect(self._new_collection)
        self.refresh()

    def refresh(self) -> None:
        index = self.tag_filter.currentIndex()
        tag = self.tag_filter.itemData(index) if index > 0 else None
        found = self.library.list_items(
            query=self.search.text(),
            tag=tag,
            favorite_only=self.favorites_only.isChecked(),
        )
        selected_id = self.selected_item_id()
        self.items.blockSignals(True)
        self.items.clear()
        for item in found:
            star = "* " if item.favorite else ""
            bits = []
            if item.bpm:
                bits.append(f"{item.bpm:.0f} BPM")
            if item.duration_sec >= 1.0:
                bits.append(format_time(item.duration_sec))
            label = f"{star}{item.title}   ({', '.join(bits) or humanize(item.kind)})"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item.id)
            self.items.addItem(row)
            if item.id == selected_id:
                self.items.setCurrentRow(self.items.count() - 1)
        self.items.blockSignals(False)
        if self.items.currentRow() < 0 and self.items.count():
            self.items.setCurrentRow(0)
        self._rebuild_tag_combo(tag)
        if not found:
            self.details.setPlainText(
                "No matching items.\n"
                "Generate music or import audio files to fill the library."
            )

    def _rebuild_tag_combo(self, current: str | None) -> None:
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("All tags", None)
        for tag in self.library.all_tags():
            self.tag_filter.addItem(tag, tag)
            if current == tag:
                self.tag_filter.setCurrentIndex(self.tag_filter.count() - 1)
        self.tag_filter.blockSignals(False)

    def selected_item_id(self) -> int | None:
        row = self.items.currentItem()
        return row.data(Qt.UserRole) if row is not None else None

    def _selected(self) -> Item | None:
        item_id = self.selected_item_id()
        if item_id is None:
            return None
        try:
            return self.library.get(item_id)
        except ValidationError:
            return None

    def _show_details(self, *_args) -> None:
        item = self._selected()
        if item is None:
            return
        lines = [f"<b>{item.title}</b> ({humanize(item.kind)})"]
        if item.path:
            lines.append(f"File: {item.path}")
        stats = []
        if item.integrated_lufs is not None:
            stats.append(f"{item.integrated_lufs:.1f} LUFS")
        if item.true_peak_dbtp is not None:
            stats.append(f"{item.true_peak_dbtp:.1f} dBTP")
        if item.sample_rate:
            stats.append(f"{item.sample_rate // 1000} kHz")
        if item.channels:
            stats.append("mono" if item.channels == 1 else f"{item.channels} ch")
        if stats:
            lines.append(" - ".join(stats))
        gen = []
        if item.bpm:
            gen.append(f"{item.bpm:.0f} BPM")
        if item.key_name:
            gen.append(str(item.key_name))
        if item.seed is not None:
            gen.append(f"seed {item.seed}")
        if gen:
            lines.append("Generated: " + " - ".join(gen))
        if item.tags:
            lines.append("Tags: " + ", ".join(item.tags))
        if item.notes:
            lines.append(f"Notes: {item.notes}")
        self.details.setHtml("<br/>".join(lines))

    def _toggle_favorite(self) -> None:
        item = self._selected()
        if item is None:
            return
        updated = self.library.set_favorite(item.id, not item.favorite)
        mark = "Starred" if updated.favorite else "Un-starred"
        self.window().statusBar().showMessage(f"{mark} {updated.title}", 4000)
        self.refresh()

    def _delete_selected(self) -> None:
        item = self._selected()
        if item is None:
            return
        try:
            self.library.delete_item(item.id)
            self.window().statusBar().showMessage(f"Deleted {item.title}", 4000)
        except ValidationError as exc:
            self.window().statusBar().showMessage(str(exc), 6000)
        self.refresh()

    def _add_to_collection(self) -> None:
        item = self._selected()
        if item is None:
            return
        collections = self.library.list_collections()
        if not collections:
            self.window().statusBar().showMessage(
                "Create a collection first.", 5000
            )
            return
        name, ok = QInputDialog.getItem(
            self, "Add to collection", "Collection:", list(collections), 0, False
        )
        if ok and name:
            self.library.add_to_collection(name, item.id)
            self.window().statusBar().showMessage(
                f"Added {item.title} to {name}", 4000
            )

    def _new_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "New collection", "Name:")
        if not ok or not name:
            return
        try:
            self.library.create_collection(name)
            self.window().statusBar().showMessage(
                f"Created collection {name.strip()}", 4000
            )
        except ValidationError as exc:
            self.window().statusBar().showMessage(str(exc), 6000)


class MixPage(QWidget):
    """Per-track channel strips (volume/pan/mute/solo) for the timeline.

    Edits emit ``property_changed`` so MainWindow can apply them as
    undoable ``SetTrackPropertyCommand``s. Effect chains and ducking UI
    stay deferred (documented in docs/MIXER.md).
    """

    property_changed = Signal(str, str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("Mix")
        heading.setObjectName("page-title")
        outer.addWidget(heading)
        outer.addSpacing(10)
        self.strips_area = QWidget()
        self.strips_layout = QHBoxLayout(self.strips_area)
        self.strips_layout.setContentsMargins(0, 0, 0, 0)
        self.strips_layout.setSpacing(10)
        outer.addWidget(self.strips_area)
        outer.addStretch(1)
        self.set_document(None)

    def set_document(self, document: TimelineDocument | None) -> None:
        while self.strips_layout.count():
            item = self.strips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if document is None:
            empty = QLabel("No timeline loaded.")
            empty.setObjectName("muted")
            self.strips_layout.addWidget(empty)
            return
        for track in document.tracks:
            strip = self._build_strip(track)
            self.strips_layout.addWidget(strip)

    def _build_strip(self, track: TrackState) -> QGroupBox:
        box = QGroupBox(track.name)
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        volume = QSlider(Qt.Horizontal)
        volume.setRange(-60, 12)
        volume_label = QLabel(f"{track.volume_db:.0f} dB")

        pan = QSlider(Qt.Horizontal)
        pan.setRange(-100, 100)
        pan_label = QLabel(f"{track.pan:+.2f}")

        mute = QPushButton("M")
        mute.setToolTip("Mute")
        solo = QPushButton("S")
        solo.setToolTip("Solo")

        # Set widget state BEFORE wiring signals so rebuilding a page never
        # re-emits user edits back into the undo stack.
        volume.setValue(int(round(track.volume_db)))
        pan.setValue(int(round(track.pan * 100)))
        mute.setCheckable(True)
        mute.setChecked(track.mute)
        solo.setCheckable(True)
        solo.setChecked(track.solo)

        volume.valueChanged.connect(
            lambda value, lab=volume_label, tid=track.track_id: (
                lab.setText(f"{value:d} dB"),
                self.property_changed.emit(tid, "volume_db", float(value)),
            )
        )
        pan.valueChanged.connect(
            lambda value, lab=pan_label, tid=track.track_id: (
                lab.setText(f"{value / 100.0:+.2f}"),
                self.property_changed.emit(tid, "pan", value / 100.0),
            )
        )
        mute.toggled.connect(
            lambda checked, tid=track.track_id: self.property_changed.emit(
                tid, "mute", bool(checked)
            )
        )
        solo.toggled.connect(
            lambda checked, tid=track.track_id: self.property_changed.emit(
                tid, "solo", bool(checked)
            )
        )

        ms_row = QHBoxLayout()
        ms_row.addWidget(mute)
        ms_row.addWidget(solo)
        ms_row.addStretch(1)

        layout.addWidget(volume_label)
        layout.addWidget(volume)
        layout.addWidget(pan_label)
        layout.addWidget(pan)
        layout.addLayout(ms_row)
        return box


class ProvenancePage(QWidget):
    """Provenance center: browse lineage of generated items, verify
    fingerprints by recomposition and export TXT/JSON certificates."""

    def __init__(self, library: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)

        heading = QLabel("Export & Provenance")
        heading.setObjectName("page-title")
        outer.addWidget(heading)
        outer.addSpacing(10)

        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("Generated item:"))
        self.item_combo = QComboBox()
        self.item_combo.currentIndexChanged.connect(self._refresh_view)
        self.reload_button = QPushButton("Reload list")
        self.reload_button.clicked.connect(self.reload_items)
        pick_row.addWidget(self.item_combo, stretch=1)
        pick_row.addWidget(self.reload_button)
        outer.addLayout(pick_row)

        self.details = QTextBrowser()
        self.details.setObjectName("card")
        outer.addWidget(self.details, stretch=1)

        export_box = QGroupBox("Render, master & deliver")
        export_row = QHBoxLayout(export_box)
        export_row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        for preset_name in known_target_presets():
            self.preset_combo.addItem(preset_name, preset_name)
        export_row.addWidget(self.preset_combo)
        self.export_dir_label = QLabel("No output folder chosen")
        export_row.addWidget(self.export_dir_label, stretch=1)
        self.choose_export_dir_button = QPushButton("Choose folder…")
        export_row.addWidget(self.choose_export_dir_button)
        self.export_button = QPushButton("Render & export")
        self.export_button.setObjectName("primary")
        export_row.addWidget(self.export_button)
        outer.addWidget(export_box)

        actions = QHBoxLayout()
        self.verify_button = QPushButton("Verify fingerprint")
        self.verify_button.setObjectName("primary")
        self.save_txt_button = QPushButton("Save certificate (TXT)")
        self.save_json_button = QPushButton("Save certificate (JSON)")
        for btn in (self.verify_button, self.save_txt_button, self.save_json_button):
            actions.addWidget(btn)
        actions.addStretch(1)
        outer.addLayout(actions)

        self.verify_button.clicked.connect(self._verify_selected)
        self.save_txt_button.clicked.connect(lambda: self._save_certificate("txt"))
        self.save_json_button.clicked.connect(lambda: self._save_certificate("json"))
        self.choose_export_dir_button.clicked.connect(self._choose_export_dir)
        self.export_button.clicked.connect(self._on_export_clicked)
        self._current_record: ProvenanceRecord | None = None
        self._export_dir: Path | None = None
        self.reload_items()

    # ------------------------------------------------------------- helpers

    def reload_items(self) -> None:
        self.item_combo.blockSignals(True)
        self.item_combo.clear()
        self._items_by_id: dict[int, Item] = {}
        for item in self.library.list_items():
            if not item.params_json:
                continue
            label = f"#{item.id} {item.title}"
            self.item_combo.addItem(label, item.id)
            self._items_by_id[item.id] = item
        self.item_combo.blockSignals(False)
        self._refresh_view()

    def _selected_item(self) -> Item | None:
        item_id = self.item_combo.currentData()
        return self._items_by_id.get(item_id) if item_id is not None else None

    def _refresh_view(self) -> None:
        item = self._selected_item()
        if item is None:
            self._current_record = None
            self.details.setHtml(
                "<i>No generated items with parameters found in the library."
                "<br/>Generate music first — every generation is archived "
                "here with full provenance.</i>"
            )
            return
        record = record_from_item(item)
        self._current_record = record
        params_html = ", ".join(
            f"<b>{key}</b>={value}" for key, value in sorted(record.parameters.items())
        )
        self.details.setHtml(
            f"<b>{record.title}</b><br/>"
            f"Fingerprint: <b>{record.fingerprint or '-'}</b><br/>"
            f"{record.bpm:.0f} BPM - {record.key_name} - "
            f"{format_duration(record.duration_sec)}<br/>"
            f"{params_html}<br/><br/>"
            f"Generator: {record.generator_version} | "
            f"App: {record.app_version}<br/>"
            f"License: {record.license_note}"
        )

    def _verify_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        result = verify_item(item)
        mark = "VERIFIED" if result.ok else "FAILED"
        self.window().statusBar().showMessage(
            f"Provenance {mark}: {result.message}", 8000
        )
        color = "#9ece6a" if result.ok else "#f7768e"
        self.details.setHtml(
            self.details.toHtml().replace(
                "</body>",
                f"<p style='color:{color};'><b>{mark}</b> — {result.message}"
                + (
                    f"<br/>Recomputed: {result.recomputed_fingerprint}"
                    if result.recomputed_fingerprint
                    else ""
                )
                + "</p></body>",
            )
        )

    def _save_certificate(self, fmt: str) -> None:
        if self._current_record is None:
            self.window().statusBar().showMessage(
                "Select a generated item first.", 5000
            )
            return
        target_dir = QFileDialog.getExistingDirectory(
            self, "Choose certificate folder"
        )
        if not target_dir:
            return
        try:
            path = write_certificate(self._current_record, target_dir, fmt=fmt)
        except (ValueError, OSError) as exc:
            self.window().statusBar().showMessage(f"Certificate failed: {exc}", 8000)
            return
        self.window().statusBar().showMessage(f"Saved {path.name}", 8000)

    def save_certificate_to_dir(self, directory, fmt: str = "txt") -> Path:
        """Direct save used by tests/scripts; bypasses the folder dialog."""
        if self._current_record is None:
            raise ValidationError("no provenance record selected")
        return write_certificate(self._current_record, directory, fmt=fmt)

    # ------------------------------------------------------------- export

    def _choose_export_dir(self) -> None:
        target_dir = QFileDialog.getExistingDirectory(
            self, "Choose output folder for rendered audio"
        )
        if not target_dir:
            return
        self._export_dir = Path(target_dir)
        self.export_dir_label.setText(str(self._export_dir))

    def _on_export_clicked(self) -> None:
        if self._export_dir is None:
            self.window().statusBar().showMessage(
                "Choose an output folder first.", 5000
            )
            return
        try:
            outcome = self.run_export(self._export_dir)
        except (ValidationError, OSError) as exc:
            self.window().statusBar().showMessage(f"Export failed: {exc}", 8000)
            return
        if outcome is not None:
            self.window().statusBar().showMessage(
                f"Delivered {outcome.final_path.name} "
                f"[{outcome.target_name}, QC: {outcome.qc.status}]", 12000
            )

    def run_export(self, output_dir: Path, *, preset_name: str | None = None):
        """Render + master + archive the selected item into ``output_dir``.

        Synchronous; used directly by tests and by the click handler.
        Returns the ExportOutcome or None when nothing is selectable.
        """
        item = self._selected_item()
        if item is None:
            return None
        preset = preset_name or self.preset_combo.currentData() or "YOUTUBE"
        status = self.window().statusBar()

        def progress(fraction: float) -> None:
            status.showMessage(f"Exporting… {fraction * 100:.0f}%")

        for btn in (
            self.export_button,
            self.verify_button,
            self.save_txt_button,
            self.save_json_button,
            self.reload_button,
        ):
            btn.setEnabled(False)
        try:
            outcome = export_item(
                self.library, item.id, output_dir, preset=preset,
                on_progress=progress,
            )
        finally:
            for btn in (
                self.export_button,
                self.verify_button,
                self.save_txt_button,
                self.save_json_button,
                self.reload_button,
            ):
                btn.setEnabled(True)
        return outcome


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1180, 720)

        self.document = TimelineDocument(title="New session", duration_sec=1800.0)
        self.commands = CommandStack()
        self._ensure_music_track()

        self.library = LibraryService(db_path if db_path is not None else DEFAULT_DB_PATH)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        for item_name in SIDEBAR_ITEMS:
            self.sidebar.addItem(QListWidgetItem(item_name))

        self.library_page = LibraryPage(self.library)
        self.generate_page = GeneratePage()
        self.timeline_canvas = TimelineCanvas()
        timeline_page = QWidget()
        timeline_layout = QVBoxLayout(timeline_page)
        timeline_layout.setContentsMargins(28, 24, 28, 24)
        timeline_heading = QLabel("Timeline")
        timeline_heading.setObjectName("page-title")
        timeline_layout.addWidget(timeline_heading)
        timeline_layout.addWidget(self.timeline_canvas, stretch=1)
        self.mix_page = MixPage()
        self.provenance_page = ProvenancePage(self.library)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.library_page)
        self.pages.addWidget(self.generate_page)
        self.pages.addWidget(timeline_page)
        self.pages.addWidget(self.mix_page)
        self.pages.addWidget(self.provenance_page)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.pages, stretch=1)

        self.transport = TransportBar()

        container = QWidget()
        window_layout = QVBoxLayout(container)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(body, stretch=1)
        window_layout.addWidget(self.transport)
        self.setCentralWidget(container)

        self.statusBar().showMessage("Ready.")

        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sidebar.setCurrentRow(1)

        self.generate_page.generate_requested.connect(self._on_generate)
        self.mix_page.property_changed.connect(self._on_mix_property)
        self._build_actions()
        self.refresh_timeline_view()

    def _build_actions(self) -> None:
        menu = self.menuBar().addMenu("&Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self._undo)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        self.redo_action.triggered.connect(self._redo)
        menu.addAction(self.undo_action)
        menu.addAction(self.redo_action)

    def _ensure_music_track(self) -> None:
        if not any(track.kind == "MUSIC" for track in self.document.tracks):
            self.commands.execute(
                AddTrackCommand(TrackState(name="Music 1")), self.document
            )

    def refresh_timeline_view(self) -> None:
        self.transport.set_range(self.document.duration_sec)
        self.timeline_canvas.set_document(self.document)
        self.mix_page.set_document(self.document)

    def _on_mix_property(self, track_id: str, field_name: str, value) -> None:
        try:
            command = SetTrackPropertyCommand(track_id, field_name, value)
        except ValidationError as exc:
            self.statusBar().showMessage(str(exc), 6000)
            return
        self.commands.execute(command, self.document)
        self.statusBar().showMessage(
            f"{command.name} — Ctrl+Z to undo", 4000
        )

    def _undo(self) -> None:
        command = self.commands.undo(self.document)
        if command is not None:
            self.statusBar().showMessage(f"Undo: {command.name}")
            self.refresh_timeline_view()

    def _redo(self) -> None:
        command = self.commands.redo(self.document)
        if command is not None:
            self.statusBar().showMessage(f"Redo: {command.name}")
            self.refresh_timeline_view()

    def generate_from_payload(self, payload: dict) -> Clip | None:
        try:
            params = GenerationParameters(
                seed=payload["seed"],
                duration_sec=payload["duration_sec"],
                genre=payload["genre"],
                moods=payload["moods"],
                intensity=payload["intensity"],
            )
            params.validate()
            composition = Composer(params).compose()
        except ValidationError as exc:
            self.statusBar().showMessage(f"Invalid parameters: {exc}", 8000)
            return None

        track = next(t for t in self.document.tracks if t.kind == "MUSIC")
        start = max(
            (clip.end_sec for clip in self.document.clips_on_track(track.track_id)),
            default=0.0,
        )
        label = f"{humanize(params.genre)} {composition.fingerprint}"
        clip = Clip(
            track_id=track.track_id,
            start_sec=start,
            duration_sec=params.duration_sec,
            label=label,
            source_kind="GENERATED",
            source_ref=composition.fingerprint,
        )
        self.commands.execute(AddClipCommand(clip), self.document)
        self.refresh_timeline_view()
        library_note = ""
        try:
            item = self.library.register_composition(composition, params)
            library_note = f", saved to library #{item.id}"
        except ValidationError:
            library_note = ""
        self.statusBar().showMessage(
            f"Generated {composition.fingerprint} — {composition.bpm:.0f} BPM "
            f"{composition.key_name}, repetition score "
            f"{composition.repetition_score:.1f}{library_note}",
            10000,
        )
        return clip

    def _on_generate(self, payload: dict) -> None:
        try:
            self.generate_from_payload(payload)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            self.statusBar().showMessage(f"Generation failed: {exc}", 8000)


def run() -> int:
    app = QApplication.instance() or QApplication([])
    from lfms.app.theme import DARK_QSS

    app.setStyleSheet(DARK_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
