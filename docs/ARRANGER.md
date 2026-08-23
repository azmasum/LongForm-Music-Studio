# Long-form Arranger

Status: Phase 4 implemented and tested (173 tests passing overall).

## Pipeline

```
EnergyCurve (preset or user points)
        │
SectionPlanner ──▶ SectionSpans (bar-aligned, energy per section)
        │                              │
HarmonyGenerator ── global chords ─▶ slice per section
        │                              │
     per-section generation (own RNG namespace per section):
       MELODY (thinned + octave-shift variants)   PAD / BASS / SPARKLE
       PULSE (absolute-time windowed)
        │
     velocity scaling by section energy → clip to duration
        │
Composition (+ sections, energy_curve_name, repetition_score)
```

## Energy curves

Nine presets (`FLAT`, `SLOW_BUILD`, `CINEMATIC_BUILD`, `EMOTIONAL_WAVE`,
`DOCUMENTARY`, `SUSPENSE`, `RELAXATION`, `INTRO_PEAK_OUTRO`,
`RANDOM_ORGANIC` — the last is seed-deterministic). Users can pass explicit
`(time, value)` points which override presets. Section energy scales density,
melody probability, pulse level and event velocities.

## Sections

- Tracks under 60 s stay a single THEME_A span.
- Longer tracks get INTRO (4–16 bars) + a repeating middle cycle drawn from
  seeded templates (THEME_A/VARIATION/THEME_B/DEVELOPMENT/BREAKDOWN/
  TRANSITION) + OUTRO, all bar-aligned.
- Role gates per type: INTRO/BREAKDOWN/OUTRO thin out foreground layers.

## Anti-repetition (Repetition Score)

`repetition_score(composition) -> 0..100`, deterministic:

- Windows are always 8 bars; a 60-minute piece yields ~200 windows.
- Features describe the **foreground only** (MELODY/SPARKLE/PULSE with low
  pulse weight; onset-gap histogram uses melodic events). Steady pads/bass
  are supposed to repeat in background music and must not dominate.
- Pairwise similarities use deviations from the track's mean window
  (Pearson-style), so shared key/scale baseline cancels out; top-decile mean
  becomes the score.

Calibration measurements:

| Composition | Score |
| --- | --- |
| Literal copy-paste loop (synthetic) | 100 |
| Progressively varied (synthetic) | ~0 |
| Arranged real tracks (300 s – 3600 s, various genres) | 62–88 |

## Measured performance (dev machine)

- Composing a 1-hour track: 45 sections, 18k events, ~2 s.
- Rendering it: 7.4x realtime (48 kHz stereo), memory flat, exact frames.

## Known limitations (next phases)

- Score currently reports; the auto "reduce repetition" re-roll loop arrives
  with the GUI (regenerate-until-below-target).
- Imported audio clips enter the timeline in Phase 5+.
