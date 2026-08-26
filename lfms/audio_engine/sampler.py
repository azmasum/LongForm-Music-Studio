"""Chromatic sampler: loads a single WAV and plays it at any MIDI pitch.

The sample is resampled at creation time to the project sample rate and
stored in memory.  Pitch-shifting is done via linear interpolation with
the standard MIDI semitone formula (f = base_freq * 2^((note - base_note)/12)).

For long samples, memory is kept flat-ish by loading as float32 and only
converting to float64 during process() (where the mixer expects it).
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.sources import SourceNode


def _midi_to_freq(note: int, a4: float = 440.0) -> float:
    return a4 * 2.0 ** ((note - 69) / 12.0)


class SamplerVoice(SourceNode):
    """Plays back a pre-loaded sample at a target pitch.

    finish() is set to True when all frames have been emitted.
    """

    def __init__(
        self,
        sample_rate: int,
        data: np.ndarray,
        base_note: int,
        target_note: int,
        *,
        velocity: float = 0.8,
        gain_db: float = 0.0,
    ) -> None:
        super().__init__(sample_rate)
        self._data = data.astype(np.float64)
        self._base_note = int(base_note)
        self._target_note = int(target_note)
        self._velocity = max(0.0, min(1.0, float(velocity)))
        self._gain = 10.0 ** (float(gain_db) / 20.0)
        ratio = _midi_to_freq(self._target_note) / max(
            1e-9, _midi_to_freq(self._base_note)
        )
        self._step = ratio
        self._pos = 0.0
        self.finished = False

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        indices = self._pos + np.arange(n, dtype=np.float64) * self._step
        whole = indices.astype(np.int64)
        frac = indices - whole
        valid = whole < len(self._data) - 1
        if not np.any(valid):
            self.finished = True
            return np.zeros((1, n), dtype=np.float32)
        out = np.zeros(n, dtype=np.float64)
        w = whole[valid]
        f = frac[valid]
        out[valid] = self._data[w] * (1.0 - f) + self._data[w + 1] * f
        self._pos = float(indices[-1]) + self._step
        if self._pos >= len(self._data) - 1:
            self.finished = True
        return (out * self._velocity * self._gain)[None, :].astype(np.float32)


class SamplerSource(SourceNode):
    """Plays a list of note events using a single loaded sample.

    events: list of dicts with keys pitch, start_sec, duration_sec, velocity.
    """
    DECODE_BLOCK = 1 << 16

    def __init__(
        self,
        sample_rate: int,
        sample_data: np.ndarray,
        base_note: int,
        events: list[dict],
    ) -> None:
        super().__init__(sample_rate)
        self._data = sample_data.astype(np.float32)
        self._base_note = int(base_note)
        events_sorted = sorted(events, key=lambda e: e["start_sec"])
        self._events = events_sorted
        self._start_frames = [
            max(0, int(round(e["start_sec"] * sample_rate))) for e in events_sorted
        ]
        self._frames = 0
        self._index = 0
        self._active: list[tuple[int, SamplerVoice]] = []
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
            voice = SamplerVoice(
                self.sample_rate,
                self._data,
                self._base_note,
                ev["pitch"],
                velocity=ev.get("velocity", 0.8),
                gain_db=ev.get("gain_db", 0.0),
            )
            self._active.append((self._start_frames[self._index], voice))
            self._index += 1
        still_active: list[tuple[int, SamplerVoice]] = []
        for start_frame, voice in self._active:
            offset = start_frame - self._frames
            if offset < 0:
                offset = 0
            if offset >= n:
                still_active.append((start_frame, voice))
                continue
            segment = voice.process(n - offset)
            out[offset:] += segment[0, : n - offset]
            if not voice.finished:
                still_active.append((start_frame, voice))
        self._active = still_active
        self._frames = end_frame
        if self._index >= len(self._events) and not self._active:
            self.finished = True
        return out[None, :]
