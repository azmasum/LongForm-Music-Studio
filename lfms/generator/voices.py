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


class StringsVoice(VoiceBase):
    """Detuned saw ensemble with a slow bow-like attack."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note,
            attack=timbre.get("attack", 0.45), decay=0.5,
            sustain=0.78, release=1.6,
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.osc = Oscillator(
            self.sample_rate, wave="SAW", frequency=freq,
            unison_voices=3, detune_cents=14.0,
        )
        cutoff = min(float(self.timbre.get("brightness_hz", 1800.0)) * 1.2, 6000.0)
        self.filter = BiquadFilter(self.sample_rate, kind="lowpass", cutoff=cutoff, q=0.5)

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(signal)


class ChoirVoice(VoiceBase):
    """Vowel-ish pad: vibrato triangle through a formant pair."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note,
            attack=0.55, decay=0.4, sustain=0.85,
            release=timbre.get("release", 1.8),
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.osc = Oscillator(
            self.sample_rate, wave="TRIANGLE", frequency=freq,
            unison_voices=3, detune_cents=8.0,
            am_rate=5.2, am_depth=0.22,
        )
        center = min(float(self.timbre.get("brightness_hz", 1800.0)) + 700.0, 3200.0)
        self.formant = BiquadFilter(self.sample_rate, kind="bandpass", cutoff=center, q=0.9)
        self.tame = BiquadFilter(self.sample_rate, kind="lowpass", cutoff=4200.0, q=0.6)

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        shaped = 0.65 * signal + 0.35 * self.formant.process(signal)
        return self.tame.process(shaped)


class OrganVoice(VoiceBase):
    """Additive drawbar organ: f + 2f + 3f sines."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note, attack=0.02, decay=0.15, sustain=0.9, release=0.25
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.oct2 = Oscillator(self.sample_rate, wave="SINE", frequency=freq * 2.0)
        self.oct3 = Oscillator(self.sample_rate, wave="SINE", frequency=freq * 3.0)
        self.main = Oscillator(self.sample_rate, wave="SINE", frequency=freq)

    def _osc(self, n: int) -> np.ndarray:
        return (
            self.main.process(n) * 0.55
            + self.oct2.process(n) * 0.30
            + self.oct3.process(n) * 0.15
        )


class EPianoVoice(VoiceBase):
    """FM electric piano with a short tine overtone."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note, attack=0.004, decay=0.95, sustain=0.24, release=0.6
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.carrier = Oscillator(
            self.sample_rate, wave="SINE", frequency=freq, fm_ratio=2.0, fm_index=0.8
        )
        self.tine_osc = Oscillator(self.sample_rate, wave="SINE", frequency=freq * 4.0)
        self.tine_env = ADSR(self.sample_rate, attack=0.001, decay=0.18, sustain=0.0, release=0.1)

    def _osc(self, n: int) -> np.ndarray:
        tine = self.tine_osc.process(n) * self.tine_env.process(n) * 0.30
        return self.carrier.process(n) * 0.95 + tine


class MarimbaVoice(VoiceBase):
    """Woody mallet: fundamental sine plus a fast-fading 4th harmonic."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note,
            attack=0.002, decay=timbre.get("decay", 0.7),
            sustain=0.0, release=0.3,
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.fund = Oscillator(self.sample_rate, wave="SINE", frequency=freq)
        self.harm = Oscillator(self.sample_rate, wave="SINE", frequency=freq * 4.0)
        self.harm_env = ADSR(self.sample_rate, attack=0.001, decay=0.12, sustain=0.0, release=0.08)

    def _osc(self, n: int) -> np.ndarray:
        harmonic = self.harm.process(n) * self.harm_env.process(n) * 0.35
        return self.fund.process(n) * 0.95 + harmonic


class NylonVoice(VoiceBase):
    """Karplus-Strong plucked nylon-string guitar."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict, *, rng_seed: int = 0) -> None:
        self._rng = np.random.default_rng(rng_seed)
        self.timbre = timbre
        super().__init__(
            sample_rate, note,
            attack=0.002, decay=timbre.get("decay", 1.8),
            sustain=0.0, release=0.35,
        )

    def _build(self) -> None:
        freq = float(np.clip(midi_to_freq(self.note.midi), 60.0, 2000.0))
        period = max(2, int(round(self.sample_rate / freq)))
        total = int(self.dur_frames * 1.6) + 64
        buf = self._rng.uniform(-1.0, 1.0, period)
        damping = 0.5 * (1.0 - min(0.35, freq / 8000.0))  # brighter highs damp faster
        out = np.empty(total, dtype=np.float32)
        cursor = 0
        while cursor < total:
            chunk = min(period, total - cursor)
            out[cursor : cursor + chunk] = buf[:chunk]
            nxt = np.concatenate((buf[chunk:], buf[:chunk])) if chunk < period else buf
            buf = damping * (buf + nxt)
            cursor += chunk
        peak = float(np.max(np.abs(out))) or 1.0
        self._cache = out / peak
        self._cursor = 0

    def _osc(self, n: int) -> np.ndarray:
        end = min(self._cursor + int(n), len(self._cache))
        piece = self._cache[self._cursor : end]
        self._cursor = end
        if len(piece) < int(n):
            piece = np.pad(piece, (0, int(n) - len(piece)))
        return piece.astype(np.float64)


