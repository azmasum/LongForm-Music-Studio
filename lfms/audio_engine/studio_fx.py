"""Studio effects: EQ, Compressor, Delay, Reverb.

All inherit from Effect and process stereo (2, n) float32 blocks.
They are stateful (streaming) so parameters can be changed between blocks
without clicks — except reverb tail may ring briefly.
"""
from __future__ import annotations

import numpy as np

from lfms.audio_engine.dsp import db_to_gain
from lfms.audio_engine.effects import Effect
from lfms.audio_engine.filters import BiquadFilter

# ── EQ ─────────────────────────────────────────────────────────────────────


class EqEffect(Effect):
    """3-band parametric EQ: low shelf, peaking mid, high shelf.

    Parameters are immediately effective (coefficients recomputed on change).
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        low_cutoff: float = 200.0,
        low_gain_db: float = 0.0,
        mid_cutoff: float = 1000.0,
        mid_q: float = 0.707,
        mid_gain_db: float = 0.0,
        high_cutoff: float = 4000.0,
        high_gain_db: float = 0.0,
    ) -> None:
        self._sr = sample_rate
        self._low = BiquadFilter(sample_rate, kind="lowshelf",
                                 cutoff=low_cutoff, q=0.707, gain_db=low_gain_db, channels=2)
        self._mid = BiquadFilter(sample_rate, kind="peaking",
                                 cutoff=mid_cutoff, q=mid_q, gain_db=mid_gain_db, channels=2)
        self._high = BiquadFilter(sample_rate, kind="highshelf",
                                  cutoff=high_cutoff, q=0.707, gain_db=high_gain_db, channels=2)

    def process(self, block: np.ndarray) -> np.ndarray:
        out = self._low.process(block.astype(np.float64))
        out = self._mid.process(out)
        out = self._high.process(out)
        return out.astype(np.float32)

    # -- parameter access --------------------------------------------------
    @property
    def low_gain_db(self) -> float:
        return self._low.gain_db

    @low_gain_db.setter
    def low_gain_db(self, v: float):
        self._low.set_params(gain_db=float(v))

    @property
    def mid_gain_db(self) -> float:
        return self._mid.gain_db

    @mid_gain_db.setter
    def mid_gain_db(self, v: float):
        self._mid.set_params(gain_db=float(v))

    @property
    def high_gain_db(self) -> float:
        return self._high.gain_db

    @high_gain_db.setter
    def high_gain_db(self, v: float):
        self._high.set_params(gain_db=float(v))

    def to_dict(self) -> dict:
        return {
            "type": "eq",
            "low_cutoff": self._low.cutoff,
            "low_gain_db": self._low.gain_db,
            "mid_cutoff": self._mid.cutoff,
            "mid_q": self._mid.q,
            "mid_gain_db": self._mid.gain_db,
            "high_cutoff": self._high.cutoff,
            "high_gain_db": self._high.gain_db,
        }


# ── Compressor ─────────────────────────────────────────────────────────────


class CompressorEffect(Effect):
    """Feed-forward compressor with smoothed envelope.

    Parameters:
        threshold_db: level above which compression starts.
        ratio: compression ratio (1 = no compression, ∞ = hard limiter).
        attack_sec: attack time constant for the envelope follower.
        release_sec: release time constant.
        makeup_db: output gain补偿.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_sec: float = 0.005,
        release_sec: float = 0.050,
        makeup_db: float = 0.0,
    ) -> None:
        self._sr = sample_rate
        self.threshold_db = float(threshold_db)
        self.ratio = max(1.0, float(ratio))
        self.attack_sec = max(0.0001, float(attack_sec))
        self.release_sec = max(0.001, float(release_sec))
        self.makeup_db = float(makeup_db)
        self._envelope = np.float64(db_to_gain(threshold_db))

    def process(self, block: np.ndarray) -> np.ndarray:
        x = block.astype(np.float64)
        n = x.shape[1]
        rms = np.sqrt(np.mean(x ** 2, axis=0) + 1e-12)
        atk = 1.0 - np.exp(-1.0 / (self._sr * self.attack_sec))
        rel = 1.0 - np.exp(-1.0 / (self._sr * self.release_sec))
        env = np.empty(n, dtype=np.float64)
        e = self._envelope
        for i in range(n):
            coeff = atk if rms[i] > e else rel
            e = e + coeff * (rms[i] - e)
            env[i] = e
        self._envelope = float(e)
        thresh_linear = db_to_gain(self.threshold_db)
        above = env > thresh_linear
        gain = np.ones(n, dtype=np.float64)
        if np.any(above):
            ratio_atten = 1.0 / self.ratio
            over_db = 20.0 * np.log10(env[above] / max(thresh_linear, 1e-12))
            compressed_db = over_db * ratio_atten
            gain[above] = db_to_gain(-(over_db - compressed_db))
        makeup = db_to_gain(self.makeup_db)
        out = x * gain[None, :] * makeup
        return out.astype(np.float32)

    def to_dict(self) -> dict:
        return {
            "type": "compressor",
            "threshold_db": self.threshold_db,
            "ratio": self.ratio,
            "attack_sec": self.attack_sec,
            "release_sec": self.release_sec,
            "makeup_db": self.makeup_db,
        }


