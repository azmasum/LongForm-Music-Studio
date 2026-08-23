# Batch generation & render queue

Status: Phase 11 implemented and tested (312 tests passing overall).

## Package layout (`lfms.batch`)

| Module | Contents |
| --- | --- |
| `queue.py` | `RenderQueue`, `BatchJob`, `JobStatus`, `make_batch` |

## Queue model

- One daemon worker thread runs jobs **sequentially** through the full
  pipeline (`exporter.export_parameters`: compose → offline render →
  auto-master → QC → library archive → certificate).
- `make_batch(base_params, count)` clones parameters with **unique
  seeds** — no duplicate tracks from one enqueue.
- Job states: PENDING → RUNNING → DONE / FAILED / CANCELLED.
- Control: pause/resume (cooperative, blocks inside the renderer's
  chunk loop via `RenderJobControl.checkpoint()`), cancel pending
  instantly or running cooperatively mid-render, retry failed/cancelled,
  reorder within the pending block, remove, clear finished.
- Cancellation cleans up the raw temp file; a cancelled render never
  leaves half-written delivery files behind.

## Thread safety

The worker shares the `LibraryService` with the GUI: the service now
opens SQLite with `check_same_thread=False` and serializes every public
call through one reentrant lock. The GUI never touches Qt objects from
the worker — `BatchPage` polls `queue.snapshot()` on a 400 ms timer.

## Performance monitor

The queue keeps a rolling window of (elapsed, audio-duration) samples;
the Batch page shows the last job's realtime factor and the average
(e.g. "done 4 | last 120s audio in 24.1s (5.0x realtime) | avg 4.8x").

## Honest limitations

- Single exports on the Export page still run synchronously on the GUI
  thread; only the Batch queue is off-thread.
- No per-job CPU/RAM gauges (no psutil dependency); realtime factor is
  the honest performance signal.
- Jobs are not persisted across app restarts.
