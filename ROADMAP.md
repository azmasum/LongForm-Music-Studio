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
- [x] Channel strips: volume/pan/mute/solo, linear fades (`ChannelState`,
      `fade_gain_curve`)
- [x] Effect chain: EQ3 / compressor / delay / reverb with param validation,
      reset + serialization; 6 curated presets
      (`lfms.mixer.effects/chain/presets`)
- [x] Voiceover ducking/sidechain: hop-based envelope ducker wired into the
      offline `MixBus` (VO bus drives, music buses duck)
- **Exit criteria met:** deterministic mixes (byte-identical re-renders),
  solo/mute/fades/pan verified by tests; 60 s 3-channel mix with reverb +
  ducking at ~45x realtime; 221 tests passing. Mixer UI stays a placeholder
  until Phase 8 (documented in docs/MIXER.md).

## Phase 7 — Mastering & QC
- [x] Measurement: BS.1770-4 K-weighted integrated/momentary/short-term
      loudness, gated, any sample rate; oversampled true peak, RMS
      (`lfms.mastering.measure`)
- [x] Auto-master presets (YouTube/PODCAST/EBU_R128/BACKGROUND_BED) with
      look-ahead true-peak limiter and stable secant convergence
- [x] QC report before export: peak/loudness/DC/clipping/silence/balance
      gates -> READY/WARNING (`lfms.mastering.qc`)
- **Exit criteria met:** reference sine anchors match the standard's filter
  tables; limiter never exceeds ceiling; sparse material that physically
  cannot reach target stops honestly (documented); 240 tests passing.
  Export-page UI wiring deferred to Phase 8 (docs/MASTERING.md).

## Phase 8 — Library services + UI
- [x] SQLite-backed library: items, tags, favorites, collections with
      validation + cascade deletes (`lfms.library`)
- [x] Search/filter (query, tag, favorite, collection, sort), import
      analysis via soundfile + BS.1770 measurement, smart tags for both
      generated and imported material
- [x] App wiring: functional Library page; Generate auto-registers into the
      library; Mix page upgraded from placeholder to per-track strips
      (volume/pan/mute/solo as undoable commands)
- **Exit criteria met:** 260 tests passing incl. offscreen GUI smoke.
  Deferred honestly: library audio preview, import-from-disk dialog button,
  effect-chain/ducking UI (docs/LIBRARY.md).

## Phase 9 — Licensing/provenance center
- [x] Provenance certificates: full lineage record (versions, seed/params,
      fingerprint, composition facts, loudness/QC, license note) exportable
      as TXT + JSON (`lfms.provenance`)
- [x] Verification: recompose stored parameters and compare fingerprints
      (`verify_item`) — deterministic proof of lineage
- [x] Export page is now the provenance center: item browser, live lineage
      summary, verify button, TXT/JSON certificate saving
- **Exit criteria met:** 279 tests passing incl. offscreen GUI smoke.
  PDF optional → not implemented. Follow-up in the same phase closed the
  flagged gap: `lfms.exporter` now renders compositions offline,
  auto-masters them (preset), runs QC and archives results — the full
  generate → master → deliver loop works from the Export page.

## Phase 10 — AI Music Director (optional)
- [x] `lfms.director` package: prompt → structured parameters through
      provider adapters (deterministic offline interpreter + optional
      local Ollama LLM adapter)
- [x] Disabled by default; enabling requires an explicit consent
      checkbox that states where the prompt goes per provider
- [x] All provider output normalized/clamped (genre/mood whitelists,
      duration/intensity/bpm clamps, stable seed derivation) — hostile
      or malformed payloads can never produce invalid parameters
- [x] App fully functional offline; Generate page gained the director
      section (provider combo, prompt, "Suggest parameters")
- **Exit criteria met:** 302 tests passing incl. offscreen GUI smoke;
  the same prompt always yields the same suggestion (deterministic).

## Phase 11 — Batch generation & render queue
- [x] N-track batch with unique seeds (`make_batch`), full pipeline per
      track (render → master → QC → archive → certificate)
