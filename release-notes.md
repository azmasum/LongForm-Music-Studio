# LFMS 1.2.0 — 15 instruments, reference-inspired generation, clean audio

## Added
- **Instrument palette expanded from 7 to 15 voices**: Strings ensemble, Choir,
  Organ, Electric Piano, Marimba, Karplus-Strong nylon guitar, Saw Bass and
  Snare backbeat join the originals. Every genre picks its lead/pad/bass
  voice from a **seed-driven palette**, so tracks in the same genre finally
  sound different from each other.
- **Reference-inspired generation**: pick any local audio file (or paste a
  direct .mp3/.wav/.ogg/.flac URL) on the Generate page. LFMS analyses it
  locally and borrows its tempo, key/mode, intensity and energy envelope to
  compose a similar-style track whose melody is always original. Streaming
  platform links (YouTube/Spotify/…) are refused by design.
- **"New seed every generate"** checkbox on the Generate page (on by
  default) — repeated clicks now give a different track each time; uncheck
  to reproduce exactly. AI-director suggestions pin their seed.

## Fixed
- **Audio quality**: stateful streaming limiter keeps every render at/below
  −0.26 dBFS continuously (no more block-boundary clicks/buzz/distortion);
  fade-in/fade-out at file boundaries; tamer gain staging on the new
  voices; reduced saw aliasing.

## Downloads
| File | Size | SHA256 |
|---|---|---|
| `LongFormMusicStudio-1.2.0-portable.zip` | 85.8 MB | `C711B643BF832B9F82F49FB766E42E38470629B25C7BF7C5AA7C98B5AE11479F` |
| `LongFormMusicStudio-1.2.0-setup.exe` | 54.0 MB | `C26C1C768FB12E1C85B3EBAF0E6506759F41A928CC0DEF3D50017948DEE77A7C` |

387 automated tests green · ruff clean · CI passing on Windows & Ubuntu × Python 3.10/3.12.
