"""Cooperative pause/resume/cancel control for long render jobs."""
from __future__ import annotations

import threading
import time


class RenderJobControl:
    def __init__(self, *, poll_interval: float = 0.05) -> None:
        self._running = threading.Event()
        self._running.set()
        self._cancelled = False
        self._lock = threading.Lock()
        self.poll_interval = max(0.01, float(poll_interval))

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        if not self.cancelled:
            self._running.set()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
        self._running.set()

    def checkpoint(self) -> bool:
        """Block while paused; return False when the job must stop."""
        while not self.cancelled and not self._running.is_set():
            time.sleep(self.poll_interval)
        return not self.cancelled
