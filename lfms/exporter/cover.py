"""Deterministic cover art derivation for exported tracks.

No external image assets are needed: a square PNG is painted from the
composition's own fingerprint (palette seeds), section energy curve
(vertical spectrum bars) and BPM/key panel, so every generated track ships
with unique, reproducible artwork.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_HASH_SEED = 14695981039346656037  # FNV-1a 64-bit offset basis


def _fnv1a(text: str) -> int:
    value = _HASH_SEED
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _hex(components: tuple[float, float, float], gamma: float = 1.0) -> str:
    rgb = tuple(int(max(0.0, min(1.0, c**gamma)) * 255) for c in components)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hue_color(hue: float, sat: float, light: float) -> tuple[float, float, float]:
    c = (1.0 - abs(2 * light - 1.0)) * sat
    hp = hue / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    if 0 <= hp < 1:
        r, g, b = c, x, 0.0
    elif 1 <= hp < 2:
        r, g, b = x, c, 0.0
    elif 2 <= hp < 3:
        r, g, b = 0.0, c, x
    elif 3 <= hp < 4:
        r, g, b = 0.0, x, c
    elif 4 <= hp < 5:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    m = light - c / 2.0
    return (r + m, g + m, b + m)


def _section_energy(section) -> float:
    for attr in ("energy", "loudness", "intensity", "role_index"):
        value = getattr(section, attr, None)
        if value is not None:
            try:
                return float(max(0.0, min(1.0, value)))
            except (TypeError, ValueError):
                continue
    return 0.6


def _energy_levels(composition, bars: int, rng: np.random.Generator) -> np.ndarray:
    sections = getattr(composition, "sections", None) or []
    if not sections:
        return np.linspace(0.3, 1.0, bars) * rng.uniform(0.55, 1.0, bars)
    total = max(1.0, float(sections[-1].end_sec))
    levels = np.zeros(bars, dtype=np.float64)
    for section in sections:
        start_i = int(float(section.start_sec) / total * bars)
        end_i = int(float(section.end_sec) / total * bars)
        value = _section_energy(section)
        for i in range(max(0, start_i), max(start_i, end_i)):
            levels[i] = max(levels[i], value)
    return levels.clip(0.05, 1.0)


def generate_cover_art(
    composition,
    out_path: str | Path,
    size: int = 800,
) -> Path:
    """Render deterministic cover art from a :class:`Composition`."""
    seed = _fnv1a(composition.fingerprint or f"{composition.seed}")
    rng = np.random.default_rng(seed)
    base_hue = seed % 360

    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    top = _hue_color((base_hue + 40.0) % 360.0, 0.55, 0.18)
    bottom = _hue_color(base_hue, 0.6, 0.08)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=_hex(tuple(_mix(top[i], bottom[i], t) for i in range(3))),
        )

    bars = 64
    levels = _energy_levels(composition, bars, rng)
    bass_top = size - 170
    bar_w = (size * 0.82) / bars
    left = size * 0.09
    for i, value in enumerate(levels):
        h = int((bass_top - 40) * float(value))
        hue = (base_hue + i * 3) % 360.0
        x0 = left + i * bar_w + 2
        x1 = left + (i + 1) * bar_w - 2
        if x1 <= x0:
            continue
        draw.rectangle(
            [x0, bass_top - h, x1, bass_top],
            fill=_hex(_hue_color(hue, 0.85, 0.12 + 0.5 * float(value))),
        )

    try:
        font = ImageFont.truetype("consolas.ttf", 26)
        bold = ImageFont.truetype("consolasb.ttf", 46)
    except (OSError, ValueError):
        font = ImageFont.load_default()
        bold = font
    key_name = getattr(composition, "key_name", "") or ""
    bpm = int(getattr(composition, "bpm", 0) or 0)
    label = f"{key_name}  /  {bpm} BPM" if key_name else f"{bpm} BPM"
    curve = getattr(composition, "energy_curve_name", "") or ""
    draw.text(
        (size * 0.09, size - 132),
        label,
        font=bold,
        fill=_hex(_hue_color(base_hue, 0.5, 0.9)),
    )
    draw.text(
        (size * 0.09, size - 86),
        f"{curve or 'FREEFORM'}  \u00b7  fp {str(seed)[:8]}",
        font=font,
        fill=_hex(_hue_color((base_hue + 120) % 360.0, 0.6, 0.75)),
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG")
    return out


def cover_bytes_for(composition, size: int = 600) -> tuple[bytes, str]:
    """PNG bytes + mime type for a composition's generated artwork."""
    with tempfile.TemporaryDirectory() as tmp:
        image = generate_cover_art(composition, str(Path(tmp) / "cover.png"), size=size)
        return image.read_bytes(), "image/png"
