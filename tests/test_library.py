"""Library service tests: items, search, tags, favorites, collections."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lfms.core.errors import ValidationError
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import (
    Item,
    LibraryService,
    humanized_stem,
    normalize_tag,
    smart_tags_for_generation,
)


@pytest.fixture()
def lib():
    service = LibraryService(":memory:")
    yield service
    service.close()


def _composition(duration_sec: float = 30.0):
    params = GenerationParameters(
        seed=42,
        duration_sec=duration_sec,
        genre="DOCUMENTARY",
        moods=("CALM",),
        intensity=40.0,
        voiceover_safe=True,
    )
    params.validate()
    return Composer(params).compose(), params


# ------------------------------------------------------------------ items

def test_add_and_get_item_roundtrip(lib):
    item = lib.add_item("Rain Loop", path="/audio/rain.wav", duration_sec=12.5)
    assert isinstance(item, Item)
    fetched = lib.get(item.id)
    assert fetched.title == "Rain Loop"
    assert fetched.path == "/audio/rain.wav"
    assert fetched.favorite is False
    assert fetched.to_dict()["tags"] == []


def test_duplicate_path_rejected(lib):
    lib.add_item("One", path="same.wav")
    with pytest.raises(ValidationError):
        lib.add_item("Two", path="same.wav")
    assert len(lib.list_items()) == 1


def test_title_validation(lib):
    with pytest.raises(ValidationError):
        lib.add_item("   ")
    with pytest.raises(ValidationError):
        lib.add_item("x" * 201)


def test_delete_cascades_tags(lib):
    item = lib.add_item("Temp")
    lib.add_tag(item.id, "ambient")
    lib.delete_item(item.id)
    with pytest.raises(ValidationError):
        lib.get(item.id)
    assert lib.all_tags() == ()


# ------------------------------------------------------- compositions/import

def test_register_composition_with_smart_tags(lib):
    composition, params = _composition()
    item = lib.register_composition(composition, params, title="Doc Bed 30s")
    assert item.kind == "GENERATED"
    assert item.bpm == pytest.approx(composition.bpm)
    assert item.fingerprint == composition.fingerprint
    tags = set(item.tags)
    assert "genre:documentary" in tags
    assert "mood:calm" in tags
    assert "voiceover-safe" in tags
    assert any(t.startswith("bpm:") for t in tags)
    payload = json.loads(item.params_json)
    assert payload["seed"] == 42


def test_import_audio_file_measures_and_tags(lib, tmp_path: Path):
    sr = 22050
    t = np.arange(int(sr * 2.0)) / sr
    quiet = (0.01 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)[None, :]
    wav = tmp_path / "quiet_bed.wav"
    sf.write(str(wav), quiet.T, sr)
    item = lib.import_audio_file(wav)
    assert item.kind == "AUDIO_FILE"
    assert item.duration_sec == pytest.approx(2.0, abs=0.05)
    assert item.sample_rate == sr
    assert item.channels == 1
    assert item.integrated_lufs is not None and item.integrated_lufs < -24
    assert "mono" in item.tags
    assert "level:quiet" in item.tags
    assert "sting" in item.tags
    assert item.title == "Quiet bed"


def test_import_missing_file_raises(lib, tmp_path: Path):
    with pytest.raises(ValidationError):
        lib.import_audio_file(tmp_path / "ghost.wav")


# --------------------------------------------------------------- searching

def test_search_matches_title_path_fingerprint_and_tag(lib):
    a = lib.add_item("Ocean Waves", path="/sfx/ocean.wav")
    b = lib.add_item("Wind", fingerprint="fp-123")
    lib.add_tag(a.id, "nature ambience")

    assert [i.id for i in lib.list_items("ocean")] == [a.id]
    assert [i.id for i in lib.list_items("/sfx")] == [a.id]
    assert [i.id for i in lib.list_items("fp-123")] == [b.id]
    assert [i.id for i in lib.list_items("ambience")] == [a.id]
    assert lib.list_items("nothing-matches") == ()


def test_search_is_case_insensitive(lib):
    lib.add_item("Deep Focus")
    assert len(lib.list_items("DEEP focus")) == 1


def test_filters_tag_favorite_collection(lib):
    keep = lib.add_item("Keep Me")
    drop = lib.add_item("Other")
    lib.add_tag(keep.id, "rain")
    lib.set_favorite(keep.id, True)

    assert [i.id for i in lib.list_items(tag="rain")] == [keep.id]
    assert [i.id for i in lib.list_items(favorite_only=True)] == [keep.id]
    assert {i.id for i in lib.list_items()} == {keep.id, drop.id}

    lib.create_collection("Storms")
    lib.add_to_collection("Storms", keep.id)
    assert [i.id for i in lib.list_items(collection="Storms")] == [keep.id]


def test_sort_orders(lib):
    long_item = lib.add_item("Zulu", duration_sec=900.0)
    lib.add_item("Alpha", duration_sec=10.0)
    titles = [i.title for i in lib.list_items(sort="title_asc")]
    assert titles == ["Alpha", "Zulu"]
    assert lib.list_items(sort="duration_desc")[0].id == long_item.id
    with pytest.raises(ValidationError):
        lib.list_items(sort="nonsense")


def test_unknown_metadata_field_rejected(lib):
    with pytest.raises(ValidationError):
        lib.add_item("Bad", nonsense=1)


# -------------------------------------------------------------------- tags

def test_tags_normalize_dedupe_and_remove(lib):
    item = lib.add_item("Tagged")
    lib.add_tag(item.id, "  Rain   Loop ")
    lib.add_tag(item.id, "rain loop")
    item_updated = lib.get(item.id)
    assert item_updated.tags == ("rain loop",)
    updated = lib.remove_tag(item.id, "RAIN LOOP")
    assert updated.tags == ()
    with pytest.raises(ValidationError):
        lib.add_tag(item.id, "")


def test_smart_tag_helpers():
    params_json = json.dumps(
        {
            "genre": "LOFI",
            "moods": ["CHILL"],
            "voiceover_safe": True,
            "intensity": 20,
        }
    )
    tags = set(smart_tags_for_generation(params_json, bpm=82.4))
    assert {"genre:lofi", "mood:chill", "voiceover-safe", "energy:low", "bpm:80"} <= tags
    assert smart_tags_for_generation(None, None) == ()
    assert normalize_tag("A B") == "a b"


# ------------------------------------------------- favorites & collections

def test_favorite_and_notes_persist(tmp_path: Path):
    db = tmp_path / "lib.db"
    first = LibraryService(db)
    item = first.add_item("Persisted")
    first.set_favorite(item.id, True)
    first.update_notes(item.id, "nice bed")
    first.close()

    second = LibraryService(db)
    loaded = second.get(item.id)
    assert loaded.favorite is True
    assert loaded.notes == "nice bed"
    second.close()


def test_collections_crud_and_membership(lib):
    lib.create_collection("Focus Sets")
    with pytest.raises(ValidationError):
        lib.create_collection("Focus Sets")
    item = lib.add_item("Member")
    lib.add_to_collection("Focus Sets", item.id)
    assert [i.id for i in lib.collection_items("Focus Sets")] == [item.id]
    lib.remove_from_collection("Focus Sets", item.id)
    assert lib.collection_items("Focus Sets") == ()
    lib.delete_collection("Focus Sets")
    with pytest.raises(ValidationError):
        lib._collection_id("Focus Sets")


def test_delete_missing_entities_raise(lib):
    with pytest.raises(ValidationError):
        lib.delete_item(999)
    with pytest.raises(ValidationError):
        lib.set_favorite(999, True)
    with pytest.raises(ValidationError):
        lib.add_to_collection("Nope", 1)
    with pytest.raises(ValidationError):
        lib.delete_collection("Nope")


def test_humanized_stem():
    assert humanized_stem("rainy_day-loop.mp3") == "Rainy day loop"
    assert humanized_stem(".wav") == ".wav"
