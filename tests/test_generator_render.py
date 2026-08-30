"""End-to-end quick_generate tests, including golden byte reproducibility."""
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.generator import GenerationParameters, quick_generate


def _params(seed: int = 424242, **overrides):
    defaults = dict(
        seed=seed,
        duration_sec=6.0,
        genre="LOFI",
        moods=("CALM", "WARM"),
        intensity=55.0,
        sample_rate=32000,
    )
    defaults.update(overrides)
    return GenerationParameters(**defaults)


def test_quick_generate_wav_exit_criteria(tmp_path: Path):
    destination = tmp_path / "track.wav"
    composition, result = quick_generate(_params(), destination)
    assert result.ok
    assert result.frames == int(round(6.0 * 32000))
    assert result.sample_rate == 32000
    assert result.channels == 2
    data, sr = sf.read(destination, dtype="float32", always_2d=True)
    assert sr == 32000
    assert data.shape == (result.frames, 2)
    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(np.square(data))))
    assert 0.0 < peak <= 1.0
    assert rms > 1e-3


def test_same_seed_renders_identical_bytes(tmp_path: Path):
    first_path = tmp_path / "a.wav"
    second_path = tmp_path / "b.wav"
    quick_generate(_params(seed=777), first_path)
    quick_generate(_params(seed=777), second_path)
    assert first_path.read_bytes() == second_path.read_bytes()


def test_different_seed_renders_different_bytes(tmp_path: Path):
    first_path = tmp_path / "a.wav"
    second_path = tmp_path / "b.wav"
    quick_generate(_params(seed=1), first_path)
    quick_generate(_params(seed=2), second_path)
    assert first_path.read_bytes() != second_path.read_bytes()


def test_flac_container_roundtrip(tmp_path: Path):
    destination = tmp_path / "track.flac"
    _, result = quick_generate(_params(), destination, container="FLAC", bit_depth=16)
    assert result.ok
    data, sr = sf.read(destination, dtype="float32", always_2d=True)
    assert sr == 32000
    assert data.shape[0] == result.frames


def test_voiceover_safe_alters_mix(tmp_path: Path):
    normal = tmp_path / "normal.wav"
    safe = tmp_path / "safe.wav"
    params = _params(genre="PIANO", intensity=60.0)
    quick_generate(params, normal)
    safe_params = _params(genre="PIANO", intensity=60.0, voiceover_safe=True)
    quick_generate(safe_params, safe)
    assert normal.read_bytes() != safe.read_bytes()


def test_style_controls_change_render_output(tmp_path: Path):
    base = _params(genre="ELECTRONIC", intensity=60.0, duration_sec=8.0)
    baseline = tmp_path / "baseline.wav"
    bright = tmp_path / "bright.wav"
    dist = tmp_path / "dist.wav"
    quick_generate(base, baseline)
    quick_generate(
        _params(genre="ELECTRONIC", intensity=60.0, duration_sec=8.0,
                supersaw_brightness=100.0, bass_distortion=80.0,
                sidechain_amount=100.0, drop_intensity=100.0),
        bright,
    )
    quick_generate(
        _params(genre="ELECTRONIC", intensity=60.0, duration_sec=8.0,
                supersaw_brightness=0.0, bass_distortion=0.0,
                sidechain_amount=0.0, drop_intensity=0.0),
        dist,
    )
    # Confirm the controls actually influence the rendered audio.
    assert baseline.read_bytes() != bright.read_bytes()
    assert bright.read_bytes() != dist.read_bytes()
