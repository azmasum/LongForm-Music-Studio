"""Studio project rendering: TimelineDocument -> audio files.

Phase A of the studio roadmap. Builds an AudioGraph from the timeline:

- GENERATED clips are recomposed deterministically from the library item's
  stored parameters (same provenance contract as exporter/service.py).
- AUDIO_FILE clips stream any libsndfile-readable file from disk, with
  automatic sample-rate conversion.
- Clip placement, per-clip gain and fades are handled by ClipSequenceSource;
  track volume/pan/mute/solo by TrackStrip; volume automation lanes by a
  piecewise-linear envelope evaluated against absolute timeline frames.

Two entry points: render_project_mixdown (one mastered file) and
render_project_stems (one raw WAV per track). Both stream block-by-block,
so memory stays flat for hour-long projects.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.dsp import db_to_gain
from lfms.audio_engine.formats import resolve_sf_params
from lfms.audio_engine.graph import AudioGraph
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.audio_engine.renderer import OfflineRenderer, RenderResult
from lfms.audio_engine.sources import AudioFileSource, SourceNode
from lfms.core.errors import ValidationError
from lfms.generator.composer import Composer
from lfms.generator.plan import params_from_payload
from lfms.generator.render import CompositionRenderer
from lfms.library.service import LibraryService
from lfms.mastering.master import auto_master, resolve_target_preset
from lfms.timeline.model import AutomationLane, Clip, TimelineDocument

TAIL_SEC = 2.0


# --------------------------------------------------------------- clip sources


class _CompositionClipSource(SourceNode):
    """Plays one GENERATED clip: recomposes from stored parameters and sums
    the composition's role strips to mono (identical gains to solo export)."""

    def __init__(self, sample_rate: int, composition) -> None:
        super().__init__(sample_rate)
        self._graph = CompositionRenderer(composition, master_volume_db=0.0).build_graph()
        self._ctx = RenderContext(sample_rate=sample_rate, channels=2)

    def process(self, n_frames: int) -> np.ndarray:
        bus = self._graph.mixer.process(self._ctx, n_frames).astype(np.float64)
        self._ctx.advance(int(n_frames))
        return ((bus[0] + bus[1]) * 0.5)[None, :].astype(np.float32)


class ClipSequenceSource(SourceNode):
    """One timeline track as a source: plays its clips back to back with
    silence in gaps, applying each clip's gain_db and fade in/out."""

    def __init__(
        self,
        sample_rate: int,
        clips: list[Clip],
        *,
        build_child: Callable[[Clip], SourceNode],
    ) -> None:
        super().__init__(sample_rate)
        self._clips = sorted(clips, key=lambda c: c.start_sec)
        self._build_child = build_child
        self._frames = 0
        self._active_index: int | None = None
        self._child: SourceNode | None = None
        self._clip_start_frame = 0

    def process(self, n_frames: int) -> np.ndarray:
        n = int(n_frames)
        out = np.zeros(n, dtype=np.float32)
        end_frame = self._frames + n
        for index, clip in enumerate(self._clips):
            start_frame = int(round(clip.start_sec * self.sample_rate))
            end_clip_frame = start_frame + int(round(clip.duration_sec * self.sample_rate))
            if end_clip_frame <= self._frames or start_frame >= end_frame:
                if self._active_index == index:
                    self._active_index = None
                    self._child = None
                continue
            if self._active_index != index or self._child is None:
                self._active_index = index
                self._clip_start_frame = start_frame
                self._child = self._build_child(clip)
                just_activated = True
            else:
                just_activated = False
            overlap_start = max(0, start_frame - self._frames)
            overlap_end = min(n, end_clip_frame - self._frames)
            length = overlap_end - overlap_start
            if length <= 0:
                continue
            # on the clip's very first block, advance the child past any
            # frames before the block we are rendering
            if just_activated:
                lead = max(0, self._frames + overlap_start - self._clip_start_frame)
                if lead:
                    self._child.process(min(lead, length))
            segment = self._child.process(length)[0].astype(np.float64)
            if len(segment) < length:  # file shorter than clip: pad silence
                segment = np.concatenate(
                    [segment, np.zeros(length - len(segment), dtype=np.float64)]
                )
            segment = segment[:length]
            gain = db_to_gain(clip.gain_db)
            fade_in_frames = int(round(clip.fade_in_sec * self.sample_rate))
            fade_out_frames = int(round(clip.fade_out_sec * self.sample_rate))
            total_frames = end_clip_frame - start_frame
            local = np.arange(
                self._frames + overlap_start - self._clip_start_frame,
                self._frames + overlap_start - self._clip_start_frame + length,
                dtype=np.float64,
            )
            env = np.ones(length, dtype=np.float64)
            if fade_in_frames > 0:
                env *= np.clip(local / fade_in_frames, 0.0, 1.0)
            if fade_out_frames > 0:
                env *= np.clip((total_frames - 1 - local) / fade_out_frames, 0.0, 1.0)
            out[overlap_start:overlap_end] += segment * env * gain
        self._frames = end_frame
        return out[None, :]


