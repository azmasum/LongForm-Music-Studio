"""Reference-inspired generation (style transfer via parameter analysis)."""
from lfms.reference.analyzer import (
    ReferenceAnalysis,
    analyze_file,
    download_audio,
    is_platform_link,
    known_audio_suffixes,
    merge_into_payload,
)

__all__ = [
    "ReferenceAnalysis",
    "analyze_file",
    "download_audio",
    "is_platform_link",
    "known_audio_suffixes",
    "merge_into_payload",
]
