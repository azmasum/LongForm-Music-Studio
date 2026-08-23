"""LFMS error hierarchy.

Every error carries a human-readable message, optional technical details and
an actionable suggestion so the GUI can present useful dialogs.
"""
from __future__ import annotations

from typing import Any


class LFMSError(Exception):
    """Base class for all LFMS errors."""

    def __init__(self, message: str, *, technical: str = "", suggestion: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical
        self.suggestion = suggestion

    def to_dict(self) -> dict[str, str]:
        return {
            "error": type(self).__name__,
            "message": self.message,
            "technical": self.technical,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        text = self.message
        if self.suggestion:
            text = f"{text} {self.suggestion}"
        return text


class ConfigurationError(LFMSError):
    pass


class StorageError(LFMSError):
    pass


class DatabaseError(LFMSError):
    pass


class ValidationError(LFMSError):
    pass


class ProjectFileError(LFMSError):
    pass


class AudioDeviceError(LFMSError):
    pass


class GenerationError(LFMSError):
    pass


class RenderError(LFMSError):
    pass


class ImportExportError(LFMSError):
    pass


class LicenseError(LFMSError):
    pass


def describe_exception(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "repr": repr(exc),
    }