# ------------------------------------------------------------ graph assembly


def find_item_by_fingerprint(service: LibraryService, fingerprint: str):
    matches = [
        item
        for item in service.list_items(query=fingerprint)
        if item.fingerprint == fingerprint
    ]
    if not matches:
        raise ValidationError(
            f"no library item with fingerprint {fingerprint}",
            suggestion="generate the clip again or re-link it to an audio file",
        )
    return matches[0]


def _composition_for_clip(service: LibraryService, clip: Clip):
    item = find_item_by_fingerprint(service, clip.source_ref)
    if not item.params_json:
        raise ValidationError(
            f"library item #{item.id} has no stored parameters; "
            "cannot recompose clip",
        )
    try:
        payload = json.loads(item.params_json)
        params = params_from_payload(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("stored parameters are not valid JSON") from exc
    return Composer(params).compose()


def _volume_envelope_factory(lane: AutomationLane | None, sample_rate: int):
    """Piecewise-linear interpolation over automation points; value 0..1."""
    points = sorted(lane.points, key=lambda p: p.time_sec) if lane else []

    def envelope(start_frame: int, n_frames: int) -> np.ndarray:
        if not points:
            return np.ones(n_frames, dtype=np.float64)
        times = np.arange(n_frames, dtype=np.float64)
        times += start_frame
        times /= float(sample_rate)
        xs = np.array([p.time_sec for p in points], dtype=np.float64)
        ys = np.array([p.value for p in points], dtype=np.float64)
        return np.interp(times, xs, ys, left=ys[0], right=ys[-1])

    return envelope


def _validate_clip_source(service: LibraryService, clip: Clip) -> None:
    """Eagerly verify a clip's source is resolvable before rendering."""
    if clip.source_kind == "AUDIO_FILE":
        if not Path(clip.source_ref).is_file():
            raise ValidationError(
                f"audio file missing for clip {clip.label!r}: {clip.source_ref}",
                suggestion="re-import the file or remove the clip",
            )
    elif clip.source_kind == "GENERATED":
        item = find_item_by_fingerprint(service, clip.source_ref)
        if not item.params_json:
            raise ValidationError(
                f"library item #{item.id} has no stored parameters; "
                "cannot recompose clip",
            )
        try:
            params_from_payload(json.loads(item.params_json))
        except json.JSONDecodeError as exc:
            raise ValidationError("stored parameters are not valid JSON") from exc
    elif clip.source_kind == "MIDI":
        if clip.midi_data is None:
            raise ValidationError(
                f"MIDI clip {clip.label!r} has no embedded note data",
                suggestion="re-import the MIDI file or create a new MIDI clip",
            )
    else:
        raise ValidationError(f"unknown clip source kind {clip.source_kind!r}")


def build_project_graph(
    document: TimelineDocument,
    library: LibraryService,
    *,
    only_track_id: str | None = None,
    master_volume_db: float = 0.0,
) -> AudioGraph:
    """Build a renderable graph for the whole document (or a single track).

    Raises ValidationError when a GENERATED clip's fingerprint is missing
    from the library or an AUDIO_FILE clip's path no longer exists.
    """
    tracks = (
        [document.track(only_track_id)]
        if only_track_id is not None
        else list(document.tracks)
    )
    if not tracks:
        raise ValidationError("timeline has no tracks to render")
    graph = AudioGraph(48000)
    composition_cache: dict[str, object] = {}
    for track in tracks:
        clips = document.clips_on_track(track.track_id)
        if not clips:
            continue
        for clip in clips:
            _validate_clip_source(library, clip)

        def make_child(clip: Clip, _service=library, _cache=composition_cache):
            if clip.source_kind == "AUDIO_FILE":
                path = Path(clip.source_ref)
                if not path.is_file():
                    raise ValidationError(
                        f"audio file missing for clip {clip.label!r}: {path}",
                        suggestion="re-import the file or remove the clip",
                    )
                return AudioFileSource(graph.sample_rate, str(path))
            if clip.source_kind == "GENERATED":
                fingerprint = clip.source_ref
                if fingerprint not in _cache:
                    _cache[fingerprint] = _composition_for_clip(_service, clip)
                comp = _cache[fingerprint]
                if int(comp.sample_rate) != graph.sample_rate:
                    raise ValidationError(
                        f"composition sample rate {comp.sample_rate} does not "
                        f"match project rate {graph.sample_rate}"
                    )
                return _CompositionClipSource(graph.sample_rate, comp)
            if clip.source_kind == "MIDI":
                from lfms.audio_engine.midi_source import DefaultSineSource
                from lfms.midi.model import MidiClip as _MidiClip

                midi_clip = _MidiClip.from_dict(clip.midi_data)
                return DefaultSineSource(graph.sample_rate, midi_clip)
            raise ValidationError(f"unknown clip source kind {clip.source_kind!r}")

        sequence = ClipSequenceSource(graph.sample_rate, clips, build_child=make_child)
        strip = graph.create_track(
            track.name,
            sequence,
            volume_db=track.volume_db,
            pan=track.pan,
        )
        strip.mute = track.mute
        strip.solo = track.solo
        volume_lane = next(
            (
                lane
                for lane in document.lanes
                if lane.track_id == track.track_id and lane.parameter == "volume"
            ),
            None,
        )
        strip.volume_envelope = _volume_envelope_factory(volume_lane, graph.sample_rate)
    if not graph.mixer.strips:
        raise ValidationError("selected track has no clips to render")
    graph.mixer.master_volume_db = master_volume_db
    return graph


def content_duration_sec(document: TimelineDocument) -> float:
    """Last audible moment across all clips (+ tail), at least 5 s."""
    end = max((clip.end_sec for clip in document.clips), default=0.0)
    return max(5.0, end + TAIL_SEC)


# ------------------------------------------------------------------ entry API


@dataclass
class ProjectRenderOutcome:
    paths: list[Path] = field(default_factory=list)
    results: dict[str, RenderResult] = field(default_factory=dict)
    master_name: str | None = None


def render_project_mixdown(
    document: TimelineDocument,
    library: LibraryService,
    output_dir: str | Path,
    *,
    filename: str = "project-mixdown",
    preset: str | None = "YOUTUBE",
    container: str = "WAV",
    bit_depth: int = 24,
    on_progress: Callable[[float], None] | None = None,
    should_cancel=None,
) -> ProjectRenderOutcome:
    """Render the full timeline to one file; optionally auto-master it.

    preset=None renders raw (no mastering), useful as a mix reference.
    """
    from lfms.core.errors import RenderCancelled

    def check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise RenderCancelled("mixdown cancelled by user")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    check_cancel()
    graph = build_project_graph(document, library)
    duration = content_duration_sec(document)

    class _JC(RenderJobControl):
        def checkpoint(self) -> bool:
            return not (should_cancel is not None and should_cancel())

    raw_path = out_dir / f"{filename}-raw.wav"
    renderer = OfflineRenderer()
    result = renderer.render(
        graph,
        raw_path,
        duration,
        container="WAV",
        bit_depth=24,
        on_progress=(lambda f: on_progress(0.7 * f) if on_progress else None),
        job_control=_JC() if should_cancel is not None else None,
    )
    if result.cancelled:
        raise RenderCancelled("mixdown cancelled by user")
    data, sr = sf.read(str(raw_path), always_2d=True, dtype="float32")
    raw_path.unlink(missing_ok=True)
    fmt, subtype = resolve_sf_params(container, bit_depth)
    extension = ".wav"
    final_path = out_dir / f"{filename}{extension}"
    if preset is not None:
        target = resolve_target_preset(preset)
        master = auto_master(data.T.astype(np.float32), sr, target)
        sf.write(str(final_path), master.output.T, sr, format=fmt, subtype=subtype)
        outcome_master = target.name
    else:
        sf.write(str(final_path), data, sr, format=fmt, subtype=subtype)
        outcome_master = None
    if on_progress is not None:
        on_progress(1.0)
    return ProjectRenderOutcome(
        paths=[final_path], results={"mixdown": result}, master_name=outcome_master
    )


def _safe_stem(name: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name)
    return stem.strip("-")[:40] or "track"


def render_project_stems(
    document: TimelineDocument,
    library: LibraryService,
    output_dir: str | Path,
    *,
    prefix: str = "stem",
    on_progress: Callable[[float], None] | None = None,
    should_cancel=None,
) -> ProjectRenderOutcome:
    """One unmastered WAV per timeline track (stems), streamed to disk."""
    from lfms.core.errors import RenderCancelled

    def check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise RenderCancelled("stem export cancelled by user")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = content_duration_sec(document)
    tracks = [t for t in document.tracks if document.clips_on_track(t.track_id)]
    if not tracks:
        raise ValidationError("timeline has no clips to export")
    renderer = OfflineRenderer()
    outcome = ProjectRenderOutcome()
    for index, track in enumerate(tracks):
        check_cancel()
        graph = build_project_graph(document, library, only_track_id=track.track_id)
        path = out_dir / f"{prefix}-{index + 1:02d}-{_safe_stem(track.name)}.wav"
        n_tracks = len(tracks)
        result = renderer.render(
            graph,
            path,
            duration,
            container="WAV",
            bit_depth=24,
            on_progress=(
                (lambda f, base=index / n_tracks, span=1.0 / n_tracks: on_progress(base + span * f))
                if on_progress
                else None
            ),
        )
        outcome.paths.append(path)
        outcome.results[track.name] = result
    if on_progress is not None:
        on_progress(1.0)
    return outcome
