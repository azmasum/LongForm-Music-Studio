"""Deterministic prompt interpreter — the always-offline director."""
from __future__ import annotations

import hashlib
import re

from lfms.generator.plan import known_moods

_DEFAULT_DURATION = 600.0
_MAX_DURATION = 7200.0

_GENRE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("lo-fi", "LOFI"), ("lofi", "LOFI"),
    ("chillhop", "CHILL"), ("chill", "CHILL"),
    ("meditation", "MEDITATION"), ("meditative", "MEDITATION"),
    ("yoga", "MEDITATION"), ("spa", "RELAXATION"),
    ("sleep", "RELAXATION"), ("relax", "RELAXATION"),
    ("documentary", "DOCUMENTARY"), ("docu", "DOCUMENTARY"),
    ("trailer", "DRAMATIC"), ("dramatic", "DRAMATIC"),
    ("horror", "HORROR"), ("scary", "HORROR"), ("haunting", "HORROR"),
    ("suspense", "SUSPENSE"), ("thriller", "SUSPENSE"),
    ("mystery", "MYSTERY"), ("noir", "MYSTERY"), ("detective", "MYSTERY"),
    ("sci-fi", "FUTURISTIC"), ("cyberpunk", "FUTURISTIC"),
    ("futuristic", "FUTURISTIC"),
    ("technology", "TECHNOLOGY"), ("startup demo", "TECHNOLOGY"),
    ("app demo", "TECHNOLOGY"), ("product demo", "TECHNOLOGY"),
    ("corporate", "CORPORATE"), ("business", "CORPORATE"),
    ("news", "NEWS"), ("broadcast", "NEWS"),
    ("podcast", "PODCAST"), ("interview", "PODCAST"),
    ("storytelling", "STORYTELLING"), ("narrative", "STORYTELLING"),
    ("educational", "EDUCATIONAL"), ("tutorial", "EDUCATIONAL"),
    ("explainer", "EDUCATIONAL"), ("course", "EDUCATIONAL"),
    ("motivational", "MOTIVATIONAL"), ("workout", "MOTIVATIONAL"),
    ("gym", "MOTIVATIONAL"),
    ("inspirational", "INSPIRATIONAL"), ("uplifting", "EMOTIONAL"),
    ("cinematic", "CINEMATIC"), ("film score", "CINEMATIC"),
    ("movie", "CINEMATIC"),
    ("emotional", "EMOTIONAL"), ("heartfelt", "EMOTIONAL"),
    ("acoustic", "ACOUSTIC"), ("guitar", "ACOUSTIC"),
    ("piano", "PIANO"),
    ("electronic", "ELECTRONIC"), ("synthwave", "ELECTRONIC"),
    ("synth", "ELECTRONIC"), ("edm", "ELECTRONIC"),
    ("minimal", "MINIMAL"),
    ("nature", "NATURE"), ("forest", "NATURE"), ("rain", "NATURE"),
    ("ocean", "NATURE"), ("wildlife", "NATURE"),
    ("dark", "DARK"), ("ominous", "DARK"), ("brooding", "DARK"),
    ("ambient", "AMBIENT"), ("atmospheric", "AMBIENT"),
    ("drone", "AMBIENT"),
)

_MOOD_WORDS: tuple[tuple[str, str], ...] = (
    ("peaceful", "PEACEFUL"), ("serene", "PEACEFUL"),
    ("tranquil", "PEACEFUL"), ("calm", "CALM"),
    ("soothing", "CALM"),
    ("melancholic", "SAD"), ("melancholy", "SAD"), ("sad", "SAD"),
    ("hopeful", "HOPEFUL"), ("uplifting", "HOPEFUL"),
    ("optimistic", "HOPEFUL"),
    ("mysterious", "MYSTERIOUS"), ("enigmatic", "MYSTERIOUS"),
    ("suspenseful", "SUSPENSEFUL"), ("tense", "TENSE"),
    ("nervous", "TENSE"), ("anxious", "TENSE"),
    ("energetic", "ENERGETIC"), ("driving", "ENERGETIC"),
    ("powerful", "POWERFUL"), ("bold", "POWERFUL"), ("epic", "EPIC"),
    ("grand", "EPIC"), ("heroic", "EPIC"),
    ("warm", "WARM"), ("cozy", "WARM"),
    ("nostalgic", "NOSTALGIC"), ("retro", "NOSTALGIC"),
    ("dreamy", "DREAMY"), ("hazy", "DREAMY"),
    ("lonely", "LONELY"), ("solitary", "LONELY"),
    ("emotional", "EMOTIONAL"), ("touching", "EMOTIONAL"),
    ("futuristic", "FUTURISTIC"), ("scientific", "SCIENTIFIC"),
)

