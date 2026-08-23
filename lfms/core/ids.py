"""Identifier and fingerprint helpers.

Fingerprints are deterministic identifiers derived from project material.
They are an internal identification mechanism only and are NOT legal
copyright registrations.
"""
from __future__ import annotations

import base64
import hashlib
import uuid
from collections.abc import Iterable


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def fingerprint(parts: Iterable[str], *, prefix: str = "LFMS") -> str:
    joined = "|".join(str(p) for p in parts)
    digest = hashlib.blake2b(joined.encode("utf-8"), digest_size=16).digest()
    raw = base64.b32encode(digest).decode("ascii").rstrip("=")[:12]
    grouped = "-".join(raw[i : i + 4] for i in range(0, 12, 4))
    return f"{prefix}-{grouped}"


def audio_fingerprint(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    raw = base64.b32encode(digest).decode("ascii").rstrip("=")[:12]
    grouped = "-".join(raw[i : i + 4] for i in range(0, 12, 4))
    return f"AUD-{grouped}"
