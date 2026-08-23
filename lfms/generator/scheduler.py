"""Streaming event-to-audio conversion.

EventTrackSource walks a sorted event list block by block; notes are
activated exactly when the playhead reaches them, so memory stays flat for
multi-hour compositions.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.sources import SourceNode
from lfms.core.seed import SeedSystem
from lfms.generator.events import NoteEvent
from lfms.generator.voices import make_voice


class EventTrackSource(SourceNode):
    """Renders a list of NoteEvents sequentially as a mono source (1, n)."""

    def __init__(
        self,
        sample_rate: int,
        events: list[NoteEvent],
        *,
        timbre: dict | None = None,
        seed: int = 0,
        default_instrument: str | None = None,
    ) -> None:
        super().__init__(sample_rate)
        self._events = sorted(events, key=lambda e: (e.start_sec, e.instrument, e.midi))
        self._start_frames = [
            max(0, int(round(event.start_sec * sample_rate))) for event in self._events
        ]
        self._timbre = timbre or {}
        self._seed_base = int(SeedSystem(seed).derive("voice"))
        self._default_instrument = default_instrument
        self._index = 0
        self._frames = 0
        self._active: list[tuple[int, object]] = []

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        out = np.zeros(n, dtype=np.float32)
        end_frame = self._frames + n

        while (
            self._index < len(self._events)
            and self._start_frames[self._index] < end_frame
        ):
            event = self._events[self._index]
            instrument = event.instrument or self._default_instrument or "PLUCK"
            voice = make_voice(
                instrument,
                self.sample_rate,
                event,
                self._timbre,
                rng_seed=self._seed_base + self._index,
            )
            self._active.append((self._start_frames[self._index], voice))
            self._index += 1

        still_active = []
        for start_frame, voice in self._active:
            offset = start_frame - self._frames
            if offset < 0:
                offset = 0
            if offset >= n:
                still_active.append((start_frame, voice))
                continue
            segment = voice.process(n - offset)
            out[offset:] += segment[: n - offset]
            if not voice.finished:
                still_active.append((start_frame, voice))
        self._active = still_active
        self._frames = end_frame
        return out[None, :]

    @property
    def drained(self) -> bool:
        return self._index >= len(self._events) and not self._active
