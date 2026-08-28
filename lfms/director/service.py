"""MusicDirector: gated entry point to the optional AI director feature.

Disabled by default; ``enable(True)`` requires explicit consent. All
provider output passes through the same normalization so that even a
misbehaving LLM cannot produce invalid generation parameters.
"""
from __future__ import annotations

from lfms.core.errors import ValidationError
from lfms.director.base import (
    DirectorSuggestion,
    create_provider,
    known_providers,
)
from lfms.generator.plan import (
    GenerationParameters,
    known_moods,
    params_from_payload,
)

_MIN_DURATION = 10.0
_MAX_DURATION = 4 * 3600.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def coerce_payload(payload: dict, prompt: str) -> tuple[dict, list[str]]:
    """Normalize any provider payload into valid, clamped parameters."""
    warnings: list[str] = []
    clean: dict = dict(payload)

    genre = clean.get("genre")
    if not isinstance(genre, str) or not genre:
        if "genre" in clean:
            warnings.append("dropped invalid genre")
        clean["genre"] = "AMBIENT"
        warnings.append("no usable genre; fell back to AMBIENT")

    moods = clean.get("moods")
    known_mood_set = set(known_moods())
    if isinstance(moods, (list, tuple)):
        filtered = [str(m).upper() for m in moods if str(m).upper() in known_mood_set]
        dropped = len(list(moods)) - len(filtered)
        if dropped:
            warnings.append(f"dropped {dropped} unknown mood(s)")
        clean["moods"] = tuple(filtered[:3]) or ("NEUTRAL",)
    else:
        if "moods" in clean:
            warnings.append("dropped invalid moods")
        clean["moods"] = ("NEUTRAL",)

    try:
        duration = float(clean.get("duration_sec"))
        if duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        warnings.append("invalid duration; used 600 s")
        duration = 600.0
    clamped_duration = _clamp(duration, _MIN_DURATION, _MAX_DURATION)
    if clamped_duration != duration:
        warnings.append(f"clamped duration {duration:g} -> {clamped_duration:g} s")
    clean["duration_sec"] = clamped_duration

    try:
        intensity = float(clean.get("intensity", 50.0))
    except (TypeError, ValueError):
        warnings.append("invalid intensity; used 50")
        intensity = 50.0
    clamped_intensity = _clamp(intensity, 0.0, 100.0)
    if clamped_intensity != intensity:
        warnings.append(f"clamped intensity {intensity:g} -> {clamped_intensity:g}")
    clean["intensity"] = clamped_intensity

    if clean.get("bpm") is not None:
        try:
            bpm = int(clean["bpm"])
            if not 30 <= bpm <= 220:
                raise ValueError
            clean["bpm"] = bpm
        except (TypeError, ValueError):
            warnings.append("dropped invalid bpm")
            clean["bpm"] = None

    for key in ("key_root", "key_mode", "energy_curve"):
        if key in clean and clean[key] is None:
            del clean[key]

    seed = clean.get("seed")
    try:
        clean["seed"] = int(seed)
    except (TypeError, ValueError):
        digest = __import__("hashlib").sha256(
            prompt.strip().lower().encode("utf-8")
        ).digest()
        clean["seed"] = int.from_bytes(digest[:8], "big") % 2_147_483_647
        warnings.append("derived stable seed from prompt")
    clean["seed"] %= 2_147_483_648

    if "voiceover_safe" in clean:
        clean["voiceover_safe"] = bool(clean["voiceover_safe"])

    if "drums" in clean:
        clean["drums"] = bool(clean["drums"])
    try:
        clean["drum_energy"] = _clamp(float(clean.get("drum_energy", 50.0)), 0.0, 100.0)
    except (TypeError, ValueError):
        clean["drum_energy"] = 50.0
    return clean, warnings


class MusicDirector:
    """User-facing director service. **Off unless explicitly enabled.**"""

    def __init__(self) -> None:
        self.enabled = False
        self._provider_name = "offline"

    # ------------------------------------------------------------- gating

    def enable(self, consent: bool) -> None:
        if consent is not True:
            raise ValidationError(
                "AI Music Director requires explicit consent to enable"
            )
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    # ----------------------------------------------------------- providers

    def provider_names(self) -> tuple[str, ...]:
        return known_providers()

    def use(self, provider_name: str) -> None:
        if provider_name not in known_providers():
            raise ValidationError(f"unknown director provider {provider_name!r}")
        self._provider_name = provider_name

    @property
    def active_provider(self) -> str:
        return self._provider_name

    # -------------------------------------------------------------- direct

    def direct(self, prompt: str) -> DirectorSuggestion:
        if not self.enabled:
            raise ValidationError(
                "AI Music Director is disabled; enable it explicitly first"
            )
        text = str(prompt).strip()
        if not text:
            raise ValidationError("prompt is empty")
        provider = create_provider(self._provider_name)
        reply = provider.suggest(text)
        payload, warnings = coerce_payload(dict(reply.payload), prompt=text)
        try:
            params = params_from_payload(payload)
        except Exception as exc:  # noqa: BLE001 - advisory feature must not crash
            fallback = GenerationParameters(
                seed=payload.get("seed", 1),
                duration_sec=600.0,
                genre="AMBIENT",
                moods=("NEUTRAL",),
                intensity=50.0,
            )
            params = fallback
            warnings.append(f"provider payload unusable ({exc}); safe defaults applied")
        return DirectorSuggestion(
            params=params,
            provider=provider.name,
            rationale=reply.rationale,
            warnings=tuple(warnings),
            raw_payload=dict(reply.payload),
        )
