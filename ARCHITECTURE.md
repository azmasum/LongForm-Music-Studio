# LFMS Technical Architecture

LongForm Music Studio (LFMS) — professional long-form background music
production for Windows. This document is the Required First Deliverable
(sections A–M) from the product specification and will evolve with the code.

---

## A. System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                          GUI (PySide6)                             │
│  Dashboard · Generator · Timeline · Mixer · Mastering · Export     │
│  Library · Licensing Center · Settings        (MVVM + QThreads)    │
├────────────────────────────────────────────────────────────────────┤
│                       Application Services                         │
│  ProjectService · PresetService · RenderQueue · BatchService       │
├───────────────┬────────────────────┬───────────────────────────────┤
│  Generator     │  Arranger          │  AI Music Director (optional)  │
│  (procedural   │  (sections, energy │  provider adapters:            │
│   composition, │   curves, anti-    │  local / OpenAI-compat /       │
│   seeds)       │   repetition)      │  Gemini-compat (offline core)  │
├───────────────┴────────────────────┴───────────────────────────────┤
│                       Audio Engine                                  │
│  Synth voices · Ambience generators · Effect chains · Mixer graph   │
│  Realtime sink (sounddevice)  |  Offline chunked renderer           │
├────────────────────────────────────────────────────────────────────┤
│                    Mastering & Analysis                             │
│  Loudness (LUFS/TP/RMS) · Auto-master presets · QC checks           │
├────────────────────────────────────────────────────────────────────┤
│                Persistence & Infrastructure                         │
│  SQLite DB · .lfms project files · JSON presets/config              │
│  Portable-mode paths · Backups/autosave · Logging/crash reports     │
└────────────────────────────────────────────────────────────────────┘
```

Layer rules:

1. The **offline core** (generator → engine → renderer → export) never requires
   network access. The AI layer is an optional, pluggable adapter set.
2. GUI never touches audio buffers directly; it drives services via commands.
3. All long-audio processing is **chunked and streamed to/from disk**; a
   2-hour WAV is never fully resident in RAM.

## B. Technology Stack

| Concern | Choice | Rationale |
| --- | --- | --- |
| Language | Python 3.10+ | Maintainable by an independent developer; mature audio ecosystem |
| Numerics | NumPy (BSD-3) | Vectorized DSP; universal wheels |
| Audio I/O | soundfile/libsndfile (LGPL-2.1) for WAV/FLAC/OGG read-write; python-sounddevice/PortAudio (MIT) for realtime playback | Reliable, streaming-capable |
| MP3 encode | FFmpeg subprocess when present | libsndfile cannot write MP3; app degrades gracefully without it |
| GUI | PySide6 / Qt6 (LGPL-3.0) | Professional desktop widgets, dark theming, accessibility, i18n |
| Storage | SQLite (public domain) via stdlib `sqlite3` | Zero-config local database |
| Optional AI | HTTP adapters to OpenAI/Gemini-compatible APIs or local model servers | Prompt→parameters only; never uploads audio without consent |
| Packaging | PyInstaller (portable ZIP) + Inno Setup installer | Both distribution modes from the spec |

Rejected alternatives: Electron/web wrappers (heavy, not native), C++/JUCE
(slower independent development), pure CLI (spec demands pro GUI).

## C. Folder Structure

```
LongForm-Music-Studio/
├── lfms/                  # Python package
│   ├── core/              # config, paths, logging, errors, ids, seed,
│   │                      # db+schema.sql, models, repository, backup
│   ├── audio_engine/      # synthesis primitives, effect chain, mixer graph,
│   │                      # realtime sink, offline chunk renderer
│   ├── generator/         # composition planning, motifs/harmony, genres/moods
│   ├── arranger/          # sections, energy curves, anti-repetition metric
│   ├── timeline/          # timeline data model + operations (undo/redo)
│   ├── mixer/             # track strips, routing, automation evaluation
│   ├── mastering/         # loudness measurement, auto-master presets, QC
│   ├── renderer/          # render queue jobs, encoding, filename generator
│   ├── licensing/         # license classes, provenance records, certificates
│   ├── library/           # library services, tagging, import analysis
│   ├── metadata/          # metadata writing (WAV INFO/INFO tags etc.)
│   ├── presets/           # preset store over repository
│   ├── ai/                # Music Director prompt parsing + provider adapters
│   └── app/               # PySide6 GUI (views/viewmodels/workers/theme/i18n)
├── tests/                 # pytest unit + integration tests
├── docs/                  # user/developer guides, audio/licensing docs
├── scripts/               # dev_setup.ps1 and build scripts
├── installer/             # Inno Setup script, PyInstaller spec (Phase 12)
├── examples/              # example projects/presets
├── assets/                # icons, fonts (redistributable only)
├── logs/                  # dev-run logs (gitignored)
└── pyproject.toml         # packaging + tool config
```

The spec's flat top-level layout was adapted into the `lfms.*` package so the
library installs cleanly (`pip install -e .`) without polluting site-packages
with generic module names.

## D. Dependency List

| Package | License | Purpose | Phase |
| --- | --- | --- | --- |
| numpy ≥1.24 | BSD-3 | DSP math | 2 |
| soundfile ≥0.12 | BSD-3 (libsndfile LGPL-2.1) | WAV/FLAC/OGG stream I/O | 2 |
| sounddevice ≥0.4 | MIT (PortAudio MIT-like) | Playback device output | 2 |
| PySide6 ≥6.6 | LGPL-3.0 | Desktop GUI | 5+ |
| requests ≥2.31 | Apache-2.0 | Optional AI adapters | 10 |
| pytest ≥7.4 | MIT | Tests | now |
| ruff ≥0.4 | MIT | Lint/format | now |

FFmpeg (LGPL/GPL depending on build) is optional at runtime for MP3 export.
See THIRD_PARTY_LICENSES.md — third-party licenses are not covered by the
LFMS license.

## E. Database Schema

Implemented in `lfms/core/schema.sql` (migration v1):

| Table | Purpose |
| --- | --- |
| `projects` | One row per music project: duration/BPM/key/intensity/genre/moods/energy curve/voiceover-safe settings/seed/generator version/fingerprint/license |
| `tracks` | Timeline tracks per project (kind, gain/pan/mute/solo, effects+automation JSON, placement, fades); cascade-deleted with project |
| `assets` | Imported audio files with mandatory license classification, source/author/attribution/commercial-use fields, fingerprint |
| `library_tracks` | Generated/exported track catalog: file path, musical metadata, tags, favorite/collection/rating |
| `presets` | Generator/instrument/effect/mastering/video/project-template presets (JSON payload, builtin flag) |
| `render_jobs` | Render queue entries: target format/bit depth/status/progress/errors |
| `provenance_records` | License certificates (JSON) per subject (project/library track/asset) |
| `project_versions` | Version-history snapshots per project |
| `app_settings` | Key-value runtime state |
| `schema_migrations` | Applied schema versions |

## F. Audio Engine Architecture

- **Sample-format**: float32 internally; project sample rate configurable
  (44.1/48/96 kHz).
- **Processing model**: fixed block size (default 1024 frames). Every node
  implements `process(block: ndarray, ctx: RenderContext) -> ndarray`.
- **Graph**: `SourceNode → EffectChain[n] → TrackGain/Pan → Bus → MasterChain → Sink`.
- **Sinks**:
  - *RealtimeSink*: PortAudio callback pulls blocks from a lock-free queue;
    underruns are logged, never crash.
  - *OfflineRenderer*: pulls source generators block-by-block, writes frames
    incrementally via soundfile; supports pause/resume/cancel through job flags
    checked between blocks; progress = frames_done/total.
- **Synthesis** (Phase 2–3): oscillators (sine/tri/saw/square/noise/FM/AM/sub),
  ADSR, state-variable filter, LFO, unison/detune — all procedural, no samples.
- **Ambience** (procedural): filtered noise processes for rain/wind/ocean/room
  tone, pink/brown noise generators.
- **Effects** (Phase 6): biquad EQ family, compressor/limiter (envelope
  follower), reverb (Freeverb-style comb/allpass), delay, chorus, stereo
  widener, saturation, gate, fades/crossfades — each with preset dicts.
- **Memory strategy**: sources are either procedural (recomputed per block from
  seed) or disk-streamed imported audio opened with `sf.SoundFile`; cache holds
  small decoded windows only.

## G. Generator Architecture

Pipeline (all randomness flows from `SeedSystem.derive(namespace)`):

1. **Plan** — map genre/mood/intensity/duration → musical constraints
   (BPM range, key candidate, instrument palette, density targets).
2. **Harmony** — chord progression pool per mode; cadence points at section
   boundaries; voice-leading-aware voicing selection.
3. **Motif** — generate melodic cells (rhythm patterns + pitch contours);
   variation transforms (transpose/octave/duration mutation/ornament) applied
   per section with similarity budget.
4. **Arrangement** (Phase 4) — split total duration into section types
   (Intro, Theme A/Variation, Transition, Theme B, Breakdown, Development,
   Return, Outro) sized by energy-curve sampling; curve presets + user-drawn
   points drive per-section intensity → density/dynamics/brightness mapping.
5. **Event rendering** — note events → synth voices → per-track audio streams
   consumed by the offline renderer.
6. **Anti-repetition** — rolling feature vector (pitch-class histogram, onset
   density, spectral centroid proxy, rhythm entropy) compared between adjacent
   sections; if similarity > threshold, apply another transform pass. Exposed
   as the Repetition Score meter.
7. **Extend engine** (Phase 4+) — analyze an imported clip (tempo/grid, key,
   energy envelope), then re-compose compatible material around loop-safe
   boundaries instead of naive tiling.

Reproducibility: `(generator_version, seed, parameters)` must regenerate
identical plans; golden-file tests lock this contract.

## H. GUI Architecture

- **Framework**: PySide6; pattern: MVVM-lite (View ↔ ViewModel ↔ Service).
- **Navigation** (left sidebar): Home/Dashboard, Generate, Projects, Library,
  Composer, Timeline, Mixer, Mastering, Export, Settings.
- **Threading rule**: no audio/render work on the GUI thread. Generation and
  rendering run in worker threads (`QThread`/`concurrent.futures` bridges)
  reporting progress via queued signals.
- **Transport bar** (bottom): play/pause/stop, position, BPM, key, master
  volume, LUFS/peak readout.
- **Waveform view**: precomputed peak/RMS mipmaps per zoom level; renders only
  the visible window; energy curve overlaid.
- **Theme**: dark default, light/system options; QSS stylesheet tokens.
- **i18n**: all strings through a translation layer from day one; English +
  Bangla catalogs planned; Unicode-safe fonts.
- **Accessibility**: keyboard-first shortcuts (Space/Ctrl+S/Ctrl+Z/…),
  scalable font factor, tooltips, screen-reader-friendly labels.

## I. Rendering Pipeline

```
Export request → RenderJob(PENDING) → Queue (reorderable)
  → prepare (validate project, resolve assets, QC pre-checks)
  → render chunks offline (pause/resume/cancel checkpoints every N sec)
  → mastering stage (auto-master preset, limiter ceiling)
  → QC post-checks (clipping/TP/LUFS/silence/DC) → READY/WARNING report
  → encode (WAV/FLAC/OGG via libsndfile; MP3 via ffmpeg if available)
  → register in library + provenance record → DONE
