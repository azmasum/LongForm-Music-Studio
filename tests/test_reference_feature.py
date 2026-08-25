"""Reference-inspired generation: analysis, merging, URL guards, GUI flow."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lfms.core.errors import ValidationError
from lfms.reference import (
    analyze_file,
    is_platform_link,
    merge_into_payload,
)


def _make_reference_wav(path: Path, *, bpm: float = 100.0) -> None:
    """Synthetic 'song': A-minor-ish triad + clicks at the target BPM."""
    sr = 22050
    beat = 60.0 / bpm
    duration = 8.0
    t = np.arange(int(sr * duration)) / sr
    audio = np.zeros_like(t)
    # sustained triad (A3 C4 E4) -> strong A-minor chroma
    for midi, amp in ((57, 0.30), (60, 0.22), (64, 0.20)):
        f = 440.0 * 2 ** ((midi - 69) / 12)
        audio += amp * np.sin(2 * np.pi * f * t)
    # percussive clicks on each beat -> tempo fingerprint
    click_len = int(0.03 * sr)
    rng = np.random.default_rng(0)
    pos = 0.0
    while pos < duration - 0.1:
        start = int(pos * sr)
        burst = rng.uniform(-1, 1, click_len) * np.exp(
            -np.arange(click_len) / (0.004 * sr)
        )
        end = min(start + click_len, audio.size)
        audio[start:end] += 0.9 * burst[: end - start]
        pos += beat
    peak = float(np.max(np.abs(audio)))
    sf.write(str(path), (audio / peak * 0.5).astype(np.float32), sr)


def test_analyze_file_extracts_tempo_key_and_levels(tmp_path) -> None:
    wav = tmp_path / "ref.wav"
    _make_reference_wav(wav, bpm=100.0)
    analysis = analyze_file(wav)
    assert analysis.bpm == pytest.approx(100, abs=8)
    assert analysis.key_root == "A"
    assert analysis.key_mode in ("MINOR", "PHRYGIAN", "DORIAN")
    assert 0 < analysis.intensity <= 100
    assert len(analysis.rms_points) >= 2
    assert all(0.0 <= level <= 1.0 for _, level in analysis.rms_points)
    assert "BPM" in analysis.summary()


def test_merge_overrides_style_keeps_user_choices() -> None:
    from lfms.reference import ReferenceAnalysis

    analysis = ReferenceAnalysis(
        source="x.wav", source_hash="abc123", duration_sec=120.0,
        bpm=92, key_root="F", key_mode="MINOR", brightness_hz=2200.0,
        intensity=61.5, pulse_level=0.4,
        rms_points=((0.0, 0.2), (0.5, 0.9), (1.0, 0.4)),
    )
    payload = {"seed": 7, "genre": "LOFI", "duration_sec": 600.0,
               "moods": ("CALM",), "intensity": 50.0}
    merged = merge_into_payload(payload, analysis)
    assert merged["bpm"] == 92
    assert merged["key_root"] == "F"
    assert merged["key_mode"] == "MINOR"
    assert merged["intensity"] == 61.5
    assert merged["energy_points"] == ((0.0, 0.2), (0.5, 0.9), (1.0, 0.4))
    # user-controlled fields untouched
    assert merged["seed"] == 7
    assert merged["genre"] == "LOFI"
    assert merged["duration_sec"] == 600.0


def test_merged_payload_survives_params_from_payload() -> None:
    from lfms.generator.plan import params_from_payload
    from lfms.reference import ReferenceAnalysis

    analysis = ReferenceAnalysis(
        source="x.wav", source_hash="abc", duration_sec=60.0,
        bpm=84, key_root="D", key_mode="DORIAN", brightness_hz=1800.0,
        intensity=55.0, pulse_level=0.3,
        rms_points=((0.0, 0.1), (1.0, 0.8)),
    )
    merged = merge_into_payload({"seed": 2, "duration_sec": 300.0,
                                 "genre": "AMBIENT", "moods": ("NEUTRAL",)}, analysis)
    params = params_from_payload(merged)   # must ignore _reference/_pulse_hint
    assert params.bpm == 84
    assert params.key_root == "D"
    assert params.key_mode == "DORIAN"
    params.validate()


def test_platform_links_are_refused() -> None:
    assert is_platform_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_platform_link("https://open.spotify.com/track/xyz")
    assert not is_platform_link("https://example.com/songs/podcast-ep12.mp3")
    with pytest.raises(ValidationError):
        from lfms.reference import download_audio

        download_audio("https://www.youtube.com/watch?v=x")


def test_download_rejects_non_audio_suffix(tmp_path) -> None:
    from lfms.reference import download_audio

    with pytest.raises(ValidationError):
        download_audio("https://example.com/page.html")


def test_direct_audio_url_downloads_and_analyzes(tmp_path, monkeypatch) -> None:
    import lfms.reference.analyzer as analyzer_mod

    wav = tmp_path / "real.wav"
    _make_reference_wav(wav, bpm=100.0)

    class FakeResponse:
        def __init__(self, data: bytes):
            self.headers = {"Content-Length": str(len(data))}
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n=-1):
            return self._data if n == -1 else self._data[:n]

    monkeypatch.setattr(
        analyzer_mod.urllib.request, "urlopen",
        lambda url, timeout=30: FakeResponse(wav.read_bytes()),
    )
    path = analyzer_mod.download_audio("https://cdn.example.com/mix/loop.wav")
    try:
        analysis = analyze_file(path)
        assert analysis.bpm == pytest.approx(100, abs=8)
        assert analysis.key_root == "A"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.skipif(
    os.environ.get("LFMS_GUI_SMOKE") != "1",
    reason="GUI tests need LFMS_GUI_SMOKE=1",
)
def test_gui_generate_uses_reference(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])  # ensure an app exists
    from lfms.app.main_window import MainWindow

    window = MainWindow(db_path=tmp_path / "ref-lib.db")
    wav = tmp_path / "gui-ref.wav"
    _make_reference_wav(wav, bpm=96.0)

    from lfms.reference import analyze_file as _af

    info = _af(wav)
    window.generate_page.set_reference(wav, info.summary())
    out_dir = tmp_path / "ref-out"
    out_dir.mkdir()
    window.generate_page.set_output_dir(out_dir)

    payload = {
        "seed": 31337, "genre": "AMBIENT", "moods": ("NEUTRAL",),
        "duration_sec": 4.0, "intensity": 50.0,
    }
    merged = window._apply_reference(dict(payload))
    assert merged["bpm"] == pytest.approx(info.bpm, abs=1)
    assert merged["key_root"] == info.key_root

    clip = window.generate_from_payload(merged)
    assert clip is not None
    # library item carries the reference provenance tag
    item = window.library.list_items()[0]
    tags = getattr(item, "tags", ())
    assert any(str(t).startswith("ref:") for t in tags)
    window.library.close()
