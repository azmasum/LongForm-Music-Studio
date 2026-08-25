"""Integration tests for the offline renderer and job control.

Includes the Phase 2 exit criteria: a 30-second procedural fixture with exact
duration, sample rate, non-silence and bounded peak assertions.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lfms.audio_engine.graph import AudioGraph
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.audio_engine.renderer import OfflineRenderer
from lfms.audio_engine.sources import AmbienceSource, DroneSource, ToneSource
from lfms.core.errors import RenderError

SR = 48000


def make_music_graph(sample_rate: int = SR) -> AudioGraph:
    graph = AudioGraph(sample_rate)
    graph.create_track("drone", DroneSource(sample_rate, frequency=110.0, seed=42), volume_db=-9.0)
    graph.create_track("rain", AmbienceSource(sample_rate, kind="RAIN", seed=7, level=0.14), volume_db=-12.0)
    return graph


class TestPhase2ExitCriteria:
    def test_render_30_second_fixture(self, tmp_path: Path) -> None:
        dest = tmp_path / "fixture_30s.wav"
        result = OfflineRenderer().render(make_music_graph(), dest, 30.0)
        assert result.ok
        info = sf.info(str(dest))
        assert info.frames == 30 * SR
        assert info.samplerate == SR
        assert info.channels == 2
        data, sr = sf.read(str(dest), dtype="float64")
        assert data.shape == (30 * SR, 2)
        assert float(np.max(np.abs(data))) < 1.0
        assert float(np.sqrt(np.mean(np.square(data)))) > 1e-3
        assert result.peak < 1.0
        assert result.duration_sec == pytest.approx(30.0)


class TestRenderBasics:
    def test_exact_frame_count_odd_duration(self, tmp_path: Path) -> None:
        duration = 1.234
        sr = 44100
        g = AudioGraph(sr)
        g.create_track("tone", ToneSource(sr, frequency=220.0))
        dest = tmp_path / "odd.wav"
        result = OfflineRenderer(block_size=1024).render(g, dest, duration)
        expected = int(round(duration * sr))
        assert result.frames == expected
        assert sf.info(str(dest)).frames == expected

    def test_mono_render(self, tmp_path: Path) -> None:
        g = AudioGraph(SR, channels=1)
        g.create_track("t", ToneSource(SR, frequency=200.0))
        dest = tmp_path / "mono.wav"
        result = OfflineRenderer().render(g, dest, 0.5)
        info = sf.info(str(dest))
        assert info.channels == 1
        assert result.channels == 1

    def test_flac_roundtrip(self, tmp_path: Path) -> None:
        dest = tmp_path / "clip.flac"
        result = OfflineRenderer().render(make_music_graph(), dest, 0.8, container="FLAC")
        assert result.ok
        info = sf.info(str(dest))
        assert info.format == "FLAC" and info.subtype == "PCM_24"

    def test_ogg_smoke(self, tmp_path: Path) -> None:
        dest = tmp_path / "clip.ogg"
        result = OfflineRenderer().render(make_music_graph(), dest, 0.5, container="OGG")
        assert result.ok and dest.exists()

    def test_progress_monotonic_and_complete(self, tmp_path: Path) -> None:
        seen: list[float] = []
        OfflineRenderer(block_size=4800).render(
            make_music_graph(),
            tmp_path / "p.wav",
            1.0,
            on_progress=seen.append,
        )
        assert seen[0] > 0.0
        assert all(b >= a for a, b in zip(seen, seen[1:], strict=False))
        assert seen[-1] == pytest.approx(1.0)

    def test_reproducibility_same_seed_identical_bytes(self, tmp_path: Path) -> None:
        one = tmp_path / "one.wav"
        two = tmp_path / "two.wav"
        OfflineRenderer().render(make_music_graph(), one, 0.7)
        OfflineRenderer().render(make_music_graph(), two, 0.7)
        assert one.read_bytes() == two.read_bytes()

    def test_safety_limit_bounds_output(self, tmp_path: Path) -> None:
        loud = AudioGraph(SR)
        loud.create_track("loud", ToneSource(SR, frequency=100.0), volume_db=+12.0)
        safe = tmp_path / "safe.wav"
        result = OfflineRenderer().render(loud, safe, 0.4)
        # the streaming limiter now keeps everything at/below its ceiling
        assert result.peak <= 0.98
        data, _ = sf.read(str(safe), dtype="float64")
        assert float(np.max(np.abs(data))) <= 1.0 + 1e-6

    def test_block_shape_mismatch_raises(self, tmp_path: Path) -> None:
        class BrokenGraph:
            sample_rate = SR
            channels = 2

            def process(self, ctx, n):  # noqa: ANN001
                return np.zeros((3, n), dtype=np.float32)

        with pytest.raises(RenderError):
            OfflineRenderer().render(BrokenGraph(), tmp_path / "broken.wav", 0.1)  # type: ignore[arg-type]


class TestJobControl:
    def test_cancel_removes_partial_file(self, tmp_path: Path) -> None:
        control = RenderJobControl()
        state = {"calls": 0}

        def progress(_frac: float) -> None:
            state["calls"] += 1
            if state["calls"] == 1:
                control.cancel()

        dest = tmp_path / "cancelled.wav"
        result = OfflineRenderer(block_size=24000).render(
            make_music_graph(), dest, 5.0, on_progress=progress, job_control=control
        )
        assert result.cancelled
        assert not dest.exists()

    def test_pause_resume_completes(self, tmp_path: Path) -> None:
        control = RenderJobControl()
        paused_once = threading.Event()

        def progress(frac: float) -> None:
            if frac >= 0.25 and not paused_once.is_set():
                paused_once.set()
                control.pause()

        timer = threading.Timer(0.4, control.resume)
        timer.start()
        try:
            started = time.perf_counter()
            result = OfflineRenderer(block_size=12000).render(
                make_music_graph(), tmp_path / "paused.wav", 2.0,
                on_progress=progress, job_control=control,
            )
            elapsed = time.perf_counter() - started
        finally:
            timer.cancel() if not paused_once.is_set() else None
        assert result.ok
        assert elapsed >= 0.35
        assert sf.info(str(tmp_path / "paused.wav")).frames == 2 * SR

    def test_checkpoint_blocks_while_paused(self) -> None:
        control = RenderJobControl(poll_interval=0.01)
        control.pause()
        done = threading.Event()
        outcome = {}

        def waiter() -> None:
            outcome["alive"] = control.checkpoint()
            done.set()

        thread = threading.Thread(target=waiter, daemon=True)
        thread.start()
        time.sleep(0.15)
        assert not done.is_set()
        control.resume()
        done.wait(timeout=1.0)
        assert outcome.get("alive") is True


class TestPlayerHelpers:
    def test_interleave_layout(self) -> None:
        from lfms.audio_engine.playback import _interleave

        block = np.array([[1, 2], [3, 4]], dtype=np.float32)
        assert _interleave(block).tolist() == [1.0, 3.0, 2.0, 4.0]
