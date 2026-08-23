"""Tests for seeds and fingerprints."""
from __future__ import annotations

import re

from lfms.core.ids import audio_fingerprint, fingerprint, new_id
from lfms.core.seed import SEED_RANGE, SeedSystem


def test_random_seed_within_range() -> None:
    for _ in range(20):
        seed = SeedSystem.random_seed()
        assert 0 <= seed < SEED_RANGE


def test_derive_is_deterministic() -> None:
    a = SeedSystem(1234)
    b = SeedSystem(1234)
    for ns in ("melody", "harmony", "arranger", "ambience"):
        assert a.derive(ns) == b.derive(ns)


def test_derive_differs_by_namespace() -> None:
    s = SeedSystem(42)
    values = {s.derive(ns) for ns in ("a", "b", "c", "d")}
    assert len(values) == 4


def test_normalize_numeric_string() -> None:
    assert SeedSystem.normalize("9384721") == 9384721 % SEED_RANGE
    word_seed = SeedSystem.normalize("dark psychology")
    assert 0 <= word_seed < SEED_RANGE
    assert word_seed == SeedSystem.normalize("dark psychology")


def test_same_seed_same_object_equality() -> None:
    assert SeedSystem(7) == SeedSystem(7)
    assert SeedSystem(7).copy_with(9) == SeedSystem(9)


def test_fingerprint_format_is_stable() -> None:
    fp = fingerprint(["prj-abc", "seed:9384721", "lfms-gen-0.1.0"])
    assert re.fullmatch(r"LFMS(-[A-Z2-7]{4}){3}", fp)
    again = fingerprint(["prj-abc", "seed:9384721", "lfms-gen-0.1.0"])
    assert fp == again


def test_fingerprint_changes_with_input() -> None:
    assert fingerprint(["a"]) != fingerprint(["b"])


def test_audio_fingerprint_depends_on_bytes() -> None:
    assert audio_fingerprint(b"\x00\x01") != audio_fingerprint(b"\x00\x02")


def test_new_id_prefix() -> None:
    pid = new_id("prj")
    assert pid.startswith("prj-") and len(pid) == len("prj") + 1 + 12
