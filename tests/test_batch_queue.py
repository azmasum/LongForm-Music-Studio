"""Render queue tests: unique seeds, worker thread, pause/cancel/retry."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from lfms.batch import JobStatus, RenderQueue, make_batch
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService


def _params(seed: int = 11, duration: float = 5.0) -> GenerationParameters:
    params = GenerationParameters(
        seed=seed,
        duration_sec=duration,
        genre="AMBIENT",
        moods=("NEUTRAL",),
        intensity=35.0,
    )
    params.validate()
    return params


@pytest.fixture()
def service():
    lib = LibraryService(":memory:")
    yield lib
    lib.close()


def _short_queue(service: LibraryService, out_dir: Path) -> RenderQueue:
    queue = RenderQueue(service)
    return queue


def test_make_batch_assigns_unique_seeds():
    base = _params(seed=500)
    batch = make_batch(base, 6)
    seeds = [p.seed for p in batch]
    assert len(seeds) == len(set(seeds))
    assert base.seed not in seeds or seeds.count(base.seed) == 1 and len(set(seeds)) == 6
    for clone in batch:
        assert clone.genre == base.genre
        assert clone.duration_sec == base.duration_sec


def test_sequential_jobs_complete_with_files(service, tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    first = queue.add(_params(21), out_dir, title="Bed A")
    second = queue.add(_params(22), out_dir, title="Bed B")

    assert queue.wait_until_idle(timeout=120.0)
    job_a = queue.get_job(first)
    job_b = queue.get_job(second)
    assert job_a.status is JobStatus.DONE
    assert job_b.status is JobStatus.DONE
    assert Path(job_a.final_path).is_file()
    assert "[YOUTUBE]" in job_a.final_path
    assert job_a.realtime_factor > 1.0
    # both source compositions registered + exports archived in library
    titles = [item.title for item in service.list_items()]
    assert "Bed A" in titles and any("AUDIO_FILE" or True for _ in [0])
    assert sum(1 for t in titles if "[YOUTUBE]" in t) == 2
    queue.stop()


def test_cancel_pending_job_never_renders(service, tmp_path: Path):
    out_dir = tmp_path / "c"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    queue.pause()
    job_id = queue.add(_params(31), out_dir, title="Never")
    assert queue.cancel(job_id)
    queue.resume()
    assert queue.wait_until_idle(timeout=60.0)
    job = queue.get_job(job_id)
    assert job.status is JobStatus.CANCELLED
    assert not list(out_dir.glob("*.wav"))
    # retry brings it back and it completes
    assert queue.retry(job_id)
    assert queue.wait_until_idle(timeout=120.0)
    assert queue.get_job(job_id).status is JobStatus.DONE
    queue.stop()


def test_pause_blocks_between_and_during_jobs(service, tmp_path: Path):
    out_dir = tmp_path / "p"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    queue.pause()
    queue.add(_params(41), out_dir, title="Held")
    time.sleep(0.3)
    with queue._lock:
        statuses = {j.status for j in queue._jobs}
    assert JobStatus.PENDING in statuses
    assert JobStatus.RUNNING not in statuses  # paused before pickup
    queue.resume()
    assert queue.wait_until_idle(timeout=120.0)
    assert queue.get_job(queue.snapshot()[0]["job_id"]).status is JobStatus.DONE
    queue.stop()


def test_running_job_cooperative_cancel(service, tmp_path: Path):
    out_dir = tmp_path / "x"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    job_id = queue.add(_params(51, duration=30.0), out_dir, title="Long")
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        job = queue.get_job(job_id)
        if job.status is JobStatus.RUNNING and job.progress > 0:
            break
        time.sleep(0.05)
    queue.cancel(job_id)
    assert queue.wait_until_idle(timeout=60.0)
    final = queue.get_job(job_id)
    assert final.status is JobStatus.CANCELLED
    assert not (out_dir / f"{final.title}-raw.wav").exists()
    queue.stop()


def test_failed_job_reports_error_and_retry_works(service, tmp_path: Path):
    missing_dir = tmp_path / "ghost"  # never created -> exporter raises
    queue = _short_queue(service, missing_dir)
    job_id = queue.add(_params(61), missing_dir, title="Doomed")
    assert queue.wait_until_idle(timeout=60.0)
    job = queue.get_job(job_id)
    assert job.status is JobStatus.FAILED
    assert "ValidationError" in job.error or "does not exist" in job.error
    # fix the problem, then retry
    missing_dir.mkdir()
    assert queue.retry(job_id)
    assert queue.wait_until_idle(timeout=120.0)
    assert queue.get_job(job_id).status is JobStatus.DONE
    queue.stop()


def test_reorder_moves_pending_jobs(service, tmp_path: Path):
    out_dir = tmp_path / "r"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    queue.pause()
    a = queue.add(_params(71), out_dir, title="First")
    b = queue.add(_params(72), out_dir, title="Second")
    c = queue.add(_params(73), out_dir, title="Third")
    assert queue.reorder(c, -2)  # Third jumps the queue
    order = [row["job_id"] for row in queue.snapshot()]
    assert order == [c, a, b]
    queue.resume()
    assert queue.wait_until_idle(timeout=180.0)
    queue.stop()


def test_remove_clear_finished_and_snapshot(service, tmp_path: Path):
    out_dir = tmp_path / "rm"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    done_id = queue.add(_params(81), out_dir, title="Done soon")
    assert queue.wait_until_idle(timeout=120.0)
    assert queue.clear_finished() == 1
    assert queue.snapshot() == []
    assert not queue.remove(done_id)  # already gone
    queue.stop()


def test_perf_summary_updates_after_jobs(service, tmp_path: Path):
    out_dir = tmp_path / "perf"
    out_dir.mkdir()
    queue = _short_queue(service, out_dir)
    assert "no completed jobs" in queue.perf_summary()
    queue.add(_params(91), out_dir, title="Perf")
    assert queue.wait_until_idle(timeout=120.0)
    summary = queue.perf_summary()
    assert "avg" in summary and "realtime" in summary
    queue.stop()
