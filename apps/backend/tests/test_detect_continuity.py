"""
W1-W4 integration tests for the detect write path.

Calls _apply_frame_detections directly (bypassing ONNX inference) to verify:
  - Consistent detections write keyframes (ACCEPT → WRITE_DETECTED).
  - Inconsistent/low-quality detections extend held segments (REJECT → EXTEND_HELD).
  - Marginal detections produce anchored keyframes (ACCEPT_ANCHORED → WRITE_ANCHORED).
  - Manual keyframes are never overwritten (SKIP).
  - Existing track-matching behaviour is preserved.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from auto_mosaic.domain.project import Keyframe, MaskTrack
from auto_mosaic.infra.ai.detect_video import _TrackCursor, _apply_frame_detections

# Temp directory shared by all tests in this module (mirrors test_cli_smoke pattern).
_TEST_DIR = Path(tempfile.mkdtemp(prefix="taurimozaic-detect-continuity-"))
_MODEL_DIR = _TEST_DIR / "models"
_MODEL_DIR.mkdir(parents=True, exist_ok=True)


def _frame() -> np.ndarray:
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _det(bbox: list[float], score: float) -> dict:
    return {"bbox_norm": bbox, "score": score}


# ---------------------------------------------------------------------------
# First detection always writes (no continuity history on a new track)
# ---------------------------------------------------------------------------

def test_first_detection_on_new_track_always_writes() -> None:
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    assert len(tracks) == 1
    assert len(tracks[0].keyframes) == 1
    assert tracks[0].keyframes[0].frame_index == 0
    assert len(tracks[0].segments) == 0


# ---------------------------------------------------------------------------
# Accept: consistent detection writes keyframe (ACCEPT → WRITE_DETECTED)
# ---------------------------------------------------------------------------

def test_consistent_detection_writes_keyframe() -> None:
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # Near-identical detection — all continuity axes pass → ACCEPT
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.92)],
        2, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    assert len(tracks) == 1
    track = tracks[0]
    assert len(track.keyframes) == 2
    assert track.keyframes[0].frame_index == 0
    assert track.keyframes[1].frame_index == 2
    assert len(track.segments) == 0
    # The written keyframe carries the detection's bbox.
    assert abs(track.keyframes[1].bbox[0] - 0.11) < 1e-5


# ---------------------------------------------------------------------------
# Reject: hard reject (confidence < _CONFIDENCE_REJECT=0.20) → EXTEND_HELD
# ---------------------------------------------------------------------------

def test_low_confidence_detection_extends_held_not_keyframe() -> None:
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # confidence=0.15 < _CONFIDENCE_REJECT (0.20) → hard reject → EXTEND_HELD
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.15)],
        2, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    track = tracks[0]
    assert len(track.keyframes) == 1, "rejected detection must not create a keyframe"
    assert track.keyframes[0].frame_index == 0
    assert len(track.segments) == 1
    assert track.segments[0].start_frame == 2
    assert track.segments[0].end_frame == 2
    assert track.segments[0].state == "held"


def test_consecutive_rejects_extend_single_held_segment() -> None:
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # Frames 2 and 3 both rejected: held segment should grow contiguously.
    for frame in [2, 3]:
        _apply_frame_detections(
            [_det([0.11, 0.10, 0.20, 0.20], 0.15)],
            frame, _frame(), "none", _MODEL_DIR, tracks, cursors,
        )
    track = tracks[0]
    assert len(track.keyframes) == 1
    assert len(track.segments) == 1
    assert track.segments[0].start_frame == 2
    assert track.segments[0].end_frame == 3
    assert track.segments[0].state == "held"


# ---------------------------------------------------------------------------
# Accept-anchored: marginal detection → WRITE_ANCHORED
# frame_gap=15 (soft-fail) + confidence=0.30 (soft-fail) = exactly 2 soft-fails
# → ACCEPT_ANCHORED → shape copied from frame 0 anchor, bbox from detection
# ---------------------------------------------------------------------------

def test_marginal_detection_writes_anchored_keyframe() -> None:
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    anchor_kf = tracks[0].keyframes[0]

    # gap=10 > _FRAME_GAP_PASS(8) → soft-fail; gap ≤ 12 so cursor matching still passes
    # confidence=0.30 < _CONFIDENCE_PASS(0.50) → soft-fail
    # all geometric axes pass (near-identical position) → ACCEPT_ANCHORED (2 soft-fails)
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.30)],
        10, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    track = tracks[0]
    assert len(track.keyframes) == 2, "WRITE_ANCHORED must produce a keyframe"
    kf10 = track.keyframes[1]
    assert kf10.frame_index == 10
    # bbox and confidence come from the candidate.
    assert abs(kf10.bbox[0] - 0.11) < 1e-5
    assert abs(kf10.confidence - 0.30) < 1e-5
    # shape_type and points are inherited from the anchor.
    assert kf10.shape_type == anchor_kf.shape_type
    assert kf10.points == anchor_kf.points


# ---------------------------------------------------------------------------
# Manual protection: manual keyframe at the target frame → SKIP
# ---------------------------------------------------------------------------

def test_manual_keyframe_not_overwritten_by_detector() -> None:
    """
    If a track already carries a manual keyframe at frame N, a detector
    detection at frame N must be silently skipped (decide_write step 0).
    """
    manual_kf = Keyframe(
        frame_index=5,
        shape_type="ellipse",
        points=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
        bbox=[0.1, 0.1, 0.2, 0.2],
        confidence=1.0,
        source="manual",
    )
    prior_kf = Keyframe(
        frame_index=0,
        shape_type="ellipse",
        points=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
        bbox=[0.1, 0.1, 0.2, 0.2],
        confidence=0.90,
        source="detector",
    )
    track = MaskTrack(
        track_id="test-manual-track",
        label="test",
        state="active",
        source="manual",
        visible=True,
        keyframes=[prior_kf, manual_kf],
    )
    cursor = _TrackCursor(
        track=track,
        last_frame_index=5,
        last_bbox=[0.1, 0.1, 0.2, 0.2],
    )
    tracks = [track]
    cursors = [cursor]

    _apply_frame_detections(
        [_det([0.11, 0.11, 0.20, 0.20], 0.85)],
        5, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )

    kfs_at_5 = [kf for kf in track.keyframes if kf.frame_index == 5]
    assert len(kfs_at_5) == 1, "only the original manual kf should remain"
    assert kfs_at_5[0].source == "manual"
    assert kfs_at_5[0].confidence == 1.0


# ---------------------------------------------------------------------------
# Regression: existing track-matching behaviour survives W1-W4 integration
# ---------------------------------------------------------------------------

def test_track_matching_identity_preserved() -> None:
    """Two tracks retain their spatial identities across frames."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    tracks: list[MaskTrack] = []
    cursors: list = []

    _apply_frame_detections(
        [
            _det([0.10, 0.10, 0.16, 0.16], 0.95),
            _det([0.62, 0.10, 0.16, 0.16], 0.93),
        ],
        0, frame, "none", _MODEL_DIR, tracks, cursors,
    )
    _apply_frame_detections(
        [
            _det([0.60, 0.10, 0.16, 0.16], 0.94),
            _det([0.12, 0.10, 0.16, 0.16], 0.92),
        ],
        2, frame, "none", _MODEL_DIR, tracks, cursors,
    )

    assert len(tracks) == 2
    assert [kf.frame_index for kf in tracks[0].keyframes] == [0, 2]
    assert [kf.frame_index for kf in tracks[1].keyframes] == [0, 2]
    assert tracks[0].keyframes[1].bbox[0] < 0.2     # track 0 stayed near x=0.10
    assert tracks[1].keyframes[1].bbox[0] > 0.5     # track 1 stayed near x=0.62


