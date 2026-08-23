"""MixBus, channel state, fades and sidechain ducking tests."""
import numpy as np
import pytest

from lfms.core.errors import ValidationError
from lfms.mixer import (
    ChannelState,
    DuckingSettings,
    EffectChain,
    MixBus,
    SidechainDucker,
    fade_gain_curve,
)

SR = 48000


def _tone(freq: float, seconds: float, amp: float = 0.4) -> np.ndarray:
    t = np.arange(int(SR * seconds), dtype=np.float64) / SR
    wave = amp * np.sin(2 * np.pi * freq * t)
    return np.stack([wave, wave]).astype(np.float32)


def _vo_burst(seconds: float, amp: float = 0.6) -> np.ndarray:
    return _tone(300.0, seconds, amp=amp)


def test_channel_state_validation():
    with pytest.raises(ValidationError):
        ChannelState(name=" ").validate()
    with pytest.raises(ValidationError):
        ChannelState(name="A", kind="SUBWOOFER").validate()
    with pytest.raises(ValidationError):
        ChannelState(name="A", volume_db=-99.0).validate()
    with pytest.raises(ValidationError):
        ChannelState(name="A", fade_in_sec=-1.0).validate()


def test_fade_gain_curve_shapes_edges():
    curve = fade_gain_curve(int(2.0 * SR), SR, 0.5, 0.5)
    assert curve[0] == pytest.approx(0.0)
    mid = curve[int(1.0 * SR)]
    assert mid == pytest.approx(1.0)
    assert curve[-1] == pytest.approx(0.0)
    flat = fade_gain_curve(100, SR, 0.0, 0.0)
    assert np.all(flat == 1.0)


def test_ducking_settings_validation():
    with pytest.raises(ValidationError):
        DuckingSettings(floor_db=10.0)
    with pytest.raises(ValidationError):
        DuckingSettings(threshold_db=5.0)


def test_ducker_reduces_music_during_voiceover():
    ducker = SidechainDucker(
        SR,
        DuckingSettings(threshold_db=-30.0, floor_db=-15.0, attack_ms=20.0, range_db=12.0),
    )
    music = _tone(500.0, 2.0)
    vo = np.zeros((2, int(2.0 * SR)), dtype=np.float32)
    vo[:, int(0.5 * SR) : int(1.5 * SR)] = _vo_burst(1.0)
    out = ducker.process(music, vo)

    def level(seg):
        return float(np.sqrt(np.mean(out[0, seg] ** 2)))

    before = slice(int(0.2 * SR), int(0.45 * SR))
    during = slice(int(0.9 * SR), int(1.4 * SR))
    after = slice(int(1.7 * SR), int(1.95 * SR))
    assert level(during) < level(before) * 0.45
    assert level(after) > level(during) * 1.3
    # No VO at all -> unity gain passthrough.
    clean = SidechainDucker(SR).process(music, np.zeros((2, music.shape[1]), dtype=np.float32))
    assert np.allclose(clean, music)


def test_ducker_floor_respected_and_reset():
    settings = DuckingSettings(threshold_db=-40.0, floor_db=-18.0, attack_ms=5.0, range_db=6.0)
    ducker = SidechainDucker(SR, settings)
    loud_vo = _vo_burst(1.0, amp=0.9)
    music = np.ones((2, int(1.0 * SR)), dtype=np.float32) * 0.5
    out = ducker.process(music, loud_vo)
    steady = out[0, int(0.8 * SR) :]
    assert float(np.max(steady)) <= 0.5 + 1e-4
    min_gain = 10 ** (settings.floor_db / 20.0)
    assert float(np.mean(steady)) < 0.5 * (min_gain + 0.05)
    ducker.reset()
    assert ducker.current_gain == pytest.approx(1.0)


def test_bus_mute_solo_volume_and_length():
    bus = MixBus(SR)
    bus.add_stem("music", _tone(500.0, 1.0), volume_db=-6.0)
    bus.add_stem("pad", _tone(500.0, 1.0), volume_db=-6.0)
    mixed = bus.render()
    assert mixed.shape == (2, SR)
    ref = bus.channel("music")
    ref.state.mute = True
    muted = bus.render()
    # Coherent tones: full mix is exactly twice the muted level.
    assert float(np.max(np.abs(muted))) == pytest.approx(
        float(np.max(np.abs(mixed))) / 2.0, rel=0.05
    )

    ref.state.solo = True
    bus.channel("pad").state.solo = True
    solo_mix = bus.render()
    assert not np.array_equal(solo_mix, np.zeros_like(solo_mix))


