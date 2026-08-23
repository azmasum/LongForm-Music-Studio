# Procedural Generator

Status: Phase 3 core implemented and tested (143 tests passing overall).

## Pipeline

```
GenerationParameters ──build_plan──▶ MusicPlan
      MusicPlan ──HarmonyGenerator──▶ ChordSegments
      MusicPlan ──MelodyGenerator──▶ NoteEvents (MELODY)
      MusicPlan ──PadGenerator─────▶ NoteEvents (PAD voicings, voice-led)
      MusicPlan ──BassGenerator────▶ NoteEvents (BASS)
      MusicPlan ──SparkleGenerator─▶ NoteEvents (SPARKLE bells)
      MusicPlan ──PulseGenerator───▶ NoteEvents (PULSE kick/hat)
                    │
              Composer.compose() ─▶ Composition (fingerprinted, clipped)
                    │
        CompositionRenderer / quick_generate() ─▶ audio file
```

## Determinism contract

- Every layer draws from its own RNG namespace derived from the user seed:
  `plan`, `harmony`, `melody`, `pad`, `bass`, `sparkle`, `pulse`, `voice`.
- Same `(seed, parameters)` ⇒ byte-identical rendered file (tested).
- Composition fingerprint format: `LFMS-XXXX-XXXX-XXXX`.

## Parameter mapping highlights

- **Genre** sets BPM range, density, brightness, pulse, register, melody
  instrument, mode pool and reverb amount (30 profiles).
- **Moods** apply bounded deltas/multipliers on top of the genre profile.
- **Intensity [0..100]** scales density/pulse/melody probability/brightness;
  high intensity unlocks the soft PULSE layer.
- **voiceover_safe** ducks MELODY (-3 dB) and SPARKLE (-4 dB) as an interim
  step until full sidechain ducking lands in Phase 6.

## Voices

`PAD` (detuned triangles + LP filter), `PIANO` (sine + fast-decaying octave),
`PLUCK` (triangle pluck), `BELL` (FM sine), `BASS` (sub sine/triangle),
`KICK` (pitch-swept sine + click), `HAT` (high-passed noise burst). All are
stateful per-note voices streaming mono blocks through the event scheduler.

## Performance (dev machine)

- ~8x realtime for a 5-layer 120 s stereo mix at 48 kHz.
- Memory stays flat regardless of composition length (streaming scheduler).

## Usage

```python
from lfms.generator import GenerationParameters, quick_generate

params = GenerationParameters(
    seed=20260823,
    duration_sec=3600,
    genre="CINEMATIC",
    moods=("HOPEFUL",),
    intensity=60.0,
)
composition, result = quick_generate(params, "hour.wav")
print(result.frames, result.peak, composition.fingerprint)
```

## Known limitations (next phases)

- Single repeating section with motif variation — full multi-section
  arrangement, energy curves and anti-repetition scoring arrive in Phase 4.
- Reverb is planned but not yet inserted into the render chain.
