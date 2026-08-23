"""Capture real GUI screenshots without a display.

Runs the actual PySide6 app headlessly (QT_QPA_PLATFORM=offscreen), populates
it with a small demo session, and saves one PNG per page:

    python scripts/make_screenshots.py

Output: docs/screenshots/0N-<page>.png (referenced from README.md).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from lfms.app.main_window import MainWindow  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "screenshots"

PAGES = [
    ("01-library", 0),
    ("02-generate", 1),
    ("03-batch", 2),
    ("04-timeline", 3),
    ("05-mixer", 4),
    ("06-provenance", 5),
]


def populate(window: MainWindow) -> None:
    """Generate a few short tracks so every page shows real content."""
    session = [
        {"seed": 20260823, "genre": "DOCUMENTARY", "moods": ("CALM",),
         "duration_sec": 30.0, "intensity": 45.0},
        {"seed": 777001, "genre": "LOFI", "moods": ("DREAMY",),
         "duration_sec": 20.0, "intensity": 35.0, "voiceover_safe": True},
        {"seed": 31337, "genre": "AMBIENT", "moods": ("NEUTRAL",),
         "duration_sec": 15.0, "intensity": 30.0},
    ]
    for payload in session:
        window.generate_from_payload(payload)


def grab(app: QApplication, window: MainWindow) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, index in PAGES:
        window.sidebar.setCurrentRow(index)
        app.processEvents()
        pixmap = window.grab()
        target = OUT_DIR / f"{name}.png"
        if not pixmap.save(str(target), "PNG"):
            raise SystemExit(f"failed to save {target}")
        print(f"saved {target} ({pixmap.width()}x{pixmap.height()})")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lfms-shots-") as workdir:
        app = QApplication.instance() or QApplication([])
        window = MainWindow(db_path=Path(workdir) / "library.db")
        window.resize(1440, 900)
        window.show()
        app.processEvents()

        populate(window)
        window.provenance_page.reload_items()
        window.provenance_page._verify_selected()
        app.processEvents()

        grab(app, window)

        window.batch_page.queue.stop()
        window.library.close()


if __name__ == "__main__":
    main()
