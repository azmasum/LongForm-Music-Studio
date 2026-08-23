"""Logging configuration and crash reporting.

Logs are written to rotating files under the Logs data directory. Crash
reports capture full tracebacks without logging user media content.
"""
from __future__ import annotations

import datetime as _dt
import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

from lfms.core.version import APP_CODE, VERSION

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONFIGURED_FLAG = "_lfms_configured"


def setup_logging(logs_dir: Path | str, level: int = logging.INFO, console: bool = True) -> None:
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    if getattr(root, _CONFIGURED_FLAG, False):
        return
    formatter = logging.Formatter(_LOG_FORMAT)
    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / f"{APP_CODE.lower()}.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
    setattr(root, _CONFIGURED_FLAG, True)


def write_crash_report(logs_dir: Path | str, exc_type: type, exc: BaseException, tb: object) -> Path:
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = logs_dir / f"crash_{stamp}.txt"
    body = traceback.format_exception(exc_type, exc, tb)
    header = (
        f"{APP_CODE} crash report {VERSION}\n"
        f"time: {_dt.datetime.now().isoformat()}\n"
        + "=" * 60
        + "\n"
    )
    path.write_text(header + "".join(body), encoding="utf-8")
    logging.getLogger(__name__).error("Crash report written: %s", path)
    return path


def install_crash_handlers(logs_dir: Path | str) -> None:
    def sys_hook(exc_type, exc, tb):
        write_crash_report(logs_dir, exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        write_crash_report(logs_dir, args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = sys_hook
    threading.excepthook = thread_hook
