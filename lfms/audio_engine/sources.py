"""Procedural sound sources: tones, colored noise, ambiences and drones.

Every source renders mono float32 blocks of shape (1, n). All randomness
flows from explicit seeds so identical parameters reproduce identical audio.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import lfilter

from lfms.audio_engine.dsp import rms
from lfms.audio_engine.filters import BiquadFilter
from lfms.audio_engine.lfo import LFO
from lfms.audio_engine.oscillators import Oscillator

_AMBIENCE_KINDS = ("RAIN", "WIND", "OCEAN", "ROOM_TONE", "NIGHT", "CITY")
_NOISE_COLORS = ("WHITE", "PINK", "BROWN")

_PINK_B = np.array([0.049922035, -0.095993537, 0.050612699, -0.004408786])
_PINK_A = np.array([1.0, -2.494956002, 2.017265875, -0.522189400])


class SourceNode:
    """Base class for mono block sources."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = int(sample_rate)

    def process(self, n_frames: int) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class ToneSource(SourceNode):
    def __init__(self, sample_rate: int, *, frequency: float = 440.0, wave: str = "SINE") -> None:
        super().__init__(sample_rate)
        self._osc = Oscillator(sample_rate, wave=wave, frequency=frequency)

    def set_frequency(self, hz: float) -> None:
        self._osc.set_frequency(hz)

    def process(self, n_frames: int) -> np.ndarray:
        return self._osc.process(n_frames)


class NoiseSource(SourceNode):
    def __init__(
        self,
        sample_rate: int,
        *,
        color: str = "WHITE",
        seed: int | None = None,
        target_rms: float = 0.15,
    ) -> None:
        super().__init__(sample_rate)
        color = color.upper()
        if color not in _NOISE_COLORS:
            raise ValueError(f"unknown noise color {color!r}")
        self.color = color
        self._rng = np.random.default_rng(seed)
        self.target_rms = float(target_rms)
        self._pink_zi = np.zeros(3)
        self._brown_zi = np.zeros(1)

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        white = self._rng.standard_normal(n)
        if self.color == "WHITE":
            data = white * 0.25
        elif self.color == "PINK":
            data, self._pink_zi = lfilter(_PINK_B, _PINK_A, white, zi=self._pink_zi)
            gain = self.target_rms / max(rms(data), 1e-9)
            data *= min(gain, 50.0)
        else:
            r = np.exp(-2.0 * np.pi * 4.0 / self.sample_rate)
            data, self._brown_zi = lfilter([1.0], [1.0, -r], white, zi=self._brown_zi)
            gain = self.target_rms / max(rms(data), 1e-9)
            data *= min(gain, 50.0)
        return data.astype(np.float32)[None, :]


