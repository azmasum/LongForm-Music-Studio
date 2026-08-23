"""Export pipeline tests: full render -> master -> QC -> archive flow."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lfms.core.errors import ValidationError
from lfms.exporter import export_item
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters
from lfms.library import LibraryService
from lfms.mastering.measure import measure


def _register(lib: LibraryService, seed: int = 21, duration: float = 10.0):
    params = GenerationParameters(
        seed=seed,
        duration_sec=duration,
        genre="DOCUMENTARY",
        moods=("CALM",),
        intensity=40.0,
        voiceover_safe=True,
    )
    params.validate()
    composition = Composer(params).compose()
    return lib.register_composition(composition, params, title=f"Export Bed {seed}")


@pytest.fixture()
def lib():
    service = LibraryService(":memory:")
    yield service
    service.close()


def test_full_export_produces_mastered_file_and_certificate(lib, tmp_path: Path):
    source = _register(lib)
    out_dir = tmp_path / "delivery"
    out_dir.mkdir()
    seen: list[float] = []
    outcome = export_item(
        lib, source.id, out_dir, preset="YOUTUBE",
        on_progress=seen.append,
    )

    assert outcome.final_path.is_file() and outcome.final_path.suffix == ".wav"
    assert outcome.certificate_path.is_file()
    assert not (out_dir / f"{outcome.final_path.stem}-raw.wav").exists()
    assert seen and seen[0] == 0.0 and seen[-1] == 1.0
    assert seen == sorted(seen)

    # delivered file hits the preset target without breaking the ceiling
    delivered, sr = __import__("soundfile").read(
        str(outcome.final_path), always_2d=True, dtype="float32"
    )
    m = measure(delivered.T, sr)
    assert abs(m.integrated_lufs - (-14.0)) < 1.0
    assert m.true_peak_dbtp <= -0.9
    assert outcome.qc.status in ("READY", "WARNING")

    # library entry with measurement + tags
    exported = lib.get(outcome.library_item_id)
    assert exported.kind == "AUDIO_FILE"
    assert exported.path == str(outcome.final_path.resolve())
    assert exported.integrated_lufs is not None
    assert "export" in exported.tags
    assert "target:youtube" in exported.tags
    assert f"fp-source:{source.id}" in exported.tags

    # certificate carries the lineage of the SOURCE composition
    payload = json.loads(outcome.certificate_path.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == source.fingerprint
    assert payload["parameters"]["seed"] == 21
    assert payload["qc_status"] == outcome.qc.status


def test_export_with_podcast_preset_hits_minus_sixteen(lib, tmp_path: Path):
    source = _register(lib, seed=33)
    out = tmp_path / "out"
    out.mkdir()
    outcome = export_item(lib, source.id, out, preset="PODCAST")
    assert outcome.target_name == "PODCAST"
    assert "[PODCAST]" in outcome.final_path.name
    assert abs(outcome.master.after.integrated_lufs - (-16.0)) < 0.8


def test_export_supports_flac_container(lib, tmp_path: Path):
    source = _register(lib, seed=34, duration=8.0)
    out = tmp_path / "flac-out"
    out.mkdir()
    outcome = export_item(lib, source.id, out, container="FLAC")
    assert outcome.final_path.suffix == ".flac"
    assert outcome.final_path.is_file()


def test_export_rejects_missing_directory_and_bad_items(lib, tmp_path: Path):
    source = _register(lib, seed=35)
    with pytest.raises(ValidationError):
        export_item(lib, source.id, tmp_path / "does-not-exist")

    bare = lib.add_item("No Params")
    with pytest.raises(ValidationError):
        export_item(lib, bare.id, tmp_path)

    with pytest.raises(ValidationError):
        export_item(lib, 9999, tmp_path)


def test_export_rejects_unknown_preset(lib, tmp_path: Path):
    source = _register(lib, seed=36)
    out = tmp_path / "p"
    out.mkdir()
    with pytest.raises(ValidationError):
        export_item(lib, source.id, out, preset="NOT-A-PRESET")


def test_export_is_repeatable_deterministically(lib, tmp_path: Path):
    source = _register(lib, seed=77, duration=6.0)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    r1 = export_item(lib, source.id, first)
    r2 = export_item(lib, source.id, second)
    assert r1.master.after.to_dict().keys() == r2.master.after.to_dict().keys()
    for key in ("integrated_lufs", "true_peak_dbtp"):
        assert getattr(r1.master.after, key) == pytest.approx(
            getattr(r2.master.after, key), abs=0.01
        )
