"""Instrument voices: one NoteEvent rendered as sequential mono samples.

Every voice is deterministic: oscillators carry no randomness and any noise
comes from an RNG seeded by the composition seed plus the event index.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.envelopes import ADSR
from lfms.audio_engine.filters import BiquadFilter
from lfms.audio_engine.oscillators import Oscillator
from lfms.generator.events import NoteEvent
from lfms.generator.theory import midi_to_freq


class VoiceBase:
    """Streams one note as mono blocks; call process() strictly in order."""

    def __init__(
        self,
        sample_rate: int,
        note: NoteEvent,
        *,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.note = note
        self.dur_frames = max(1, int(note.duration_sec * sample_rate))
        self._produced = 0
        self._gate_off_sent = False
        self.vel_gain = (float(np.clip(note.velocity, 1, 127)) / 127.0) ** 1.5 * 0.9
        self.env = ADSR(
            sample_rate,
            attack=attack,
            decay=decay,
            sustain=sustain,
            release=release,
        )
        self._build()
        self.env.gate_on()

    def _build(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def _osc(self, n_frames: int) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return signal

    def process(self, n_frames: int) -> np.ndarray:
        raw = self._osc(int(n_frames))
        if raw.ndim > 1:
            raw = raw[0]
        out = self._shape(raw) * self.env.process(int(n_frames))
        out = out * self.vel_gain
        self._produced += int(n_frames)
        if not self._gate_off_sent and self._produced >= self.dur_frames:
            self.env.gate_off()
            self._gate_off_sent = True
        return out.astype(np.float32)

    @property
    def finished(self) -> bool:
        return self.env.finished


class PadVoice(VoiceBase):
    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        brightness = float(self.note.velocity) / 127.0
        self.osc = Oscillator(
            self.sample_rate,
            wave="TRIANGLE",
            frequency=freq,
            unison_voices=3,
            detune_cents=10.0 + 8.0 * brightness,
        )
        cutoff = min(float(self.timbre.get("brightness_hz", 1800.0)) * 1.3, 9000.0)
        self.filter = BiquadFilter(
            self.sample_rate, kind="lowpass", cutoff=cutoff, q=0.6
        )

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate,
            note,
            attack=timbre.get("attack", 1.1),
            decay=0.3,
            sustain=0.85,
            release=timbre.get("release", 2.5),
        )

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(signal)


class PluckVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate,
            note,
            attack=0.004,
            decay=timbre.get("decay", 1.1),
            sustain=0.0,
            release=0.4,
        )

    def _build(self) -> None:
        self.osc = Oscillator(
            self.sample_rate,
            wave="TRIANGLE",
            frequency=midi_to_freq(self.note.midi),
        )
        cutoff = min(float(self.timbre.get("brightness_hz", 2000.0)) * 1.6, 12000.0)
        self.filter = BiquadFilter(
            self.sample_rate, kind="lowpass", cutoff=cutoff, q=0.7
        )

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(signal)


class BellVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate,
            note,
            attack=0.002,
            decay=timbre.get("decay", 1.9),
            sustain=0.0,
            release=0.6,
        )

    def _build(self) -> None:
        self.osc = Oscillator(
            self.sample_rate,
            wave="SINE",
            frequency=midi_to_freq(self.note.midi),
            fm_ratio=3.5,
            fm_index=2.2,
        )

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)


class PianoVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate,
            note,
            attack=0.003,
            decay=1.4,
            sustain=0.22,
            release=0.7,
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.osc_main = Oscillator(
            self.sample_rate, wave="SINE", frequency=freq, am_rate=0.0
        )
        self.osc_third = Oscillator(
            self.sample_rate, wave="SINE", frequency=freq * 2.0
        )
        self.env_third = ADSR(
            self.sample_rate, attack=0.003, decay=0.55, sustain=0.0, release=0.3
        )

    def _osc(self, n: int) -> np.ndarray:
        third = self.osc_third.process(n) * self.env_third.process(n) * 0.45
        return self.osc_main.process(n) * 0.9 + third


class BassVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate,
            note,
            attack=0.012,
            decay=0.25,
            sustain=0.75,
            release=0.3,
        )

    def _build(self) -> None:
        self.osc = Oscillator(
            self.sample_rate,
            wave="SINE",
            frequency=midi_to_freq(self.note.midi),
            sub_level=0.4,
        )
        self.filter = BiquadFilter(
            self.sample_rate, kind="lowpass", cutoff=min(float(self.timbre.get("brightness_hz", 2000.0)) * 0.35, 500.0), q=0.7
        )

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(signal)


class KickVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        self._phase = 0.0
        self._elapsed = 0.0
        super().__init__(
            sample_rate, note, attack=0.001, decay=0.10, sustain=0.0, release=0.05
        )

    def _build(self) -> None:
        base = float(np.clip(midi_to_freq(self.note.midi), 40.0, 90.0))
        self.f_start = base * 2.2

    def _osc(self, n: int) -> np.ndarray:
        idx = np.arange(int(n), dtype=np.float64) / self.sample_rate
        time = self._elapsed + idx
        freq = self.f_start * np.exp(-time * 26.0) + 41.0
        phase = self._phase + np.cumsum(freq) / self.sample_rate
        self._phase = float(phase[-1] % 1.0)
        self._elapsed = float(time[-1]) + 1.0 / self.sample_rate
        body = np.sin(2.0 * np.pi * phase) * np.exp(-time * 5.5)
        click = np.exp(-time * 220.0) * 0.35
        return (body + click).astype(np.float64)


class HatVoice(VoiceBase):
    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict, *, rng_seed: int = 0) -> None:
        self._rng = np.random.default_rng(rng_seed)
        self.timbre = timbre
        super().__init__(
            sample_rate, note, attack=0.001, decay=0.055, sustain=0.0, release=0.03
        )

    def _build(self) -> None:
        self.noise_gain = 0.55
        self.filter = BiquadFilter(
            self.sample_rate, kind="highpass", cutoff=6500.0, q=0.707
        )

    def _osc(self, n: int) -> np.ndarray:
        return self._rng.standard_normal(int(n)) * self.noise_gain

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(np.asarray(signal, dtype=np.float64))


_VOICE_CLASSES = {
    "PAD": PadVoice,
    "PLUCK": PluckVoice,
    "BELL": BellVoice,
    "PIANO": PianoVoice,
    "BASS": BassVoice,
    "KICK": KickVoice,
    "HAT": HatVoice,
}


def make_voice(
    instrument: str,
    sample_rate: int,
    note: NoteEvent,
    timbre: dict | None = None,
    *,
    rng_seed: int = 0,
):
    cls = _VOICE_CLASSES.get(str(instrument).upper())
    if cls is None:
        raise ValueError(f"unknown instrument {instrument!r}")
    if cls is HatVoice:
        return cls(sample_rate, note, timbre or {}, rng_seed=rng_seed)
    return cls(sample_rate, note, timbre or {})
