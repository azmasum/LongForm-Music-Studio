# LFMS Development Roadmap

Methodology: build module-by-module; a phase is complete only when its
automated tests pass and the documented behavior actually works.

## Phase 1 — Project architecture ✅
- [x] Repository layout, packaging (`pyproject.toml`), dev tooling (pytest, ruff)
- [x] Portable-mode path resolution + data directories
- [x] Config system with safe defaults, atomic saves, corrupt-file recovery
- [x] Logging + rotating files + crash reports
- [x] Error hierarchy with user/technical/suggestion fields
- [x] Seed system + deterministic fingerprints
- [x] SQLite schema v1 + repository layer + migrations
- [x] Backup manager + autosave timer
- **Exit criteria:** full unit suite green. ✅

## Phase 2 — Audio engine core
- Block-based processing graph, RenderContext, OfflineRenderer writing WAV via
  soundfile, oscillator/filter/ADSR primitives, ambience noise generators,
  RealtimeSink on sounddevice.
- **Exit criteria:** render 30 s procedural fixture; duration/sample-rate/
  non-silence/peak tests pass; playback smoke test manual checklist.

## Phase 3 — Basic generator
- Genre/mood/intensity → parameter plan; harmony + motif generation from seed;
  Quick Generate produces a real audio file.
- Reproducibility golden test (same seed ⇒ identical output bytes).

## Phase 4 — Long-form arranger
- Section planner, energy curves (presets + user points), anti-repetition
  metric + Repetition Score, extend engine for imported clips, intro/outro.
- **Exit criteria:** generate 60-min track without obvious repetition;
  similarity meter within tested bounds.

## Phase 5 — Timeline editor model (+ GUI skeleton)
- Track/clips/automation data model, undo/redo command stack, markers/sections.
- PySide6 app shell: sidebar navigation, dark theme, transport bar, waveform
  view with mipmaps.

## Phase 6 — Mixer & effects
- Per-track volume/pan/mute/solo/fades, effect chain (EQ/compressor/reverb/
  delay/etc.) with presets, voiceover ducking/sidechain.

## Phase 7 — Mastering & QC
- LUFS/true-peak/RMS measurement, auto-master presets (YouTube etc.), QC
  report (READY/WARNING) before export.

## Phase 8 — Library services + UI
- Search/filter/tag/favorites/collections, import analysis, smart tagging.

## Phase 9 — Licensing/provenance center
- Certificate generation/export (TXT/JSON/PDF-optional), provenance browsing.

## Phase 10 — AI Music Director (optional)
- Prompt → structured parameters via provider adapters; disabled by default;
  explicit consent warnings; app fully functional offline.

## Phase 11 — Batch generation & render queue
- N-track batch with unique seeds, queue UI (reorder/pause/cancel/retry),
  performance monitor.

## Phase 12 — Installer & portable build
- PyInstaller portable ZIP + Inno Setup installer; release checklist.

## Phase 13 — Testing hardening
- Integration coverage per spec §71; performance budgets; crash-recovery drills.

## Phase 14 — GitHub release v1.0.0
- Docs finalized, screenshots, release artifacts, changelog.

## Success criteria mapping (spec §99)
The MVP loop (create project → choose genre/mood/duration → generate → preview
→ edit → master → export WAV/MP3 → save/reopen) must work end-to-end before
Phase 5 GUI polish continues; success criteria 1–18 are tracked in the issue
tracker as the v1.0.0 acceptance checklist.
