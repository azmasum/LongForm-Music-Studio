"""Batch generation & render queue: N tracks, unique seeds, worker thread.

The queue owns one daemon worker. Jobs run sequentially through the full
export pipeline (render -> master -> QC -> archive). Pause/resume/cancel
are cooperative via :class:`lfms.audio_engine.jobcontrol.RenderJobControl`
semantics; the GUI polls :meth:`RenderQueue.snapshot` so no Qt objects
are touched from the worker thread.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from lfms.core.errors import RenderCancelled
from lfms.exporter.service import export_parameters
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService

_MAX_SEED = 2_147_483_647


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def make_batch(
    base_params: GenerationParameters,
    count: int,
    *,
    distinct_seeds: bool = True,
    rng: random.Random | None = None,
) -> list[GenerationParameters]:
    """Clone ``base_params`` into ``count`` jobs with unique seeds."""
    if count < 1:
        raise ValueError("count must be >= 1")
    rng = rng or random.Random()
    params_list: list[GenerationParameters] = []
    used: set[int] = {int(base_params.seed)} if distinct_seeds else set()
    for _ in range(count):
        data = asdict(base_params)
        seed = int(base_params.seed)
        if distinct_seeds:
            while seed in used:
                seed = rng.randrange(1, _MAX_SEED)
            used.add(seed)
        data["seed"] = seed
        params_list.append(GenerationParameters(**data))
    return params_list


@dataclass
class BatchJob:
    job_id: int
    title: str
    params: GenerationParameters
    output_dir: Path
    preset: str = "YOUTUBE"
    container: str = "WAV"
    bit_depth: int = 24
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    error: str = ""
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    final_path: str = ""
    started_at: float | None = None

    @property
    def realtime_factor(self) -> float | None:
        if self.elapsed_sec > 0 and self.duration_sec > 0:
            return self.duration_sec / self.elapsed_sec
        return None

    def to_row(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "status": self.status.value,
            "progress": round(self.progress * 100),
            "error": self.error,
            "elapsed_sec": round(self.elapsed_sec, 1),
            "realtime_factor": self.realtime_factor,
            "final_path": self.final_path,
            "duration_sec": round(self.duration_sec, 1),
        }


@dataclass
class _PerfHistory:
    """Rolling performance stats over finished jobs."""

    samples: list[tuple[float, float]] = field(default_factory=list)

    def add(self, elapsed_sec: float, audio_sec: float) -> None:
        self.samples.append((elapsed_sec, audio_sec))
        if len(self.samples) > 32:
            self.samples.pop(0)

    def summary(self) -> str:
        if not self.samples:
            return "no completed jobs yet"
        factors = [audio / max(elapsed, 1e-6) for elapsed, audio in self.samples]
        last_elapsed, last_audio = self.samples[-1]
        avg = sum(factors) / len(factors)
        return (
            f"done {len(self.samples)} | last {last_audio:.0f}s audio in "
            f"{last_elapsed:.1f}s ({last_audio / max(last_elapsed, 1e-6):.1f}x "
            f"realtime) | avg {avg:.1f}x"
        )


class RenderQueue:
    """Sequential background render queue with pause/cancel/retry/reorder."""

    def __init__(self, service: LibraryService) -> None:
        self._service = service
        self._jobs: list[BatchJob] = []
        self._next_id = 1
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._current_control: object | None = None
        self._worker: threading.Thread | None = None
        self.perf = _PerfHistory()

    # ------------------------------------------------------------ enqueue

    def add(
        self,
        params: GenerationParameters,
        output_dir: str | Path,
        *,
        title: str | None = None,
        preset: str = "YOUTUBE",
        container: str = "WAV",
        bit_depth: int = 24,
    ) -> int:
        params.validate()
        out_dir = Path(output_dir)
        with self._lock:
            job = BatchJob(
                job_id=self._next_id,
                title=title or f"Track {params.seed}",
                params=params,
                output_dir=out_dir,
                preset=preset,
                container=container,
                bit_depth=bit_depth,
                duration_sec=float(params.duration_sec),
            )
            self._jobs.append(job)
            job_id = self._next_id
            self._next_id += 1
            self._wake.notify_all()
        self.start()
        return job_id

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs if j.status is JobStatus.PENDING)

    def wait_until_idle(self, timeout: float = 300.0) -> bool:
        """Block until nothing is PENDING/RUNNING (test convenience)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                busy = any(
                    j.status in (JobStatus.PENDING, JobStatus.RUNNING)
                    for j in self._jobs
                )
            if not busy and not self.paused:
                return True
            time.sleep(0.05)
        return False

    # ------------------------------------------------------------- control

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                self._wake.notify_all()
                return
            self._stopped.clear()
            self._worker = threading.Thread(
                target=self._run_loop, name="lfms-render-queue", daemon=True
            )
            self._worker.start()

    def stop(self, join_timeout: float = 5.0) -> None:
        with self._lock:
            self._stopped.set()
            self.resume()
            self._wake.notify_all()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=join_timeout)

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def pause(self) -> None:
        self._paused.set()
        control = self._current_control
        if control is not None:
            control.pause()

    def resume(self) -> None:
        self._paused.clear()
        control = self._current_control
        if control is not None:
            control.resume()

    def cancel(self, job_id: int) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None:
                return False
            if job.status is JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                job.error = "cancelled before start"
                return True
        control = self._current_control
        if control is not None and job.status is JobStatus.RUNNING:
            control.cancel()
        return True

    def retry(self, job_id: int) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None or job.status not in (
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                return False
            job.status = JobStatus.PENDING
            job.progress = 0.0
            job.error = ""
            job.started_at = None
            self._wake.notify_all()
            return True

    def remove(self, job_id: int) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None or job.status is JobStatus.RUNNING:
                return False
            self._jobs.remove(job)
            return True

    def reorder(self, job_id: int, delta: int) -> bool:
        """Move a PENDING job ``delta`` positions within the pending block."""
        with self._lock:
            job = self._find(job_id)
            if job is None or job.status is not JobStatus.PENDING:
                return False
            pending_indexes = [
                idx
                for idx, other in enumerate(self._jobs)
                if other.status is JobStatus.PENDING
            ]
            pending_ids = [self._jobs[i].job_id for i in pending_indexes]
            pos = pending_ids.index(job.job_id)
            new_pos = max(0, min(len(pending_ids) - 1, pos + delta))
            if new_pos != pos:
                pending_ids.pop(pos)
                pending_ids.insert(new_pos, job.job_id)
                by_id = {j.job_id: j for j in self._jobs}
                replacement = iter(pending_ids)
                for idx, other in enumerate(self._jobs):
                    if other.status is JobStatus.PENDING:
                        self._jobs[idx] = by_id[next(replacement)]
            return True

    def clear_finished(self) -> int:
        with self._lock:
            done_statuses = {
                JobStatus.DONE,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }
            keep = [j for j in self._jobs if j.status not in done_statuses]
            removed = len(self._jobs) - len(keep)
            self._jobs = keep
            return removed

    # -------------------------------------------------------------- access

    def _find(self, job_id: int) -> BatchJob | None:
        for job in self._jobs:
            if job.job_id == job_id:
                return job
        return None

    def get_job(self, job_id: int) -> BatchJob | None:
        with self._lock:
            job = self._find(job_id)
            return None if job is None else job

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [job.to_row() for job in self._jobs]

    def perf_summary(self) -> str:
        with self._lock:
            return self.perf.summary()

    # --------------------------------------------------------------- worker

    def _run_loop(self) -> None:
        while not self._stopped.is_set():
            with self._wake:
                while (
                    not self._stopped.is_set()
                    and (
                        self._paused.is_set()
                        or self.pending_count() == 0
                    )
                ):
                    self._wake.wait(timeout=0.2)
                if self._stopped.is_set():
                    return
                job = next(
                    (j for j in self._jobs if j.status is JobStatus.PENDING),
                    None,
                )
            if job is None:
                continue
            self._execute(job)

    def _execute(self, job: BatchJob) -> None:
        from lfms.audio_engine.jobcontrol import RenderJobControl

        control = RenderJobControl(poll_interval=0.05)
        with self._lock:
            self._current_control = control
            job.status = JobStatus.RUNNING
            job.progress = 0.0
            job.error = ""
            job.started_at = time.time()
        start = time.perf_counter()
        try:
            outcome = export_parameters(
                self._service,
                job.params,
                job.output_dir,
                title=job.title,
                preset=job.preset,
                container=job.container,
                bit_depth=job.bit_depth,
                on_progress=lambda fraction: self._set_progress(job, fraction),
                should_cancel=lambda: control.cancelled,
            )
            elapsed = time.perf_counter() - start
            with self._lock:
                job.status = JobStatus.DONE
                job.progress = 1.0
                job.elapsed_sec = elapsed
                job.final_path = str(outcome.final_path)
                self.perf.add(elapsed, job.duration_sec)
        except RenderCancelled:
            with self._lock:
                job.status = JobStatus.CANCELLED
                job.error = "cancelled mid-render"
                job.elapsed_sec = time.perf_counter() - start
        except Exception as exc:  # noqa: BLE001 - queue must survive failures
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"[:200]
                job.elapsed_sec = time.perf_counter() - start
        finally:
            with self._lock:
                self._current_control = None

    def _set_progress(self, job: BatchJob, fraction: float) -> None:
        with self._lock:
            job.progress = max(0.0, min(1.0, float(fraction)))
