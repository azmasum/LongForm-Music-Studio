# Sound Library

Status: Phase 8 services + Library/Mix pages implemented and tested
(260 tests passing overall, GUI smoke included).

## Package layout (`lfms.library`)

| Module | Contents |
| --- | --- |
| `models.py` | `Item` dataclass (metadata + measurement + generation info) |
| `service.py` | `LibraryService` (SQLite), smart-tag helpers |

Default database location: `%USERPROFILE%\.lfms\library.db`
(`MainWindow(db_path=...)` overrides it; tests use temp/in-memory DBs).

## Data model

- **items**: path (unique), title, kind (`GENERATED` / `AUDIO_FILE`),
  duration/format, measured `integrated_lufs`/`true_peak_dbtp`, generation
  metadata (bpm/key/seed/fingerprint/params JSON), notes, favorite,
  timestamps.
- **tags**: many-to-many, lowercase normalized (max 60 chars).
- **collections** + membership: named sets of items, unique names.

Deleting an item cascades its tags and collection memberships
(`PRAGMA foreign_keys=ON`).

## Service API

```python
lib = LibraryService(db_path)
item = lib.register_composition(composition, params)   # generated music
item = lib.import_audio_file("beds/rain.wav")          # analyzed import
lib.list_items(query="ocean", tag="level:quiet",
               favorite_only=False, collection=None,
               sort="added_desc")
lib.set_favorite(id, True); lib.add_tag(id, "rain")
lib.create_collection("Storms"); lib.add_to_collection("Storms", id)
```

Search matches title/path/fingerprint substrings and tags, case-
insensitively. Unknown fields, empty titles, duplicate paths/collection
names raise `ValidationError`; missing entities raise on delete/favorite.

### Import analysis

`import_audio_file` reads format via soundfile, decodes and measures full
BS.1770 loudness + true peak for files up to 15 minutes (longer files skip
loudness rather than stalling imports) and stores everything on the item.

### Smart tagging

- Generated: `genre:*`, `mood:*`, `bpm:<bucket-of-5>`, `voiceover-safe`,
  `energy:{low,mid,high}` from intensity.
- Imported audio: `level:{quiet<=-24,moderate,loud>=-14} LUFS buckets`,
  `mono`/`stereo`, `long-form` (>=300 s), `sting` (<=30 s).

## App integration

- **Generate page**: every successful generation auto-registers the
  composition in the library (fingerprint + params + smart tags).
- **Library page**: live search box, tag filter combo, favorites-only
  checkbox, details pane (measurement/generation/tags/notes), favorite
  toggle, delete, create/add-to collections.
- **Mix page** (upgraded from placeholder): one strip per timeline track —
  volume slider (-60..12 dB), pan slider, mute/solo toggles. Edits run as
  undoable `SetTrackPropertyCommand`s (Ctrl+Z works). Effect-chain and
  ducking controls remain deferred by design (see docs/MIXER.md).

## Deferred (honest notes)

- Audio preview playback from the library list (needs the Phase 6+ playback
  graph wired to a device).
- Import-from-disk dialog button (service exists; UI entry point pending).
- Export page UI lands with Phase 9 provenance certificates.
