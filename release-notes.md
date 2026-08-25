# LFMS 1.1.0 — MP3/OGG export + playback & timeline UX fixes

## Added
- **MP3 and OGG export** on the Export & Provenance page (libsndfile 1.2+ encodes both natively; no external tool needed).
- Generated music is now written to a real WAV file in a folder you choose (**defaults to your Downloads folder**) and registered in the library with its file path — nothing gets lost.
- The generated audio loads straight into the transport player, so **Play / Pause / Stop work immediately** after generation.
- Timeline clips are interactive: click to select, drag horizontally to move, press Delete to remove — every action undoable with Ctrl+Z.
- Usage hints on the Timeline and Mix pages explaining what each control does.

## Fixed
- Deadlock in the audio engine player when stopping during active playback.

## Downloads
| File | Size | SHA256 |
|---|---|---|
| `LongFormMusicStudio-1.1.0-portable.zip` | 85.8 MB | `44C15D9CCAF91A499644DAC7B3036872E439C288F6EEB6BC40CE60B1C861F8D1` |
| `LongFormMusicStudio-1.1.0-setup.exe` | 54.0 MB | `BA7894713693F8D94B7B626E9403CABE536EE31DDA587EC4300988E080372D46` |

352 automated tests green, ruff clean, CI passing on Windows & Ubuntu × Python 3.10/3.12.
