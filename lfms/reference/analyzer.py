"""Reference-track analysis: learn style parameters, never the melody.

The analyzer extracts tempo, key, brightness, loudness and an energy
envelope from a user-supplied audio file. Those *style descriptors* are fed
into the normal composer, which then writes original music in a similar
vein. No reference audio (and no transcribed melody) is ever stored or
reproduced.
"""
from __future__ import annotations

import hashlib
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from lfms.core.errors import ValidationError
from lfms.generator.theory import NOTE_NAMES

_MAX_ANALYSIS_SEC = 180.0          # analyze at most the first 3 minutes
_MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024
_AUDIO_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif", ".m4a", ".wma"}
_PLATFORM_HOSTS = (
    "youtube.com", "youtu.be", "spotify.com", "music.youtube.com",
    "apple.com", "soundcloud.com", "bandcamp.com", "tidal.com",
    "deezer.com", "gaana.com",
)

_KRUMHANSL_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                             2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KRUMHANSL_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                             2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass(frozen=True)
class ReferenceAnalysis:
    source: str                 # file path or URL
    source_hash: str            # sha1 prefix of the audio bytes
    duration_sec: float
    bpm: int
    key_root: str
    key_mode: str
    brightness_hz: float
    intensity: float            # 0..100
    pulse_level: float          # 0..1 onset density proxy
    rms_points: tuple[tuple[float, float], ...]   # normalized energy envelope

    def summary(self) -> str:
        return (
            f"reference {Path(self.source).name}: ~{self.bpm} BPM, "
            f"{self.key_root} {self.key_mode.capitalize()}, "
            f"intensity {self.intensity:.0f}"
        )


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    try:
        info = sf.info(str(path))
    except Exception as exc:
        raise ValidationError(
            f"Could not read reference audio: {path.name}",
            suggestion="Use WAV/FLAC/OGG/MP3 files.",
        ) from exc
    frames = min(info.frames, int(_MAX_ANALYSIS_SEC * info.samplerate))
    try:
        data, sr = sf.read(str(path), frames=frames, always_2d=True, dtype="float32")
    except sf.LibsndfileError as exc:
        raise ValidationError(
            f"Could not decode reference audio: {path.name}",
        ) from exc
    mono = data.mean(axis=1)
    if mono.size < sr // 2:
        raise ValidationError("Reference audio is too short (need at least 0.5 s).")
    return mono.astype(np.float64), sr


def _spectral_flux_envelope(mono: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """Onset-strength envelope + hop seconds."""
    n_fft, hop = 2048, 512
    if mono.size < n_fft * 2:
        n_fft = max(256, 1 << (mono.size.bit_length() - 2))
    window = np.hanning(n_fft)
    frames = 1 + (mono.size - n_fft) // hop
    if frames < 4:
        raise ValidationError("Reference audio too short for tempo analysis.")
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * window, axis=1))
    log_spec = np.log1p(10.0 * spec)
    flux = np.maximum(0.0, np.diff(log_spec, axis=0)).sum(axis=1)
    flux = np.concatenate(([0.0], flux))
    return flux, hop / sr


def estimate_bpm(flux: np.ndarray, hop_sec: float) -> int:
    """Autocorrelation of the onset envelope over 55-190 BPM."""
    centered = flux - flux.mean()
    lag_min = int(round(60.0 / 190.0 / hop_sec))
    lag_max = int(round(60.0 / 55.0 / hop_sec))
    lag_max = min(lag_max, centered.size - 1)
    if lag_min >= lag_max:
        return 100
    corr = np.correlate(centered, centered, mode="full")[centered.size - 1:]
    segment = corr[lag_min : lag_max + 1]
    best = lag_min + int(np.argmax(segment))
    bpm = 60.0 / (best * hop_sec)
    while bpm < 70.0:   # fold extreme octaves back into a musical range
        bpm *= 2.0
    while bpm > 180.0:
        bpm /= 2.0
    return int(round(bpm))


def estimate_key(mono: np.ndarray, sr: int) -> tuple[str, str]:
    """Chroma vector correlated with Krumhansl major/minor profiles."""
    n_fft, hop = 4096, 2048
    frames = max(1, (mono.size - n_fft) // hop)
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(mono[idx] * np.hanning(n_fft), axis=1))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    midi = 12.0 * np.log2(np.maximum(freqs, 20.0) / 440.0) + 69.0
    chroma = np.zeros(12)
    weights = spec.mean(axis=0)
    valid = (midi >= 21) & (midi < 108)
    pcs = np.mod(np.round(midi[valid]).astype(int), 12)
    for pc in range(12):
        chroma[pc] = float(weights[valid][pcs == pc].sum())
    norm = np.linalg.norm(chroma)
    if norm < 1e-9:
        return "C", "MAJOR"
    chroma = chroma / norm
    best_root, best_mode, best_score = "C", "MAJOR", -2.0
    for rotation in range(12):
        rotated = np.roll(chroma, -rotation)
        for profile, mode in ((_KRUMHANSL_MAJOR, "MAJOR"), (_KRUMHANSL_MINOR, "MINOR")):
            score = float(np.dot(rotated, profile / np.linalg.norm(profile)))
            if score > best_score:
                best_root, best_mode, best_score = NOTE_NAMES[rotation], mode, score
    return best_root, best_mode


