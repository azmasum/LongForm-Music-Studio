"""Offline chunked renderer writing WAV/FLAC/OGG incrementally to disk."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.dsp import Limiter, peak
from lfms.audio_engine.formats import resolve_sf_params
from lfms.audio_engine.graph import AudioGraph
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.core.errors import RenderError


@dataclass
class RenderResult:
    path: Path
    frames: int = 0
    sample_rate: int = 48000
    channels: int = 2
    container: str = "WAV"
    bit_depth: int | None = 24
    peak: float = 0.0
    rms: float = 0.0
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    cancelled: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.cancelled


ProgressCallback = Callable[[float], None]


class OfflineRenderer:
    """Streams a graph block-by-block into an audio file; never loads the
    whole project into RAM, so multi-hour renders stay memory-flat."""

    def __init__(self, *, block_size: int = 1 << 15) -> None:
        self.block_size = int(block_size)

    def render(
        self,
        graph: AudioGraph,
        dest_path: Path | str,
        duration_sec: float,
        *,
        container: str = "WAV",
        bit_depth: int | None = 24,
        sample_rate: int | None = None,
        channels: int | None = None,
        on_progress: ProgressCallback | None = None,
        job_control: RenderJobControl | None = None,
        safety_limit: bool = True,
        fade_out_sec: float = 0.012,
    ) -> RenderResult:
        sr = int(sample_rate or graph.sample_rate)
        ch = int(channels or graph.channels)
        total_frames = max(1, int(round(duration_sec * sr)))
        fmt, subtype = resolve_sf_params(container, bit_depth)
        path = Path(dest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx = RenderContext(sample_rate=sr, channels=ch)
        limiter = Limiter(sr) if safety_limit else None
        fade_in = max(1, int(0.005 * sr))   # 5 ms de-click at file start
        fade_out = max(1, int(float(fade_out_sec) * sr))  # de-click at file end
        started = time.perf_counter()
        written = 0
        sum_squares = 0.0
        max_peak = 0.0
        cancelled = False

        try:
            with sf.SoundFile(str(path), mode="w", samplerate=sr, channels=ch, format=fmt, subtype=subtype) as handle:
                while written < total_frames:
                    if job_control is not None:
                        try:
                            alive = job_control.checkpoint()
                        except Exception as exc:  # pragma: no cover - defensive
                            raise RenderError("Render job control failed.", technical=str(exc)) from exc
                        if not alive:
                            cancelled = True
                            break
                    n = min(self.block_size, total_frames - written)
                    ctx.frames_done = written
                    block = graph.process(ctx, n)
                    if block.shape != (ch, n):
                        raise RenderError(
                            "Graph produced unexpected block shape.",
                            technical=f"expected {(ch, n)}, got {tuple(block.shape)}",
                        )
                    data = block.astype(np.float64)
                    if limiter is not None:
                        data = limiter.process(data)
                    # global de-click fades at the file boundaries
                    block_end = written + n
                    if written < fade_in:
                        idx = np.arange(written, min(block_end, fade_in))
                        ramp = (idx + 1) / fade_in
                        data[:, : len(idx)] *= ramp[None, :]
                    if block_end > total_frames - fade_out:
                        start = max(written, total_frames - fade_out)
                        idx = np.arange(start - written, n)
                        remaining = np.arange(0, block_end - start)
                        ramp = 1.0 - (remaining + 1) / fade_out
                        data[:, idx] *= np.maximum(ramp, 0.0)[None, :]
                    chunk_peak = peak(data)
                    max_peak = max(max_peak, chunk_peak)
                    sum_squares += float(np.sum(np.square(data)))
                    handle.write(np.ascontiguousarray(data.T).astype(np.float32))
                    written += n
                    ctx.advance(n)
                    if on_progress is not None:
                        on_progress(min(1.0, written / total_frames))
        except sf.LibsndfileError as exc:
            raise RenderError(
                f"Could not write audio file: {path.name}",
                technical=str(exc),
                suggestion="Check free disk space and that the output folder is writable.",
            ) from exc

        if cancelled:
            try:
                path.unlink()
            except OSError:
                pass
            return RenderResult(
                path=path, sample_rate=sr, channels=ch, container=fmt,
                bit_depth=bit_depth, elapsed_sec=time.perf_counter() - started,
                cancelled=True,
            )

        frames_total = written
        result = RenderResult(
            path=path,
            frames=frames_total,
            sample_rate=sr,
            channels=ch,
            container=fmt,
            bit_depth=bit_depth,
            peak=max_peak,
            rms=float(np.sqrt(sum_squares / max(frames_total * ch, 1))),
            duration_sec=frames_total / sr,
            elapsed_sec=time.perf_counter() - started,
        )
        if max_peak >= 0.999:
            result.warnings.append("Output reached full scale; consider lowering master gain.")
        if result.rms < 1e-5:
            result.warnings.append("Output is (near) silent; check source levels.")
        return result
