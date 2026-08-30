"""Composition rendering: build an AudioGraph from roles and render to disk."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from lfms.audio_engine.dsp import db_to_gain, gain_to_db
from lfms.audio_engine.effects import DriveEffect, SoftLimiter, StereoWidth
from lfms.audio_engine.filters import BiquadFilter
from lfms.audio_engine.graph import AudioGraph
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.audio_engine.renderer import OfflineRenderer, RenderResult
from lfms.audio_engine.studio_fx import EqEffect
from lfms.core.enums import ExportContainer
from lfms.generator.composer import Composer
from lfms.generator.events import Composition
from lfms.generator.plan import GenerationParameters
from lfms.generator.scheduler import EventTrackSource

ROLE_GAINS_DB = {
    "PAD": -7.0,
    "MELODY": -9.0,
    "BASS": -8.0,
    "SPARKLE": -13.0,
    "PULSE": -6.0,
}

_VOICEOVER_SAFE_EXTRA_DB = {"MELODY": -3.0, "SPARKLE": -4.0}

# Loudness normalization: if a rendered mix stays far below full scale it
# reads as weak/ambient rather than produced music. Tracks whose peak never
# reaches this floor get a makeup boost up to a healthy peak (below the
# limiting ceiling). Already-hot mixes are untouched.
NORMALIZE_FLOOR = 0.6
NORMALIZE_TARGET = 0.85
NORMALIZE_MAX_DB = 14.0
NORMALIZE_FADE_OUT = 0.03


def _kick_duck_envelope(
    comp: Composition,
    sample_rate: int,
    *,
    reduction_db: float = 4.0,
) -> Callable[[int, int], object]:
    """Return a BASS-track volume envelope that ducks under each kick.

    Classic sidechain: every time a kick hits, the bass dips briefly then
    recovers by the next beat — this frees the low-end and stops kick and
    sub-bass from fighting each other (mud). Deterministic from the kick
    event times already in the composition.
    """
    kicks = sorted(
        e.start_sec
        for e in comp.roles.get("PULSE", [])
        if getattr(e, "instrument", "") == "KICK"
    )
    if not kicks:
        return None
    beat = 60.0 / max(1, comp.bpm)
    dip = db_to_gain(-reduction_db)
    attack_s = 0.004
    release_s = max(0.12, min(0.32, beat * 0.8))
    attacks = sorted(round(t * sample_rate) for t in kicks)
    n_attack = max(1, int(attack_s * sample_rate))
    n_release = max(1, int(release_s * sample_rate))
    n_total = n_attack + n_release
    template = np.empty(n_total, dtype=np.float64)
    template[:n_attack] = np.linspace(1.0, dip, n_attack)
    template[n_attack:] = dip + (1.0 - dip) * np.linspace(
        0.0, 1.0, n_release, endpoint=False
    )
    curve = np.ones(sample_rate, dtype=np.float64)
    for k in attacks:
        seg = k % sample_rate
        room = sample_rate - seg
        src = template if n_total <= room else template[:room]
        if src.size:
            curve[seg : seg + src.size] = np.minimum(
                curve[seg : seg + src.size], src
            )
    curve = np.ascontiguousarray(curve)

    def _env(start_frame: int, n_frames: int) -> object:
        idx = np.arange(start_frame, start_frame + n_frames) % sample_rate
        return curve[idx]

    return _env


def _role_pan(role: str, index: int) -> float:
    """Spread non-rhythm, non-bass roles for a wider, 3D stage.

    Kick and bass stay dead-center (they carry the power). Pads widen out,
    hats ping-pong across the stereo field, and the lead melody sits central
    with a touch of width. `index` is a stable per-role seed offset.
    """
    if role in ("BASS", "KICK", "SNARE"):
        return 0.0
    if role == "HAT":
        return {0: -0.6, 1: 0.6, 2: -0.5, 3: 0.5}.get(index % 4, 0.0)
    if role == "PAD":
        return {0: -0.55, 1: 0.55, 2: -0.38, 3: 0.38}.get(index % 4, 0.0)
    if role == "SPARKLE":
        return {0: 0.6, 1: -0.6, 2: 0.25, 3: -0.25}.get(index % 4, 0.0)
    if role == "MELODY":
        return 0.14
    return 0.0


def _role_eq(sample_rate: int, role: str) -> list[object]:
    """Per-track EQ to fix mud and harshness.

    - BASS/PAD: high-pass subsonic rumble below ~30 Hz (cleans up low-end mud
      without touching the audible sub-bass/kick body).
    - MELODY: gentle dip in the harsh 4-6 kHz presence range (de-ess the lead).
    - HAT: tame the bright 8-12 kHz edge so hats aren't painfully sharp.
    """
    if role in ("BASS", "PAD"):
        return [
            BiquadFilter(
                sample_rate,
                kind="highpass",
                cutoff=30.0,
                q=0.707,
                channels=2,
            )
        ]
    if role == "MELODY":
        return [
            EqEffect(
                sample_rate,
                mid_cutoff=5200.0,
                mid_q=3.0,
                mid_gain_db=-2.5,
            )
        ]
    if role == "HAT":
        return [
            EqEffect(
                sample_rate,
                high_cutoff=9000.0,
                high_gain_db=-3.0,
            )
        ]
    return []


def _tracks_for(comp: Composition) -> list[tuple[str, str, list]]:
    """Expand composition roles into render tracks.

    The PULSE role bundles kick + snare + hat onto one shared bus, which
    forces every drum to the same pan. To let hats spread across the stereo
    field while the kick and snare stay dead-center (the "3D stage" fix), we
    split PULSE into per-instrument tracks here.
    """
    tracks: list[tuple[str, str, list]] = []
    for role in comp.role_names():
        if role != "PULSE":
            tracks.append((role, role, comp.roles[role]))
            continue
        grouped: dict[str, list] = {}
        for event in comp.roles[role]:
            grouped.setdefault(getattr(event, "instrument", "KICK"), []).append(event)
        for instrument, events in grouped.items():
            tracks.append((instrument, "PULSE", events))
    return tracks


class CompositionRenderer:
    def __init__(
        self,
        composition: Composition,
        *,
        master_volume_db: float = -1.0,
    ) -> None:
        self.composition = composition
        self.master_volume_db = float(master_volume_db)

    def build_graph(self, *, master_boost_db: float = 0.0) -> AudioGraph:
        comp = self.composition
        graph = AudioGraph(comp.sample_rate)
        timbre = {"brightness_hz": comp.brightness_hz}
        bass_duck = _kick_duck_envelope(
            comp,
            comp.sample_rate,
            reduction_db=4.0 * (float(comp.sidechain_amount) / 100.0),
        )
        for index, (track_name, role, events) in enumerate(_tracks_for(comp)):
            gain = ROLE_GAINS_DB.get(role, -10.0)
            if comp.voiceover_safe:
                gain += _VOICEOVER_SAFE_EXTRA_DB.get(role, 0.0)
            source = EventTrackSource(
                comp.sample_rate,
                events,
                timbre=timbre,
                seed=comp.seed,
            )
            effects = list(_role_eq(comp.sample_rate, track_name))
            if role == "BASS" and float(comp.bass_distortion) > 0.0:
                drive = 0.7 * float(comp.bass_distortion) / 100.0
                effects.append(DriveEffect(drive=max(0.05, drive)))
            if role == "SAW":
                effects.append(
                    EqEffect(
                        comp.sample_rate,
                        high_cutoff=5200.0,
                        high_gain_db=(float(comp.supersaw_brightness) - 50.0) * 0.10,
                    )
                )
            if role == "SAW":
                gain += (float(comp.drop_intensity) - 50.0) * 0.05
            strip = graph.create_track(
                track_name.lower(),
                source,
                volume_db=gain,
                pan=_role_pan(track_name, index),
                effects=effects,
            )
            # Kick -> bass sidechain: bass ducks briefly on every kick so the
            # low-end stays clean instead of muddy kick-vs-sub overlap.
            if role == "BASS" and bass_duck is not None:
                strip.volume_envelope = bass_duck
        graph.mixer.master_volume_db = self.master_volume_db + float(master_boost_db)
        # Master bus: soften harsh 4-8 kHz presence (de-ess), a soft ceiling
        # (only shapes above 0.95 so intros/transients stay pristine) and
        # gentle stereo widening — a glued, mastered, DJ-appropriate send.
        graph.mixer.master_effects.extend(
            [
                EqEffect(
                    comp.sample_rate,
                    mid_cutoff=5200.0,
                    mid_q=2.0,
                    mid_gain_db=-2.0,
                ),
                SoftLimiter(threshold=0.95),
                StereoWidth(width=1.5),
            ]
        )
        return graph

    def render(
        self,
        destination: str | Path,
        *,
        container: str | ExportContainer = ExportContainer.WAV,
        bit_depth: int = 24,
        job_control: RenderJobControl | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> RenderResult:
        container_name = (
            container.value if isinstance(container, ExportContainer) else str(container)
        )
        renderer = OfflineRenderer()
        # Keep the caller's UI alive AND progress monotonic across a possible
        # loudness-normalization second pass. The first pass maps its native
        # [0,1] progress onto [0, SPLIT]; if normalization re-renders, that
        # second pass maps onto [SPLIT, 1.0]. Because both passes drive the
        # caller's callback (which ordinarily pumps the GUI event loop), the
        # app never freezes at "100%" mid-normalize — the reported figure is
        # monotonic non-decreasing, so callers that assert that still pass.
        split = 0.85
        def first_progress(p: float) -> None:
            if on_progress is not None:
                on_progress(0.85 * max(0.0, min(1.0, p)))

        result = renderer.render(
            self.build_graph(),
            destination,
            self.composition.duration_sec,
            container=container_name,
            bit_depth=bit_depth,
            on_progress=first_progress,
            job_control=job_control,
        )
        # Loudness normalize: sparse/quiet arrangements can come out far too
        # quiet to read as music (RMS ~0.05 vs a DJ-appropriate ~0.2+). If the
        # raw mix never comes close to full scale, render once more with a
        # makeup boost so quiet tracks stand up; loud tracks are left alone.
        if result.ok and result.peak > 1e-4 and result.peak < NORMALIZE_FLOOR:
            boost_db = gain_to_db(NORMALIZE_TARGET / result.peak)
            boost_db = min(boost_db, NORMALIZE_MAX_DB)
            if boost_db > 1.0:
                def second_progress(p: float) -> None:
                    if on_progress is not None:
                        on_progress(split + (1.0 - split) * max(0.0, min(1.0, p)))

                result = renderer.render(
                    self.build_graph(master_boost_db=boost_db),
                    destination,
                    self.composition.duration_sec,
                    container=container_name,
                    bit_depth=bit_depth,
                    on_progress=second_progress,
                    job_control=job_control,
                    fade_out_sec=NORMALIZE_FADE_OUT,
                )
        elif on_progress is not None:
            # Single-pass path: fold the reserved tail up to 100% so the
            # reported figure ends at 1.0 exactly.
            on_progress(1.0)
        return result


def quick_generate(
    params: GenerationParameters,
    destination: str | Path,
    *,
    container: str | ExportContainer = ExportContainer.WAV,
    bit_depth: int = 24,
    master_volume_db: float = -1.0,
    job_control: RenderJobControl | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[Composition, RenderResult]:
    """Compose from parameters and render a real audio file in one call."""
    composition = Composer(params).compose()
    renderer = CompositionRenderer(composition, master_volume_db=master_volume_db)
    result = renderer.render(
        destination,
        container=container,
        bit_depth=bit_depth,
        job_control=job_control,
        on_progress=on_progress,
    )
    return composition, result
