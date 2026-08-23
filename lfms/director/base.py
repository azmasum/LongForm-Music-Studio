"""AI Music Director base types and provider registry (optional feature)."""
from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from lfms.core.errors import ValidationError
from lfms.generator.plan import GenerationParameters


@dataclass(frozen=True)
class DirectorSuggestion:
    """One provider's answer for a prompt."""

    params: GenerationParameters
    provider: str
    rationale: str = ""
    warnings: tuple[str, ...] = ()
    raw_payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderReply:
    """Raw provider output before normalization/coercion."""

    payload: dict
    rationale: str = ""


class DirectorProvider(ABC):
    """Adapter turning a natural-language prompt into parameter JSON.

    Implementations must never touch the network unless the user has
    explicitly enabled the AI director; ``requires_network`` documents
    what enabling means for privacy.
    """

    name: str = "abstract"
    description: str = ""
    requires_network: bool = False

    @abstractmethod
    def available(self) -> bool:
        """Cheap check whether this provider can run right now."""

    @abstractmethod
    def suggest(self, prompt: str) -> ProviderReply:
        """Return a raw parameter payload for the prompt."""


class OfflineHeuristicDirector(DirectorProvider):
    """Deterministic keyword/heuristic mapping — always available offline.

    See :mod:`lfms.director.offline` for the implementation.
    """

    name = "offline"
    description = (
        "Rule-based interpreter. Runs entirely on this machine; no data "
        "leaves the app."
    )
    requires_network = False

    def available(self) -> bool:
        return True

    def suggest(self, prompt: str) -> ProviderReply:
        from lfms.director.offline import interpret_prompt

        payload, notes = interpret_prompt(prompt)
        return ProviderReply(payload=payload, rationale="; ".join(notes))


def _ollama_host() -> str:
    return os.environ.get("LFMS_OLLAMA_HOST", "http://127.0.0.1:11434")


class OllamaDirector(DirectorProvider):
    """Local LLM via an Ollama server (localhost by default).

    Only usable when the user enables the AI director AND an Ollama
    server is reachable at the configured host. The prompt is sent to
    that server; nothing else leaves the machine.
    """

    name = "ollama"
    description = (
        "Local LLM through your own Ollama server. The prompt text is "
        "sent to the configured host (default localhost:11434)."
    )
    requires_network = True

    def __init__(self, host: str | None = None, model: str | None = None,
                 timeout_sec: float = 20.0) -> None:
        self.host = host or _ollama_host()
        self.model = model or os.environ.get("LFMS_OLLAMA_MODEL", "llama3.2")
        self.timeout_sec = float(timeout_sec)

    def available(self) -> bool:
        try:
            parsed = urllib.request.urlparse(self.host)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 80
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            return False

    def suggest(self, prompt: str) -> ProviderReply:
        instruction = (
            "You translate music briefs into JSON parameters for a "
            "procedural music generator. Answer with ONLY a JSON object "
            "using these optional keys: seed (int), duration_sec (number),"
            " genre, moods (list), intensity (0-100), bpm (30-220), "
            "key_root like 'C'/'F#', key_mode ('MAJOR','MINOR','DORIAN',"
            "'PHRYGIAN','LYDIAN','MIXOLYDIAN'), voiceover_safe (bool), "
            "energy_curve ('FLAT','SLOW_BUILD','CINEMATIC_BUILD',"
            "'EMOTIONAL_WAVE','DOCUMENTARY','SUSPENSE','RELAXATION',"
            "'INTRO_PEAK_OUTRO'). Valid genres include AMBIENT, "
            "CINEMATIC, DOCUMENTARY, EMOTIONAL, CORPORATE, TECHNOLOGY, "
            "DARK, SUSPENSE, MYSTERY, HORROR, MEDITATION, LOFI, CHILL, "
            "ELECTRONIC, NATURE, NEWS, PODCAST, MOTIVATIONAL.\nBrief: "
            + prompt
        )
        body = json_dumps(
            {
                "model": self.model,
                "prompt": instruction,
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.host.rstrip("/") + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_sec
            ) as response:
                import json

                outer = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError(f"Ollama request failed: {exc}") from exc
        payload = extract_json_object(str(outer.get("response", "")))
        if not isinstance(payload, dict):
            raise ValidationError("Ollama returned no usable JSON object")
        return ProviderReply(payload=payload, rationale=f"model {self.model}")


def json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj)


def extract_json_object(text: str) -> dict:
    """Best-effort extraction of the first JSON object in messy LLM text."""
    import json

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for idx in range(start, len(cleaned)):
            if cleaned[idx] == "{":
                depth += 1
            elif cleaned[idx] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(cleaned[start : idx + 1])
                        if isinstance(candidate, dict):
                            return candidate
                    except ValueError:
                        break
        start = cleaned.find("{", start + 1)
    return {}


PROVIDERS: dict[str, type[DirectorProvider]] = {
    OfflineHeuristicDirector.name: OfflineHeuristicDirector,
    OllamaDirector.name: OllamaDirector,
}


def known_providers() -> tuple[str, ...]:
    return tuple(PROVIDERS)


def create_provider(name: str, **kwargs) -> DirectorProvider:
    try:
        cls = PROVIDERS[name]
    except KeyError as exc:
        raise ValidationError(f"unknown director provider {name!r}") from exc
    return cls(**kwargs)
