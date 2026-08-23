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

## Phase 2 — Audio engine core ✅
- [x] Block-based processing graph + `RenderContext`
- [x] `OfflineRenderer` writing WAV/FLAC/OGG incrementally via soundfile
      (exact frame counts, progress callbacks, pause/resume/cancel, safety
      soft-limit, QC stats)
- [x] Oscillators (sine/tri/saw/square, unison/detune, FM/AM/sub), ADSR,
      RBJ biquad filters (scipy lfilter), LFOs
- [x] Ambience generators (rain/wind/ocean/room tone/night/city) and drones
- [x] Track strips + mixer graph with mute/solo/master chain
- [x] Realtime `Player` on sounddevice with graceful device errors
- **Exit criteria met:** 30 s procedural fixture rendered in tests with exact
  frames/sample-rate/non-silence/bounded-peak assertions; byte-identical
  reproducibility for identical seeds; measured ~15x realtime render speed.

## Phase 3 — Basic generator ✅
- [x] Genre/mood/intensity → `MusicPlan` (30 genre profiles, mood modifiers)
- [x] Seeded harmony: diatonic progressions, voice-led pad voicings
- [x] Seeded melody: motif generation with variation transforms, chord-tone
      snapping on strong beats
- [x] Bass / sparkle bells / soft pulse layers; 7 instrument voices
- [x] Streaming event scheduler + Quick Generate producing real audio files
- **Exit criteria met:** reproducibility golden test — same seed renders
  byte-identical output; different seeds differ; 143 tests passing;
  ~8x realtime render speed.

## Phase 4 — Long-form arranger ✅
- [x] Section planner: bar-aligned spans, seeded middle cycles, INTRO/OUTRO,
      role gates per section type
- [x] Energy curves (9 presets + user points + seed-deterministic organic)
      driving density/melody/pulse/velocity
- [x] Per-section generation with own RNG namespaces, thinning and
      octave-shift variation
- [x] Repetition Score: foreground-focused, deviation-based windowed
      self-similarity (literal loop = 100; arranged 60-min ≈ 70–82)
- **Exit criteria met:** composed a 60-min track (45 sections, 18k events,
  score 70.5) and rendered it fully — exact frames at 7.4x realtime;
  173 tests passing.

## Phase 5 — Timeline editor model (+ GUI skeleton)
- [x] Timeline document model: tracks, clips, automation lanes, markers —
      validation + JSON roundtrip (`lfms.timeline.model`)
- [x] Undo/redo Command stack with macro batching and 200-step limit
      (`lfms.timeline.commands`)
- [x] PySide6 app shell: sidebar navigation, dark theme, transport bar,
      Generate page wired to the composer, timeline canvas drawing
      clips/markers (`python -m lfms.app`)
- **Exit criteria met:** 197 tests (194 pass; GUI smoke offscreen-gated via
  `LFMS_GUI_SMOKE=1`). Waveform view with mipmaps deferred to Phase 7 QC
  work — the canvas currently draws clip/marker geometry.

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
