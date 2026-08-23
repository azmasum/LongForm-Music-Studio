"""PySide6 application shell: sidebar navigation, dark theme, transport bar,
timeline canvas and a functional Quick Generate page."""
from __future__ import annotations

import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from lfms.app.theme import ACCENT, BORDER, POSITIVE, TEXT_DIM
from lfms.core.enums import Genre, Mood
from lfms.core.errors import ValidationError
from lfms.core.version import APP_NAME, VERSION
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.timeline import (
    AddClipCommand,
    AddTrackCommand,
    Clip,
    CommandStack,
    TimelineDocument,
    TrackState,
)

SIDEBAR_ITEMS = ("Library", "Generate", "Timeline", "Mix", "Export")
PLACEHOLDER_TEXTS = {
    "Library": "Sound library browser arrives in Phase 8.",
    "Mix": "Per-track mixer, effect chains and voiceover ducking arrive in Phase 6.",
    "Export": "Render/export pipeline UI arrives in Phase 9.",
}


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


class PlaceholderPage(QWidget):
    def __init__(self, title: str, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel(title)
        heading.setObjectName("page-title")
        body = QLabel(message)
        body.setObjectName("muted")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addSpacing(8)
        layout.addWidget(body)
        layout.addStretch(1)


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

        self.generate_button = QPushButton("Generate into timeline")
        self.generate_button.setObjectName("primary")
        outer.addWidget(self.generate_button, alignment=Qt.AlignLeft)
        outer.addStretch(1)

        self.randomize.clicked.connect(
            lambda: self.seed.setValue(float(random.randrange(1, 1_000_000)))
        )
        self.intensity.valueChanged.connect(self.intensity_value.setNum)
        self.generate_button.clicked.connect(self._emit_request)

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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.resize(1180, 720)

        self.document = TimelineDocument(title="New session", duration_sec=1800.0)
        self.commands = CommandStack()
        self._ensure_music_track()

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(190)
        for item_name in SIDEBAR_ITEMS:
            self.sidebar.addItem(QListWidgetItem(item_name))

        self.generate_page = GeneratePage()
        self.timeline_canvas = TimelineCanvas()
        timeline_page = QWidget()
        timeline_layout = QVBoxLayout(timeline_page)
        timeline_layout.setContentsMargins(28, 24, 28, 24)
        timeline_heading = QLabel("Timeline")
        timeline_heading.setObjectName("page-title")
        timeline_layout.addWidget(timeline_heading)
        timeline_layout.addWidget(self.timeline_canvas, stretch=1)

        self.pages = QStackedWidget()
        self.pages.addWidget(PlaceholderPage("Library", PLACEHOLDER_TEXTS["Library"]))
        self.pages.addWidget(self.generate_page)
        self.pages.addWidget(timeline_page)
        self.pages.addWidget(PlaceholderPage("Mix", PLACEHOLDER_TEXTS["Mix"]))
        self.pages.addWidget(PlaceholderPage("Export", PLACEHOLDER_TEXTS["Export"]))

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
        self.statusBar().showMessage(
            f"Generated {composition.fingerprint} — {composition.bpm:.0f} BPM "
            f"{composition.key_name}, repetition score "
            f"{composition.repetition_score:.1f}",
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
