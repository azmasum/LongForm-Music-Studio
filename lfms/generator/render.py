"""Composition rendering: build an AudioGraph from roles and render to disk."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lfms.audio_engine.dsp import gain_to_db
from lfms.audio_engine.effects import SoftLimiter, StereoWidth
from lfms.audio_engine.graph import AudioGraph
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.audio_engine.renderer import OfflineRenderer, RenderResult
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
        for role in comp.role_names():
            gain = ROLE_GAINS_DB.get(role, -10.0)
            if comp.voiceover_safe:
                gain += _VOICEOVER_SAFE_EXTRA_DB.get(role, 0.0)
            source = EventTrackSource(
                comp.sample_rate,
                comp.roles[role],
                timbre=timbre,
                seed=comp.seed,
            )
            graph.create_track(role.lower(), source, volume_db=gain)
        graph.mixer.master_volume_db = self.master_volume_db + float(master_boost_db)
        # Master bus glue: a soft ceiling (only shapes samples above 0.95, so
        # delicate intros/transients stay pristine) plus gentle stereo widening
        # so the mix sits together and reads as a mastered, DJ-appropriate
        # send — not a dry, unbalanced stem stack. Peak sections stay musical
        # instead of distorting.
        graph.mixer.master_effects.extend(
            [
                SoftLimiter(threshold=0.95),
                StereoWidth(width=1.15),
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
        result = renderer.render(
            self.build_graph(),
            destination,
            self.composition.duration_sec,
            container=container_name,
            bit_depth=bit_depth,
            on_progress=on_progress,
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
                # The first pass already reported 0->1 progress; keeping the
                # loudness-normalized re-render silent preserves a monotonic
                # overall progress sequence for the caller.
                result = renderer.render(
                    self.build_graph(master_boost_db=boost_db),
                    destination,
                    self.composition.duration_sec,
                    container=container_name,
                    bit_depth=bit_depth,
                    on_progress=None,
                    job_control=job_control,
                    fade_out_sec=NORMALIZE_FADE_OUT,
                )
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
