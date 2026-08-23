"""Ordered effect chains built from presets or explicit recipes."""
from __future__ import annotations

import numpy as np

from lfms.core.errors import ValidationError
from lfms.mixer.effects import EFFECT_TYPES, ParametricEffect, create_effect
from lfms.mixer.presets import known_chain_presets, preset_recipe


class ChainSlot:
    """One named effect in a chain."""

    def __init__(self, effect_type: str, effect: ParametricEffect) -> None:
        self.effect_type = effect_type.upper()
        self.effect = effect


class EffectChain:
    def __init__(self) -> None:
        self._slots: list[ChainSlot] = []

    @classmethod
    def from_recipe(
        cls, recipe: tuple[tuple[str, dict], ...], sample_rate: int
    ) -> EffectChain:
        chain = cls()
        for effect_type, overrides in recipe:
            chain.append(effect_type, sample_rate, **overrides)
        return chain

    @classmethod
    def from_preset(cls, name: str, sample_rate: int) -> EffectChain:
        if name.upper() not in {p for p in known_chain_presets()}:
            raise ValidationError(f"unknown chain preset {name!r}")
        return cls.from_recipe(preset_recipe(name), sample_rate)

    def append(self, effect_type: str, sample_rate: int, **overrides) -> ParametricEffect:
        effect = create_effect(effect_type, sample_rate, **overrides)
        self._slots.append(ChainSlot(effect_type, effect))
        return effect

    def remove(self, index: int) -> ChainSlot:
        return self._slots.pop(index)

    def move(self, index: int, new_index: int) -> None:
        if not 0 <= index < len(self._slots) or not 0 <= new_index < len(self._slots):
            raise ValidationError("chain move index out of range")
        slot = self._slots.pop(index)
        self._slots.insert(new_index, slot)

    def set_param(self, index: int, name: str, value: float) -> None:
        self._slots[index].effect.set_param(name, value)

    def slot(self, index: int) -> ChainSlot:
        return self._slots[index]

    def __len__(self) -> int:
        return len(self._slots)

    def __iter__(self):
        return iter(self._slots)

    def types(self) -> tuple[str, ...]:
        return tuple(slot.effect_type for slot in self._slots)

    def process(self, block: np.ndarray) -> np.ndarray:
        out = block
        for slot in self._slots:
            out = slot.effect.process(out).astype(np.float32)
        return out

    def reset(self) -> None:
        for slot in self._slots:
            slot.effect.reset()

    def to_dict(self) -> list[dict]:
        return [
            {"type": slot.effect_type, "params": slot.effect.params()}
            for slot in self._slots
        ]


def validate_effect_type(effect_type: str) -> str:
    upper = effect_type.upper()
    if upper not in EFFECT_TYPES:
        raise ValidationError(f"unknown effect type {effect_type!r}")
    return upper
