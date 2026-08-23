"""Timeline document model tests."""
import pytest

from lfms.core.errors import ValidationError
from lfms.timeline import AutomationPoint, Clip, Marker, TimelineDocument, TrackState


def _track(name: str = "Music", **overrides) -> TrackState:
    return TrackState(name=name, **overrides)


def _clip(track_id: str, start: float = 0.0, duration: float = 30.0) -> Clip:
    return Clip(track_id=track_id, start_sec=start, duration_sec=duration)


def test_add_and_remove_track_cascades():
    doc = TimelineDocument()
    track = doc.add_track(_track())
    doc.add_clip(_clip(track.track_id))
    doc.set_automation_point(track.track_id, "volume", 5.0, 0.8)
    assert len(doc.clips) == 1
    assert len(doc.lanes) == 1

    removed_track, removed_clips, removed_lanes = doc.remove_track(track.track_id)
    assert removed_track.track_id == track.track_id
    assert len(removed_clips) == 1
    assert len(removed_lanes) == 1
    assert doc.clips == []
    assert doc.lanes == []
    with pytest.raises(ValidationError):
        doc.track(track.track_id)


def test_track_validation_enforced():
    doc = TimelineDocument()
    with pytest.raises(ValidationError):
        doc.add_track(_track(kind="NOPE"))
    with pytest.raises(ValidationError):
        doc.add_track(TrackState(name="  "))
    with pytest.raises(ValidationError):
        doc.add_track(_track(volume_db=-100.0))


def test_duplicate_ids_rejected():
    doc = TimelineDocument()
    track = doc.add_track(_track())
    duplicate = _track()
    duplicate.track_id = track.track_id
    with pytest.raises(ValidationError):
        doc.add_track(duplicate)

    clip = _clip(track.track_id)
    doc.add_clip(clip)
    twin = _clip(track.track_id)
    twin.clip_id = clip.clip_id
    with pytest.raises(ValidationError):
        doc.add_clip(twin)


def test_clip_move_resize_with_bounds():
    doc = TimelineDocument()
    track = doc.add_track(_track())
    clip = doc.add_clip(_clip(track.track_id, start=10.0))

    moved = doc.move_clip(clip.clip_id, 25.0)
    assert moved.start_sec == pytest.approx(25.0)
    resized = doc.resize_clip(clip.clip_id, 12.5)
    assert resized.duration_sec == pytest.approx(12.5)
    assert resized.end_sec == pytest.approx(37.5)

    with pytest.raises(ValidationError):
        doc.move_clip(clip.clip_id, -1.0)
    with pytest.raises(ValidationError):
        doc.resize_clip(clip.clip_id, 0.0)


def test_clips_in_range_and_on_track_sorted():
    doc = TimelineDocument()
    track_a = doc.add_track(_track("A"))
    track_b = doc.add_track(_track("B"))
    for start in (50.0, 10.0, 90.0):
        doc.add_clip(_clip(track_b.track_id, start=start))
    doc.add_clip(_clip(track_a.track_id, start=15.0))

    on_b = doc.clips_on_track(track_b.track_id)
    assert [c.start_sec for c in on_b] == [10.0, 50.0, 90.0]
    overlapping = doc.clips_in_range(45.0, 55.0)
    assert {c.track_id for c in overlapping} == {track_b.track_id}


def test_markers_stay_time_sorted():
    doc = TimelineDocument()
    doc.add_marker(Marker(time_sec=40.0, label="B"))
    doc.add_marker(Marker(time_sec=10.0, label="A"))
    doc.add_marker(Marker(time_sec=25.0, label="C"))
    assert [m.label for m in doc.markers] == ["A", "C", "B"]
    with pytest.raises(ValidationError):
        doc.add_marker(Marker(time_sec=-1.0, label="X"))


def test_automation_points_replace_at_same_time_and_sort():
    doc = TimelineDocument()
    track = doc.add_track(_track())
    doc.set_automation_point(track.track_id, "volume", 10.0, 0.2)
    doc.set_automation_point(track.track_id, "volume", 20.0, 0.9)
    doc.set_automation_point(track.track_id, "volume", 10.0, 0.5)
    lane = doc.lane(track.track_id, "volume")
    assert [p.value for p in lane.points] == [0.5, 0.9]
    with pytest.raises(ValidationError):
        doc.set_automation_point(track.track_id, "volume", 5.0, 2.0)
    with pytest.raises(ValidationError):
        doc.set_automation_point(track.track_id, "tempo", 5.0, 0.5)


def test_remove_automation_point_missing_raises():
    doc = TimelineDocument()
    track = doc.add_track(_track())
    with pytest.raises(ValidationError):
        doc.remove_automation_point(track.track_id, "pan", 3.0)


def test_serialization_roundtrip_preserves_document():
    doc = TimelineDocument(title="Demo", duration_sec=300.0)
    track_a = doc.add_track(_track("Music A"))
    track_b = doc.add_track(_track("Ambience", kind="AMBIENCE", volume_db=-6.0))
    doc.add_clip(Clip(track_a.track_id, start_sec=0.0, duration_sec=120.0, label="Theme"))
    doc.add_clip(
        Clip(
            track_b.track_id,
            start_sec=60.0,
            duration_sec=200.0,
            source_kind="AUDIO_FILE",
            source_ref=r"G:\audio\rain.wav",
            gain_db=-3.0,
        )
    )
    doc.set_automation_point(track_a.track_id, "volume", 30.0, 0.75)
    doc.set_automation_point(track_b.track_id, "pan", 10.0, 0.25)
    doc.add_marker(Marker(time_sec=120.0, label="Chapter 2"))

    restored = TimelineDocument.from_dict(doc.to_dict())
    assert restored.to_dict() == doc.to_dict()
    assert restored.title == "Demo"
    assert len(restored.tracks) == 2
    assert len(restored.clips) == 2
    assert restored.markers[0].label == "Chapter 2"
    points = restored.lanes[0].points
    assert isinstance(points[0], AutomationPoint)
