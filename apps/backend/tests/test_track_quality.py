"""
Tests for detect_video.py track quality improvements:
  - filter_ephemeral_tracks: remove short auto tracks
  - stitch_tracks: merge temporally/spatially close fragments
  - _match_detection_to_track: matching gap constant
"""
from __future__ import annotations

import pytest

from auto_mosaic.domain.project import Keyframe, MaskTrack
from auto_mosaic.domain.track_quality import (
    MATCH_MAX_FRAME_GAP,
    MIN_TRACK_KEYFRAMES,
    STITCH_MAX_FRAME_GAP,
    filter_ephemeral_tracks,
    stitch_compatible,
    stitch_tracks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kf(frame: int, bbox: list[float] | None = None) -> Keyframe:
    b = bbox or [0.1, 0.1, 0.2, 0.2]
    return Keyframe(
        frame_index=frame,
        shape_type="polygon",
        points=[[b[0], b[1]], [b[0] + b[2], b[1]], [b[0] + b[2], b[1] + b[3]], [b[0], b[1] + b[3]]],
        bbox=list(b),
        confidence=0.9,
        source="detector",
    )


def _track(
    track_id: str,
    keyframes: list[Keyframe],
    source: str = "detector",
    user_edited: bool = False,
) -> MaskTrack:
    return MaskTrack(
        track_id=track_id,
        label=f"Track {track_id}",
        state="active",
        source=source,
        visible=True,
        keyframes=keyframes,
        user_edited=user_edited,
    )


# ---------------------------------------------------------------------------
# filter_ephemeral_tracks
# ---------------------------------------------------------------------------

class TestFilterEphemeralTracks:
    def test_removes_single_keyframe_track(self):
        tracks = [_track("t1", [_kf(0)])]
        result = filter_ephemeral_tracks(tracks)
        assert len(result) == 0

    def test_keeps_two_keyframe_track(self):
        tracks = [_track("t1", [_kf(0), _kf(10)])]
        result = filter_ephemeral_tracks(tracks)
        assert len(result) == 1

    def test_keeps_manual_single_keyframe_track(self):
        tracks = [_track("t1", [_kf(0)], source="manual", user_edited=True)]
        result = filter_ephemeral_tracks(tracks)
        assert len(result) == 1

    def test_mixed_keeps_valid_removes_ephemeral(self):
        t1 = _track("t1", [_kf(0)])
        t2 = _track("t2", [_kf(0), _kf(5), _kf(10)])
        t3 = _track("t3", [_kf(0)])
        result = filter_ephemeral_tracks([t1, t2, t3])
        assert len(result) == 1
        assert result[0].track_id == "t2"

    def test_empty_list(self):
        assert filter_ephemeral_tracks([]) == []


# ---------------------------------------------------------------------------
# stitch_compatible
# ---------------------------------------------------------------------------

class TestStitchCompatible:
    def test_adjacent_same_position(self):
        a = _track("a", [_kf(0), _kf(10)])
        b = _track("b", [_kf(15), _kf(20)])
        assert stitch_compatible(a, b) is True

    def test_gap_within_limit(self):
        a = _track("a", [_kf(0), _kf(10)])
        b = _track("b", [_kf(100), _kf(110)])
        assert stitch_compatible(a, b) is True

    def test_gap_exceeds_limit(self):
        a = _track("a", [_kf(0), _kf(10)])
        gap_start = 10 + STITCH_MAX_FRAME_GAP + 1
        b = _track("b", [_kf(gap_start), _kf(gap_start + 10)])
        assert stitch_compatible(a, b) is False

    def test_overlapping_rejected(self):
        a = _track("a", [_kf(0), _kf(10)])
        b = _track("b", [_kf(5), _kf(15)])
        assert stitch_compatible(a, b) is False

    def test_far_apart_spatially(self):
        a = _track("a", [_kf(0, [0.0, 0.0, 0.1, 0.1]), _kf(10, [0.0, 0.0, 0.1, 0.1])])
        b = _track("b", [_kf(15, [0.9, 0.9, 0.1, 0.1]), _kf(20, [0.9, 0.9, 0.1, 0.1])])
        assert stitch_compatible(a, b) is False

    def test_empty_tracks(self):
        a = _track("a", [])
        b = _track("b", [_kf(0)])
        assert stitch_compatible(a, b) is False


# ---------------------------------------------------------------------------
# stitch_tracks
# ---------------------------------------------------------------------------

class TestStitchTracks:
    def test_two_compatible_fragments_merged(self):
        a = _track("a", [_kf(0), _kf(10)])
        b = _track("b", [_kf(15), _kf(20)])
        result = stitch_tracks([a, b])
        assert len(result) == 1
        assert len(result[0].keyframes) == 4

    def test_incompatible_fragments_kept_separate(self):
        a = _track("a", [_kf(0, [0.0, 0.0, 0.1, 0.1]), _kf(10, [0.0, 0.0, 0.1, 0.1])])
        b = _track("b", [_kf(15, [0.9, 0.9, 0.1, 0.1]), _kf(20, [0.9, 0.9, 0.1, 0.1])])
        result = stitch_tracks([a, b])
        assert len(result) == 2

    def test_single_track_unchanged(self):
        a = _track("a", [_kf(0), _kf(10)])
        result = stitch_tracks([a])
        assert len(result) == 1
        assert len(result[0].keyframes) == 2

    def test_three_fragments_chained(self):
        a = _track("a", [_kf(0), _kf(10)])
        b = _track("b", [_kf(15), _kf(20)])
        c = _track("c", [_kf(25), _kf(30)])
        result = stitch_tracks([a, b, c])
        assert len(result) == 1
        assert len(result[0].keyframes) == 6


# ---------------------------------------------------------------------------
# Constants alignment
# ---------------------------------------------------------------------------

class TestTrackingConstants:
    def test_match_gap_aligned_with_pyside6(self):
        assert MATCH_MAX_FRAME_GAP == 60

    def test_min_keyframes_aligned_with_pyside6(self):
        assert MIN_TRACK_KEYFRAMES == 2

    def test_stitch_gap_aligned_with_pyside6(self):
        assert STITCH_MAX_FRAME_GAP == 180
