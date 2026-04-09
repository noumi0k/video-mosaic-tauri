"""
Unit tests for W5: merge_held_segments.

Verifies:
  - adjacent held + held → merged
  - adjacent uncertain + uncertain → merged
  - overlapping held + held → merged
  - overlapping uncertain + uncertain → merged
  - held + uncertain → NOT merged (different states)
  - separated same-state → NOT merged (gap ≥ 1 frame)
  - three-way merge of adjacent same-state segments
  - idempotent (calling twice has no extra effect)
  - other states ("confirmed", "detected") are untouched
  - keyframes are never mutated
  - empty segment list is a no-op
  - no mergeable segments is a no-op
  - detect integration: fragmented same-state segments normalised after detect pass
"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import numpy as np

from auto_mosaic.domain.mask_continuity import merge_held_segments
from auto_mosaic.domain.project import Keyframe, MaskSegment, MaskTrack
from auto_mosaic.infra.ai.detect_video import _apply_frame_detections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL_DIR = Path(tempfile.mkdtemp(prefix="taurimozaic-merge-held-"))
_MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _track(*segments: MaskSegment) -> MaskTrack:
    """Create a minimal MaskTrack with the given segments."""
    track = MaskTrack(
        track_id="t1", label="T", state="detected", source="detector", visible=True,
    )
    track.segments = list(segments)
    return track


def _seg(start: int, end: int, state: str) -> MaskSegment:
    return MaskSegment(start_frame=start, end_frame=end, state=state)


def _kf(frame: int) -> Keyframe:
    return Keyframe(
        frame_index=frame,
        shape_type="polygon",
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=[0.1, 0.1, 0.1, 0.1],
        confidence=0.9,
        source="detector",
    )


def _det(bbox: list[float], score: float) -> dict:
    return {"bbox_norm": bbox, "score": score}


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Adjacent merges
# ---------------------------------------------------------------------------

def test_adjacent_held_merges() -> None:
    """[0,3] held + [4,7] held → [0,7] held."""
    track = _track(_seg(0, 3, "held"), _seg(4, 7, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 0
    assert s.end_frame == 7
    assert s.state == "held"


def test_adjacent_uncertain_merges() -> None:
    """[0,3] uncertain + [4,7] uncertain → [0,7] uncertain."""
    track = _track(_seg(0, 3, "uncertain"), _seg(4, 7, "uncertain"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 0
    assert s.end_frame == 7
    assert s.state == "uncertain"


# ---------------------------------------------------------------------------
# Overlapping merges
# ---------------------------------------------------------------------------

def test_overlapping_held_merges() -> None:
    """[0,5] held + [3,8] held → [0,8] held."""
    track = _track(_seg(0, 5, "held"), _seg(3, 8, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 0
    assert s.end_frame == 8
    assert s.state == "held"


def test_overlapping_uncertain_merges() -> None:
    """[2,6] uncertain + [4,9] uncertain → [2,9] uncertain."""
    track = _track(_seg(2, 6, "uncertain"), _seg(4, 9, "uncertain"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 2
    assert s.end_frame == 9
    assert s.state == "uncertain"


# ---------------------------------------------------------------------------
# Different states must NOT merge
# ---------------------------------------------------------------------------

def test_held_and_uncertain_do_not_merge() -> None:
    """Adjacent [0,3] held + [4,7] uncertain must remain two separate segments."""
    track = _track(_seg(0, 3, "held"), _seg(4, 7, "uncertain"))
    merge_held_segments(track)
    assert len(track.segments) == 2
    states = {s.state for s in track.segments}
    assert states == {"held", "uncertain"}


def test_held_and_uncertain_do_not_merge_reversed() -> None:
    """Adjacent [0,3] uncertain + [4,7] held must also remain separate."""
    track = _track(_seg(0, 3, "uncertain"), _seg(4, 7, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 2


# ---------------------------------------------------------------------------
# Separated segments do NOT merge
# ---------------------------------------------------------------------------

def test_separated_held_do_not_merge() -> None:
    """[0,3] held and [5,8] held have a gap at frame 4 → no merge."""
    track = _track(_seg(0, 3, "held"), _seg(5, 8, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 2
    assert track.segments[0].end_frame == 3
    assert track.segments[1].start_frame == 5


def test_separated_uncertain_do_not_merge() -> None:
    """[1,4] uncertain and [6,9] uncertain — gap at frame 5 → no merge."""
    track = _track(_seg(1, 4, "uncertain"), _seg(6, 9, "uncertain"))
    merge_held_segments(track)
    assert len(track.segments) == 2


# ---------------------------------------------------------------------------
# Three-way merge
# ---------------------------------------------------------------------------

def test_three_adjacent_held_merge_into_one() -> None:
    """[0,3] + [4,7] + [8,11] held → [0,11] held."""
    track = _track(_seg(0, 3, "held"), _seg(4, 7, "held"), _seg(8, 11, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 0
    assert s.end_frame == 11
    assert s.state == "held"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotent_adjacent_held() -> None:
    """Calling merge_held_segments twice gives the same result as once."""
    track = _track(_seg(0, 3, "held"), _seg(4, 7, "held"))
    merge_held_segments(track)
    segs_after_first = [(s.start_frame, s.end_frame, s.state) for s in track.segments]
    merge_held_segments(track)
    segs_after_second = [(s.start_frame, s.end_frame, s.state) for s in track.segments]
    assert segs_after_first == segs_after_second


def test_idempotent_no_change_needed() -> None:
    """A single held segment is unchanged by merge_held_segments."""
    track = _track(_seg(0, 10, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    assert track.segments[0].start_frame == 0
    assert track.segments[0].end_frame == 10


# ---------------------------------------------------------------------------
# Other states untouched
# ---------------------------------------------------------------------------

def test_confirmed_segment_untouched() -> None:
    """Segments with state 'confirmed' are not modified."""
    track = _track(_seg(0, 10, "confirmed"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    assert track.segments[0].state == "confirmed"
    assert track.segments[0].start_frame == 0
    assert track.segments[0].end_frame == 10


def test_mixed_states_confirmed_held() -> None:
    """confirmed + two adjacent held → confirmed untouched, held merged."""
    track = _track(
        _seg(0, 5, "confirmed"),
        _seg(10, 14, "held"),
        _seg(15, 20, "held"),
    )
    merge_held_segments(track)
    assert len(track.segments) == 2
    confirmed = [s for s in track.segments if s.state == "confirmed"]
    held = [s for s in track.segments if s.state == "held"]
    assert len(confirmed) == 1
    assert confirmed[0].start_frame == 0 and confirmed[0].end_frame == 5
    assert len(held) == 1
    assert held[0].start_frame == 10 and held[0].end_frame == 20


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_segments_noop() -> None:
    """Track with no segments does not raise."""
    track = _track()
    merge_held_segments(track)  # must not raise
    assert track.segments == []


def test_no_mergeable_segments_noop() -> None:
    """Track with only non-mergeable states passes through unchanged."""
    track = _track(_seg(0, 5, "confirmed"), _seg(6, 10, "detected"))
    merge_held_segments(track)
    assert len(track.segments) == 2


def test_keyframes_not_mutated() -> None:
    """merge_held_segments must not touch track.keyframes."""
    track = _track(_seg(0, 3, "held"), _seg(4, 7, "held"))
    track.keyframes = [_kf(0), _kf(5)]
    kf_before = copy.deepcopy(track.keyframes)
    merge_held_segments(track)
    assert len(track.keyframes) == 2
    for before, after in zip(kf_before, track.keyframes):
        assert before.frame_index == after.frame_index
        assert before.source == after.source


def test_single_frame_segments_merge() -> None:
    """Three consecutive single-frame held segments merge into one span."""
    track = _track(_seg(5, 5, "held"), _seg(6, 6, "held"), _seg(7, 7, "held"))
    merge_held_segments(track)
    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 5
    assert s.end_frame == 7
    assert s.state == "held"


# ---------------------------------------------------------------------------
# Detect integration: fragmented segments normalised after simulated detect pass
# ---------------------------------------------------------------------------

def test_detect_integration_fragmented_segments_normalised() -> None:
    """
    Simulates a track loaded from a legacy project where the same-state adjacent
    segments were stored as fragments.  merge_held_segments must collapse them.
    """
    track = MaskTrack(
        track_id="t1", label="T", state="detected", source="detector", visible=True,
    )
    # Simulate pre-fragmented state (e.g., from a legacy project load or
    # a prior version that stored single-frame segments without contiguous extension).
    track.keyframes = [_kf(0)]
    track.segments = [
        _seg(2, 2, "held"),
        _seg(3, 3, "held"),
        _seg(4, 4, "held"),
        _seg(5, 5, "held"),
    ]

    merge_held_segments(track)

    assert len(track.segments) == 1
    s = track.segments[0]
    assert s.start_frame == 2
    assert s.end_frame == 5
    assert s.state == "held"
    # Keyframe must be untouched.
    assert track.keyframes[0].frame_index == 0


def test_detect_path_consecutive_rejects_produce_single_segment_after_merge() -> None:
    """
    After running _apply_frame_detections for several rejected frames and then
    calling merge_held_segments, the track must have exactly one held segment
    covering all rejected frames (no fragmentation).
    """
    tracks: list[MaskTrack] = []
    cursors: list = []

    # Frame 0: good detection → WRITE_DETECTED (kf written, no segment).
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # Frames 2, 3, 4: low confidence → EXTEND_HELD.
    for frame in [2, 3, 4]:
        _apply_frame_detections(
            [_det([0.11, 0.10, 0.20, 0.20], 0.15)],
            frame, _frame(), "none", _MODEL_DIR, tracks, cursors,
        )

    # Simulate the track-finalisation step in detect_video.py.
    for track in tracks:
        track.keyframes.sort(key=lambda kf: kf.frame_index)
        merge_held_segments(track)

    assert len(tracks) == 1
    track = tracks[0]
    held = [s for s in track.segments if s.state == "held"]
    assert len(held) == 1, f"expected 1 held segment, got {held}"
    assert held[0].start_frame == 2
    assert held[0].end_frame == 4
