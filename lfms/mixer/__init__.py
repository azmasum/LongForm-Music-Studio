"""Mixer & effects (Phase 6): channels, effect chains, presets, ducking, bus."""
from __future__ import annotations

from lfms.mixer.bus import MixBus, MixChannel
from lfms.mixer.chain import ChainSlot, EffectChain
from lfms.mixer.channel import CHANNEL_KINDS, ChannelState, fade_gain_curve
from lfms.mixer.ducking import DuckingSettings, SidechainDucker
from lfms.mixer.effects import (
    EFFECT_TYPES,
    CompressorEffect,
    DelayEffect,
    EQ3Effect,
    ParametricEffect,
    ReverbEffect,
    create_effect,
)
from lfms.mixer.presets import CHAIN_PRESETS, known_chain_presets, preset_recipe

__all__ = [
    "CHAIN_PRESETS",
    "CHANNEL_KINDS",
    "ChainSlot",
    "ChannelState",
    "CompressorEffect",
    "DelayEffect",
    "DuckingSettings",
    "EFFECT_TYPES",
    "EQ3Effect",
    "EffectChain",
    "MixBus",
    "MixChannel",
    "ParametricEffect",
    "ReverbEffect",
    "SidechainDucker",
    "create_effect",
    "fade_gain_curve",
    "known_chain_presets",
    "preset_recipe",
]
