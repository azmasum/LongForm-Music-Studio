"""Timeline document model: tracks, clips, automation lanes and markers.

Pure data + validation — no Qt here, so the whole model is unit-testable
and reusable by CLI/render paths. Serialization is plain JSON dicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from lfms.core.errors import ValidationError
from lfms.core.ids import new_id

TRACK_KINDS = ("MUSIC", "AMBIENCE", "VOICEOVER", "REFERENCE")
CLIP_SOURCE_KINDS = ("GENERATED", "AUDIO_FILE")
MARKER_KINDS = ("SECTION", "CUE", "CHAPTER")
AUTOMATION_PARAMS = ("volume", "pan")


@dataclass
class TrackState:
    name: str
    kind: str = "MUSIC"
    track_id: str = field(default_factory=lambda: new_id("TRK"))
    volume_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    order: int = 0

    def validate(self) -> None:
        if not self.name.strip():
            raise ValidationError("track name must not be empty")
        if self.kind not in TRACK_KINDS:
            raise ValidationError(f"unknown track kind {self.kind!r}")
        if not -60.0 <= self.volume_db <= 12.0:
            raise ValidationError("track volume_db must be within [-60, 12]")
        if not -1.0 <= self.pan <= 1.0:
            raise ValidationError("track pan must be within [-1, 1]")


@dataclass
class Clip:
    track_id: str
    start_sec: float
    duration_sec: float
    label: str = ""
    clip_id: str = field(default_factory=lambda: new_id("CLP"))
    source_kind: str = "GENERATED"
    source_ref: str = ""
    gain_db: float = 0.0

    @property
    def end_sec(self) -> float:
        return self.start_sec + self.duration_sec

    def validate(self) -> None:
        if self.start_sec < 0.0:
            raise ValidationError("clip start must be >= 0")
        if self.duration_sec <= 0.0:
            raise ValidationError("clip duration must be positive")
        if self.source_kind not in CLIP_SOURCE_KINDS:
            raise ValidationError(f"unknown clip source kind {self.source_kind!r}")


@dataclass
class AutomationPoint:
    time_sec: float
    value: float


@dataclass
class AutomationLane:
    track_id: str
    parameter: str
    points: list[AutomationPoint] = field(default_factory=list)

    def validate(self) -> None:
        if self.parameter not in AUTOMATION_PARAMS:
            raise ValidationError(f"unknown automation parameter {self.parameter!r}")

    def sort(self) -> None:
        self.points.sort(key=lambda point: point.time_sec)


@dataclass
class Marker:
    time_sec: float
    label: str
    kind: str = "SECTION"
    marker_id: str = field(default_factory=lambda: new_id("MRK"))

    def validate(self) -> None:
        if self.time_sec < 0.0:
            raise ValidationError("marker time must be >= 0")
        if not self.label.strip():
            raise ValidationError("marker label must not be empty")
        if self.kind not in MARKER_KINDS:
            raise ValidationError(f"unknown marker kind {self.kind!r}")


@dataclass
class TimelineDocument:
    title: str = "Untitled timeline"
    duration_sec: float = 600.0
    tracks: list[TrackState] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)
    lanes: list[AutomationLane] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    # -- tracks ---------------------------------------------------------
    def add_track(self, track: TrackState) -> TrackState:
        track.validate()
        if any(existing.track_id == track.track_id for existing in self.tracks):
            raise ValidationError(f"duplicate track id {track.track_id}")
        track.order = len(self.tracks)
        self.tracks.append(track)
        return track

    def track(self, track_id: str) -> TrackState:
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        raise ValidationError(f"unknown track {track_id}")

    def remove_track(self, track_id: str) -> tuple[TrackState, list[Clip], list[AutomationLane]]:
        track = self.track(track_id)
        removed_clips = [clip for clip in self.clips if clip.track_id == track_id]
        removed_lanes = [lane for lane in self.lanes if lane.track_id == track_id]
        self.tracks.remove(track)
        self.clips = [clip for clip in self.clips if clip.track_id != track_id]
        self.lanes = [lane for lane in self.lanes if lane.track_id != track_id]
        for index, remaining in enumerate(self.tracks):
            remaining.order = index
        return track, removed_clips, removed_lanes

    # -- clips ----------------------------------------------------------
    def add_clip(self, clip: Clip) -> Clip:
        clip.validate()
        self.track(clip.track_id)
        if any(existing.clip_id == clip.clip_id for existing in self.clips):
            raise ValidationError(f"duplicate clip id {clip.clip_id}")
        self.clips.append(clip)
        return clip

    def clip(self, clip_id: str) -> Clip:
        for clip in self.clips:
            if clip.clip_id == clip_id:
                return clip
        raise ValidationError(f"unknown clip {clip_id}")

    def remove_clip(self, clip_id: str) -> Clip:
        clip = self.clip(clip_id)
        self.clips.remove(clip)
        return clip

    def move_clip(self, clip_id: str, new_start: float) -> Clip:
        clip = self.clip(clip_id)
        if new_start < 0.0:
            raise ValidationError("clip start must be >= 0")
        moved = replace(clip, start_sec=float(new_start))
        self.clips[self.clips.index(clip)] = moved
        return moved

    def resize_clip(self, clip_id: str, new_duration: float) -> Clip:
        clip = self.clip(clip_id)
        if new_duration <= 0.0:
            raise ValidationError("clip duration must be positive")
        resized = replace(clip, duration_sec=float(new_duration))
        self.clips[self.clips.index(clip)] = resized
        return resized

    def clips_in_range(self, start_sec: float, end_sec: float) -> list[Clip]:
        return [
            clip
            for clip in self.clips
            if clip.start_sec < end_sec and clip.end_sec > start_sec
        ]

    def clips_on_track(self, track_id: str) -> list[Clip]:
        return sorted(
            (clip for clip in self.clips if clip.track_id == track_id),
            key=lambda clip: clip.start_sec,
        )

    # -- automation ------------------------------------------------------
    def lane(self, track_id: str, parameter: str) -> AutomationLane:
        for lane in self.lanes:
            if lane.track_id == track_id and lane.parameter == parameter:
                return lane
        lane = AutomationLane(track_id=track_id, parameter=parameter)
        lane.validate()
        self.lanes.append(lane)
        return lane

    def set_automation_point(
        self, track_id: str, parameter: str, time_sec: float, value: float
    ) -> AutomationPoint:
        if not 0.0 <= value <= 1.0:
            raise ValidationError("automation value must be within [0, 1]")
        if time_sec < 0.0:
            raise ValidationError("automation time must be >= 0")
        lane = self.lane(track_id, parameter)
        lane.points = [
            point for point in lane.points if abs(point.time_sec - time_sec) > 1e-9
        ]
        point = AutomationPoint(time_sec=float(time_sec), value=float(value))
        lane.points.append(point)
        lane.sort()
        return point

    def remove_automation_point(
        self, track_id: str, parameter: str, time_sec: float
    ) -> AutomationPoint:
        lane = self.lane(track_id, parameter)
        for index, point in enumerate(lane.points):
            if abs(point.time_sec - time_sec) <= 1e-9:
                return lane.points.pop(index)
        raise ValidationError("no automation point at that time")

    # -- markers ---------------------------------------------------------
    def add_marker(self, marker: Marker) -> Marker:
        marker.validate()
        self.markers.append(marker)
        self.markers.sort(key=lambda item: item.time_sec)
        return marker

    def remove_marker(self, marker_id: str) -> Marker:
        for index, marker in enumerate(self.markers):
            if marker.marker_id == marker_id:
                return self.markers.pop(index)
        raise ValidationError(f"unknown marker {marker_id}")

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "duration_sec": self.duration_sec,
            "tracks": [vars(track) | {} for track in self.tracks],
            "clips": [vars(clip) | {} for clip in self.clips],
            "lanes": [
                {
                    "track_id": lane.track_id,
                    "parameter": lane.parameter,
                    "points": [
                        {"time_sec": p.time_sec, "value": p.value}
                        for p in lane.points
                    ],
                }
                for lane in self.lanes
            ],
            "markers": [vars(marker) | {} for marker in self.markers],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TimelineDocument:
        document = cls(
            title=str(data.get("title", "Untitled timeline")),
            duration_sec=float(data.get("duration_sec", 600.0)),
        )
        for raw in data.get("tracks", []):
            document.add_track(TrackState(**raw))
        for raw in data.get("clips", []):
            document.add_clip(Clip(**raw))
        for raw in data.get("lanes", []):
            lane = AutomationLane(
                track_id=raw["track_id"], parameter=raw["parameter"]
            )
            lane.points = [
                AutomationPoint(time_sec=p["time_sec"], value=p["value"])
                for p in raw.get("points", [])
            ]
            lane.validate()
            lane.sort()
            document.lanes.append(lane)
        for raw in data.get("markers", []):
            document.add_marker(Marker(**raw))
        return document