# ── Delay ──────────────────────────────────────────────────────────────────


class DelayEffect(Effect):
    """Stereo delay with feedback and wet/dry mix.

    Parameters:
        delay_sec: delay time in seconds (per channel; L is offset by a bit).
        feedback: 0..0.95 feedback amount.
        wet: wet/dry mix (0 = dry only, 1 = wet only).
        ping_pong: if True, L feeds into R and vice versa.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        delay_sec: float = 0.25,
        feedback: float = 0.3,
        wet: float = 0.3,
        ping_pong: bool = False,
    ) -> None:
        self._sr = sample_rate
        self.delay_sec = max(0.001, float(delay_sec))
        self.feedback = max(0.0, min(0.95, float(feedback)))
        self.wet = max(0.0, min(1.0, float(wet)))
        self.ping_pong = bool(ping_pong)
        max_samples = int(sample_rate * 2.0)
        self._buf_l = np.zeros(max_samples, dtype=np.float64)
        self._buf_r = np.zeros(max_samples, dtype=np.float64)
        self._pos = 0

    def process(self, block: np.ndarray) -> np.ndarray:
        n = int(block.shape[1])
        x = block.astype(np.float64)
        out_l = np.empty(n, dtype=np.float64)
        out_r = np.empty(n, dtype=np.float64)
        delay_samples = max(1, int(self.delay_sec * self._sr))
        buf_len = len(self._buf_l)
        pos = self._pos
        fb = self.feedback
        for i in range(n):
            read_idx = (pos - delay_samples) % buf_len
            dl = self._buf_l[read_idx]
            dr = self._buf_r[read_idx]
            if self.ping_pong:
                dl, dr = dr, dl
            out_l[i] = x[0, i] + dl * self.wet
            out_r[i] = x[1, i] + dr * self.wet
            self._buf_l[pos] = x[0, i] + dl * fb
            self._buf_r[pos] = x[1, i] + dr * fb
            pos = (pos + 1) % buf_len
        self._pos = pos
        return np.stack([out_l, out_r]).astype(np.float32)

    def to_dict(self) -> dict:
        return {
            "type": "delay",
            "delay_sec": self.delay_sec,
            "feedback": self.feedback,
            "wet": self.wet,
            "ping_pong": self.ping_pong,
        }


# ── Reverb ─────────────────────────────────────────────────────────────────


class ReverbEffect(Effect):
    """Algorithmic reverb using parallel Schroeder comb filters + allpass.

    Parameters:
        room_size: 0..1, controls comb filter delays.
        damping: 0..1, high-frequency damping inside comb loops.
        wet: wet/dry mix (0 = dry only, 1 = wet only).
    """

    COMB_DELAYS = [1557, 1617, 1491, 1422, 1277, 1356, 1188, 1233]
    ALLPASS_DELAYS = [225, 556, 441, 341]

    def __init__(
        self,
        sample_rate: int,
        *,
        room_size: float = 0.7,
        damping: float = 0.5,
        wet: float = 0.3,
    ) -> None:
        self._sr = sample_rate
        self.room_size = max(0.0, min(1.0, float(room_size)))
        self.damping = max(0.0, min(1.0, float(damping)))
        self.wet = max(0.0, min(1.0, float(wet)))
        self._combs: list[_CombFilter] = []
        for d in self.COMB_DELAYS:
            scaled = int(d * sample_rate / 44100)
            self._combs.append(_CombFilter(max(1, scaled), self.room_size, self.damping))
        self._allpasses: list[_AllpassFilter] = []
        for d in self.ALLPASS_DELAYS:
            scaled = int(d * sample_rate / 44100)
            self._allpasses.append(_AllpassFilter(max(1, scaled)))

    def process(self, block: np.ndarray) -> np.ndarray:
        n = int(block.shape[1])
        x = block.astype(np.float64)
        mono = 0.5 * (x[0] + x[1])
        comb_out = np.zeros(n, dtype=np.float64)
        for comb in self._combs:
            comb_out += comb.process(mono)
        comb_out *= 1.0 / len(self._combs)
        for ap in self._allpasses:
            comb_out = ap.process(comb_out)
        wet = self.wet
        out_l = x[0] * (1.0 - wet) + comb_out * wet
        out_r = x[1] * (1.0 - wet) + comb_out * wet
        return np.stack([out_l, out_r]).astype(np.float32)

    def to_dict(self) -> dict:
        return {
            "type": "reverb",
            "room_size": self.room_size,
            "damping": self.damping,
            "wet": self.wet,
        }


# ── internal helpers ───────────────────────────────────────────────────────


class _CombFilter:
    def __init__(self, size: int, feedback: float, damping: float):
        self._buf = np.zeros(size, dtype=np.float64)
        self._pos = 0
        self._feedback = feedback
        self._damp_coeff = damping
        self._last = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        out = np.empty(n, dtype=np.float64)
        buf = self._buf
        pos = self._pos
        fb = self._feedback
        d = self._damp_coeff
        last = self._last
        sz = len(buf)
        for i in range(n):
            read = buf[pos]
            filtered = read * (1.0 - d) + last * d
            last = filtered
            buf[pos] = x[i] + filtered * fb
            out[i] = read
            pos = (pos + 1) % sz
        self._pos = pos
        self._last = last
        return out


class _AllpassFilter:
    def __init__(self, size: int):
        self._buf = np.zeros(size, dtype=np.float64)
        self._pos = 0

    def process(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        out = np.empty(n, dtype=np.float64)
        buf = self._buf
        pos = self._pos
        sz = len(buf)
        for i in range(n):
            read = buf[pos]
            out[i] = -x[i] + read
            buf[pos] = x[i] + read * 0.5
            pos = (pos + 1) % sz
        self._pos = pos
        return out


# ── factory ────────────────────────────────────────────────────────────────

EFFECT_TYPES: dict[str, type[Effect]] = {
    "gain": None,  # imported from lfms.audio_engine.effects
    "eq": EqEffect,
    "compressor": CompressorEffect,
    "delay": DelayEffect,
    "reverb": ReverbEffect,
}


def build_effect_from_dict(data: dict, sample_rate: int) -> Effect:
    """Construct an Effect from a serialized dict."""
    from lfms.audio_engine.effects import GainEffect

    kind = data.get("type", "")
    if kind == "gain":
        return GainEffect(gain_db=float(data.get("gain_db", 0.0)))
    if kind == "eq":
        return EqEffect(
            sample_rate,
            low_cutoff=float(data.get("low_cutoff", 200)),
            low_gain_db=float(data.get("low_gain_db", 0)),
            mid_cutoff=float(data.get("mid_cutoff", 1000)),
            mid_q=float(data.get("mid_q", 0.707)),
            mid_gain_db=float(data.get("mid_gain_db", 0)),
            high_cutoff=float(data.get("high_cutoff", 4000)),
            high_gain_db=float(data.get("high_gain_db", 0)),
        )
    if kind == "compressor":
        return CompressorEffect(
            sample_rate,
            threshold_db=float(data.get("threshold_db", -20)),
            ratio=float(data.get("ratio", 4)),
            attack_sec=float(data.get("attack_sec", 0.005)),
            release_sec=float(data.get("release_sec", 0.05)),
            makeup_db=float(data.get("makeup_db", 0)),
        )
    if kind == "delay":
        return DelayEffect(
            sample_rate,
            delay_sec=float(data.get("delay_sec", 0.25)),
            feedback=float(data.get("feedback", 0.3)),
            wet=float(data.get("wet", 0.3)),
            ping_pong=bool(data.get("ping_pong", False)),
        )
    if kind == "reverb":
        return ReverbEffect(
            sample_rate,
            room_size=float(data.get("room_size", 0.7)),
            damping=float(data.get("damping", 0.5)),
            wet=float(data.get("wet", 0.3)),
        )
    raise ValueError(f"unknown effect type {kind!r}")


def serialize_effect(effect: Effect) -> dict:
    """Serialize an effect to a dict if it supports to_dict()."""
    if hasattr(effect, "to_dict"):
        return effect.to_dict()
    from lfms.audio_engine.effects import GainEffect
    if isinstance(effect, GainEffect):
        return {"type": "gain", "gain_db": effect.gain_db}
    from lfms.audio_engine.effects import SoftLimiter
    if isinstance(effect, SoftLimiter):
        return {"type": "soft_limiter", "threshold": effect.threshold}
    from lfms.audio_engine.effects import DCBlockEffect
    if isinstance(effect, DCBlockEffect):
        return {"type": "dc_block"}
    from lfms.audio_engine.effects import StereoWidth
    if isinstance(effect, StereoWidth):
        return {"type": "stereo_width", "width": effect.width}
    return {"type": "unknown"}
