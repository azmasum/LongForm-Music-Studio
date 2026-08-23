# Changelog

All notable changes are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: semver.

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
