"""Frozen-app entry point for PyInstaller builds.

Supports two non-GUI modes so builds can be verified automatically:

- ``LongFormMusicStudio.exe --version`` exits 0 after printing the
  version (stdout may be invisible for windowed builds; the exit code
  is the assertion).
- ``LFMS_SELF_CHECK=1`` imports every shipped package (engine,
  generator, mixer, mastering, library, provenance, exporter, batch,
  director) and exits 0 — proving the bundle is complete without
  opening a window.
"""
from __future__ import annotations

import os
import sys


def _self_check() -> int:
    import lfms.app.main_window  # noqa: F401
    import lfms.audio_engine  # noqa: F401
    import lfms.batch  # noqa: F401
    import lfms.director  # noqa: F401
    import lfms.exporter  # noqa: F401
    import lfms.generator  # noqa: F401
    import lfms.library  # noqa: F401
    import lfms.mastering  # noqa: F401
    import lfms.mixer  # noqa: F401
    import lfms.provenance  # noqa: F401
    import lfms.timeline  # noqa: F401
    return 0


def main() -> int:
    if "--version" in sys.argv[1:]:
        from lfms.core.version import APP_NAME, VERSION

        print(f"{APP_NAME} {VERSION}")
        return 0
    if os.environ.get("LFMS_SELF_CHECK") == "1":
        return _self_check()
    from lfms.app.main_window import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
