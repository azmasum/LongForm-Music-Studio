"""Realtime playback sink backed by sounddevice (PortAudio).

Import of sounddevice and stream creation are lazy so headless environments
only fail when playback is actually requested.
"""
from __future__ import annotations

import threading

import numpy as np

from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.graph import AudioGraph
from lfms.core.errors import AudioDeviceError


def _interleave(block: np.ndarray) -> np.ndarray:
    """(channels, n) -> interleaved (n*channels,) float32 for PortAudio."""
    return np.ascontiguousarray(block.T.reshape(-1)).astype(np.float32)


class Player:
    def __init__(self) -> None:
        self._stream = None
        # RLock: play() holds the lock and calls stop(); a plain Lock would
        # self-deadlock on that nested acquire.
        self._lock = threading.RLock()
        self._graph: AudioGraph | None = None
        self._ctx: RenderContext | None = None
        self._block_size = 2048
        self._underruns = 0

    @property
    def playing(self) -> bool:
        return self._stream is not None and getattr(self._stream, "active", False)

    @property
    def underruns(self) -> int:
        return self._underruns

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self._underruns += 1
        if self._graph is None or self._ctx is None:
            outdata.fill(0)
            return
        block = self._graph.process(self._ctx, frames)
        if block.shape[1] < frames:
            pad = np.zeros((block.shape[0], frames - block.shape[1]), dtype=np.float32)
            block = np.concatenate([block, pad], axis=1)
        outdata[:] = _interleave(block[:, :frames]).reshape(frames, -1)

    def play(self, graph: AudioGraph, *, device: int | str | None = None, block_size: int = 2048) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioDeviceError(
                "The audio playback backend is unavailable.",
                technical=str(exc),
                suggestion="Install the sounddevice package (pip install sounddevice).",
            ) from exc

        with self._lock:
            if self._stream is not None:
                self.stop()
            self._graph = graph
            self._ctx = RenderContext(sample_rate=graph.sample_rate, channels=2)
            self._block_size = int(block_size)
            try:
                self._stream = sd.OutputStream(
                    samplerate=graph.sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=self._block_size,
                    device=device,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                name = type(exc).__name__
                if "PortAudio" in name or "device" in str(exc).lower():
                    raise AudioDeviceError(
                        "Audio device unavailable. Check Windows sound settings or select another device.",
                        technical=str(exc),
                        suggestion="Close apps holding the device exclusively, then retry.",
                    ) from exc
                raise AudioDeviceError(
                    "Playback could not start.", technical=f"{name}: {exc}"
                ) from exc

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                finally:
                    self._stream = None
            self._graph = None
            self._ctx = None


_shared_player: Player | None = None


def get_player() -> Player:
    global _shared_player
    if _shared_player is None:
        _shared_player = Player()
    return _shared_player


class BufferPlayer:
    """Plays an in-memory stereo/mono buffer through the default device.

    Position tracking is lock-free enough for a UI poller: ``position_sec``
    derives from the callback-owned cursor guarded by the stream lock.
    Pause keeps the cursor; ``restart()`` rewinds it to zero.
    """

    def __init__(self) -> None:
        self._stream = None
        self._data: np.ndarray | None = None
        self._cursor = 0  # frames since start of buffer
        # RLock: load()/stop()/pause() nest under one held lock.
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        return self._data is not None

    @property
    def duration_sec(self) -> float:
        if self._data is None:
            return 0.0
        return self._frames / self._sample_rate

    @property
    def position_sec(self) -> float:
        with self._lock:
            if self._data is None:
                return 0.0
            return self._cursor / self._sample_rate

    @property
    def playing(self) -> bool:
        return self._stream is not None and getattr(self._stream, "active", False)

    def load(self, data: np.ndarray, sample_rate: int) -> None:
        """``data`` is (channels, frames) float32."""
        with self._lock:
            self.stop()
            self._data = np.ascontiguousarray(data.astype(np.float32))
            self._sample_rate = int(sample_rate)
            self._frames = self._data.shape[1]
            self._cursor = 0

    def play(self, *, device: int | str | None = None) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioDeviceError(
                "The audio playback backend is unavailable.",
                technical=str(exc),
                suggestion="Install the sounddevice package (pip install sounddevice).",
            ) from exc
        with self._lock:
            if self._data is None:
                raise AudioDeviceError(
                    "Nothing is loaded to play.",
                    suggestion="Generate music first.",
                )
            if self._stream is not None:
                return  # already playing

            channels = self._data.shape[0]
            data = self._data

            def callback(outdata, frames, time_info, status) -> None:  # noqa: ANN001
                start = self._cursor
                end = min(start + frames, self._frames)
                chunk = data[:, start:end]
                outdata[: end - start, :] = chunk.T
                if end - start < frames:
                    outdata[end - start :, :] = 0
                    self.playback_finished = True
                self._cursor = end

            self.playback_finished = False
            try:
                self._stream = sd.OutputStream(
                    samplerate=self._sample_rate,
                    channels=channels,
                    dtype="float32",
                    blocksize=1024,
                    device=device,
                    callback=callback,
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                raise AudioDeviceError(
                    "Audio device unavailable. Check Windows sound settings.",
                    technical=str(exc),
                    suggestion="Close apps holding the audio device exclusively, then retry.",
                ) from exc

    def pause(self) -> None:
        """Stop streaming but keep the playhead where it is."""
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                finally:
                    self._stream = None

    def stop(self) -> None:
        self.pause()
        with self._lock:
            self._cursor = 0
