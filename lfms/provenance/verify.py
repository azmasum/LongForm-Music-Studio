"""Fingerprint verification: prove a certificate's lineage by recomposition.

LFMS generation is fully deterministic for a given parameter set, so a
stored fingerprint can be checked by recomposing the recorded parameters
and comparing. No fingerprint, no proof.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from lfms.core.errors import ValidationError
from lfms.generator.composer import Composer
from lfms.generator.plan import GenerationParameters


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    message: str
    expected_fingerprint: str | None = None
    recomputed_fingerprint: str | None = None

    @property
    def status(self) -> str:
        return "VERIFIED" if self.ok else "FAILED"


def params_from_payload(payload: dict) -> GenerationParameters:
    """Build validated ``GenerationParameters`` from a stored JSON dict."""
    allowed = set(GenerationParameters.__dataclass_fields__)
    kwargs = {key: value for key, value in payload.items() if key in allowed}
    if not {"seed", "duration_sec", "genre"} <= set(kwargs):
        raise ValidationError(
            "parameters payload lacks seed/duration_sec/genre"
        )
    params = GenerationParameters(**kwargs)
    params.validate()
    return params


def verify_parameters(payload: dict, expected_fingerprint: str) -> VerifyResult:
    """Recompose ``payload`` and compare against the recorded fingerprint."""
    try:
        params = params_from_payload(payload)
        composition = Composer(params).compose()
    except ValidationError as exc:
        return VerifyResult(False, f"parameters unusable: {exc}", expected_fingerprint)
    recomputed = str(composition.fingerprint)
    if recomputed != expected_fingerprint:
        return VerifyResult(
            False,
            "fingerprint mismatch — audio does not match the certificate",
            expected_fingerprint,
            recomputed,
        )
    return VerifyResult(True, "fingerprint matches recorded parameters", expected_fingerprint, recomputed)


def verify_item(item) -> VerifyResult:
    """Verify a library item's stored fingerprint via its params_json."""
    if not item.fingerprint:
        return VerifyResult(False, "item has no recorded fingerprint")
    if not item.params_json:
        return VerifyResult(False, "item has no stored generation parameters")
    try:
        payload = json.loads(item.params_json)
    except json.JSONDecodeError:
        return VerifyResult(False, "stored parameters are not valid JSON")
    return verify_parameters(payload, str(item.fingerprint))
