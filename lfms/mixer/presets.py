"""Named effect-chain presets for common production scenarios."""
from __future__ import annotations

from lfms.core.errors import ValidationError

CHAIN_PRESETS: dict[str, tuple[tuple[str, dict], ...]] = {
    "CLEAN": (),
    "PODCAST_VOICE": (
        ("EQ3", {"high_hz": 6000.0, "high_gain_db": 2.0}),
        (
            "COMPRESSOR",
            {"threshold_db": -28.0, "ratio": 3.5, "attack_ms": 8.0, "release_ms": 120.0, "makeup_db": 3.0},
        ),
    ),
    "RADIO_WARM": (
        ("EQ3", {"low_hz": 120.0, "low_gain_db": 3.0, "mid_hz": 2500.0, "mid_gain_db": -1.5}),
        (
            "COMPRESSOR",
            {"threshold_db": -24.0, "ratio": 4.0, "attack_ms": 10.0, "release_ms": 100.0, "makeup_db": 4.0},
        ),
    ),
    "CINEMATIC_SPACE": (
        ("EQ3", {"low_hz": 60.0, "low_gain_db": 2.0, "mid_hz": 900.0, "mid_gain_db": -2.0}),
        ("REVERB", {"room_size": 0.8, "damping": 0.35, "wet": 0.42}),
        ("DELAY", {"time_ms": 380.0, "feedback": 0.28, "mix": 0.18}),
    ),
    "LOFI_TAPE": (
        ("EQ3", {"high_hz": 4500.0, "high_gain_db": -6.0, "mid_hz": 400.0, "mid_gain_db": 1.5}),
        ("DELAY", {"time_ms": 180.0, "feedback": 0.22, "mix": 0.12}),
        ("REVERB", {"room_size": 0.35, "damping": 0.7, "wet": 0.22}),
    ),
    "WIDE_AMBIENCE": (
        ("EQ3", {"mid_hz": 500.0, "mid_gain_db": -2.5, "high_hz": 8000.0, "high_gain_db": 1.5}),
        ("REVERB", {"room_size": 0.95, "damping": 0.25, "wet": 0.55}),
    ),
}


def known_chain_presets() -> tuple[str, ...]:
    return tuple(sorted(CHAIN_PRESETS))


def preset_recipe(name: str) -> tuple[tuple[str, dict], ...]:
    try:
        return CHAIN_PRESETS[name.upper()]
    except KeyError as exc:
        raise ValidationError(f"unknown chain preset {name!r}") from exc
