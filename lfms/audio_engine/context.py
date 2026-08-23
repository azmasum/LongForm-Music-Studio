"""Render context passed through the processing graph."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RenderContext:
    sample_rate: int
    frames_done: int = 0
    channels: int = 2
    extra: dict = field(default_factory=dict)

    @property
    def time(self) -> float:
        return self.frames_done / self.sample_rate

    def advance(self, frames: int) -> None:
        self.frames_done += frames
