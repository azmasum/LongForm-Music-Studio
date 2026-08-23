# Third-Party Licenses & Asset Registry

LFMS code is MIT-licensed. **Third-party components keep their own licenses**
and are not covered by the LFMS license. Nothing questionable is bundled
silently; every runtime dependency and any future sample/preset asset must be
registered here.

## Runtime Python dependencies

| Package | License | Notes |
| --- | --- | --- |
| NumPy | BSD-3-Clause | Numerical core |
| soundfile (python binding) | BSD-3-Clause | Audio file I/O |
| libsndfile (binary dep of soundfile) | LGPL-2.1-or-later | Used dynamically; not modified |
| python-sounddevice | MIT | Playback |
| PortAudio (binary dep) | MIT-style | Used dynamically |
| PySide6 / Qt 6 | LGPL-3.0 (or commercial) | Linked dynamically as permitted by LGPL; keep it dynamically linked when distributing |
| requests | Apache-2.0 | Optional AI adapters |

## Optional external tools

| Tool | License | Usage |
| --- | --- | --- |
| FFmpeg | LGPL-2.1+ / GPL builds vary | MP3 encoding subprocess; user- or installer-provided; build provenance documented at release time |

## Development-only

| Package | License |
| --- | --- |
| pytest | MIT |
| ruff | MIT |

## Sample/preset asset registry

Currently **empty by design** — LFMS generates all audio procedurally.
Any future bundled asset must list: source, author, license, URL,
attribution requirement, commercial-use status — reviewed before merging.
