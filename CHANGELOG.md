# Changelog

All notable changes are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: semver.

## [0.9.0] — 2026-08-23 (Phase 9)

### Added
- `lfms.provenance` package:
  - Provenance certificates: lineage record (app/generator versions,
    seed + full parameters, fingerprint, BPM/key/repetition, loudness +
    QC status, license note) with TXT and JSON export.
  - Fingerprint verification by recomposition (`verify_item` /
    `verify_parameters`) — deterministic proof that audio matches its
    certificate; honest failure reasons when data is missing.
- App: Export page replaced by the provenance center — generated-item
  browser, live lineage summary, verify action, certificate saving.

### Added
- `lfms.exporter` package: one-call export pipeline — recompose from
  stored parameters, offline render (~10x realtime), auto-master to
  preset, QC gates, WAV/FLAC delivery, library registration with tags,
  provenance certificate next to the delivered file.
- App: Export page gained the render & deliver section (preset picker,
  output folder, progress in status bar). The full MVP loop — generate →
  archive → verify → master → deliver — now works end to end.

### Known gap (flagged)
- Export runs synchronously on the GUI thread; moves off-thread with the
  Phase 11 render queue.

### Verified
- 279 tests passing incl. offscreen GUI smoke; ruff clean.

## [0.8.0] — 2026-08-23 (Phase 8)

### Added
- `lfms.library` package:
  - SQLite-backed sound library: items (path/title/kind/measurement/
    generation metadata/notes/favorite), normalized tags, named collections
    with cascade deletes.
  - Search & filters: case-insensitive query across title/path/fingerprint/
    tags, tag filter, favorites-only, collection filter, four sort orders.
  - Import analysis: soundfile format probe + BS.1770 loudness/true-peak
    measurement on import (files up to 15 min).
  - Smart tagging: genre/mood/BPM-bucket/voiceover-safe/energy tags for
    generated items; level/mono-stereo/length tags for imports.
- App pages:
  - Library page: live search, tag combo, favorites toggle, details pane,
    favorite/delete/collection actions.
  - Mix page (replaces placeholder): per-track volume/pan/mute/solo strips;
    edits are undoable `SetTrackPropertyCommand`s.
  - Generate now auto-registers compositions in the library.

### Verified
- 260 tests passing including offscreen GUI smoke; ruff clean.

## [0.7.0] — 2026-08-23 (Phase 7)

### Added
- `lfms.mastering` package:
  - BS.1770-4 measurement: K-weighted gated integrated loudness,
    momentary/short-term maxima, 4x-oversampled true peak, sample peak,
    RMS; parametric filter coefficients valid at any sample rate
    (verified against the published 48 kHz tables).
  - Auto-master presets: YOUTUBE (-14 LUFS / -1 dBTP), PODCAST, EBU_R128,
    BACKGROUND_BED; look-ahead true-peak limiter (oversampled gain curve,
    minimum-filter look-ahead + one-pole release).
  - `auto_master`: fresh-candidate secant search — stable on sparse peaky
    material, stops honestly at the physical loudness ceiling.
  - QC gates (`run_qc`): duration, true peak, loudness range, DC offset,
    clipping, silence fraction, stereo balance -> READY/WARNING report with
    serializable checks for Phase 9 certificates.

### Fixed
- Mastering convergence: iterative re-limiting of already-limited audio
  could diverge downward on burst-heavy material; candidates are now always
  built fresh from the source.

### Verified
- 240 tests passing (19 new mastering tests); ruff clean.

## [0.6.0] — 2026-08-23 (Phase 6)

### Added
- `lfms.mixer` package:
  - Channel strips: `ChannelState` (volume/pan/mute/solo/kind/fades) with
    validation; linear full-length fade curves.
  - Parametric effects: EQ3 (shelf/peaking/shelf biquads), compressor
    (linked envelope + smooth gain), stereo feedback delay, Schroeder
    reverb (4 combs + 2 allpasses, vectorized fixed-lag windows). All
    deterministic, validating, streamable (`params`/`set_param`/`reset`).
  - Effect chains with 6 curated presets and JSON roundtrip.
  - Voiceover sidechain ducking: 256-sample-hop envelope ducker; VO-kind
    channels drive it in the offline `MixBus` while bypassing it.
  - `MixBus`: streaming offline mixer — stems or live sources, solo/mute,
    fades, equal-power pan, chains, master volume/effects.

### Performance
- Reverb/delay recursions vectorized via fixed-lag window processing;
  60 s 3-channel mix with reverb + ducking renders at ~45x realtime.

### Verified
- 221 tests passing (24 new mixer tests); ruff clean.

## [0.5.0] — 2026-08-23 (Phase 5)