def test_track_matching_creates_new_track_for_far_detection() -> None:
    """A detection too far from any existing cursor spawns a new track."""
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    tracks: list[MaskTrack] = []
    cursors: list = []

    _apply_frame_detections(
        [_det([0.10, 0.10, 0.16, 0.16], 0.95)],
        0, frame, "none", _MODEL_DIR, tracks, cursors,
    )
    _apply_frame_detections(
        [_det([0.72, 0.58, 0.16, 0.16], 0.90)],
        1, frame, "none", _MODEL_DIR, tracks, cursors,
    )

    assert len(tracks) == 2
    assert [kf.frame_index for kf in tracks[0].keyframes] == [0]
    assert [kf.frame_index for kf in tracks[1].keyframes] == [1]


# ---------------------------------------------------------------------------
# Cursor advances on reject so the track stays matchable next frame
# ---------------------------------------------------------------------------

def test_cursor_advances_on_reject_so_track_stays_matchable() -> None:
    """
    After a REJECT at frame 2, the cursor must advance to frame 2 so that
    a good detection at frame 3 can still match this track (gap ≤ 12).
    """
    tracks: list[MaskTrack] = []
    cursors: list = []
    _apply_frame_detections(
        [_det([0.10, 0.10, 0.20, 0.20], 0.90)],
        0, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # Frame 2: hard reject (low confidence)
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.15)],
        2, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    # Frame 3: good detection — must still match the same track
    _apply_frame_detections(
        [_det([0.11, 0.10, 0.20, 0.20], 0.90)],
        3, _frame(), "none", _MODEL_DIR, tracks, cursors,
    )
    assert len(tracks) == 1, "no spurious new track should be created at frame 3"
    kf_frames = [kf.frame_index for kf in tracks[0].keyframes]
    assert 3 in kf_frames, "good detection at frame 3 must be written to the existing track"
