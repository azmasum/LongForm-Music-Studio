"""Audio-quality regression: limiter ceiling, no clicks, boundary fades."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from lfms.audio_engine.dsp import Limiter


def test_limiter_keeps_hot_signal_under_ceiling() -> None:
    limiter = Limiter(48000)
    t = np.arange(48000) / 48000
    hot = 2.5 * np.sin(2 * np.pi * 220 * t)
    blocks = [hot[i:i + 8192] for i in range(0, 48000, 8192)]
    out = np.concatenate([limiter.process(b[None, :]) for b in blocks], axis=1)
    assert float(np.max(np.abs(out))) <= 0.98
    # gain recovers toward unity after the overdrive stops
    for _ in range(20):
        limiter.process((0.2 * np.sin(2 * np.pi * 110 * t[:4096]))[None, :])
    assert limiter._gain > 0.5


def test_limiter_state_smooth_across_blocks() -> None:
    limiter = Limiter(32000, release_ms=40.0)
    rng = np.random.default_rng(3)
    prev_gain = None
    for _ in range(40):
        block = rng.uniform(-1.6, 1.6, (1, 2048))
        limiter.process(block)
        if prev_gain is not None:
            # smoothed gain must never jump wildly between blocks
            assert abs(limiter._gain - prev_gain) < 0.35
        prev_gain = limiter._gain
    assert limiter._gain > 0.05


def _render(params_kwargs: dict, tmp_path, name: str):
    from lfms.generator.composer import Composer
    from lfms.generator.plan import GenerationParameters
    from lfms.generator.render import CompositionRenderer

    params = GenerationParameters(moods=("NEUTRAL",), **params_kwargs)
    composition = Composer(params).compose()
    out = tmp_path / name
    result = CompositionRenderer(composition).render(out, container="WAV", bit_depth=16)
    return result, out


@pytest.mark.parametrize("genre,intensity,seed", [
    ("ELECTRONIC", 95.0, 4242),   # saw bass + snare + pulse: worst case
    ("CINEMATIC", 80.0, 77),
    ("AMBIENT", 30.0, 90210),
])
def test_rendered_peaks_stay_at_or_below_ceiling(genre, intensity, seed, tmp_path) -> None:
    result, path = _render(
        {"seed": seed, "genre": genre, "duration_sec": 5.0,
         "intensity": intensity}, tmp_path, f"{genre}-{seed}.wav",
    )
    data, _sr = sf.read(str(path), dtype="float64")
    assert float(np.max(np.abs(data))) <= 1.0
    assert result.peak <= 0.99


def test_no_boundary_clicks_and_end_fade(tmp_path) -> None:
    result, path = _render(
        {"seed": 555, "genre": "LOFI", "duration_sec": 4.0, "intensity": 70.0},
        tmp_path, "clicks.wav",
    )
    data, sr = sf.read(str(path), dtype="float64")
    assert abs(result.duration_sec - 4.0) < 0.2
    # start fade-in: first 5 ms must be well below the file's typical level
    head = np.abs(data[: int(0.004 * sr)])
    body = np.abs(data[int(0.5 * sr):int(0.6 * sr)])
    assert float(head.max()) < max(0.02, float(body.max()) * 0.5)
    # end fade-out: final 10 ms approaches silence
    tail = np.abs(data[-int(0.010 * sr):])
    assert float(tail.max()) < 0.15