class SawBassVoice(VoiceBase):
    """Filtered saw bass with sub reinforcement; grittier than the sine bass."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict) -> None:
        self.timbre = timbre
        super().__init__(
            sample_rate, note, attack=0.008, decay=0.3, sustain=0.7, release=0.25
        )

    def _build(self) -> None:
        freq = midi_to_freq(self.note.midi)
        self.osc = Oscillator(
            self.sample_rate, wave="SAW", frequency=freq, sub_level=0.30
        )
        cutoff = min(float(self.timbre.get("brightness_hz", 2000.0)) * 0.5, 750.0)
        self.filter = BiquadFilter(self.sample_rate, kind="lowpass", cutoff=cutoff, q=1.0)

    def _osc(self, n: int) -> np.ndarray:
        return self.osc.process(n)

    def _shape(self, signal: np.ndarray) -> np.ndarray:
        return self.filter.process(signal)


class SnareVoice(VoiceBase):
    """Noise-plus-tone snare for the backbeat."""

    def __init__(self, sample_rate: int, note: NoteEvent, timbre: dict, *, rng_seed: int = 0) -> None:
        self._rng = np.random.default_rng(rng_seed)
        self.timbre = timbre
        self._phase = 0.0
        self._elapsed = 0.0
        super().__init__(
            sample_rate, note, attack=0.001, decay=0.13, sustain=0.0, release=0.08
        )

    def _build(self) -> None:
        self.noise_filter = BiquadFilter(
            self.sample_rate, kind="highpass", cutoff=1700.0, q=0.707
        )

    def _osc(self, n: int) -> np.ndarray:
        idx = np.arange(int(n), dtype=np.float64) / self.sample_rate
        time = self._elapsed + idx
        self._elapsed = float(time[-1]) + 1.0 / self.sample_rate
        tone_phase = self._phase + np.cumsum(190.0 * np.exp(-time * 14.0)) / self.sample_rate
        self._phase = float(tone_phase[-1] % 1.0)
        tone = np.sin(2.0 * np.pi * tone_phase) * np.exp(-time * 18.0) * 0.7
        noise = self.noise_filter.process(
            self._rng.standard_normal(int(n)) * np.exp(-time * 11.0)
        )
        return (tone + 0.9 * noise).astype(np.float64)


_SEEDED_VOICES = ("HAT", "NYLON", "SNARE")
_VOICE_CLASSES = {
    "PAD": PadVoice,
    "PLUCK": PluckVoice,
    "BELL": BellVoice,
    "PIANO": PianoVoice,
    "BASS": BassVoice,
    "KICK": KickVoice,
    "HAT": HatVoice,
    "STRINGS": StringsVoice,
    "CHOIR": ChoirVoice,
    "ORGAN": OrganVoice,
    "EPIANO": EPianoVoice,
    "MARIMBA": MarimbaVoice,
    "NYLON": NylonVoice,
    "SAW_BASS": SawBassVoice,
    "SNARE": SnareVoice,
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
    if str(instrument).upper() in _SEEDED_VOICES:
        return cls(sample_rate, note, timbre or {}, rng_seed=rng_seed)
    return cls(sample_rate, note, timbre or {})
