"""Generation parameters and the MusicPlan that drives all generators.

The plan is the single source of truth for downstream modules: harmony,
melody and the renderer never look at raw user input, only at MusicPlan.
Every field is deterministic for a given (seed, params) pair.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from lfms.core.enums import Genre, KeyMode
from lfms.core.errors import ValidationError
from lfms.core.ids import fingerprint
from lfms.core.seed import SeedSystem
from lfms.generator.theory import NOTE_NAMES

DEFAULT_SAMPLE_RATE = 48000


@dataclass(frozen=True)
class _GenreProfile:
    bpm_range: tuple[int, int]
    density: float
    brightness_hz: float
    pulse: float
    melody_probability: float
    register_center: int
    melody_instrument: str
    modes: tuple[str, ...]
    reverb_amount: float


_GENRE_PROFILES: dict[str, _GenreProfile] = {
    "AMBIENT": _GenreProfile((58, 76), 0.32, 1600, 0.00, 0.55, 57, "PLUCK", ("MINOR", "DORIAN"), 0.50),
    "CINEMATIC": _GenreProfile((70, 90), 0.42, 2000, 0.05, 0.60, 55, "PIANO", ("MINOR", "MAJOR"), 0.50),
    "DOCUMENTARY": _GenreProfile((88, 104), 0.48, 2400, 0.12, 0.65, 57, "PIANO", ("MAJOR", "MIXOLYDIAN"), 0.35),
    "EMOTIONAL": _GenreProfile((72, 92), 0.45, 2600, 0.06, 0.75, 58, "PIANO", ("MINOR", "MAJOR"), 0.45),
    "INSPIRATIONAL": _GenreProfile((84, 100), 0.50, 2800, 0.15, 0.70, 59, "PIANO", ("MAJOR",), 0.40),
    "CORPORATE": _GenreProfile((96, 112), 0.50, 3000, 0.18, 0.60, 60, "PLUCK", ("MAJOR", "MIXOLYDIAN"), 0.30),
    "TECHNOLOGY": _GenreProfile((100, 118), 0.46, 3200, 0.22, 0.50, 58, "BELL", ("DORIAN", "LYDIAN"), 0.30),
    "FUTURISTIC": _GenreProfile((98, 116), 0.44, 3400, 0.20, 0.50, 58, "BELL", ("DORIAN", "PHRYGIAN"), 0.35),
    "DARK": _GenreProfile((50, 68), 0.30, 900, 0.03, 0.30, 48, "PLUCK", ("MINOR", "PHRYGIAN"), 0.50),
    "SUSPENSE": _GenreProfile((56, 72), 0.34, 1100, 0.06, 0.35, 50, "PLUCK", ("MINOR", "PHRYGIAN"), 0.45),
    "MYSTERY": _GenreProfile((60, 76), 0.36, 1300, 0.05, 0.40, 52, "BELL", ("MINOR", "DORIAN"), 0.50),
    "PSYCHOLOGICAL": _GenreProfile((54, 70), 0.32, 1200, 0.04, 0.35, 50, "PLUCK", ("MINOR", "PHRYGIAN"), 0.50),
    "HORROR": _GenreProfile((48, 62), 0.28, 800, 0.03, 0.25, 45, "PLUCK", ("PHRYGIAN", "MINOR"), 0.55),
    "CALM": _GenreProfile((54, 68), 0.26, 1500, 0.00, 0.45, 55, "PLUCK", ("MAJOR", "DORIAN"), 0.45),
    "MEDITATION": _GenreProfile((50, 62), 0.24, 1200, 0.00, 0.35, 53, "PLUCK", ("DORIAN", "MINOR"), 0.50),
    "RELAXATION": _GenreProfile((56, 70), 0.30, 1600, 0.02, 0.50, 56, "PLUCK", ("MAJOR", "DORIAN"), 0.45),
    "PIANO": _GenreProfile((66, 86), 0.42, 2500, 0.04, 0.80, 58, "PIANO", ("MINOR", "MAJOR"), 0.40),
    "ACOUSTIC": _GenreProfile((84, 98), 0.46, 2200, 0.14, 0.60, 57, "PLUCK", ("MAJOR", "MIXOLYDIAN"), 0.30),
    "LOFI": _GenreProfile((68, 82), 0.44, 1900, 0.16, 0.60, 56, "PIANO", ("MINOR", "DORIAN"), 0.35),
    "CHILL": _GenreProfile((72, 86), 0.42, 2000, 0.12, 0.60, 57, "PLUCK", ("MINOR", "DORIAN"), 0.38),
    "MINIMAL": _GenreProfile((96, 112), 0.34, 2300, 0.18, 0.40, 57, "PLUCK", ("MINOR", "DORIAN"), 0.30),
    "ELECTRONIC": _GenreProfile((120, 140), 0.54, 3000, 0.34, 0.50, 57, "PLUCK", ("MINOR", "DORIAN"), 0.20),
    "CLASSICAL_INSPIRED": _GenreProfile((72, 96), 0.46, 2500, 0.06, 0.70, 58, "PIANO", ("MAJOR", "MINOR"), 0.38),
    "NATURE": _GenreProfile((60, 76), 0.30, 1700, 0.04, 0.40, 57, "PLUCK", ("MAJOR", "DORIAN"), 0.45),
    "NEWS": _GenreProfile((96, 110), 0.50, 2600, 0.20, 0.55, 58, "PLUCK", ("MAJOR", "MIXOLYDIAN"), 0.25),
    "PODCAST": _GenreProfile((76, 92), 0.36, 2000, 0.08, 0.50, 56, "PLUCK", ("MAJOR", "DORIAN"), 0.30),
    "STORYTELLING": _GenreProfile((74, 90), 0.38, 2100, 0.08, 0.55, 56, "PIANO", ("MINOR", "MAJOR"), 0.38),
    "EDUCATIONAL": _GenreProfile((88, 102), 0.42, 2300, 0.10, 0.55, 58, "PLUCK", ("MAJOR", "MIXOLYDIAN"), 0.30),
    "MOTIVATIONAL": _GenreProfile((84, 102), 0.52, 2800, 0.18, 0.70, 59, "PIANO", ("MAJOR", "MINOR"), 0.38),
    "DRAMATIC": _GenreProfile((76, 92), 0.50, 2100, 0.12, 0.60, 54, "PIANO", ("MINOR", "PHRYGIAN"), 0.45),
}

_MOOD_MODIFIERS: dict[str, dict[str, float]] = {
    "CALM": {"density_delta": -0.06, "pulse_mult": 0.5},
    "PEACEFUL": {"density_delta": -0.06, "brightness_mult": 0.9},
    "EMOTIONAL": {"reverb_delta": 0.05},
    "SAD": {"register_delta": -3, "brightness_mult": 0.85},
    "HOPEFUL": {"brightness_mult": 1.15, "register_delta": 2},
    "INSPIRATIONAL": {"density_delta": 0.05, "brightness_mult": 1.10},
    "MYSTERIOUS": {"brightness_mult": 0.90, "register_delta": -1},
    "DARK": {"register_delta": -4, "brightness_mult": 0.75},
    "SUSPENSEFUL": {"pulse_delta": 0.05},
    "ENERGETIC": {"density_delta": 0.08, "pulse_delta": 0.08},
    "POWERFUL": {"density_delta": 0.08, "register_delta": -1},
    "EPIC": {"density_delta": 0.12, "register_delta": -2},
    "WARM": {"brightness_mult": 0.95},
    "NOSTALGIC": {"brightness_mult": 0.90, "reverb_delta": 0.03},
    "DREAMY": {"density_delta": -0.05, "reverb_delta": 0.08, "brightness_mult": 0.95},
    "LONELY": {"density_delta": -0.08, "register_delta": -2},
    "TENSE": {"pulse_delta": 0.07, "brightness_mult": 1.05},
    "NEUTRAL": {},
    "FUTURISTIC": {"brightness_mult": 1.10},
    "SCIENTIFIC": {"brightness_mult": 1.05},
}

VALID_MODES = tuple(m for m in KeyMode if m.value != "CUSTOM")

# Seed-picked instrument palettes per genre family. The first entry is the
# classic sound for the genre; further entries give each seed variety.
_INSTRUMENT_FAMILIES: dict[str, dict[str, tuple[str, ...]]] = {
    "AMBIENT": {"melody": ("PLUCK", "BELL", "MARIMBA", "NYLON"), "pad": ("PAD", "STRINGS", "CHOIR"), "bass": ("BASS", "SAW_BASS")},
    "CALM": {"melody": ("PLUCK", "NYLON", "MARIMBA"), "pad": ("PAD", "STRINGS"), "bass": ("BASS",)},
    "MEDITATION": {"melody": ("BELL", "PLUCK", "MARIMBA"), "pad": ("CHOIR", "PAD"), "bass": ("BASS",)},
    "RELAXATION": {"melody": ("PLUCK", "NYLON", "EPIANO"), "pad": ("PAD", "STRINGS"), "bass": ("BASS",)},
    "NATURE": {"melody": ("NYLON", "PLUCK", "MARIMBA"), "pad": ("STRINGS", "PAD"), "bass": ("BASS", "NYLON")},
    "DARK": {"melody": ("PLUCK", "MARIMBA", "BELL"), "pad": ("STRINGS", "CHOIR"), "bass": ("SAW_BASS", "BASS")},
    "SUSPENSE": {"melody": ("PLUCK", "MARIMBA"), "pad": ("STRINGS", "PAD"), "bass": ("BASS", "SAW_BASS")},
    "MYSTERY": {"melody": ("BELL", "MARIMBA", "PLUCK"), "pad": ("CHOIR", "STRINGS"), "bass": ("BASS",)},
    "PSYCHOLOGICAL": {"melody": ("PLUCK", "BELL"), "pad": ("STRINGS", "PAD"), "bass": ("SAW_BASS", "BASS")},
    "HORROR": {"melody": ("PLUCK", "BELL"), "pad": ("CHOIR", "STRINGS"), "bass": ("SAW_BASS",)},
    "CINEMATIC": {"melody": ("PIANO", "NYLON", "BELL"), "pad": ("STRINGS", "CHOIR", "PAD"), "bass": ("BASS", "NYLON")},
    "EMOTIONAL": {"melody": ("PIANO", "EPIANO", "NYLON"), "pad": ("STRINGS", "CHOIR"), "bass": ("BASS",)},
    "DRAMATIC": {"melody": ("PIANO", "NYLON", "PLUCK"), "pad": ("STRINGS", "CHOIR"), "bass": ("BASS", "SAW_BASS")},
    "STORYTELLING": {"melody": ("PIANO", "NYLON", "PLUCK"), "pad": ("PAD", "STRINGS"), "bass": ("BASS",)},
    "CLASSICAL_INSPIRED": {"melody": ("PIANO", "NYLON", "MARIMBA"), "pad": ("STRINGS", "PAD"), "bass": ("BASS", "NYLON")},
    "DOCUMENTARY": {"melody": ("PIANO", "PLUCK", "MARIMBA"), "pad": ("PAD", "ORGAN", "STRINGS"), "bass": ("BASS", "SAW_BASS")},
    "CORPORATE": {"melody": ("PLUCK", "EPIANO", "PIANO"), "pad": ("PAD", "ORGAN"), "bass": ("BASS", "SAW_BASS")},
    "NEWS": {"melody": ("PLUCK", "EPIANO", "MARIMBA"), "pad": ("ORGAN", "PAD"), "bass": ("SAW_BASS", "BASS")},
    "EDUCATIONAL": {"melody": ("MARIMBA", "PLUCK", "EPIANO"), "pad": ("PAD", "ORGAN"), "bass": ("BASS",)},
    "PODCAST": {"melody": ("NYLON", "PLUCK", "EPIANO"), "pad": ("PAD", "ORGAN"), "bass": ("BASS",)},
    "INSPIRATIONAL": {"melody": ("PIANO", "EPIANO", "PLUCK"), "pad": ("STRINGS", "ORGAN", "PAD"), "bass": ("BASS",)},
    "MOTIVATIONAL": {"melody": ("PIANO", "EPIANO", "PLUCK"), "pad": ("STRINGS", "ORGAN"), "bass": ("SAW_BASS", "BASS")},
    "TECHNOLOGY": {"melody": ("BELL", "EPIANO", "MARIMBA"), "pad": ("CHOIR", "PAD"), "bass": ("SAW_BASS",)},
    "FUTURISTIC": {"melody": ("BELL", "EPIANO", "PLUCK"), "pad": ("CHOIR", "PAD"), "bass": ("SAW_BASS",)},
    "ELECTRONIC": {"melody": ("PLUCK", "EPIANO", "BELL"), "pad": ("PAD", "CHOIR", "ORGAN"), "bass": ("SAW_BASS",)},
    "MINIMAL": {"melody": ("PLUCK", "MARIMBA", "BELL"), "pad": ("PAD",), "bass": ("SAW_BASS", "BASS")},
    "PIANO": {"melody": ("PIANO", "EPIANO"), "pad": ("PAD", "STRINGS"), "bass": ("BASS",)},
    "ACOUSTIC": {"melody": ("NYLON", "PIANO", "PLUCK"), "pad": ("PAD", "STRINGS"), "bass": ("BASS", "NYLON")},
    "LOFI": {"melody": ("EPIANO", "PIANO", "NYLON"), "pad": ("PAD", "CHOIR"), "bass": ("BASS",)},
    "CHILL": {"melody": ("PLUCK", "EPIANO", "NYLON"), "pad": ("PAD", "CHOIR"), "bass": ("BASS", "SAW_BASS")},
}
_DEFAULT_FAMILY = {
    "melody": ("PLUCK", "PIANO", "BELL"),
    "pad": ("PAD", "STRINGS"),
    "bass": ("BASS",),
}


@dataclass
class GenerationParameters:
    """User-facing request for a generated track."""

    seed: int
    duration_sec: float = 1800.0
    genre: str = Genre.AMBIENT.value
    moods: tuple[str, ...] | list[str] = ("NEUTRAL",)
    intensity: float = 50.0
    bpm: int | None = None
    key_root: str | None = None
    key_mode: str | None = None
    sample_rate: int = DEFAULT_SAMPLE_RATE
    voiceover_safe: bool = False
    energy_curve: str | None = None
    energy_points: tuple[tuple[float, float], ...] | None = None
    drums: bool = False
    drum_energy: float = 50.0
    drum_style: str = ""
    crowd_chant: bool = False
    exclude_vocals: bool = False
    drop_intensity: float = 50.0
    bass_distortion: float = 0.0
    supersaw_brightness: float = 50.0
    sidechain_amount: float = 100.0

    def validate(self) -> None:
        if self.genre not in _GENRE_PROFILES:
            raise ValidationError(f"unknown genre {self.genre!r}")
        if not isinstance(self.moods, (tuple, list)) or not self.moods:
            raise ValidationError("moods must be a non-empty sequence")
        for mood in self.moods:
            if mood not in _MOOD_MODIFIERS:
                raise ValidationError(f"unknown mood {mood!r}")
        if not 0.0 <= float(self.intensity) <= 100.0:
            raise ValidationError("intensity must be within [0, 100]")
        if float(self.duration_sec) <= 0:
            raise ValidationError("duration_sec must be positive")
        if self.duration_sec > 4 * 3600:
            raise ValidationError("duration_sec above hard limit of 4 hours")
        if self.bpm is not None and not 30 <= int(self.bpm) <= 220:
            raise ValidationError("bpm must be within [30, 220]")
        if self.key_root is not None and self.key_root not in NOTE_NAMES:
            raise ValidationError(f"invalid key_root {self.key_root!r}")
        if self.key_mode is not None and self.key_mode not in {m.value for m in VALID_MODES}:
            raise ValidationError(f"invalid key_mode {self.key_mode!r}")
        if int(self.sample_rate) not in (22050, 32000, 44100, 48000, 88200, 96000):
            raise ValidationError(f"unsupported sample_rate {self.sample_rate}")
        if not 0.0 <= float(self.drum_energy) <= 100.0:
            raise ValidationError("drum_energy must be within [0, 100]")
        for name in (
            "drop_intensity",
            "bass_distortion",
            "supersaw_brightness",
            "sidechain_amount",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValidationError(f"{name} must be within [0, 100]")
        if self.energy_curve is not None:
            from lfms.arranger.energy import known_energy_presets

            if self.energy_curve not in known_energy_presets():
                raise ValidationError(
                    f"unknown energy_curve {self.energy_curve!r}"
                )
        try:
            int(self.seed)
        except (TypeError, ValueError) as exc:
            raise ValidationError("seed must be an integer") from exc


@dataclass
class MusicPlan:
    """Resolved musical constraints; input to harmony/melody/renderer."""

    seed: int
    duration_sec: float
    genre: str
    moods: tuple[str, ...]
    intensity: float
    bpm: int
    key_root_pc: int
    key_mode: str
    density: float
    brightness_hz: float
    pulse_level: float
    melody_probability: float
    register_center: int
    reverb_amount: float
    melody_instrument: str
    pad_instrument: str = "PAD"
    bass_instrument: str = "BASS"
    perc_snare: bool = False
    drums: str = "NONE"  # NONE | LIGHT | FULL | TRIBAL | FOUR_FLOOR
    sample_rate: int = DEFAULT_SAMPLE_RATE
    voiceover_safe: bool = False
    crowd_chant: bool = False
    drop_intensity: float = 50.0
    bass_distortion: float = 0.0
    supersaw_brightness: float = 50.0
    sidechain_amount: float = 100.0
    fingerprint: str = field(default="")

    @property
    def bar_sec(self) -> float:
        return 4.0 * 60.0 / self.bpm

    @property
    def beat_sec(self) -> float:
        return 60.0 / self.bpm

    @property
    def key_name(self) -> str:
        return f"{NOTE_NAMES[self.key_root_pc]} {self.key_mode.capitalize()}"

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


def build_plan(params: GenerationParameters) -> MusicPlan:
    """Resolve GenerationParameters into a deterministic MusicPlan."""
    params.validate()
    profile = _GENRE_PROFILES[params.genre]

    rng = np.random.default_rng(SeedSystem(int(params.seed)).derive("plan"))
    bpm = int(params.bpm) if params.bpm is not None else int(rng.integers(profile.bpm_range[0], profile.bpm_range[1] + 1))
    root_name = params.key_root if params.key_root is not None else NOTE_NAMES[int(rng.integers(0, 12))]
    mode = params.key_mode if params.key_mode is not None else profile.modes[int(rng.integers(0, len(profile.modes)))]

    density = profile.density * (0.55 + 0.9 * params.intensity / 100.0)
    brightness = profile.brightness_hz * (0.75 + 0.5 * params.intensity / 100.0)
    pulse = profile.pulse * (0.4 + 1.2 * params.intensity / 100.0)
    melody_prob = profile.melody_probability * (0.4 + 1.2 * params.intensity / 100.0)
    register = profile.register_center
    reverb = profile.reverb_amount

    for mood in params.moods:
        mods = _MOOD_MODIFIERS[mood]
        density += mods.get("density_delta", 0.0)
        pulse += mods.get("pulse_delta", 0.0)
        pulse *= mods.get("pulse_mult", 1.0)
        brightness *= mods.get("brightness_mult", 1.0)
        register += int(mods.get("register_delta", 0))
        reverb += mods.get("reverb_delta", 0.0)

    density = float(np.clip(density, 0.05, 1.0))
    pulse = float(np.clip(pulse, 0.0, 1.0))
    melody_prob = float(np.clip(melody_prob, 0.0, 1.0))
    brightness = float(np.clip(brightness, 400.0, 8000.0))
    register = int(np.clip(register, 36, 72))
    reverb = float(np.clip(reverb, 0.0, 1.0))

    # Seed-driven instrument palette: same genre, different seeds get
    # different lead/pad/bass voices so tracks do not all sound alike.
    inst_rng = np.random.default_rng(
        SeedSystem(int(params.seed)).derive("instruments")
    )
    family = _INSTRUMENT_FAMILIES.get(params.genre, _DEFAULT_FAMILY)
    melody_inst = str(family["melody"][int(inst_rng.integers(0, len(family["melody"])))])
    pad_inst = str(family["pad"][int(inst_rng.integers(0, len(family["pad"])))])
    bass_inst = str(family["bass"][int(inst_rng.integers(0, len(family["bass"])))])
    snare = bool(pulse > 0.30 and inst_rng.random() < min(1.0, pulse))

    # Percussion is a first-class request: the director may explicitly
    # ask for "drums / tribal / drop / beat", in which case we guarantee a
    # driving kit rather than leaving it to the quiet genre pulse level.
    # Otherwise gentle genres keep their subtle pulse-only texture.
    drum_energy = float(params.drum_energy) if params.drum_energy is not None else params.intensity
    drum_style = (getattr(params, "drum_style", "") or "").upper()
    if params.drums:
        if drum_style == "FOUR_FLOOR":
            drum_mode = "FOUR_FLOOR"
        elif drum_energy >= 75:
            drum_mode = "TRIBAL"
        elif drum_energy >= 45:
            drum_mode = "FULL"
        else:
            drum_mode = "LIGHT"
        # explicit drums always punch through the quiet-genre pulse limit
        pw = pulse if pulse > 0.20 else 0.05 + 0.35 * drum_energy / 100.0
        pulse = max(pulse, pw)
        snare = True
    elif pulse > 0.30:
        # energy-driven pulse may still yield a snare backbeat naturally
        snare = bool(snare and drum_energy >= 25)
        drum_mode = "LIGHT" if snare else "NONE"
    else:
        snare = False
        drum_mode = "NONE"

    plan_fingerprint = fingerprint(
        [
            "PLAN",
            str(params.seed),
            params.genre,
            ",".join(tuple(params.moods)),
            f"{params.intensity:.1f}",
            str(bpm),
            f"{root_name}:{mode}",
            f"{params.duration_sec:.3f}",
        ]
    )

    return MusicPlan(
        seed=int(params.seed),
        duration_sec=float(params.duration_sec),
        genre=params.genre,
        moods=tuple(params.moods),
        intensity=float(params.intensity),
        bpm=bpm,
        key_root_pc=NOTE_NAMES.index(root_name),
        key_mode=mode,
        density=density,
        brightness_hz=brightness,
        pulse_level=pulse,
        melody_probability=melody_prob,
        register_center=register,
        reverb_amount=reverb,
        melody_instrument=melody_inst,
        pad_instrument=pad_inst,
        bass_instrument=bass_inst,
        perc_snare=snare,
        drums=drum_mode,
        sample_rate=int(params.sample_rate),
        voiceover_safe=bool(params.voiceover_safe),
        crowd_chant=bool(params.crowd_chant),
        drop_intensity=float(params.drop_intensity),
        bass_distortion=float(params.bass_distortion),
        supersaw_brightness=float(params.supersaw_brightness),
        sidechain_amount=float(params.sidechain_amount),
        fingerprint=plan_fingerprint,
    )


def genre_profile(genre: str) -> _GenreProfile:
    if genre not in _GENRE_PROFILES:
        raise ValidationError(f"unknown genre {genre!r}")
    return _GENRE_PROFILES[genre]


def known_genres() -> tuple[str, ...]:
    return tuple(sorted(_GENRE_PROFILES))


def known_moods() -> tuple[str, ...]:
    return tuple(sorted(_MOOD_MODIFIERS))


def params_from_payload(payload: dict) -> GenerationParameters:
    """Build validated ``GenerationParameters`` from a plain JSON-style dict.

    Unknown keys are ignored; seed/duration_sec/genre are required.
    """
    allowed = set(GenerationParameters.__dataclass_fields__)
    kwargs = {key: value for key, value in payload.items() if key in allowed}
    if not {"seed", "duration_sec", "genre"} <= set(kwargs):
        raise ValidationError(
            "parameters payload lacks seed/duration_sec/genre"
        )
    params = GenerationParameters(**kwargs)
    params.validate()
    return params