### Added
- `lfms.timeline` package:
  - Document model: `TrackState`, `Clip`, `AutomationLane`/`AutomationPoint`,
    `Marker`, `TimelineDocument` with validation, range queries and JSON
    roundtrip (`to_dict`/`from_dict`).
  - Undo/redo: Command pattern (`Add/Remove/Move/Resize/SetProperty`,
    marker + automation commands), atomic `MacroCommand`, bounded
    `CommandStack` (200 steps, redo cleared on new execute).
- `lfms.app` PySide6 shell (`python -m lfms.app`):
  - Dark QSS theme, sidebar navigation, transport bar, timeline canvas
    (clips/markers/ruler) and a working Generate page wired to the composer
    via the command stack.
- Optional GUI dependency: `pip install .[gui]` (PySide6).

### Verified
- 197 tests: model/command suites (21 new), offscreen GUI smoke gated by
  `LFMS_GUI_SMOKE=1`; ruff clean.

## [0.4.0] — 2026-08-23 (Phase 4)

### Added
- `lfms.arranger` package:
  - Energy curves: 9 presets, seed-deterministic RANDOM_ORGANIC, user
    `(time, value)` points; energy drives density/melody/pulse/velocity.
  - Section planner: bar-aligned spans with seeded middle cycles,
    INTRO/BREAKDOWN/OUTRO role gates.
  - Arranger: per-section generation (own RNG namespace per section),
    melody thinning, octave-shift variation, energy-scaled velocities.
  - Repetition Score: foreground-focused (melody-centric), deviation-based
    windowed self-similarity; calibrated literal=100 / varied≈0.
- `GenerationParameters.energy_curve` / `.energy_points` with validation.

### Verified
- 60-minute composition: 45 sections, 18,259 events, score 70.5, composed in
  ~2 s; full render exact frames at 7.4x realtime. 173 tests passing.

## [0.3.0] — 2026-08-23 (Phase 3)

### Added
- `lfms.generator` package:
  - `GenerationParameters` → `MusicPlan` builder: 30 genre profiles, mood
    modifiers, intensity scaling, seeded BPM/key selection, validation.
  - Music-theory core: modes, diatonic chord stacking (triads/7ths),
    voicing builder with rotation-based voice leading, progression pools.
  - Harmony generator (seeded progressions covering exact duration), melody
    generator (motifs + variation transforms + chord-tone snapping), bass,
    sparkle bells and soft pulse layers.
  - Seven instrument voices (pad/piano/pluck/bell/bass/kick/hat) streaming
    mono blocks; event scheduler keeps memory flat for hour-long pieces.
  - `Composer` + `CompositionRenderer`/`quick_generate`: parameters in,
    rendered audio file out; composition fingerprints (`LFMS-XXXX-XXXX-XXXX`).

### Verified
- Golden reproducibility: same seed ⇒ byte-identical file; different seeds
  differ. 143 tests passing overall; ~8x realtime for 5-layer mixes.

## [0.2.0] — 2026-08-23 (Phase 2)

### Added
- `lfms.audio_engine` package:
  - Vectorized oscillators (sine/tri/saw/square, unison/detune, FM/AM/sub)
    with block-continuing phase; ADSR envelopes with retrigger.
  - RBJ biquad filter family (scipy lfilter) with live parameter changes and
    DC blocker; sine/triangle/saw/random LFOs.
  - Procedural sources: white/pink/brown noise, six ambience textures
    (rain/wind/ocean/room tone/night/city), detuned drone bed.
  - Track strips + mixer graph (pan law, mute/solo, master chain, stereo width).
  - Offline chunked renderer: WAV (16/24/32f), FLAC (16/24), OGG; exact frame
    counts, incremental disk writes, progress callbacks, cooperative
    pause/resume/cancel, safety soft-limit above full scale, QC stats.
  - Realtime playback sink (sounddevice) with friendly device-error mapping.
- Dependencies: scipy, soundfile, sounddevice.

### Verified
- 112 tests passing (engine suite incl. 30 s fixture exit criteria,
  byte-identical seed reproducibility); ~15x realtime render speed measured.

## [0.1.0] — 2026-08-23 (Phase 1)

### Added
- Project architecture documents (`ARCHITECTURE.md`, `ROADMAP.md`).
- `lfms.core` foundation package:
  - Portable-mode path resolution (`portable.flag`, `LFMS_DATA_DIR`, APPDATA).
  - JSON settings with defaults, atomic writes, corrupt-file recovery.
  - Rotating-file logging and crash report writer with process/thread hooks.
  - Error hierarchy carrying user message, technical detail, suggestion.
  - Deterministic seed system + LFMS/AUD fingerprint identifiers.
  - SQLite schema v1 (projects, tracks, assets, library, presets, render
    jobs, provenance, versions, settings) with migration runner.
  - Repository data-access layer incl. safe search filters and dashboard stats.
  - Backup manager (timestamped, pruned) + autosave timer.
- Packaging (`pyproject.toml`), dev setup script, GitHub Actions CI,
  community/docs files.

### Notes
- Audio engine, generator and GUI arrive in Phases 2–5 per ROADMAP.md.
