"""Undo/redo command stack tests."""
import pytest

from lfms.core.errors import ValidationError
from lfms.timeline import (
    AddClipCommand,
    AddMarkerCommand,
    AddTrackCommand,
    Clip,
    CommandStack,
    MacroCommand,
    Marker,
    MoveClipCommand,
    RemoveClipCommand,
    RemoveMarkerCommand,
    RemoveTrackCommand,
    ResizeClipCommand,
    SetAutomationPointCommand,
    SetTrackPropertyCommand,
    TimelineDocument,
    TrackState,
)


def _doc_with_track() -> tuple[TimelineDocument, TrackState]:
    doc = TimelineDocument()
    track = doc.add_track(TrackState(name="Music"))
    return doc, track


def test_add_remove_track_roundtrip():
    doc = TimelineDocument()
    stack = CommandStack()
    track = TrackState(name="Pads")
    stack.execute(AddTrackCommand(track), doc)
    assert len(doc.tracks) == 1

    stack.undo(doc)
    assert doc.tracks == []
    assert not stack.can_undo
    assert stack.can_redo

    stack.redo(doc)
    assert len(doc.tracks) == 1


def test_move_and_resize_undo_restores_exact_state():
    doc, track = _doc_with_track()
    clip = Clip(track.track_id, start_sec=0.0, duration_sec=60.0)
    stack = CommandStack()
    stack.execute(AddClipCommand(clip), doc)
    before = doc.to_dict()

    stack.execute(MoveClipCommand(clip.clip_id, 30.0), doc)
    stack.execute(ResizeClipCommand(clip.clip_id, 45.0), doc)
    assert doc.clip(clip.clip_id).start_sec == pytest.approx(30.0)

    stack.undo(doc)
    stack.undo(doc)
    assert doc.to_dict() == before


def test_remove_clip_then_undo_restores_it():
    doc, track = _doc_with_track()
    clip = doc.add_clip(Clip(track.track_id, start_sec=5.0, duration_sec=10.0))
    stack = CommandStack()
    stack.execute(RemoveClipCommand(clip.clip_id), doc)
    assert doc.clips == []
    stack.undo(doc)
    assert doc.clip(clip.clip_id).clip_id == clip.clip_id


def test_set_track_property_captures_old_value():
    doc, track = _doc_with_track()
    stack = CommandStack()
    command = SetTrackPropertyCommand(track.track_id, "volume_db", -8.0)
    stack.execute(command, doc)
    assert doc.track(track.track_id).volume_db == pytest.approx(-8.0)
    stack.undo(doc)
    assert doc.track(track.track_id).volume_db == pytest.approx(0.0)
    assert stack.next_redo_name == "Set track volume_db"


def test_invalid_property_field_rejected():
    with pytest.raises(ValidationError):
        SetTrackPropertyCommand("TRK-x", "color", 3)


def test_marker_commands_roundtrip():
    doc = TimelineDocument()
    marker = Marker(time_sec=42.0, label="Drop")
    stack = CommandStack()
    stack.execute(AddMarkerCommand(marker), doc)
    assert len(doc.markers) == 1
    stack.execute(RemoveMarkerCommand(marker.marker_id), doc)
    assert doc.markers == []
    stack.undo(doc)
    assert [m.label for m in doc.markers] == ["Drop"]
    stack.redo(doc)
    assert doc.markers == []
    stack.undo(doc)
    assert [m.label for m in doc.markers] == ["Drop"]


def test_automation_command_replaces_existing_point():
    doc, track = _doc_with_track()
    stack = CommandStack()
    stack.execute(SetAutomationPointCommand(track.track_id, "volume", 10.0, 0.3), doc)
    stack.execute(SetAutomationPointCommand(track.track_id, "volume", 10.0, 0.9), doc)
    lane = doc.lane(track.track_id, "volume")
    assert lane.points[0].value == pytest.approx(0.9)
    stack.undo(doc)
    assert lane.points[0].value == pytest.approx(0.3)
    stack.undo(doc)
    assert lane.points == []


def test_redo_cleared_after_new_execute():
    doc, track = _doc_with_track()
    stack = CommandStack()
    stack.execute(MoveClipCommand(
        doc.add_clip(Clip(track.track_id, start_sec=0.0, duration_sec=30.0)).clip_id, 5.0
    ), doc)
    stack.undo(doc)
    assert stack.can_redo
    other = Clip(track.track_id, start_sec=0.0, duration_sec=30.0)
    stack.execute(AddClipCommand(other), doc)
    assert not stack.can_redo


def test_stack_limit_trims_oldest():
    doc, track = _doc_with_track()
    stack = CommandStack(limit=3)
    for value in (1.0, 2.0, 3.0, 4.0):
        clip = doc.add_clip(Clip(track.track_id, start_sec=value, duration_sec=10.0))
        stack.execute(RemoveClipCommand(clip.clip_id), doc)
    assert len(stack._undo) == 3
    # Oldest command (value=1.0) was trimmed; undoing three times works.
    for _ in range(3):
        stack.undo(doc)
    assert len(doc.clips) == 3


def test_macro_is_atomic():
    doc, track = _doc_with_track()
    macro = MacroCommand(
        [
            AddTrackCommand(TrackState(name="Second")),
            AddClipCommand(Clip(track.track_id, start_sec=-5.0, duration_sec=10.0)),
        ],
        name="Bad batch",
    )
    stack = CommandStack()
    with pytest.raises(ValidationError):
        stack.execute(macro, doc)
    # Rollback removed the successfully-added second track.
    assert len(doc.tracks) == 1
    assert not stack.can_undo


def test_undo_on_empty_stack_returns_none():
    doc = TimelineDocument()
    assert CommandStack().undo(doc) is None
    assert CommandStack().redo(doc) is None


def test_execute_raises_leaves_stack_clean():
    doc = TimelineDocument()
    stack = CommandStack()
    with pytest.raises(ValidationError):
        stack.execute(RemoveTrackCommand("missing"), doc)
    assert not stack.can_undo
