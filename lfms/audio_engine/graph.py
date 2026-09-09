"""Track strips and the mixer graph: sources -> pan -> effects -> bus."""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.dsp import db_to_gain, equal_power_pan
from lfms.audio_engine.effects import Effect
from lfms.audio_engine.sources import SourceNode


class TrackStrip:
    """A single mixer channel wrapping one source node."""

    def __init__(
        self,
        name: str,
        source: SourceNode,
        *,
        volume_db: float = 0.0,
        pan: float = 0.0,
        effects: list[Effect] | None = None,
        kind: str = "MUSIC",
    ) -> None:
        self.name = name
        self.source = source
        self.volume_db = float(volume_db)
        self.pan = max(-1.0, min(1.0, float(pan)))
        self.effects: list[Effect] = list(effects or [])
        self.kind = kind
        self.mute = False
        self.solo = False
        # Optional automation: callable(start_frame, n_frames) -> (n,) gain
        # multipliers in [0, 1] evaluated against the ABSOLUTE timeline.
        self.volume_envelope = None

    @property
    def sample_rate(self) -> int:
        return self.source.sample_rate

    def process(self, ctx: RenderContext, n_frames: int) -> np.ndarray:
        mono = self.source.process(n_frames)[0].astype(np.float64)
        left_gain, right_gain = equal_power_pan(self.pan)
        left = mono * left_gain
        right = mono * right_gain
        stereo = np.stack([left, right])
        for effect in self.effects:
            stereo = effect.process(stereo.astype(np.float32)).astype(np.float64)
        stereo *= db_to_gain(self.volume_db)
        if self.volume_envelope is not None:
            stereo *= self.volume_envelope(ctx.frames_done, n_frames)[None, :]
        return stereo.astype(np.float32)


class Mixer:
    """Sums active strips into a stereo (or mono-folded) master bus.

    When a :class:`SidechainDucker` is attached, strips whose ``kind`` equals
    ``duck_kind`` (voiceover) drive ducking of every other strip.
    """

    def __init__(self, *, master_volume_db: float = 0.0, channels: int = 2) -> None:
        if channels not in (1, 2):
            raise ValueError("channels must be 1 or 2")
        self.strips: list[TrackStrip] = []
        self.master_effects: list[Effect] = []
        self.master_volume_db = float(master_volume_db)
        self.channels = channels
        self.ducker = None
        self.duck_kind = "VOICEOVER"

    def add_strip(self, strip: TrackStrip) -> TrackStrip:
        self.strips.append(strip)
        return strip

    def _active_strips(self) -> list[TrackStrip]:
        any_solo = any(s.solo for s in self.strips)
        return [
            s
            for s in self.strips
            if not s.mute and (s.solo if any_solo else True)
        ]

    def _finalize(self, bus: np.ndarray) -> np.ndarray:
        for effect in self.master_effects:
            bus = effect.process(bus.astype(np.float32)).astype(np.float64)
        bus *= db_to_gain(self.master_volume_db)
        if self.channels == 1:
            mono = np.mean(bus, axis=0, keepdims=True)
            return mono.astype(np.float32)
        return bus.astype(np.float32)

    def process(self, ctx: RenderContext, n_frames: int) -> np.ndarray:
        bus = np.zeros((2, n_frames), dtype=np.float64)
        for strip in self._active_strips():
            bus += strip.process(ctx, n_frames).astype(np.float64)
        return self._finalize(bus)

    def process_ducked(self, ctx: RenderContext, n_frames: int) -> np.ndarray:
        vo = np.zeros((2, n_frames), dtype=np.float64)
        music = np.zeros((2, n_frames), dtype=np.float64)
        for strip in self._active_strips():
            block = strip.process(ctx, n_frames).astype(np.float64)
            if strip.kind == self.duck_kind:
                vo += block
            else:
                music += block
        curve = self.ducker.gain_curve_for(n_frames, vo.astype(np.float32))
        bus = music * curve.astype(np.float64)[None, :] + vo
        return self._finalize(bus)


class AudioGraph:
    """Top-level renderable graph binding sample rate and mixer."""

    def __init__(self, sample_rate: int = 48000, *, channels: int = 2) -> None:
        self.sample_rate = int(sample_rate)
        self.mixer = Mixer(channels=channels)

    @property
    def channels(self) -> int:
        return self.mixer.channels

    def create_track(
        self,
        name: str,
        source: SourceNode,
        *,
        volume_db: float = 0.0,
        pan: float = 0.0,
        effects: list[Effect] | None = None,
        kind: str = "MUSIC",
    ) -> TrackStrip:
        if source.sample_rate != self.sample_rate:
            raise ValueError(
                f"source sample rate {source.sample_rate} differs from graph {self.sample_rate}"
            )
        strip = TrackStrip(
            name, source, volume_db=volume_db, pan=pan, effects=effects, kind=kind
        )
        return self.mixer.add_strip(strip)

    def process(self, ctx: RenderContext, n_frames: int) -> np.ndarray:
        if self.mixer.ducker is not None:
            return self.mixer.process_ducked(ctx, n_frames)
        return self.mixer.process(ctx, n_frames)
