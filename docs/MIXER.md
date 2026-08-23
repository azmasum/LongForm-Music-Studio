# Mixer & Effects

Status: Phase 6 implemented and tested (221 tests passing overall).

## Package layout (`lfms.mixer`)

| Module | Contents |
| --- | --- |
| `channel.py` | `ChannelState` (fader, pan, mute/solo, fades, kind), `fade_gain_curve` |
| `effects.py` | `EQ3Effect`, `CompressorEffect`, `DelayEffect`, `ReverbEffect`, registry |
| `chain.py` | `EffectChain`: ordered slots, move/remove/set_param, preset loading, JSON dict |
| `presets.py` | Curated chains: CLEAN, PODCAST_VOICE, RADIO_WARM, CINEMATIC_SPACE, LOFI_TAPE, WIDE_AMBIENCE |
| `ducking.py` | `DuckingSettings` + `SidechainDucker` (voiceover sidechain) |
| `bus.py` | `MixBus`: streaming offline mixer with solo/mute/fades/pan/chains/ducking/master |

All DSP is deterministic (same inputs → byte-identical output) and works on
`(channels, n)` float32 blocks like the audio engine.

## Effects

- **EQ3** — low-shelf / peaking mid / high-shelf; each band re-designable via
  `set_param`. Built on engine biquads (RBJ cookbook).
- **COMPRESSOR** — linked mono peak envelope, hard knee, attack/release
  smoothing in the gain domain, makeup gain. O(n) scalar smoothing loop
  (documented hot spot; fine at mix scale).
- **DELAY** — per-channel feedback comb, dry/wet crossfade; window-
  vectorized recursion.
- **REVERB** — Schroeder topology: 4 parallel feedback combs + 2 series
  allpasses (lag-sized vector chunks). Damping = one-pole soften of comb
  input plus slightly reduced feedback (Freeverb-style), not an in-loop LP.

Every effect validates parameters (`ValidationError`) and supports
`params()` / `set_param()` / `reset()`. `EFFECT_TYPES` maps registry names;
`create_effect(type, sample_rate, **overrides)` builds instances.

## Presets

`EffectChain.from_preset(name, sample_rate)` builds ordered chains;
`chain.to_dict()` serializes slots for project files, and
`from_recipe` rebuilds them bit-exactly. Presets are a curated static list
(user-editable chains arrive with the Phase 8 UI).

## Voiceover ducking

`SidechainDucker.process(music_block, vo_block)` attenuates music while the
voiceover bus is active:

- Envelope detected on 256-sample hops (~5 ms @48 kHz), gains held per hop.
- `threshold_db` (-38 default): VO level above this engages ducking over
  `range_db` (18 dB) down to `floor_db` (-12 dB max attenuation).
- Asymmetric attack/release time constants smooth the envelope.

In `MixBus`, channels with `kind="VOICEOVER"` are summed separately, drive
the ducker, and bypass ducking themselves — everything else ducks.

## MixBus

```python
bus = MixBus(48000, master_volume_db=-1.0)
bus.add_stem("music", stem_array, volume_db=-6, fade_in_sec=2.0,
             chain=EffectChain.from_preset("WIDE_AMBIENCE", 48000))
mixed = bus.render()          # -> (2, total_frames) float32
```

- Sources: precomputed stems (`add_stem`) or any streaming source with
  `.process(n_frames)` / `.sample_rate` (+ optional `.reset()`, called at
  render start so renders are repeatable).
- Solo wins over mute (engine convention); fades are linear full-length
  curves applied per channel.
- Stereo stems are mono-folded when panned; mono sources use equal-power pan.
- Master chain effects run after summation (compress/limit the final bus).
- Measured ~45x realtime for a 3-channel 60 s mix including WIDE_AMBIENCE
  reverb and ducking (compressor chains add their scalar-loop cost).

## GUI note

The Mix page in `lfms.app` remains a labeled placeholder until Phase 8;
everything above is already usable from scripts and tests today.
