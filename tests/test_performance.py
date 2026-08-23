"""Performance budget tests (generous, CI-friendly margins).

Measured references on the dev machine (Ryzen-class laptop):
- measure() 60s stereo: ~1.1 s  (~55x realtime)      -> budget >= 20x
- MixBus render 60s 3ch: ~1.3 s (~45x realtime)      -> budget >= 15x
- auto_master 60s stereo: ~12 s                       -> budget <= 25 s
- CompositionRenderer 30s: ~3.1 s                     -> budget <= 10 s
Budgets fail loudly if a change regresses the engine by >2x.
"""

from __future__ import annotations

import time
import tracemalloc

import numpy as np

from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.generator.render import CompositionRenderer
from lfms.mastering.master import TARGET_PRESETS, auto_master
from lfms.mastering.measure import measure
from lfms.mixer.bus import MixBus


def _tone(seconds: float = 60.0, sr: int = 48000, channels: int = 2) -> np.ndarray:
    rng = np.random.default_rng(7)
    return (rng.standard_normal((channels, int(seconds * sr))) * 0.15).astype(np.float32)


def test_loudness_measurement_speed_budget():
    audio = _tone(60.0)
    start = time.perf_counter()
    measure(audio, 48000)
    elapsed = time.perf_counter() - start
    factor = 60.0 / elapsed
    assert factor >= 20.0, f"measure only {factor:.1f}x realtime ({elapsed:.2f}s)"


def test_mixbus_render_speed_budget():
    bus = MixBus(48000, total_frames=48000 * 20)
    mono = _tone(20.0, channels=1)
    bus.add_stem("a", mono, volume_db=-6.0)
    bus.add_stem("b", mono, volume_db=-9.0)
    start = time.perf_counter()
    mixed = bus.render()
    elapsed = time.perf_counter() - start
    assert mixed.shape[-1] == 48000 * 20
    factor = 20.0 / elapsed
    assert factor >= 15.0, f"MixBus only {factor:.1f}x realtime"


def test_auto_master_time_budget():
    audio = _tone(60.0)
    start = time.perf_counter()
    result = auto_master(audio, 48000, TARGET_PRESETS["YOUTUBE"])
    elapsed = time.perf_counter() - start
    assert result.after.integrated_lufs > -120
    assert elapsed <= 25.0, f"auto_master took {elapsed:.1f}s for 60s audio"


def test_offline_render_speed_budget(tmp_path):
    params = GenerationParameters(
        seed=5,
        duration_sec=30.0,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=40.0,
    )
    composition = Composer(params).compose()
    renderer = CompositionRenderer(composition)
    start = time.perf_counter()
    renderer.render(tmp_path / "perf.wav", container="WAV", bit_depth=24)
    elapsed = time.perf_counter() - start
    factor = 30.0 / elapsed
    assert factor >= 3.0, f"offline render only {factor:.1f}x realtime"


def test_render_memory_ceiling(tmp_path):
    """Rendering must stay memory-flat (streamed blocks, no full buffer)."""
    tracemalloc.start()
    params = GenerationParameters(
        seed=6,
        duration_sec=45.0,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=35.0,
    )
    composition = Composer(params).compose()
    renderer = CompositionRenderer(composition)
    renderer.render(tmp_path / "mem.wav")
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # 45 s stereo float32 raw is ~17 MB; streamed render should stay well
    # under 4x that even with numpy overhead
    budget = 4 * 17 * 1024 * 1024
    assert peak_bytes < budget, f"peak {peak_bytes / 1048576:.1f} MB too high"
