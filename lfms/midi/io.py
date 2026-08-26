"""MIDI file I/O: read/write Standard MIDI Files via mido.

All timing is converted to/from absolute seconds using the tempo map.
"""
from __future__ import annotations

from pathlib import Path

import mido

from lfms.core.errors import ValidationError
from lfms.midi.model import (
    DEFAULT_TPQ,
    MidiClip,
    MidiNote,
)


def _tempo_to_bpm(tempo: int) -> float:
    """mido stores tempo as microseconds-per-beat."""
    return 60_000_000.0 / max(1, tempo)


def _bpm_to_tempo(bpm: float) -> int:
    return int(60_000_000.0 / max(1.0, bpm))


def _ticks_to_seconds(ticks: int, tpq: int, tempo_bpm: float) -> float:
    beat = ticks / tpq
    return beat * 60.0 / tempo_bpm


def _seconds_to_ticks(sec: float, tpq: int, tempo_bpm: float) -> int:
    beat = sec * tempo_bpm / 60.0
    return int(round(beat * tpq))


def read_midi(path: str | Path, *, track_index: int | None = None) -> list[MidiClip]:
    """Read a Standard MIDI File and return one MidiClip per track.

    track_index: if given, only return that track (0-based).
    Returns empty list if the file has no note data.
    """
    try:
        mid = mido.MidiFile(str(path))
    except Exception as exc:
        raise ValidationError(
            f"cannot read MIDI file: {path}",
            technical=str(exc),
            suggestion="ensure the file is a standard MIDI file (.mid/.midi)",
        ) from exc

    tpq = mid.ticks_per_beat
    clips: list[MidiClip] = []
    for idx, track in enumerate(mid.tracks):
        if track_index is not None and idx != track_index:
            continue
        tempo_bpm = 120.0
        absolute_tick = 0
        pending_on: dict[tuple[int, int], MidiNote] = {}
        notes: list[MidiNote] = []

        for msg in track:
            absolute_tick += msg.time
            if msg.type == "set_tempo":
                tempo_bpm = _tempo_to_bpm(msg.tempo)
            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                pending_on[key] = MidiNote(
                    pitch=msg.note,
                    start_sec=_ticks_to_seconds(absolute_tick, tpq, tempo_bpm),
                    duration_sec=0.0,
                    velocity=msg.velocity / 127.0,
                    channel=msg.channel,
                )
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                on = pending_on.pop(key, None)
                if on is not None:
                    on.duration_sec = (
                        _ticks_to_seconds(absolute_tick, tpq, tempo_bpm) - on.start_sec
                    )
                    if on.duration_sec > 0.001:
                        notes.append(on)

        if notes:
            end = max(n.end_sec for n in notes)
            clip = MidiClip(
                title=Path(path).stem + (f" track {idx}" if len(mid.tracks) > 1 else ""),
                notes=notes,
                tempo_bpm=tempo_bpm,
                duration_sec=end + 0.1,
                tpq=tpq,
                track_index=idx,
            )
            clips.append(clip)

    return clips


def write_midi(
    clips: list[MidiClip] | MidiClip,
    path: str | Path,
    *,
    tpq: int = DEFAULT_TPQ,
) -> Path:
    """Write one or more MidiClips to a Standard MIDI File.

    Each clip becomes one MIDI track. Returns the written file path.
    """
    if isinstance(clips, MidiClip):
        clips = [clips]
    mid = mido.MidiFile(type=1, ticks_per_beat=tpq)
    for clip in clips:
        track = mido.MidiTrack()
        mid.tracks.append(track)
        tempo = _bpm_to_tempo(clip.tempo_bpm)
        track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        if clip.title:
            track.append(mido.MetaMessage("track_name", name=clip.title[:64], time=0))
        events: list[tuple[int, mido.Message]] = []
        for note in clip.notes:
            on_tick = _seconds_to_ticks(note.start_sec, tpq, clip.tempo_bpm)
            off_tick = _seconds_to_ticks(note.end_sec, tpq, clip.tempo_bpm)
            vel = note.midi_velocity
            events.append((on_tick, mido.Message("note_on", note=note.pitch,
                                                 velocity=vel, channel=note.channel)))
            events.append((off_tick, mido.Message("note_off", note=note.pitch,
                                                  velocity=0, channel=note.channel)))
        events.sort(key=lambda e: e[0])
        prev_tick = 0
        for tick, msg in events:
            delta = max(0, tick - prev_tick)
            msg.time = delta
            track.append(msg)
            prev_tick = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(out))
    return out