def _rms_stats(mono: np.ndarray, sr: int) -> tuple[float, tuple[tuple[float, float], ...]]:
    seg = sr  # 1-second resolution
    n_seg = max(1, mono.size // seg)
    levels = np.array([
        float(np.sqrt(np.mean(np.square(mono[i * seg:(i + 1) * seg]))))
        for i in range(n_seg)
    ])
    overall = float(np.median(levels[levels > 1e-6])) if np.any(levels > 1e-6) else 0.0
    db = 20.0 * np.log10(max(overall, 1e-6))
    intensity = float(np.clip((db + 42.0) / 36.0 * 100.0, 5.0, 100.0))
    peak = float(levels.max()) or 1.0
    reduced = np.array_split(levels, min(16, n_seg))
    points = tuple(
        (round(i / max(1, len(reduced) - 1), 3),
         round(float(np.mean(chunk)) / peak, 3))
        for i, chunk in enumerate(reduced)
    )
    return intensity, points


def analyze_file(path: Path | str) -> ReferenceAnalysis:
    p = Path(path)
    if not p.exists():
        raise ValidationError(f"Reference file not found: {p}")
    mono, sr = _load_mono(p)
    raw = p.read_bytes()
    digest = hashlib.sha1(raw).hexdigest()[:10]

    flux, hop_sec = _spectral_flux_envelope(mono, sr)
    bpm = estimate_bpm(flux, hop_sec)
    root, mode = estimate_key(mono, sr)

    spectrum = np.abs(np.fft.rfft(mono[: sr * 4]))
    freqs = np.fft.rfftfreq(min(mono.size, sr * 4), d=1.0 / sr)
    total = float(spectrum.sum()) or 1.0
    centroid = float((freqs * spectrum).sum() / total)
    brightness = float(np.clip(centroid, 400.0, 8000.0))

    intensity, points = _rms_stats(mono, sr)
    onset_rate = float((flux > flux.mean() + flux.std()).sum()) / max(
        mono.size / sr, 1.0
    )
    pulse = float(np.clip(onset_rate / 8.0, 0.02, 0.85))

    return ReferenceAnalysis(
        source=str(p),
        source_hash=digest,
        duration_sec=mono.size / sr,
        bpm=bpm,
        key_root=root,
        key_mode=mode,
        brightness_hz=brightness,
        intensity=intensity,
        pulse_level=pulse,
        rms_points=points,
    )


def is_platform_link(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in _PLATFORM_HOSTS)


def download_audio(url: str, *, timeout: float = 30.0) -> Path:
    """Stream a direct audio-file URL to a temp file (size-capped).

    Streaming-platform pages (YouTube/Spotify/...) are deliberately refused:
    ripping them violates their terms. Users should export/save the audio
    themselves and use the local file option instead.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValidationError("Reference URL must start with http:// or https://")
    if is_platform_link(url):
        raise ValidationError(
            "Streaming-platform links cannot be used directly.",
            suggestion="Download/export the audio yourself, then choose the local file.",
        )
    suffix = Path(urllib.request.urlparse(url).path).suffix.lower()
    if suffix not in _AUDIO_SUFFIXES:
        raise ValidationError(
            f"URL does not look like a direct audio file ({suffix or 'unknown type'}).",
            suggestion="Link straight to .mp3/.wav/.ogg/.flac/.m4a files.",
        )
    tmp = Path(tempfile.gettempdir()) / f"lfms-ref-{hashlib.sha1(url.encode()).hexdigest()[:10]}{suffix}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (validated scheme)
            declared = int(resp.headers.get("Content-Length") or 0)
            if declared > _MAX_DOWNLOAD_BYTES:
                raise ValidationError("Reference file is too large (limit 150 MB).")
            data = resp.read(_MAX_DOWNLOAD_BYTES + 1)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"Could not download reference: {exc}") from exc
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValidationError("Reference file is too large (limit 150 MB).")
    tmp.write_bytes(data)
    return tmp


def merge_into_payload(payload: dict, analysis: ReferenceAnalysis) -> dict:
    """Overlay reference-derived style parameters onto a generate payload.

    Genre/duration stay under the user's control; tempo, key, intensity,
    pulse and the energy envelope come from the reference.
    """
    merged = dict(payload)
    merged["bpm"] = int(analysis.bpm)
    merged["key_root"] = analysis.key_root
    merged["key_mode"] = analysis.key_mode
    merged["intensity"] = round(analysis.intensity, 1)
    merged["_pulse_hint"] = analysis.pulse_level
    if len(analysis.rms_points) >= 2:
        merged["energy_points"] = tuple(analysis.rms_points)
    merged["_reference"] = {
        "source": analysis.source,
        "hash": analysis.source_hash,
        "summary": analysis.summary(),
    }
    return merged


def known_audio_suffixes() -> frozenset[str]:
    return frozenset(_AUDIO_SUFFIXES)
