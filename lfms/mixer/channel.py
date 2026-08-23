"""Mixer channels: strip state (fader, pan, mute/solo, fades)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lfms.core.errors import ValidationError

CHANNEL_KINDS = ("MUSIC", "VOICEOVER", "AMBIENCE", "SFX")


@dataclass
class ChannelState:
    name: str
    kind: str = "MUSIC"
    volume_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    preset: str | None = None

    def validate(self) -> None:
        if not self.name.strip():
            raise ValidationError("channel name must not be empty")
        if self.kind not in CHANNEL_KINDS:
            raise ValidationError(f"unknown channel kind {self.kind!r}")
        if not -60.0 <= self.volume_db <= 12.0:
            raise ValidationError("channel volume_db must be within [-60, 12]")
        if not -1.0 <= self.pan <= 1.0:
            raise ValidationError("channel pan must be within [-1, 1]")
        if self.fade_in_sec < 0.0 or self.fade_out_sec < 0.0:
            raise ValidationError("fade times must be >= 0")


def fade_gain_curve(
    total_frames: int,
    sample_rate: int,
    fade_in_sec: float,
    fade_out_sec: float,
) -> np.ndarray:
    """Linear fade-in/out gain curve of shape (total_frames,)."""
    curve = np.ones(total_frames, dtype=np.float32)
    n_in = min(total_frames, int(fade_in_sec * sample_rate))
    if n_in > 0:
        ramp = np.linspace(0.0, 1.0, n_in, endpoint=False, dtype=np.float64)
        curve[:n_in] = ramp.astype(np.float32)
    n_out = min(total_frames - n_in, int(fade_out_sec * sample_rate))
    if n_out > 0:
        ramp = np.linspace(1.0, 0.0, n_out, endpoint=True, dtype=np.float64)
        curve[total_frames - n_out :] = np.minimum(
            curve[total_frames - n_out :], ramp.astype(np.float32)
        )
    return curve
