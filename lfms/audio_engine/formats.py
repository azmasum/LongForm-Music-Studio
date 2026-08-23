"""Mapping of export containers to libsndfile format/subtype pairs.

MP3 is intentionally not handled by libsndfile; FFmpeg-based MP3 encoding
arrives with the render-queue phase and raises a clear error until then.
"""
from __future__ import annotations

from lfms.core.enums import ExportContainer
from lfms.core.errors import ImportExportError

_WAV_SUBTYPES = {16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}
_FLAC_SUBTYPES = {16: "PCM_16", 24: "PCM_24"}


def resolve_sf_params(
    container: str | ExportContainer, bit_depth: int | None = None
) -> tuple[str, str]:
    container = ExportContainer(container)
    if container is ExportContainer.MP3:
        raise ImportExportError(
            "MP3 export requires the optional FFmpeg encoder.",
            technical="libsndfile cannot write MP3; FFmpeg integration lands in Phase 11.",
            suggestion="Export WAV or FLAC for now, or install FFmpeg once Phase 11 ships.",
        )
    if container is ExportContainer.OGG:
        return "OGG", "VORBIS"
    if container is ExportContainer.FLAC:
        depth = bit_depth if bit_depth in _FLAC_SUBTYPES else 24
        return "FLAC", _FLAC_SUBTYPES[depth]
    depth = bit_depth if bit_depth in _WAV_SUBTYPES else 24
    return "WAV", _WAV_SUBTYPES[depth]


def default_extension(container: str | ExportContainer) -> str:
    return ExportContainer(container).value.lower()