def test_bus_pan_positions_energy():
    bus = MixBus(SR)
    bus.add_stem("left", _tone(600.0, 0.5), pan=-1.0)
    left_mix = bus.render()
    left_energy = float(np.sum(left_mix[0] ** 2))
    right_energy = float(np.sum(left_mix[1] ** 2))
    assert right_energy == pytest.approx(0.0, abs=1e-12)
    assert left_energy > 0.0

    bus2 = MixBus(SR)
    bus2.add_stem("right", _tone(600.0, 0.5), pan=1.0)
    right_mix = bus2.render()
    assert float(np.sum(right_mix[0] ** 2)) == pytest.approx(0.0, abs=1e-12)


def test_bus_fades_apply_to_channel_output():
    bus = MixBus(SR, total_frames=int(1.0 * SR))
    bus.add_channel("faded", _ArraySourceStub(_tone(700.0, 1.0), SR), fade_in_sec=0.25)
    mixed = bus.render()
    first_rms = float(np.sqrt(np.mean(mixed[0, : int(0.05 * SR)] ** 2)))
    mid_rms = float(np.sqrt(np.mean(mixed[0, : int(0.9 * SR)] ** 2)))
    assert first_rms < mid_rms * 0.6


def test_bus_voiceover_kinds_drive_ducking_of_music():
    from lfms.audio_engine.dsp import band_energy

    bus = MixBus(SR, ducking=DuckingSettings(threshold_db=-30.0, floor_db=-14.0, attack_ms=10.0))
    music_len = int(2.0 * SR)
    bus.add_stem("bed", _tone(450.0, 2.0), kind="MUSIC")
    vo = np.zeros((2, music_len), dtype=np.float32)
    vo[:, int(0.5 * SR) : int(1.5 * SR)] = _vo_burst(1.0)
    bus.add_stem("vo", vo, kind="VOICEOVER")
    mixed = bus.render()

    def bed_energy(seg):
        return band_energy(mixed[0][seg].astype(np.float64), SR, 400.0, 500.0)

    quiet_bed = bed_energy(slice(int(0.85 * SR), int(1.35 * SR)))
    loud_bed = bed_energy(slice(int(1.7 * SR), int(1.95 * SR)))
    assert loud_bed > 0.0
    assert quiet_bed < loud_bed * 0.5


def test_bus_master_effects_and_volume():
    from lfms.mixer import create_effect

    limiter = create_effect("COMPRESSOR", SR, threshold_db=-40.0, ratio=10.0)
    bus = MixBus(SR, master_volume_db=-12.0, master_effects=[limiter])
    bus.add_stem("hot", _tone(500.0, 0.5, amp=0.95))
    out = bus.render()
    assert float(np.max(np.abs(out))) < 0.5


def test_bus_rejects_sample_rate_mismatch():
    class FakeSource:
        sample_rate = 44100

    bus = MixBus(SR)
    with pytest.raises(ValidationError):
        bus.add_channel("x", FakeSource())


def test_bus_render_is_deterministic():
    bus_a = MixBus(
        SR,
        ducking=DuckingSettings(),
    )
    for bus in (bus_a,):
        bus.add_stem("m", _tone(350.0, 1.0), volume_db=-4.0)
        vo = np.zeros((2, SR), dtype=np.float32)
        vo[:, : SR // 2] = _vo_burst(0.5)
        bus.add_stem("v", vo, kind="VOICEOVER")
    first = bus_a.render().copy()
    bus_a._ducker.reset()
    second = bus_a.render()
    assert np.array_equal(first, second)


class _ArraySourceStub:
    def __init__(self, data: np.ndarray, sample_rate: int) -> None:
        self.data = data.astype(np.float32)
        self.sample_rate = sample_rate
        self.frames = data.shape[1]
        self._pos = 0

    def process(self, n_frames: int) -> np.ndarray:
        stop = min(self._pos + n_frames, self.frames)
        block = self.data[:, self._pos : stop]
        pad = n_frames - block.shape[1]
        self._pos = stop
        if pad > 0:
            block = np.pad(block, ((0, 0), (0, pad)))
        return block


def test_bus_accepts_streaming_sources_with_chain():
    chain = EffectChain.from_preset("PODCAST_VOICE", SR)
    stub = _ArraySourceStub(_tone(220.0, 1.0, amp=0.8), SR)
    bus = MixBus(SR, total_frames=SR)
    bus.add_channel("voice", stub, kind="MUSIC", chain=chain)
    mixed = bus.render()
    assert mixed.shape == (2, SR)
    assert float(np.max(np.abs(mixed))) > 0.05