_INTENSITY_WORDS: tuple[tuple[str, int], ...] = (
    ("gentle", 28), ("soft", 30), ("subtle", 32), ("quiet", 32),
    ("delicate", 30),
    ("calm", 35), ("peaceful", 35), ("soothing", 33),
    ("lively", 62), ("groovy", 64),
    ("driving", 72), ("energetic", 72), ("punchy", 70),
    ("intense", 78), ("powerful", 76), ("dramatic", 78),
    ("epic", 86), ("explosive", 88), ("climax", 90),
)

_ENERGY_WORDS: tuple[tuple[str, str], ...] = (
    ("crescendo", "SLOW_BUILD"), ("builds up", "SLOW_BUILD"),
    ("slowly builds", "SLOW_BUILD"), ("builds", "SLOW_BUILD"),
    ("rises", "SLOW_BUILD"), ("grows", "SLOW_BUILD"),
    ("cinematic build", "CINEMATIC_BUILD"), ("swells", "EMOTIONAL_WAVE"),
    ("waves", "EMOTIONAL_WAVE"), ("ebbs and flows", "EMOTIONAL_WAVE"),
    ("steady", "FLAT"), ("constant", "FLAT"), ("even level", "FLAT"),
)

_VOICEOVER_WORDS = (
    "voiceover", "voice-over", "voice over", "narration", "narrator",
    "spoken word", "under speech",
)

_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr)\b")
_MINUTES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min)\b")
_SECONDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|sec)\b")
_BPM_RE = re.compile(r"\b(\d{2,3})\s*bpm\b")
_INTENSITY_RE = re.compile(r"intensity\D{0,6}(\d{1,3})\s*%?")
_KEY_RE = re.compile(
    r"\bin\s+([A-Ga-g])\s*(sharp|#|flat|b)?\s*"
    r"(major|minor|dorian|phrygian|lydian|mixolydian)\b"
)
_FLAT_TO_SHARP = {
    "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
}


def _parse_duration(text: str) -> float | None:
    hours = _HOURS_RE.search(text)
    minutes = _MINUTES_RE.search(text)
    seconds = _SECONDS_RE.search(text)
    if hours is None and minutes is None and seconds is None:
        if re.search(r"half an hour", text):
            return 1800.0
        return None
    total = 0.0
    if hours:
        total += float(hours.group(1)) * 3600.0
    if minutes:
        total += float(minutes.group(1)) * 60.0
    if seconds:
        total += float(seconds.group(1))
    return total


def _stable_seed(prompt: str) -> int:
    digest = hashlib.sha256(prompt.strip().lower().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 2_147_483_647


def interpret_prompt(prompt: str) -> tuple[dict, list[str]]:
    """Map free text to a parameter payload plus human-readable notes.

    Deterministic: the same prompt always produces the same result.
    """
    text = " ".join(str(prompt).lower().split())
    notes: list[str] = []
    payload: dict = {"seed": _stable_seed(text)}

    genre = next(
        (value for word, value in _GENRE_PATTERNS if word in text), None
    )
    payload["genre"] = genre or "AMBIENT"
    notes.append(f"genre={payload['genre']}")

    moods: list[str] = []
    for word, mood in _MOOD_WORDS:
        if word in text and mood not in moods:
            moods.append(mood)
        if len(moods) >= 3:
            break
    payload["moods"] = moods or ["NEUTRAL"]
    notes.append("moods=" + ",".join(payload["moods"]))

    duration = _parse_duration(text)
    payload["duration_sec"] = duration if duration else _DEFAULT_DURATION
    if duration is None:
        notes.append("duration=default 600 s")
    else:
        notes.append(f"duration={duration:g} s")

    bpm_match = _BPM_RE.search(text)
    if bpm_match:
        payload["bpm"] = max(30, min(220, int(bpm_match.group(1))))
        notes.append(f"bpm={payload['bpm']}")

    intensity_override = _INTENSITY_RE.search(text)
    if intensity_override:
        payload["intensity"] = float(intensity_override.group(1))
    else:
        for word, value in _INTENSITY_WORDS:
            if word in text:
                payload["intensity"] = float(value)
                break
        else:
            payload["intensity"] = 50.0
    notes.append(f"intensity={payload['intensity']:g}")

    key_match = _KEY_RE.search(text)
    if key_match:
        letter = key_match.group(1).upper()
        accidental = (key_match.group(2) or "").strip()
        root = letter + ("#" if accidental in ("sharp", "#") else "")
        if accidental in ("flat", "b"):
            root = _FLAT_TO_SHARP.get(letter + "b", root)
        mode = key_match.group(3).upper()
        payload["key_root"] = root
        payload["key_mode"] = mode
        notes.append(f"key={root} {mode}")

    if any(word in text for word in _VOICEOVER_WORDS):
        payload["voiceover_safe"] = True
        notes.append("voiceover-safe")

    for word, curve in _ENERGY_WORDS:
        if word in text:
            payload["energy_curve"] = curve
            notes.append(f"energy={curve}")
            break

    known = set(known_moods())
    payload["moods"] = [m for m in payload["moods"] if m in known]
    return payload, notes
