"""Composition rendering: build an AudioGraph from roles and render to disk."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

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
    "PULSE": -16.0,
}

_VOICEOVER_SAFE_EXTRA_DB = {"MELODY": -3.0, "SPARKLE": -4.0}


class CompositionRenderer:
    def __init__(
        self,
        composition: Composition,
        *,
        master_volume_db: float = -1.0,
    ) -> None:
        self.composition = composition
        self.master_volume_db = float(master_volume_db)

    def build_graph(self) -> AudioGraph:
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
        graph.mixer.master_volume_db = self.master_volume_db
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
        return renderer.render(
            self.build_graph(),
            destination,
            self.composition.duration_sec,
            container=container_name,
            bit_depth=bit_depth,
            on_progress=on_progress,
            job_control=job_control,
        )


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
    composer = Composer(params)
    composition = composer.compose()
    composition.seed = composer.plan.seed
    composition.sample_rate = composer.plan.sample_rate
    composition.brightness_hz = composer.plan.brightness_hz
    composition.voiceover_safe = composer.plan.voiceover_safe
    composition.bpm = composer.plan.bpm
    composition.key_name = composer.plan.key_name
    renderer = CompositionRenderer(composition, master_volume_db=master_volume_db)
    result = renderer.render(
        destination,
        container=container,
        bit_depth=bit_depth,
        job_control=job_control,
        on_progress=on_progress,
    )
    return composition, result
