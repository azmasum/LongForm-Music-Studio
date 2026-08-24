"""Mapping of export containers to libsndfile format/subtype pairs.

OGG (Vorbis) and MP3 (MPEG layer III) are lossy; ``bit_depth`` applies
only to the PCM containers (WAV, FLAC).
"""
from __future__ import annotations

from lfms.core.enums import ExportContainer

_WAV_SUBTYPES = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}
_FLAC_SUBTYPES = {16: "PCM_16", 24: "PCM_24"}


def resolve_sf_params(
    container: str | ExportContainer, bit_depth: int | None = None
) -> tuple[str, str]:
    container = ExportContainer(container)
    if container is ExportContainer.MP3:
        return "MP3", "MPEG_LAYER_III"
    if container is ExportContainer.OGG:
        return "OGG", "VORBIS"
    if container is ExportContainer.FLAC:
        depth = bit_depth if bit_depth in _FLAC_SUBTYPES else 24
        return "FLAC", _FLAC_SUBTYPES[depth]
    depth = bit_depth if bit_depth in _WAV_SUBTYPES else 24
    return "WAV", _WAV_SUBTYPES[depth]


def default_extension(container: str | ExportContainer) -> str:
    return ExportContainer(container).value.lower()
