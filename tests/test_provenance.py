"""Provenance center tests: certificate build/export and verification."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService
from lfms.provenance import (
    DEFAULT_LICENSE_NOTE,
    ProvenanceRecord,
    build_record,
    format_duration,
    record_from_item,
    verify_item,
    verify_parameters,
    write_certificate,
)


def _composition(seed: int = 99, duration: float = 25.0):
    params = GenerationParameters(
        seed=seed,
        duration_sec=duration,
        genre="DOCUMENTARY",
        moods=("CALM",),
        intensity=40.0,
        voiceover_safe=True,
    )
    params.validate()
    return Composer(params).compose(), params


# --------------------------------------------------------------- building

def test_build_record_minimal_has_defaults():
    record = build_record(title="Solo Bed", created_at="2026-08-23T00:00:00+00:00")
    assert record.schema_version == 1
    assert record.app_name == "LongForm Music Studio"
    assert record.license_note == DEFAULT_LICENSE_NOTE
    assert record.parameters == {} and record.loudness is None
    assert record.to_dict()["created_at"].startswith("2026-08-23")


def test_build_record_enriched_from_composition():
    composition, params = _composition()
    record = build_record(
        title="Enriched",
        parameters={"seed": params.seed, "genre": str(params.genre)},
        composition=composition,
        created_at="2026-08-23T00:00:00+00:00",
    )
    assert record.fingerprint == composition.fingerprint
    assert record.bpm == pytest.approx(composition.bpm)
    assert record.key_name == composition.key_name
    assert record.repetition_score is not None


def test_json_roundtrip_preserves_everything():
    composition, params = _composition(seed=5)
    record = build_record(
        title="Roundtrip",
        parameters={"seed": params.seed},
        composition=composition,
        qc_status="READY",
        created_at="2026-08-23T12:00:00+00:00",
    )
    parsed = json.loads(record.to_json())
    assert ProvenanceRecord(**{**parsed}) == record


def test_text_certificate_contains_key_fields():
    composition, params = _composition(seed=7)
    record = build_record(
        title="Text Cert",
        parameters={"seed": params.seed, "genre": "DOCUMENTARY"},
        composition=composition,
        qc_status="READY",
        created_at="2026-08-23T09:00:00+00:00",
    )
    text = record.to_text()
    for needle in (
        "PROVENANCE CERTIFICATE",
        "Text Cert",
        composition.fingerprint,
        "seed",
        "QC status             : READY",
        "LongForm Music Studio",
        "royalty-free",
    ):
        assert needle in text


def test_format_duration_variants():
    assert format_duration(None) == "-"
    assert format_duration(59.4) == "0:59"
    assert format_duration(600.0) == "10:00"
    assert format_duration(3675.0) == "1:01:15"


# ---------------------------------------------------------------- files

def test_write_certificate_txt_and_json(tmp_path: Path):
    composition, _ = _composition(seed=11)
    record = build_record(
        title="Saved Cert", fingerprint=composition.fingerprint,
        created_at="2026-08-23T00:00:00+00:00",
    )
    txt_path = write_certificate(record, tmp_path, fmt="txt")
    json_path = write_certificate(record, tmp_path, fmt=".JSON")
    assert txt_path.is_file() and txt_path.suffix == ".txt"
    assert json_path.is_file() and json_path.name.endswith(".json")
    text = txt_path.read_text(encoding="utf-8")
    assert "PROVENANCE CERTIFICATE" in text
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["fingerprint"] == composition.fingerprint
    with pytest.raises(ValueError):
        write_certificate(record, tmp_path, fmt="pdf")


def test_write_certificate_without_fingerprint_uses_fallback(tmp_path: Path):
    record = build_record(
        title="Mystery Item/with slash", created_at="2026-08-23T00:00:00+00:00"
    )
    path = write_certificate(record, tmp_path / "out", fmt="txt")
    assert path.parent.name == "out"
    assert "UNCERTIFIED" in path.name
    assert "/" not in path.stem.replace("LFMS-cert-", "")


# ------------------------------------------------------------ verification

def test_verify_parameters_matches_genuine_generation():
    composition, params = _composition(seed=123, duration=20.0)
    payload = {
        "seed": params.seed,
        "duration_sec": params.duration_sec,
        "genre": str(params.genre),
        "moods": [str(m) for m in params.moods],
        "intensity": params.intensity,
        "voiceover_safe": params.voiceover_safe,
    }
    result = verify_parameters(payload, composition.fingerprint)
    assert result.ok and result.status == "VERIFIED"
    assert result.recomputed_fingerprint == composition.fingerprint

    tampered = dict(payload, seed=payload["seed"] + 1)
    bad = verify_parameters(tampered, composition.fingerprint)
    assert not bad.ok
    assert "mismatch" in bad.message
    assert bad.recomputed_fingerprint != composition.fingerprint


def test_verify_rejects_unusable_payloads():
    ok_payload = {
        "seed": 1, "duration_sec": 20.0, "genre": "DOCUMENTARY",
    }
    assert verify_parameters(ok_payload, "nope").ok is False  # mismatch path
    result = verify_parameters({"genre": "X"}, "fp")
    assert not result.ok and "unusable" in result.message


def test_verify_item_through_library(tmp_path: Path):
    lib = LibraryService(":memory:")
    try:
        composition, params = _composition(seed=77, duration=22.0)
        item = lib.register_composition(composition, params, title="Verifiable")
        good = verify_item(item)
        assert good.ok

        tampered = lib.add_item("Tampered", fingerprint="LFMS-XXXX-XXXX-XXXX")
        lib.add_tag(tampered.id, "x")
        # reuse genuine params_json but fake fingerprint
        lib._conn.execute(
            "UPDATE items SET params_json=? WHERE id=?",
            (item.params_json, tampered.id),
        )
        lib._conn.commit()
        bad = verify_item(lib.get(tampered.id))
        assert not bad.ok and "mismatch" in bad.message

        bare = lib.add_item("No Params")
        no_params = verify_item(bare)
        assert not no_params.ok and "fingerprint" in no_params.message
    finally:
        lib.close()


def test_record_from_item_prefers_stored_metadata(tmp_path: Path):
    lib = LibraryService(":memory:")
    try:
        composition, params = _composition(seed=31, duration=24.0)
        item = lib.register_composition(composition, params, title="From Item")
        record = record_from_item(item, created_at="2026-08-23T00:00:00+00:00")
        assert record.title == "From Item"
        assert record.item_id == item.id
        assert record.fingerprint == item.fingerprint
        assert record.parameters["seed"] == 31
        assert record.bpm == pytest.approx(composition.bpm)
    finally:
        lib.close()
