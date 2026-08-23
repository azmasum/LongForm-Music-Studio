# Timeline Editor

Status: Phase 5 model + commands implemented and tested (197 tests passing
overall; GUI smoke offscreen-gated).

## Document model (`lfms.timeline.model`)

Pure-Python, JSON-serializable, no Qt — usable from CLI and render paths.

| Class | Purpose | Key invariants |
| --- | --- | --- |
| `TrackState` | One timeline lane | name/kind ∈ {MUSIC, AMBIENCE, VOICEOVER, REFERENCE}, volume_db ∈ [-60, 12], pan ∈ [-1, 1] |
| `Clip` | Placed audio region on a track | start ≥ 0, duration > 0, source_kind ∈ {GENERATED, AUDIO_FILE}; `end_sec` property |
| `AutomationLane` / `AutomationPoint` | Per-track `volume`/`pan` automation | points sorted by time, values ∈ [0, 1], one point per time |
| `Marker` | Time position label | kind ∈ {SECTION, CUE, CHAPTER}, time ≥ 0 |
| `TimelineDocument` | Root container | owns tracks/clips/lanes/markers; markers kept time-sorted |

Operations raise `lfms.core.errors.ValidationError` on any invariant breach,
including duplicate track/clip IDs. `remove_track` cascades: returns the
track plus its clips and lanes so undo can restore everything.

IDs come from `lfms.core.ids.new_id` (e.g. `TRK-…`, `CLP-…`, `MRK-…`).
`to_dict()` / `from_dict()` round-trip exactly (dict equality).

## Undo/redo (`lfms.timeline.commands`)

Command pattern; every edit is a reversible object:

- Track/clip/marker CRUD: `AddTrackCommand`, `RemoveTrackCommand`
  (snapshot-based cascade restore), `AddClipCommand`, `RemoveClipCommand`,
  `AddMarkerCommand`, `RemoveMarkerCommand`.
- Edits capture old values: `MoveClipCommand`, `ResizeClipCommand`,
  `SetTrackPropertyCommand` (whitelisted fields only),
  `SetAutomationPointCommand` (replaces or restores a point at the same
  timestamp).
- `MacroCommand`: runs children atomically — if one fails mid-way, already
  applied children are rolled back before the error propagates.
- `CommandStack(limit=200)`: `execute` clears redo; trims oldest beyond the
  limit; exposes `can_undo/can_redo` and next-command names for menus.
- Helpers `documents_equal(a, b)` compare via `to_dict()` snapshots.

## GUI shell (`lfms.app`, requires `pip install .[gui]`)

Launch: `python -m lfms.app`

- Dark Tokyo-night-inspired QSS theme (`app/theme.py`).
- Sidebar navigation: Library / Generate / Timeline / Mix / Export
  (Library/Mix/Export are labeled placeholders for Phases 8/6/9).
- **Generate page** is functional end-to-end at the composition level:
  seed/genre/mood/duration/intensity → `GenerationParameters` → `Composer()`
  → clip added to the first MUSIC track through `AddClipCommand`
  (undoable via Ctrl+Z / Ctrl+Shift+Z); status bar shows fingerprint, BPM,
  key and repetition score.
- **Timeline canvas** paints ruler ticks, per-track lanes, clips
  (accent = GENERATED, green = AUDIO_FILE) and dashed marker lines.
- Transport bar (Play/Pause/Stop + position display) — wiring to realtime
  playback arrives with Phase 6/7 work.

### Headless testing

GUI tests are skipped unless explicitly enabled:

```bat
set LFMS_GUI_SMOKE=1
python -m pytest tests/test_gui_smoke.py
```

The fixture forces `QT_QPA_PLATFORM=offscreen`, builds the real
`MainWindow`, generates a 45 s composition through the UI path and verifies
undo restores the document exactly.

## Known scope notes

- Waveform view with mipmaps deferred to Phase 7 QC work; canvas currently
  draws clip/marker geometry only.
- Clip drag/drop interactions arrive with Phase 8 library UI; today edits go
  through the command API (and the Generate page).
