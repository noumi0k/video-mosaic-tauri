"""
Post-detection track quality improvements: ephemeral track filtering and
fragment stitching.

Pure functions — no cv2/numpy dependency.  Imported by detect_video.py
after detection to clean up the raw track list.

Constants are aligned with PySide6's TrackingService defaults.
"""
from __future__ import annotations

import math

from auto_mosaic.domain.project import MaskTrack


# ---------------------------------------------------------------------------
# Constants — aligned with PySide6 TrackingService
# ---------------------------------------------------------------------------

MATCH_MAX_FRAME_GAP: int = 60
"""Maximum frame gap for matching a detection to an existing track cursor.
PySide6 TrackingService uses max_frame_gap=60."""

MIN_TRACK_KEYFRAMES: int = 2
"""Tracks with fewer keyframes than this are filtered as ephemeral.
PySide6 uses min_auto_keyframes=2."""

STITCH_MAX_FRAME_GAP: int = 180
"""Maximum gap between last frame of track A and first frame of track B
for fragment stitching.  PySide6 uses stitch_max_frame_gap=180."""

STITCH_MIN_AREA_SIMILARITY: float = 0.22
"""Minimum area ratio similarity for stitching.  Range [0, 1]."""

STITCH_MAX_CENTER_DISTANCE_RATIO: float = 1.8
"""Maximum normalized center distance for stitching candidates."""


# ---------------------------------------------------------------------------
# Geometry helpers (no numpy)
# ---------------------------------------------------------------------------

def _bbox_area(bbox: list[float]) -> float:
    if len(bbox) < 4:
        return 0.0
    return max(bbox[2], 0.0) * max(bbox[3], 0.0)


def _bbox_center_distance(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a[0], a[1], a[2], a[3]
    bx, by, bw, bh = b[0], b[1], b[2], b[3]
    acx = ax + (aw / 2.0)
    acy = ay + (ah / 2.0)
    bcx = bx + (bw / 2.0)
    bcy = by + (bh / 2.0)
    return math.hypot(acx - bcx, acy - bcy)


# ---------------------------------------------------------------------------
# Ephemeral track filtering
# ---------------------------------------------------------------------------

def filter_ephemeral_tracks(
    tracks: list[MaskTrack],
    min_keyframes: int = MIN_TRACK_KEYFRAMES,
) -> list[MaskTrack]:
    """Remove detector tracks with fewer than *min_keyframes* keyframes.

    Ephemeral single-keyframe tracks are typically noise.  PySide6's
    TrackingService uses min_auto_keyframes=2 for the same purpose.
    Manual/user-edited tracks are never filtered.
    """
    result = []
    for track in tracks:
        if track.user_edited or track.source != "detector":
            result.append(track)
            continue
        if len(track.keyframes) >= min_keyframes:
            result.append(track)
    return result


# ---------------------------------------------------------------------------
# Fragment stitching
# ---------------------------------------------------------------------------

def stitch_compatible(
    track_a: MaskTrack,
    track_b: MaskTrack,
    max_frame_gap: int = STITCH_MAX_FRAME_GAP,
    max_center_dist_ratio: float = STITCH_MAX_CENTER_DISTANCE_RATIO,
    min_area_similarity: float = STITCH_MIN_AREA_SIMILARITY,
) -> bool:
    """Check if two tracks can be stitched together.

    track_a must end before track_b starts.  Checks temporal gap and spatial
    similarity between the last keyframe of track_a and the first keyframe
    of track_b.
    """
    if not track_a.keyframes or not track_b.keyframes:
        return False

    last_kf_a = track_a.keyframes[-1]
    first_kf_b = track_b.keyframes[0]

    frame_gap = first_kf_b.frame_index - last_kf_a.frame_index
    if frame_gap <= 0 or frame_gap > max_frame_gap:
        return False

    bbox_a = last_kf_a.bbox
    bbox_b = first_kf_b.bbox

    # Center distance check.
    distance = _bbox_center_distance(bbox_a, bbox_b)
    scale = max(bbox_a[2], bbox_a[3], bbox_b[2], bbox_b[3], 1e-6)
    if (distance / scale) > max_center_dist_ratio:
        return False

    # Area similarity check.
    area_a = _bbox_area(bbox_a)
    area_b = _bbox_area(bbox_b)
    if area_a > 0 and area_b > 0:
        ratio = min(area_a, area_b) / max(area_a, area_b)
        if ratio < min_area_similarity:
            return False

    return True


def stitch_tracks(tracks: list[MaskTrack]) -> list[MaskTrack]:
    """Merge fragmented tracks that are close in time and space.

    Greedy single-pass: for each track (sorted by first keyframe), try to
    append it to an existing stitched track.  If compatible, merge keyframes
    and segments.  Otherwise keep it as a separate track.

    PySide6's TrackingService stitch uses stitch_max_frame_gap=180 with
    center distance, area similarity, and aspect similarity checks.
    """
    if len(tracks) <= 1:
        return tracks

    sorted_tracks = sorted(
        tracks,
        key=lambda t: t.keyframes[0].frame_index if t.keyframes else float("inf"),
    )

    result: list[MaskTrack] = [sorted_tracks[0]]
    for candidate in sorted_tracks[1:]:
        merged = False
        for target in result:
            if stitch_compatible(target, candidate):
                target.keyframes.extend(candidate.keyframes)
                target.keyframes.sort(key=lambda kf: kf.frame_index)
                target.segments.extend(candidate.segments)
                target.segments.sort(key=lambda s: (s.start_frame, s.end_frame))
                merged = True
                break
        if not merged:
            result.append(candidate)

    return result
