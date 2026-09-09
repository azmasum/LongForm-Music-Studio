"""Dependency-free ID3v2.3 writer for MP3 deliverables.

Embeds text frames (title/artist/album/genre/comments) and one APIC
cover-art frame at the front of the file. A pre-existing leading ID3 tag
is stripped first so a single, well-formed tag remains.
"""
from __future__ import annotations

from pathlib import Path

_HEADER_LEN = 10


def _synchsafe32(value: int) -> bytes:
    return bytes(
        (
            (value >> 21) & 0x7F,
            (value >> 14) & 0x7F,
            (value >> 7) & 0x7F,
            value & 0x7F,
        )
    )


def _text_data(text: str) -> bytes:
    return b"\x01\xff\xfe" + text.encode("utf-16-le") + b"\x00\x00"


def _frame(frame_id: str, payload: bytes) -> bytes:
    return b"".join(
        (
            frame_id.encode("ascii"),
            len(payload).to_bytes(4, "big"),
            b"\x00\x00",
            payload,
        )
    )


def _text_frame(frame_id: str, text: str) -> bytes:
    return _frame(frame_id, _text_data(text))


def _comment_frame(text: str) -> bytes:
    # encoding 1 (UTF-16), language "eng", empty short description (double NUL),
    # then the text bytes (BOM + utf-16-le + terminator)
    payload = b"\x01" + b"eng" + b"\x00\x00" + _text_data(text)[1:]
    return _frame("COMM", payload)


def _apic_frame(image_bytes: bytes, mime: str = "image/png") -> bytes:
    # encoding 0 (latin-1) text spec hello; 1 = UTF-16
    header = b"\x00" + mime.encode("ascii") + b"\x00" + bytes([3]) + b"\x00"
    return _frame("APIC", header + image_bytes)


def _lead_id3_total(path: Path) -> int:
    """Total bytes of a leading ID3v2 tag (or 0 when absent)."""
    with open(path, "rb") as fh:
        head = fh.read(_HEADER_LEN)
    if len(head) < _HEADER_LEN or head[:3] != b"ID3":
        return 0
    size = (
        (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
    )
    return _HEADER_LEN + size


def _write_tags(
    path: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    year: str | None = None,
    track: str | None = None,
    comment: str | None = None,
    cover_bytes: bytes | None = None,
    cover_mime: str = "image/png",
) -> None:
    frames = bytearray()
    for frame_id, value in (
        ("TIT2", title),
        ("TPE1", artist),
        ("TALB", album),
        ("TCON", genre),
        ("TYER", year),
        ("TRCK", track),
    ):
        if value:
            frames += _text_frame(frame_id, value)
    if comment:
        frames += _comment_frame(comment)
    if cover_bytes:
        frames += _apic_frame(cover_bytes, mime=cover_mime)

    tag = (
        b"ID3"
        + bytes([0x03, 0x00, 0x00])
        + _synchsafe32(len(frames))
        + bytes(frames)
    )

    with open(path, "rb") as fh:
        audio = fh.read()

    existing = _lead_id3_total(path)
    with open(path, "wb") as fh:
        fh.write(tag)
        fh.write(audio[existing:] if existing else audio)


def write_mp3_tags(
    path: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    year: str | None = None,
    track: str | None = None,
    comment: str | None = None,
    cover_bytes: bytes | None = None,
    cover_mime: str = "image/png",
) -> None:
    """Write ID3v2.3 tags to ``path`` (MP3 deliverable).

    A no-op for files that are not MP3 audio (by extension); the writer is
    tolerant of missing values (weak fields are simply skipped).
    """
    if path.suffix.lower() != ".mp3":
        return
    _write_tags(
        path,
        title=title,
        artist=artist,
        album=album,
        genre=genre,
        year=year,
        track=track,
        comment=comment,
        cover_bytes=cover_bytes,
        cover_mime=cover_mime,
    )