```

- Multi-threaded: independent jobs in parallel up to configured thread count;
  a single job streams sequentially (deterministic).
- Filenames auto-generated from template
  (`Genre_Mood_Duration_SampleRate_XX.wav` style), collision-safe suffixes.
- Long projects write incrementally; crash leaves a `.partial` file that is
  cleaned up on next launch.

## J. Licensing / Provenance Architecture

- `LicenseClass` enum: ORIGINAL, CC0, PUBLIC_DOMAIN, USER_OWNED,
  COMMERCIAL_LICENSE, UNKNOWN, RESTRICTED. UNKNOWN/RESTRICTED always warn.
- Every generated item stores: project id, generator version, seed, parameter
  hash, fingerprint (`LFMS-XXXX-XXXX-XXXX`), creation timestamp, source asset
  references, user modifications log (version history).
- Certificate export (TXT/JSON first; PDF via optional dependency later) lists
  the facts above plus an explicit statement that the certificate documents
  provenance **and does not constitute a legal copyright registration**; for
  imported material it repeats the user-provided license claims verbatim.
- Import flow refuses silent defaults: license field must be chosen explicitly.

## K. Development Roadmap

See [ROADMAP.md](ROADMAP.md). Phases 1–14 mirror the spec's methodology;
each phase exits only with passing automated tests.

## L. Testing Strategy

- **Unit tests** per module (current suite covers paths/portability, config,
  seeds/fingerprints determinism, DB/repository integrity incl. cascade rules
  and filter safety, backups, logging/crash reports).
- **Generator tests** (from Phase 3): same seed+params ⇒ byte-identical plan;
  anti-repetition score bounds; duration math exactness.
- **Audio integration tests** (from Phase 2): render N-second fixtures, assert
  sample-rate/channel-count/duration, non-silence, peak ceilings, crossfade
  continuity (no discontinuities > ε at boundaries).
- **Project round-trip tests**: save/load `.lfms`, autosave recovery, version
  restore.
- **Performance smoke tests**: render-time-per-minute-of-audio budget checked
  on CI-sized machines; memory ceiling assertions.
- CI: GitHub Actions on windows-latest (+ubuntu for portability lint), Python
  3.10/3.12 matrix, `pytest` + `ruff check`.

## M. Build / Installer Strategy

1. `scripts\build_portable.ps1` — clean venv → `pip install -e .[full]` →
   PyInstaller onedir bundle → assemble portable folder
   (`App/ Projects/ MusicLibrary/ Presets/ Exports/ Cache/ Settings/` +
   `portable.flag`) → zip. Runs from any drive including external HDD/SSD.
2. `installer\lfms.iss` — Inno Setup installer wrapping the portable build;
   lets users choose application/data directories.
3. Releases tagged `vX.Y.Z` (semver) attach: portable ZIP, installer EXE,
   source archive, changelog. Code signing is optional (documented for
   maintainers holding a cert).

---

*This document describes implemented behavior where marked "Done"; forward
sections are design contracts for upcoming phases.*