class AmbienceSource(SourceNode):
    """Simple procedural nature/environment textures."""

    def __init__(
        self,
        sample_rate: int,
        *,
        kind: str,
        seed: int | None = None,
        level: float = 0.2,
    ) -> None:
        super().__init__(sample_rate)
        kind = kind.upper()
        if kind not in _AMBIENCE_KINDS:
            raise ValueError(f"unknown ambience kind {kind!r}; choose from {_AMBIENCE_KINDS}")
        self.kind = kind
        self.level = float(level)
        rng_seed = seed
        if kind == "RAIN":
            self._noise = NoiseSource(sample_rate, color="PINK", seed=rng_seed, target_rms=0.12)
            self._hp = BiquadFilter(sample_rate, kind="highpass", cutoff=400.0, q=0.6)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=6000.0, q=0.6)
            self._sparkle_lfo = LFO(sample_rate, shape="RANDOM", rate_hz=9.0, seed=rng_seed)
        elif kind == "WIND":
            self._noise = NoiseSource(sample_rate, color="BROWN", seed=rng_seed, target_rms=0.2)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=400.0, q=0.9)
            self._cutoff_lfo = LFO(sample_rate, shape="SINE", rate_hz=0.05, phase=0.25)
            self._gain_lfo = LFO(sample_rate, shape="TRIANGLE", rate_hz=0.033, phase=0.6)
        elif kind == "OCEAN":
            self._noise = NoiseSource(sample_rate, color="PINK", seed=rng_seed, target_rms=0.18)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=900.0, q=0.7)
            self._swell_lfo = LFO(sample_rate, shape="SINE", rate_hz=0.08)
        elif kind == "ROOM_TONE":
            self._noise = NoiseSource(sample_rate, color="BROWN", seed=rng_seed, target_rms=0.05)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=300.0, q=0.7)
        elif kind == "NIGHT":
            self._noise = NoiseSource(sample_rate, color="PINK", seed=rng_seed, target_rms=0.06)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=1200.0, q=0.7)
        else:
            self._noise = NoiseSource(sample_rate, color="BROWN", seed=rng_seed, target_rms=0.14)
            self._lp = BiquadFilter(sample_rate, kind="lowpass", cutoff=220.0, q=0.8)
            self._rumble_lfo = LFO(sample_rate, shape="SINE", rate_hz=0.02)

    def process(self, n_frames: int) -> np.ndarray:
        data = self._noise.process(n_frames)[0].astype(np.float64)
        kind = self.kind
        if kind == "RAIN":
            data = self._hp.process(data)
            data = self._lp.process(data)
            sparkle = 0.75 + 0.5 * self._sparkle_lfo.process(n_frames).astype(np.float64)
            data *= sparkle
        elif kind == "WIND":
            depth_vals = self._cutoff_lfo.process(n_frames).astype(np.float64)
            mid_cutoff = 150.0 + 550.0 * float(np.mean(depth_vals))
            self._lp.set_params(cutoff=mid_cutoff)
            data = self._lp.process(data)
            swell = 0.55 + 0.45 * self._gain_lfo.process(n_frames).astype(np.float64)
            data *= swell
        elif kind == "OCEAN":
            data = self._lp.process(data)
            swell_vals = self._swell_lfo.process(n_frames).astype(np.float64)
            data *= 0.35 + 0.65 * swell_vals
        elif kind == "CITY":
            data = self._lp.process(data)
            rumble = 0.8 + 0.2 * self._rumble_lfo.process(n_frames).astype(np.float64)
            data *= rumble
        else:
            data = self._lp.process(data)
        data *= self.level
        return data.astype(np.float32)[None, :]


class _LinearResampler:
    """Stateful streaming linear-interpolation resampler (mono).

    Vectorized phase accumulator: each call consumes a source chunk and
    emits ``target_rate/src_rate`` output samples per input sample, carrying
    the fractional phase across calls so long renders stay seamless.
    """

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("sample rates must be positive")
        self.source_rate = int(source_rate)
        self.target_rate = int(target_rate)
        self.step = self.source_rate / self.target_rate
        self._anchor = 0.0   # most recent source sample (position 0)
        self._t = 1.0        # next output position relative to anchor
        self._started = False

    def process(self, chunk: np.ndarray) -> np.ndarray:
        chunk = np.asarray(chunk, dtype=np.float64)
        if not self._started:
            if len(chunk) == 0:
                return np.zeros(0, dtype=np.float32)
            self._anchor = float(chunk[0])
            self._t = 1.0
            self._started = True
            chunk = chunk[1:]
        m = len(chunk)
        if m == 0:
            return np.zeros(0, dtype=np.float32)
        if self._t > m:
            return np.zeros(0, dtype=np.float32)
        count = int(np.floor((m - self._t) / self.step)) + 1
        positions = self._t + np.arange(count) * self.step
        lo = np.floor(positions).astype(np.int64)
        frac = positions - lo
        extended = np.concatenate(([self._anchor], chunk))
        vals_lo = extended[lo]
        hit_edge = (lo + 1) > m
        vals_hi = extended[np.minimum(lo + 1, m)]
        out = vals_lo * (1.0 - frac) + np.where(hit_edge, 0.0, vals_hi) * np.where(
            hit_edge, 0.0, frac
        )
        self._t = float(positions[-1]) + self.step - m
        self._anchor = float(chunk[-1])
        return out.astype(np.float32)


