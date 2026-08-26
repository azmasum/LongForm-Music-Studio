"""LFMS audio engine: procedural block-based synthesis and rendering."""
from lfms.audio_engine.context import RenderContext
from lfms.audio_engine.graph import AudioGraph, Mixer, TrackStrip
from lfms.audio_engine.jobcontrol import RenderJobControl
from lfms.audio_engine.renderer import OfflineRenderer, RenderResult
from lfms.audio_engine.sampler import SamplerSource, SamplerVoice
from lfms.audio_engine.sources import (
    AmbienceSource,
    DroneSource,
    NoiseSource,
    SourceNode,
    ToneSource,
)
from lfms.audio_engine.studio_fx import (
    CompressorEffect,
    DelayEffect,
    EqEffect,
    ReverbEffect,
    build_effect_from_dict,
)

__all__ = [
    "RenderContext",
    "AudioGraph",
    "Mixer",
    "SamplerSource",
    "SamplerVoice",
    "TrackStrip",
    "RenderJobControl",
    "OfflineRenderer",
    "RenderResult",
    "SourceNode",
    "ToneSource",
    "NoiseSource",
    "AmbienceSource",
    "DroneSource",
    "CompressorEffect",
    "DelayEffect",
    "EqEffect",
    "ReverbEffect",
    "build_effect_from_dict",
]
