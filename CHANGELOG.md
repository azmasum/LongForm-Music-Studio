# Changelog

All notable changes are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: semver.

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
