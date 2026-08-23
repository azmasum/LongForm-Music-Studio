# Changelog

All notable changes are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: semver.

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
