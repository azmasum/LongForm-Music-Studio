"""Entry point: python -m lfms.app"""
from __future__ import annotations

import sys

from lfms.app.main_window import run

if __name__ == "__main__":
    sys.exit(run())