- [x] Queue UI: live table (status/progress/elapsed/realtime), reorder,
      pause/resume, cancel pending + cooperative cancel mid-render,
      retry failed, clear finished
- [x] Performance monitor: rolling realtime-factor stats in the Batch
      page; queue worker off the GUI thread; `LibraryService` made
      thread-safe for shared use
- **Exit criteria met:** 312 tests passing incl. offscreen GUI smoke;
  end-to-end batch (2 tracks) verified with delivered files on disk.

## Phase 12 — Installer & portable build
- [x] PyInstaller one-dir windowed build (`installer/lfms.spec`) with
      headless verification (`--version`, `LFMS_SELF_CHECK=1` exit codes)
- [x] scipy modulegraph crash worked around honestly: two modules
      excluded + runtime stubs; documented in docs/RELEASE.md
- [x] One-shot release script `installer/build_portable.ps1` (tests →
      ruff → build → frozen self-check → ZIP); verified end-to-end,
      ~85 MB portable ZIP produced
- [x] Inno Setup 6 script ready (`installer/setup.iss`); compilation
      requires ISCC.exe which is not installed here — stated as-is
- **Exit criteria met:** 315 tests passing incl. offscreen GUI smoke;
   release checklist in docs/RELEASE.md.

## Phase 13 — Testing hardening ✅
- [x] Integration coverage per spec §71: full MVP loop (params → compose →
      export/master/QC → library → certificate → verify), director prompt →
      delivered preset hit, 3-track batch with unique fingerprints,
      timeline edit (undo/redo) then export, tampered-parameters forgery
      drill, project round-trip, offscreen GUI full session
      (generate → verify → export → batch job)
- [x] Performance budgets with generous CI margins: loudness measure ≥20x
      realtime (measured ~55x), MixBus ≥15x (~45x), auto_master 60s ≤25s
      (~12s), offline render ≥3x realtime, tracemalloc memory ceiling for a
      streamed 45s render
- [x] Crash-recovery drills: corrupt/truncated audio rejected as clean
      ValidationError, damaged project JSON raises LFMSError, half-written
      project recovered from BackupManager rotation, uncommitted SQLite
      write rolled back after simulated crash, corrupt params_json verifies
      FAILED honestly instead of crashing, RenderQueue continues after a
      mid-batch failure + retry succeeds
- [x] Hardening fixes: `TimelineDocument.from_dict` raises ProjectFileError
      on non-dict/malformed payloads; `import_audio_file` wraps libsndfile
      decode failures into ValidationError with actionable messages
- **Exit criteria met:** integration coverage per spec §71, performance
   budgets, crash-recovery drills — 342 tests passing.

## Phase 14 — GitHub release v1.0.0 ✅
- [x] Docs finalized: README status header → v1.0.0 (all 14 phases),
      screenshots section, download & run section; docs index now lists
      BATCH/PROVENANCE/RELEASE guides
- [x] Real GUI screenshots of all six pages via new
      `scripts/make_screenshots.py` (headless Qt offscreen + grab());
      committed under `docs/screenshots/`
- [x] Release artifacts rebuilt at 1.0.0:
      `releases\LongFormMusicStudio-1.0.0-portable.zip` (~85 MB), built
      through the full gate (tests → ruff → PyInstaller → frozen
      self-check); frozen exe reports "LongForm Music Studio 1.0.0"
- [x] Changelog complete 0.x → [1.0.0]; per-release checklist and manual
      GitHub publish steps documented in docs/RELEASE.md
- **Exit criteria met:** docs finalized, screenshots, release artifacts,
   changelog. Note stated honestly: the actual GitHub publish (push, tag,
   release upload) needs a remote/push access not present on this machine —
   exact steps written in docs/RELEASE.md.

## Success criteria mapping (spec §99)
The MVP loop (create project → choose genre/mood/duration → generate → preview
→ edit → master → export WAV/MP3 → save/reopen) must work end-to-end before
Phase 5 GUI polish continues; success criteria 1–18 are tracked in the issue
tracker as the v1.0.0 acceptance checklist.
