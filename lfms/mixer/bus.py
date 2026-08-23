"""Offline mix bus: streaming sources -> chains -> fades/pan/fader -> master.

Voiceover-kind channels drive a sidechain ducker that attenuates every
non-voiceover channel. Block-streaming like the audio engine, deterministic.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.dsp import db_to_gain, equal_power_pan
from lfms.audio_engine.effects import Effect
from lfms.core.errors import ValidationError
from lfms.mixer.chain import EffectChain
from lfms.mixer.channel import ChannelState, fade_gain_curve
from lfms.mixer.ducking import DuckingSettings, SidechainDucker

DEFAULT_BLOCK = 1 << 15


class _ArraySource:
    def __init__(self, data: np.ndarray, sample_rate: int) -> None:
        self.data = np.asarray(data, dtype=np.float32)
        if self.data.ndim == 1:
            self.data = self.data[None, :]
        if self.data.ndim != 2 or self.data.shape[0] not in (1, 2):
            raise ValidationError("stem arrays must have shape (channels, n)")
        self.sample_rate = int(sample_rate)
        self._pos = 0

    @property
    def frames(self) -> int:
        return self.data.shape[1]

    def reset(self) -> None:
        self._pos = 0

    def process(self, n_frames: int) -> np.ndarray:
        stop = min(self._pos + n_frames, self.frames)
        block = self.data[:, self._pos : stop]
        pad = n_frames - block.shape[1]
        self._pos = stop
        if pad > 0:
            block = np.pad(block, ((0, 0), (0, pad)))
        return np.ascontiguousarray(block)


class MixChannel:
    """A bus channel: source + state + optional effect chain."""

    def __init__(
        self,
        state: ChannelState,
        source,
        *,
        chain: EffectChain | None = None,
    ) -> None:
        state.validate()
        self.state = state
        self.source = source
        self.chain = chain


class MixBus:
    def __init__(
        self,
        sample_rate: int,
        *,
        master_volume_db: float = 0.0,
        master_effects: list[Effect] | None = None,
        ducking: DuckingSettings | None = None,
        total_frames: int | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.master_volume_db = float(master_volume_db)
        self.master_effects: list[Effect] = list(master_effects or [])
        self.channels: list[MixChannel] = []
        self.total_frames = total_frames
        self._ducker = SidechainDucker(sample_rate, ducking)

    # -- setup -----------------------------------------------------------
    def add_channel(
        self,
        name: str,
        source,
        *,
        kind: str = "MUSIC",
        volume_db: float = 0.0,
        pan: float = 0.0,
        mute: bool = False,
        solo: bool = False,
        fade_in_sec: float = 0.0,
        fade_out_sec: float = 0.0,
        chain: EffectChain | None = None,
        state: ChannelState | None = None,
    ) -> MixChannel:
        if source.sample_rate != self.sample_rate:
            raise ValidationError(
                f"source sample rate {source.sample_rate} differs from bus {self.sample_rate}"
            )
        if state is None:
            state = ChannelState(
                name=name,
                kind=kind,
                volume_db=volume_db,
                pan=pan,
                mute=mute,
                solo=solo,
                fade_in_sec=fade_in_sec,
                fade_out_sec=fade_out_sec,
            )
        elif state.name != name:
            raise ValidationError("channel name mismatch with provided state")
        channel = MixChannel(state, source, chain=chain)
        self.channels.append(channel)
        return channel

    def add_stem(
        self,
        name: str,
        stem: np.ndarray,
        *,
        kind: str = "MUSIC",
        **kwargs,
    ) -> MixChannel:
        source = _ArraySource(stem, self.sample_rate)
        if self.total_frames is None:
            self.total_frames = source.frames
        return self.add_channel(name, source, kind=kind, **kwargs)

    def channel(self, name: str) -> MixChannel:
        for channel in self.channels:
            if channel.state.name == name:
                return channel
        raise ValidationError(f"unknown channel {name!r}")

    # -- render ----------------------------------------------------------
    def _active_channels(self) -> list[MixChannel]:
        any_solo = any(c.state.solo for c in self.channels)
        return [
            c
            for c in self.channels
            if not c.state.mute and (c.state.solo if any_solo else True)
        ]

    def _resolve_total(self) -> int:
        if self.total_frames is not None:
            return int(self.total_frames)
        lengths = [
            getattr(c.source, "frames", None) for c in self.channels
        ]
        known = [n for n in lengths if n]
        if not known:
            raise ValidationError("total_frames unknown and no finite sources")
        return max(known)

    def render(
        self,
        *,
        block_size: int = DEFAULT_BLOCK,
        on_progress=None,
    ) -> np.ndarray:
        total = self._resolve_total()
        active = self._active_channels()
        for channel in self.channels:
            reset = getattr(channel.source, "reset", None)
            if callable(reset):
                reset()
        self._ducker.reset()
        curves = {
            c.state.name: fade_gain_curve(
                total,
                self.sample_rate,
                c.state.fade_in_sec,
                c.state.fade_out_sec,
            )
            for c in self.channels
        }
        vo_names = {c.state.name for c in self.channels if c.state.kind == "VOICEOVER"}

        mix_out = np.zeros((2, total), dtype=np.float32)
        for start in range(0, total, block_size):
            stop = min(start + block_size, total)
            n = stop - start
            music_acc = np.zeros((2, n), dtype=np.float64)
            vo_acc = np.zeros((2, n), dtype=np.float64)
            for channel in active:
                block = channel.source.process(n).astype(np.float64)
                if block.shape[0] == 1:
                    left_gain, right_gain = equal_power_pan(channel.state.pan)
                    block = np.stack([block[0] * left_gain, block[0] * right_gain])
                elif channel.state.pan != 0.0:
                    mono = np.mean(block, axis=0)
                    left_gain, right_gain = equal_power_pan(channel.state.pan)
                    block = np.stack([mono * left_gain, mono * right_gain])
                if channel.chain is not None and len(channel.chain):
                    block = channel.chain.process(block.astype(np.float32)).astype(np.float64)
                block *= db_to_gain(channel.state.volume_db)
                fade_slice = curves[channel.state.name][start:stop]
                block *= fade_slice.astype(np.float64)[None, :]
                target = vo_acc if channel.state.name in vo_names else music_acc
                target += block
            if vo_names:
                duck_curve = self._ducker.gain_curve_for(n, vo_acc[:, :].astype(np.float32))
                music_acc *= duck_curve.astype(np.float64)[None, :]
            music_acc += vo_acc
            mix_out[:, start:stop] = music_acc.astype(np.float32)
            if on_progress is not None:
                on_progress(stop / total)
        out = mix_out * db_to_gain(self.master_volume_db)
        for effect in self.master_effects:
            out = effect.process(out.astype(np.float32)).astype(np.float32)
        return out.astype(np.float32)
