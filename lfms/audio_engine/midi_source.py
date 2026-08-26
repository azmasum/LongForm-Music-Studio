"""MidiClipSource: renders a MidiClip via SamplerSource.

Bridges the MIDI model to the audio engine — takes a MidiClip and a loaded
sample (numpy array + base_note), produces audio block-by-block.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.sources import SourceNode
from lfms.midi.model import MidiClip


class MidiClipSource(SourceNode):
    """Wraps SamplerSource for a single MidiClip + sample pair."""

    def __init__(
        self,
        sample_rate: int,
        clip: MidiClip,
        sample_data: np.ndarray,
        base_note: int = 60,
    ) -> None:
        super().__init__(sample_rate)
        self._clip = clip
        events = [
            {
                "pitch": n.pitch,
                "start_sec": n.start_sec,
                "duration_sec": n.duration_sec,
                "velocity": n.velocity,
                "gain_db": 0.0,
            }
            for n in clip.notes
        ]
        from lfms.audio_engine.sampler import SamplerSource

        self._inner = SamplerSource(sample_rate, sample_data, base_note, events)
        self.finished = False

    def process(self, n_frames: int) -> np.ndarray:
        out = self._inner.process(n_frames)
        if self._inner.finished:
            self.finished = True
        return out

    @property
    def clip(self) -> MidiClip:
        return self._clip


class DefaultSineSource(SourceNode):
    """Fallback: produces a sine tone per note event. Used when no sample is loaded."""

    def __init__(self, sample_rate: int, clip: MidiClip) -> None:
        super().__init__(sample_rate)
        self._clip = clip
        events = sorted(clip.notes, key=lambda n: n.start_sec)
        self._events = events
        self._start_frames = [
            max(0, int(round(e.start_sec * sample_rate))) for e in events
        ]
        self._frames = 0
        self._index = 0
        self._active: list[tuple[int, int, float, float]] = []
        self.finished = False

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        out = np.zeros(n, dtype=np.float32)
        end_frame = self._frames + n
        while (
            self._index < len(self._events)
            and self._start_frames[self._index] < end_frame
        ):
            ev = self._events[self._index]
            freq = 440.0 * 2.0 ** ((ev.pitch - 69) / 12.0)
            dur_frames = max(1, int(ev.duration_sec * self.sample_rate))
            self._active.append(
                (self._start_frames[self._index], dur_frames, freq, ev.velocity)
            )
            self._index += 1
        still_active = []
        for start_frame, dur_frames, freq, vel in self._active:
            offset = start_frame - self._frames
            if offset >= n:
                still_active.append((start_frame, dur_frames, freq, vel))
                continue
            t0 = max(0, offset)
            t_end = min(n, offset + dur_frames)
            if t0 >= t_end:
                continue
            t = np.arange(t0, t_end, dtype=np.float64) + (self._frames - start_frame)
            t_sec = t / self.sample_rate
            wave = np.sin(2.0 * np.pi * freq * t_sec) * 0.3 * vel
            out[t0:t_end] += wave.astype(np.float32)
            if offset + dur_frames > n:
                still_active.append((start_frame, dur_frames, freq, vel))
        self._active = still_active
        self._frames = end_frame
        if self._index >= len(self._events) and not self._active:
            self.finished = True
        return out[None, :]
