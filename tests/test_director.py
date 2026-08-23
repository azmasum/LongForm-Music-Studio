"""AI Music Director tests: heuristic interpreter, gating, coercion."""
from __future__ import annotations

import pytest

from lfms.core.errors import ValidationError
from lfms.director import (
    DirectorProvider,
    MusicDirector,
    coerce_payload,
    create_provider,
    known_providers,
)
from lfms.director.base import ProviderReply
from lfms.director.offline import interpret_prompt
from lfms.generator.composer import Composer
from lfms.generator.plan import params_from_payload

# ----------------------------------------------------------- interpreter

def test_documentary_narration_prompt():
    payload, notes = interpret_prompt(
        "calm documentary bed under narration, 5 minutes"
    )
    assert payload["genre"] == "DOCUMENTARY"
    assert payload["voiceover_safe"] is True
    assert "CALM" in payload["moods"]
    assert payload["duration_sec"] == 300.0


def test_epic_trailer_prompt_is_loud_and_short():
    payload, _ = interpret_prompt("epic dramatic trailer 90 seconds")
    assert payload["genre"] in ("DRAMATIC", "CINEMATIC")
    assert payload["intensity"] >= 78.0
    assert payload["duration_sec"] == 90.0


def test_lofi_chill_duration_minutes():
    payload, notes = interpret_prompt("lofi chill beat for studying, 3 minutes")
    assert payload["genre"] == "LOFI"
    assert payload["duration_sec"] == 180.0


def test_bpm_and_numeric_intensity():
    payload, notes = interpret_prompt("energetic electronic workout, 120 bpm, intensity 65%")
    assert payload["bpm"] == 120
    assert payload["intensity"] == 65.0


@pytest.mark.parametrize(
    ("text", "root", "mode"),
    [
        ("ambient piece in C major", "C", "MAJOR"),
        ("tense cue in F# minor", "F#", "MINOR"),
        ("warm acoustic song in Bb mixolydian", "A#", "MIXOLYDIAN"),
        ("dark drone in D dorian", "D", "DORIAN"),
    ],
)
def test_key_parsing(text, root, mode):
    payload, _ = interpret_prompt(text)
    assert payload["key_root"] == root
    assert payload["key_mode"] == mode


def test_energy_curve_detection():
    payload, notes = interpret_prompt("strings that slowly builds over the bed")
    assert payload["energy_curve"] == "SLOW_BUILD"


def test_interpreter_is_deterministic():
    prompt = "hopeful corporate technology demo, 2 minutes"
    first, first_notes = interpret_prompt(prompt)
    second, second_notes = interpret_prompt(prompt)
    assert first == second and first_notes == second_notes
    seed = first.pop("seed")
    second.pop("seed")
    assert first == second
    assert 0 <= seed < 2_147_483_648


def test_plain_prompt_falls_back_to_sensible_defaults():
    payload, notes = interpret_prompt("music please")
    assert payload["genre"] == "AMBIENT"
    assert payload["moods"] == ["NEUTRAL"]
    assert payload["duration_sec"] == 600.0
    assert payload["intensity"] == 50.0


def test_half_an_hour_phrase():
    payload, _ = interpret_prompt("relaxing spa music for half an hour")
    assert payload["duration_sec"] == 1800.0


# --------------------------------------------------------------- gating

def test_director_disabled_by_default_and_requires_consent():
    director = MusicDirector()
    assert director.enabled is False
    with pytest.raises(ValidationError):
        director.direct("anything")
    with pytest.raises(ValidationError):
        director.enable(False)
    with pytest.raises(ValidationError):
        director.enable("yes" == "no")
    director.enable(True)
    assert director.enabled is True
    director.disable()
    with pytest.raises(ValidationError):
        director.direct("again")


def test_unknown_provider_rejected():
    director = MusicDirector()
    with pytest.raises(ValidationError):
        director.use("skynet")


def test_empty_prompt_rejected_when_enabled():
    director = MusicDirector()
    director.enable(True)
    with pytest.raises(ValidationError):
        director.direct("   ")


def test_offline_provider_end_to_end_composes():
    director = MusicDirector()
    director.enable(True)
    suggestion = director.direct("gentle meditation soundscape for sleep, 4 minutes")
    assert suggestion.provider == "offline"
    params = suggestion.params
    assert params.genre == "MEDITATION"
    assert params.duration_sec == 240.0
    composition = Composer(params).compose()  # must be renderable
    assert composition.total_events() > 0


# ------------------------------------------------------------- registry

def test_registry_contains_offline_and_ollama():
    names = known_providers()
    assert "offline" in names and "ollama" in names
    offline = create_provider("offline")
    assert isinstance(offline, DirectorProvider)
    assert offline.available() is True


def test_ollama_with_dead_port_unavailable():
    provider = create_provider(
        "ollama", host="http://127.0.0.1:9", timeout_sec=0.5
    )
    assert provider.available() is False
    with pytest.raises(ValidationError):
        provider.suggest("calm ambient")


# ------------------------------------------------------------- coercion

class _StubProvider(DirectorProvider):
    name = "stub"

    def __init__(self, payload):
        self._payload = payload

    def available(self):
        return True

    def suggest(self, prompt):
        return ProviderReply(payload=self._payload)


def test_coerce_clamps_out_of_range_values():
    clean, warnings = coerce_payload(
        {
            "seed": 5,
            "duration_sec": 99_999,
            "genre": "AMBIENT",
            "intensity": 250,
            "bpm": 999,
            "moods": ("CALM", "NOT-A-MOOD"),
        },
        prompt="x",
    )
    assert clean["duration_sec"] <= 4 * 3600
    assert clean["intensity"] == 100.0
    assert clean["bpm"] is None
    assert clean["moods"] == ("CALM",)
    assert any("clamped" in w for w in warnings)
    params_from_payload(clean)  # must validate


def test_coerce_derives_stable_seed_when_missing_or_garbage():
    clean_a, warn_a = coerce_payload({"duration_sec": 30, "genre": "LOFI"}, prompt="night lo-fi loop")
    clean_b, warn_b = coerce_payload({"seed": "abc", "duration_sec": 30, "genre": "LOFI"}, prompt="night lo-fi loop")
    assert any("seed" in w for w in warn_a + warn_b)
    assert clean_a["seed"] == clean_b["seed"]
    assert 0 <= clean_a["seed"] < 2_147_483_648


def test_service_survives_hostile_payload_via_stub(monkeypatch):
    from lfms.director import base as base_mod
    from lfms.director import service as service_mod

    monkeypatch.setitem(base_mod.PROVIDERS, "stub", _StubProvider)
    original = service_mod.create_provider
    monkeypatch.setattr(
        service_mod,
        "create_provider",
        lambda name, **kw: (
            _StubProvider({"seed": "junk", "genre": 42, "duration_sec": "soon"})
            if name == "stub"
            else original(name, **kw)
        ),
    )

    director = MusicDirector()
    director.enable(True)
    director.use("stub")
    suggestion = director.direct("whatever")
    assert suggestion.params.genre == "AMBIENT"
    assert suggestion.warnings  # problems were reported honestly
    Composer(suggestion.params).compose()


def test_extract_json_object_handles_fenced_and_embedded_json():
    from lfms.director.base import extract_json_object

    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Sure! {"genre": "LOFI"} hope it helps') == {
        "genre": "LOFI"
    }
    assert extract_json_object("no json at all") == {}
