"""Undo/redo via the Command pattern with macro batching."""
from __future__ import annotations

from abc import ABC, abstractmethod

from lfms.core.errors import ValidationError
from lfms.timeline.model import (
    AutomationLane,
    Clip,
    Marker,
    TimelineDocument,
    TrackState,
)

DEFAULT_STACK_LIMIT = 200


class Command(ABC):
    """A reversible edit applied to a TimelineDocument."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def do(self, document: TimelineDocument) -> None: ...

    @abstractmethod
    def undo(self, document: TimelineDocument) -> None: ...


class AddTrackCommand(Command):
    def __init__(self, track: TrackState) -> None:
        super().__init__(f"Add track {track.name!r}")
        self.track = track

    def do(self, document: TimelineDocument) -> None:
        document.add_track(self.track)

    def undo(self, document: TimelineDocument) -> None:
        document.remove_track(self.track.track_id)


class RemoveTrackCommand(Command):
    def __init__(self, track_id: str) -> None:
        super().__init__("Remove track")
        self.track_id = track_id
        self._snapshot: tuple[TrackState, list[Clip], list[AutomationLane]] | None = None

    def do(self, document: TimelineDocument) -> None:
        self._snapshot = document.remove_track(self.track_id)

    def undo(self, document: TimelineDocument) -> None:
        if self._snapshot is None:
            raise ValidationError("command was never executed")
        track, clips, lanes = self._snapshot
        document.tracks.append(track)
        document.clips.extend(clips)
        document.lanes.extend(lanes)


class AddClipCommand(Command):
    def __init__(self, clip: Clip) -> None:
        super().__init__(f"Add clip {clip.label!r}" if clip.label else "Add clip")
        self.clip = clip

    def do(self, document: TimelineDocument) -> None:
        document.add_clip(self.clip)

    def undo(self, document: TimelineDocument) -> None:
        document.remove_clip(self.clip.clip_id)


class RemoveClipCommand(Command):
    def __init__(self, clip_id: str) -> None:
        super().__init__("Remove clip")
        self.clip_id = clip_id
        self._clip: Clip | None = None

    def do(self, document: TimelineDocument) -> None:
        self._clip = document.remove_clip(self.clip_id)

    def undo(self, document: TimelineDocument) -> None:
        if self._clip is None:
            raise ValidationError("command was never executed")
        document.add_clip(self._clip)


class MoveClipCommand(Command):
    def __init__(self, clip_id: str, new_start: float) -> None:
        super().__init__("Move clip")
        self.clip_id = clip_id
        self.new_start = float(new_start)
        self.old_start: float | None = None

    def do(self, document: TimelineDocument) -> None:
        clip = document.clip(self.clip_id)
        self.old_start = clip.start_sec
        document.move_clip(self.clip_id, self.new_start)

    def undo(self, document: TimelineDocument) -> None:
        if self.old_start is None:
            raise ValidationError("command was never executed")
        document.move_clip(self.clip_id, self.old_start)


class ResizeClipCommand(Command):
    def __init__(self, clip_id: str, new_duration: float) -> None:
        super().__init__("Resize clip")
        self.clip_id = clip_id
        self.new_duration = float(new_duration)
        self.old_duration: float | None = None

    def do(self, document: TimelineDocument) -> None:
        clip = document.clip(self.clip_id)
        self.old_duration = clip.duration_sec
        document.resize_clip(self.clip_id, self.new_duration)

    def undo(self, document: TimelineDocument) -> None:
        if self.old_duration is None:
            raise ValidationError("command was never executed")
        document.resize_clip(self.clip_id, self.old_duration)


class SetTrackPropertyCommand(Command):
    _FIELDS = ("name", "volume_db", "pan", "mute", "solo", "kind")

    def __init__(self, track_id: str, field_name: str, new_value: object) -> None:
        if field_name not in self._FIELDS:
            raise ValidationError(f"cannot set track field {field_name!r}")
        super().__init__(f"Set track {field_name}")
        self.track_id = track_id
        self.field_name = field_name
        self.new_value = new_value
        self.old_value: object = None
        self._executed = False

    def do(self, document: TimelineDocument) -> None:
        track = document.track(self.track_id)
        self.old_value = getattr(track, self.field_name)
        setattr(track, self.field_name, self.new_value)
        track.validate()
        self._executed = True

    def undo(self, document: TimelineDocument) -> None:
        if not self._executed:
            raise ValidationError("command was never executed")
        track = document.track(self.track_id)
        setattr(track, self.field_name, self.old_value)


class AddMarkerCommand(Command):
    def __init__(self, marker: Marker) -> None:
        super().__init__(f"Add marker {marker.label!r}")
        self.marker = marker

    def do(self, document: TimelineDocument) -> None:
        document.add_marker(self.marker)

    def undo(self, document: TimelineDocument) -> None:
        document.remove_marker(self.marker.marker_id)


class RemoveMarkerCommand(Command):
    def __init__(self, marker_id: str) -> None:
        super().__init__("Remove marker")
        self.marker_id = marker_id
        self._marker: Marker | None = None

    def do(self, document: TimelineDocument) -> None:
        self._marker = document.remove_marker(self.marker_id)

    def undo(self, document: TimelineDocument) -> None:
        if self._marker is None:
            raise ValidationError("command was never executed")
        document.add_marker(self._marker)


class SetAutomationPointCommand(Command):
    def __init__(
        self, track_id: str, parameter: str, time_sec: float, value: float
    ) -> None:
        super().__init__(f"Set automation {parameter}@{time_sec:.2f}s")
        self.track_id = track_id
        self.parameter = parameter
        self.time_sec = float(time_sec)
        self.value = float(value)
        self.previous: tuple[float, float] | None = None
        self.had_point = False
        self._executed = False

    def do(self, document: TimelineDocument) -> None:
        lane = document.lane(self.track_id, self.parameter)
        for point in lane.points:
            if abs(point.time_sec - self.time_sec) <= 1e-9:
                self.previous = (point.time_sec, point.value)
                self.had_point = True
                break
        document.set_automation_point(
            self.track_id, self.parameter, self.time_sec, self.value
        )
        self._executed = True

    def undo(self, document: TimelineDocument) -> None:
        if not self._executed:
            raise ValidationError("command was never executed")
        if self.had_point and self.previous is not None:
            document.set_automation_point(
                self.track_id, self.parameter, self.previous[0], self.previous[1]
            )
        else:
            document.remove_automation_point(
                self.track_id, self.parameter, self.time_sec
            )


class MacroCommand(Command):
    """Executes child commands as one atomic undoable step."""

    def __init__(self, children: list[Command], name: str = "Compound edit") -> None:
        super().__init__(name)
        self.children = children

    def do(self, document: TimelineDocument) -> None:
        done: list[Command] = []
        try:
            for child in self.children:
                child.do(document)
                done.append(child)
        except Exception:
            for child in reversed(done):
                child.undo(document)
            raise

    def undo(self, document: TimelineDocument) -> None:
        for child in reversed(self.children):
            child.undo(document)


class CommandStack:
    def __init__(self, *, limit: int = DEFAULT_STACK_LIMIT) -> None:
        if limit < 1:
            raise ValidationError("stack limit must be >= 1")
        self.limit = int(limit)
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def next_undo_name(self) -> str | None:
        return self._undo[-1].name if self._undo else None

    @property
    def next_redo_name(self) -> str | None:
        return self._redo[-1].name if self._redo else None

    def execute(self, command: Command, document: TimelineDocument) -> Command:
        command.do(document)
        self._undo.append(command)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()
        return command

    def undo(self, document: TimelineDocument) -> Command | None:
        if not self._undo:
            return None
        command = self._undo.pop()
        command.undo(document)
        self._redo.append(command)
        return command

    def redo(self, document: TimelineDocument) -> Command | None:
        if not self._redo:
            return None
        command = self._redo.pop()
        command.do(document)
        self._undo.append(command)
        return command


def snapshot(document: TimelineDocument) -> dict:
    return document.to_dict()


def documents_equal(a: TimelineDocument, b: TimelineDocument) -> bool:
    return a.to_dict() == b.to_dict()


__all__ = [
    "AddClipCommand",
    "AddMarkerCommand",
    "AddTrackCommand",
    "Command",
    "CommandStack",
    "DEFAULT_STACK_LIMIT",
    "MacroCommand",
    "MoveClipCommand",
    "RemoveClipCommand",
    "RemoveMarkerCommand",
    "RemoveTrackCommand",
    "ResizeClipCommand",
    "SetAutomationPointCommand",
    "SetTrackPropertyCommand",
    "documents_equal",
]
