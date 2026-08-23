# Audio Engine

Status: Phase 2 core implemented and tested (112 tests passing).

## Design summary

- **Internal format**: float32 blocks, shape `(channels, n_frames)`.
- **Block-based**: every node processes fixed-size chunks (offline default
  32768 frames; realtime 2048). A node never sees the whole project.
- **Determinism**: all randomness flows from explicit seeds (`np.random.default_rng`);
  identical parameters reproduce byte-identical renders (covered by test).
- **Measured performance** (this repo's dev machine): ~15x realtime for a
  3-track stereo 48 kHz mix — a 60-minute track renders in roughly 4 minutes.

## Modules

| Module | Contents |
| --- | --- |
| `context.py` | `RenderContext` (sample rate, frames done, time position) |
| `dsp.py` | dB/gain math, equal-power pan, soft clip, peak/RMS/band energy |
| `oscillators.py` | Vectorized `Oscillator` — sine/tri/saw/square, unison + detune, FM (phase modulation), AM tremolo, sub oscillator; stateful phase continues across blocks |
| `envelopes.py` | `ADSR` with retrigger-from-release support |
| `filters.py` | RBJ cookbook biquads (LP/HP/BP/notch/peaking/shelves) via `scipy.signal.lfilter`, per-channel state, live parameter changes; `DCBlocker` |
| `lfo.py` | Sine/triangle/saw/random S&H control LFOs in [0, 1] |
| `sources.py` | `ToneSource`, `NoiseSource` (white/pink/brown), `AmbienceSource` (RAIN/WIND/OCEAN/ROOM_TONE/NIGHT/CITY), `DroneSource` |
| `effects.py` | Gain, `SoftLimiter`, DC-block effect, `StereoWidth` (mid/side) |
| `graph.py` | `TrackStrip` (source→pan→effects→gain) and `Mixer` (mute/solo bus, master chain) inside `AudioGraph` |
| `formats.py` | Container/bit-depth → libsndfile format+subtype mapping; MP3 raises until FFmpeg integration (Phase 11) |
| `jobcontrol.py` | `RenderJobControl` — cooperative pause/resume/cancel between chunks |
| `renderer.py` | `OfflineRenderer` — incremental disk writes via soundfile, exact frame counts, progress callbacks, safety soft-limit above full scale, QC stats in `RenderResult` |
| `playback.py` | `Player` realtime sink on PortAudio (lazy import); friendly `AudioDeviceError` messages |

## Usage example

```python
from lfms.audio_engine import AudioGraph, DroneSource, AmbienceSource, OfflineRenderer

graph = AudioGraph(48000)
graph.create_track("drone", DroneSource(48000, frequency=110.0, seed=42), volume_db=-9.0)
graph.create_track("rain", AmbienceSource(48000, kind="RAIN", seed=7), volume_db=-12.0)

result = OfflineRenderer().render(graph, "output.wav", 30.0)   # seconds
print(result.frames, result.peak, result.rms)
```

## Manual playback smoke checklist (run on real hardware)

1. `Player().play(graph)` — audio audible, no device errors.
2. Stop/start repeatedly — no exceptions or stuck streams.
3. Unplug default device mid-playback — expect `AudioDeviceError` with the
   guidance message, not a crash.
4. Confirm CPU stays modest at 48 kHz / block 2048 with several tracks.

## Known limitations (addressed in later phases)

- No musical note events yet — the generator (Phase 3) drives voices from a
  composition plan instead of raw drones.
- MP3 export awaits FFmpeg subprocess integration (Phase 11).
- Realtime mixer UI automation arrives with Phase 5–6.