class AudioFileSource(SourceNode):
    """Streams any libsndfile-readable file as a mono block source.

    Handles sample-rate conversion via streaming linear interpolation, so a
    44.1 kHz import can sit on a 48 kHz timeline. Memory stays flat: only
    one decode block is held at a time.
    """

    DECODE_BLOCK = 1 << 16

    def __init__(
        self,
        sample_rate: int,
        path: str | Path,
        *,
        start_sec: float = 0.0,
    ) -> None:
        super().__init__(sample_rate)
        self.path = Path(path)
        try:
            self._handle = sf.SoundFile(str(self.path), mode="r")
        except sf.LibsndfileError as exc:
            raise ValueError(f"cannot open audio file {self.path}: {exc}") from exc
        self.file_rate = int(self._handle.samplerate)
        self.file_frames = int(self._handle.frames)
        skip = max(0, int(round(float(start_sec) * self.file_rate)))
        if skip:
            self._handle.seek(min(skip, max(0, self.file_frames - 1)))
        self._resampler = (
            None
            if self.file_rate == self.sample_rate
            else _LinearResampler(self.file_rate, self.sample_rate)
        )
        self._pending = np.zeros(0, dtype=np.float64)
        self._eof = False

    @property
    def file_duration_sec(self) -> float:
        """Duration of the whole file in seconds (time is rate-invariant)."""
        return self.file_frames / self.file_rate

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception:  # pragma: no cover - defensive
            pass

    def process(self, n_frames: int) -> np.ndarray:
        """Return up to ``n_frames`` samples; SHORTER block signals EOF."""
        n = int(n_frames)
        chunks: list[np.ndarray] = []
        filled = 0
        while filled < n and not self._eof:
            if not len(self._pending):
                raw, eof = self._read_decode_block()
                converted = (
                    self._resampler.process(raw)
                    if self._resampler is not None
                    else raw
                )
                self._pending = np.asarray(converted, dtype=np.float64)
                # EOF ends the stream once buffered audio is drained too
                if eof and len(self._pending) == 0:
                    self._eof = True
            take = min(len(self._pending), n - filled)
            if take <= 0:
                break
            chunks.append(self._pending[:take])
            filled += take
            self._pending = self._pending[take:]
        if not chunks:
            return np.zeros((1, 0), dtype=np.float32)
        return np.concatenate(chunks)[None, :].astype(np.float32)

    def _read_decode_block(self) -> tuple[np.ndarray, bool]:
        try:
            data = self._handle.read(
                self.DECODE_BLOCK, always_2d=True, dtype="float64"
            )
        except (sf.LibsndfileError, RuntimeError):
            return np.zeros(0, dtype=np.float64), True
        if len(data) == 0:
            return np.zeros(0, dtype=np.float64), True
        mono = data[:, :2].mean(axis=1)
        return mono.astype(np.float64), len(data) < self.DECODE_BLOCK


class DroneSource(SourceNode):
    """Detuned unison drone with slow filter sweep; an ambient music bed."""

    def __init__(
        self,
        sample_rate: int,
        *,
        frequency: float = 110.0,
        voices: int = 5,
        detune_cents: float = 14.0,
        seed: int | None = None,
        level: float = 0.35,
    ) -> None:
        super().__init__(sample_rate)
        self._osc = Oscillator(
            sample_rate,
            wave="SAW",
            frequency=frequency,
            unison_voices=voices,
            detune_cents=detune_cents,
            sub_level=0.4,
        )
        self._lfo = LFO(sample_rate, shape="SINE", rate_hz=0.07, phase=0.1, seed=seed)
        self._filter = BiquadFilter(sample_rate, kind="lowpass", cutoff=500.0, q=1.1)
        self.level = float(level)

    def process(self, n_frames: int) -> np.ndarray:
        raw = self._osc.process(n_frames)[0].astype(np.float64)
        lfo_val = float(np.mean(self._lfo.process(n_frames).astype(np.float64)))
        self._filter.set_params(cutoff=250.0 + 750.0 * lfo_val)
        filtered = self._filter.process(raw)
        filtered *= self.level
        return filtered.astype(np.float32)[None, :]
