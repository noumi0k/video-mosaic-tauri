"""
Mask track continuity evaluation, write decision, write-action mutation,
ellipse interpolation, export resolver, and editing resolver.

Phase 4 — W1, W2, W3, W4, W5, W6, W7, W8.

W1-W3, W6, W7, W8 are side-effect-free pure functions.
W4 (apply_write_action) and W5 (merge_held_segments) mutate the track in-place.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from auto_mosaic.domain.project import Keyframe, MaskSegment, MaskTrack


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANCHOR_DECAY_FRAMES: int = 60
"""Frames after which a manual anchor is considered expired.
Default ≈ 2 seconds at 30 fps.  Future: move to detector_config."""

# Continuity thresholds — conservative initial values.
# Future Phase 5: expose via ContinuityConfig dataclass for detector_config overrides.

_IOU_PASS: float = 0.5
_IOU_REJECT: float = 0.1

_CENTER_DIST_PASS: float = 0.25    # fraction of max(diag_anchor, diag_candidate)
_CENTER_DIST_REJECT: float = 1.0

_AREA_RATIO_PASS_MIN: float = 0.70   # area_candidate / area_anchor
_AREA_RATIO_PASS_MAX: float = 1.43   # ≈ sqrt(2)
_AREA_RATIO_REJECT_MIN: float = 0.40
_AREA_RATIO_REJECT_MAX: float = 2.50

_ASPECT_RATIO_PASS_MIN: float = 0.80   # (w_c/h_c) / (w_a/h_a)
_ASPECT_RATIO_PASS_MAX: float = 1.25
_ASPECT_RATIO_REJECT_MIN: float = 0.50
_ASPECT_RATIO_REJECT_MAX: float = 2.00

_CONFIDENCE_PASS: float = 0.50
_CONFIDENCE_REJECT: float = 0.20

_FRAME_GAP_PASS: int = 8
_FRAME_GAP_REJECT: int = 30

_FAIL_COUNT_FOR_ACCEPT_ANCHORED: int = 2
"""accept_anchored tolerates at most this many soft-fails (no hard rejects)."""

_INTERPOLATE_MAX_GAP: int = 30
"""Maximum keyframe span (frames) for which interpolation is allowed in
resolve_for_render.  Matches _FRAME_GAP_REJECT so that any span that would be
hard-rejected by the continuity evaluator is also too wide for interpolation."""

_POLYGON_MIN_VERTICES: int = 3
"""Minimum polygon vertex count required for interpolation."""

_MANUAL_SOURCES: frozenset[str] = frozenset({"manual"})
"""source values that count as a manual anchor.
Phase 4: manual_edit / manual_anchor source_details are not yet distinct,
so any kf with source=="manual" qualifies."""


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class ContinuityVerdict(str, Enum):
    """Result of evaluate_continuity.

    ACCEPT         — all 6 axes satisfy their pass threshold.
    ACCEPT_ANCHORED — 1-2 axes are marginal (none trigger hard-reject).
                      Write the keyframe using the anchor's shape but auto's position/scale.
    REJECT         — ≥1 axis triggers hard-reject, or ≥3 axes fail to pass.
                      Do not write a new keyframe; extend held/uncertain segment.
    """
    ACCEPT = "accept"
    ACCEPT_ANCHORED = "accept_anchored"
    REJECT = "reject"


class WriteAction(str, Enum):
    """Action resolved by decide_write.

    WRITE_DETECTED  — write a new Keyframe with auto detection data (source="detector")
    WRITE_ANCHORED  — write a new Keyframe: shape from anchor, position/bbox from auto
    EXTEND_HELD     — no new Keyframe; extend preceding segment as state="held"
    EXTEND_UNCERTAIN — no new Keyframe; extend preceding segment as state="uncertain"
                      (manual anchor is active and auto detection broke)
    SKIP            — no Keyframe and no segment extension
                      (no prior context, or manual kf already occupies this frame)
    """
    WRITE_DETECTED = "write_detected"
    WRITE_ANCHORED = "write_anchored"
    EXTEND_HELD = "extend_held"
    EXTEND_UNCERTAIN = "extend_uncertain"
    SKIP = "skip"


@dataclass(frozen=True)
class CandidateBBox:
    """Auto-detection candidate for a single frame.

    bbox: (x1, y1, w, h) normalized to [0, 1].
    confidence: detector-reported score in [0, 1].
    shape_type: "polygon" or "ellipse".
    """
    bbox: tuple[float, float, float, float]
    confidence: float
    shape_type: str


@dataclass(frozen=True)
class WriteDecision:
    """Output of decide_write.

    action: what the detect pipeline should do for this frame.
    anchor_frame: for WRITE_ANCHORED actions, the frame_index of the keyframe
                  whose shape (points / rotation) should be copied verbatim.
                  None for all other actions.
    """
    action: WriteAction
    anchor_frame: int | None = None


class ResolveReason(str, Enum):
    """Why a specific Keyframe was returned by resolve_for_render.

    EXPLICIT        — frame_idx has an exact keyframe in track.keyframes.
    INTERPOLATED    — synthesized via interpolate_ellipse between two adjacent
                      ellipse keyframes (gap ≤ _INTERPOLATE_MAX_GAP).
    HELD_FROM_PRIOR — the most recent prior keyframe was returned because
                      interpolation conditions were not satisfied.
    """
    EXPLICIT = "explicit"
    INTERPOLATED = "interpolated"
    HELD_FROM_PRIOR = "held_from_prior"


# ---------------------------------------------------------------------------
# Internal geometry helpers  (no numpy dependency)
# ---------------------------------------------------------------------------

def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Intersection-over-Union of two XYWH bboxes."""
    ax1, ay1, aw, ah = a[0], a[1], a[2], a[3]
    bx1, by1, bw, bh = b[0], b[1], b[2], b[3]
    ax2 = ax1 + aw
    ay2 = ay1 + ah
    bx2 = bx1 + bw
    by2 = by1 + bh
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(aw, 0.0) * max(ah, 0.0)
    area_b = max(bw, 0.0) * max(bh, 0.0)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _center_dist_ratio(a: tuple[float, ...], c: tuple[float, ...]) -> float:
    """‖center_a - center_c‖ / max(diag_a, diag_c).  Scale-invariant."""
    ax1, ay1, aw, ah = a[0], a[1], a[2], a[3]
    cx1, cy1, cw, ch = c[0], c[1], c[2], c[3]
    acx = ax1 + aw * 0.5
    acy = ay1 + ah * 0.5
    ccx = cx1 + cw * 0.5
    ccy = cy1 + ch * 0.5
    dist = math.hypot(acx - ccx, acy - ccy)
    diag_a = math.hypot(max(aw, 0.0), max(ah, 0.0))
    diag_c = math.hypot(max(cw, 0.0), max(ch, 0.0))
    scale = max(diag_a, diag_c, 1e-8)
    return dist / scale


def _area_ratio(a: tuple[float, ...], c: tuple[float, ...]) -> float:
    """area_candidate / area_anchor.  Returns 1.0 on degenerate anchor."""
    _, _, aw, ah = a[0], a[1], a[2], a[3]
    _, _, cw, ch = c[0], c[1], c[2], c[3]
    area_a = max(aw, 0.0) * max(ah, 0.0)
    area_c = max(cw, 0.0) * max(ch, 0.0)
    if area_a <= 0.0:
        return 1.0
    return area_c / area_a


def _aspect_ratio(bbox: tuple[float, ...]) -> float:
    """w / h.  Returns 1.0 on degenerate height."""
    _, _, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
    if h <= 0.0:
        return 1.0
    return w / h


# ---------------------------------------------------------------------------
# W1: evaluate_continuity
# ---------------------------------------------------------------------------

def evaluate_continuity(
    anchor: "Keyframe",
    candidate: CandidateBBox,
    frame_gap: int,
) -> ContinuityVerdict:
    """Evaluate whether a candidate auto-detection is consistent with an anchor keyframe.

    Pure function — no side effects, no mutations.

    Args:
        anchor:    The most-recent stable keyframe used as reference.
        candidate: The auto-detection for the current frame.
        frame_gap: Number of frames since anchor.frame_index.

    Returns:
        ContinuityVerdict.ACCEPT          — all 6 axes pass.
        ContinuityVerdict.ACCEPT_ANCHORED — 1-2 axes marginal, none hard-reject.
        ContinuityVerdict.REJECT          — any hard-reject or ≥3 soft-fails.

    Shape-type mismatch always yields REJECT regardless of other axes.
    """
    # Unconditional: shape-type must match.
    if anchor.shape_type != candidate.shape_type:
        return ContinuityVerdict.REJECT

    a = tuple(anchor.bbox[:4])
    c = candidate.bbox

    iou = _iou(a, c)
    cdr = _center_dist_ratio(a, c)
    ar = _area_ratio(a, c)
    asp_ratio = _aspect_ratio(c) / max(_aspect_ratio(a), 1e-8)
    conf = candidate.confidence
    gap = frame_gap

    # Hard-reject thresholds — any one failure yields REJECT immediately.
    if iou < _IOU_REJECT:
        return ContinuityVerdict.REJECT
    if cdr > _CENTER_DIST_REJECT:
        return ContinuityVerdict.REJECT
    if ar < _AREA_RATIO_REJECT_MIN or ar > _AREA_RATIO_REJECT_MAX:
        return ContinuityVerdict.REJECT
    if asp_ratio < _ASPECT_RATIO_REJECT_MIN or asp_ratio > _ASPECT_RATIO_REJECT_MAX:
        return ContinuityVerdict.REJECT
    if conf < _CONFIDENCE_REJECT:
        return ContinuityVerdict.REJECT
    if gap > _FRAME_GAP_REJECT:
        return ContinuityVerdict.REJECT

    # Soft-pass thresholds — count how many axes fully pass.
    passes = sum([
        iou >= _IOU_PASS,
        cdr <= _CENTER_DIST_PASS,
        _AREA_RATIO_PASS_MIN <= ar <= _AREA_RATIO_PASS_MAX,
        _ASPECT_RATIO_PASS_MIN <= asp_ratio <= _ASPECT_RATIO_PASS_MAX,
        conf >= _CONFIDENCE_PASS,
        gap <= _FRAME_GAP_PASS,
    ])

    fail_count = 6 - passes
    if fail_count == 0:
        return ContinuityVerdict.ACCEPT
    if fail_count <= _FAIL_COUNT_FOR_ACCEPT_ANCHORED:
        return ContinuityVerdict.ACCEPT_ANCHORED
    return ContinuityVerdict.REJECT  # 3+ soft-fails


# ---------------------------------------------------------------------------
# W2: get_active_manual_anchor
# ---------------------------------------------------------------------------

def get_active_manual_anchor(
    track: "MaskTrack",
    frame_idx: int,
    decay_frames: int = ANCHOR_DECAY_FRAMES,
) -> "Keyframe | None":
    """Return the most recent active manual anchor for this track at or before frame_idx.

    An anchor is 'active' when:
      1. It is the most recent keyframe with source in _MANUAL_SOURCES at or before frame_idx.
      2. (frame_idx - anchor.frame_index) <= decay_frames.

    Returns None if no qualifying keyframe exists or if it has expired.

    Assumes track.keyframes is sorted ascending by frame_index
    (guaranteed by MaskTrack.apply_domain_rules).
    """
    best: "Keyframe | None" = None
    for kf in track.keyframes:
        if kf.frame_index > frame_idx:
            break
        if kf.source in _MANUAL_SOURCES:
            best = kf

    if best is None:
        return None
    if frame_idx - best.frame_index > decay_frames:
        return None
    return best


# ---------------------------------------------------------------------------
# W3: decide_write
# ---------------------------------------------------------------------------

def decide_write(
    track: "MaskTrack",
    frame_idx: int,
    candidate: CandidateBBox,
    verdict: ContinuityVerdict,
) -> WriteDecision:
    """Decide what to write for frame_idx given a continuity verdict.

    Pure function — does not mutate track or write any keyframe.
    The caller (detect pipeline) executes the returned WriteDecision.

    Decision rules (in priority order):
      0. Manual keyframe already present at frame_idx → SKIP (protect manual).
      1. Shape-type mismatch against last prior kf → treat verdict as REJECT.
      2. REJECT + manual anchor active → EXTEND_UNCERTAIN.
      3. REJECT + prior kf exists → EXTEND_HELD.
      4. REJECT + no prior kf → SKIP.
      5. ACCEPT/ACCEPT_ANCHORED + manual anchor active → WRITE_ANCHORED (shape from anchor).
      6. ACCEPT → WRITE_DETECTED.
      7. ACCEPT_ANCHORED + prior kf exists → WRITE_ANCHORED (shape from last prior).
      8. ACCEPT_ANCHORED + no prior kf → WRITE_DETECTED (new track start).
    """
    # Step 0: manual protection — never overwrite an explicit manual kf.
    for kf in track.keyframes:
        if kf.frame_index == frame_idx and kf.source in _MANUAL_SOURCES:
            return WriteDecision(action=WriteAction.SKIP)

    manual_anchor = get_active_manual_anchor(track, frame_idx)
    last_prior = _last_prior_kf(track, frame_idx)

    # Step 1: shape-type mismatch overrides verdict.
    effective_verdict = verdict
    if last_prior is not None and last_prior.shape_type != candidate.shape_type:
        effective_verdict = ContinuityVerdict.REJECT

    # Step 2-4: reject path.
    if effective_verdict == ContinuityVerdict.REJECT:
        if manual_anchor is not None:
            return WriteDecision(action=WriteAction.EXTEND_UNCERTAIN)
        if last_prior is not None:
            return WriteDecision(action=WriteAction.EXTEND_HELD)
        return WriteDecision(action=WriteAction.SKIP)

    # Step 5: accept or accept_anchored — manual anchor takes priority over auto shape.
    if manual_anchor is not None:
        return WriteDecision(
            action=WriteAction.WRITE_ANCHORED,
            anchor_frame=manual_anchor.frame_index,
        )

    # Step 6: clean accept with no manual anchor.
    if effective_verdict == ContinuityVerdict.ACCEPT:
        return WriteDecision(action=WriteAction.WRITE_DETECTED)

    # Step 7-8: accept_anchored with no manual anchor.
    if last_prior is not None:
        return WriteDecision(
            action=WriteAction.WRITE_ANCHORED,
            anchor_frame=last_prior.frame_index,
        )
    return WriteDecision(action=WriteAction.WRITE_DETECTED)


def _last_prior_kf(track: "MaskTrack", frame_idx: int) -> "Keyframe | None":
    """Return the most recent keyframe strictly before frame_idx, or None."""
    result: "Keyframe | None" = None
    for kf in track.keyframes:
        if kf.frame_index < frame_idx:
            result = kf
        else:
            break
    return result


# ---------------------------------------------------------------------------
# W4 internal helpers
# ---------------------------------------------------------------------------

def _build_detected_keyframe(
    frame_idx: int,
    candidate: CandidateBBox,
) -> Keyframe:
    """Build a detector keyframe from a candidate.

    Points are the four bbox corners: TL → TR → BR → BL.
    When detect_video.py is integrated the caller will supply richer point
    data; until then, bbox-derived corners serve as a valid placeholder.
    """
    x1, y1, w, h = candidate.bbox
    points: list[list[float]] = [
        [x1,     y1    ],
        [x1 + w, y1    ],
        [x1 + w, y1 + h],
        [x1,     y1 + h],
    ]
    return Keyframe(
        frame_index=frame_idx,
        shape_type=candidate.shape_type,
        points=points,
        bbox=list(candidate.bbox),
        confidence=candidate.confidence,
        source="detector",
        source_detail="detector_accepted",
    )


def _build_anchored_keyframe(
    track: MaskTrack,
    frame_idx: int,
    candidate: CandidateBBox,
    anchor_frame: int | None,
) -> Keyframe:
    """Build a detector keyframe with shape from anchor and bbox from candidate.

    Preserves the anchor keyframe's points, rotation, and opacity so that the
    shape template survives uncertain detections.  The bbox and confidence come
    from the auto-detection result (current position/scale).

    Falls back to _build_detected_keyframe if anchor_frame cannot be resolved.
    """
    anchor_kf: Keyframe | None = None
    if anchor_frame is not None:
        for kf in track.keyframes:
            if kf.frame_index == anchor_frame:
                anchor_kf = kf
                break

    if anchor_kf is None:
        # Anchor vanished or was never set — degrade gracefully.
        return _build_detected_keyframe(frame_idx, candidate)

    return Keyframe(
        frame_index=frame_idx,
        shape_type=anchor_kf.shape_type,
        points=[list(pt) for pt in anchor_kf.points],  # deep-copy
        bbox=list(candidate.bbox),
        confidence=candidate.confidence,
        source="detector",
        rotation=anchor_kf.rotation,
        opacity=anchor_kf.opacity,
        source_detail="detector_anchored",
    )


def _upsert_keyframe(track: MaskTrack, new_kf: Keyframe) -> None:
    """Insert new_kf, replacing any non-manual keyframe at the same frame.

    Manual keyframes are never overwritten.  decide_write() should already
    have returned SKIP for those frames, but this guard provides depth-of-defence.
    """
    for i, existing in enumerate(track.keyframes):
        if existing.frame_index == new_kf.frame_index:
            if existing.source in _MANUAL_SOURCES:
                return  # protect manual
            track.keyframes[i] = new_kf
            return
    track.keyframes.append(new_kf)


def _extend_segment(
    track: MaskTrack,
    frame_idx: int,
    state: str,
) -> None:
    """Extend or create a segment of the given state to cover frame_idx.

    Contiguous extension: if any existing segment has the same state and its
    end_frame is exactly frame_idx-1, extend it to frame_idx.  Otherwise create
    a new single-frame segment [frame_idx, frame_idx, state].

    No-op if any segment already covers frame_idx (conservative — avoids
    overlapping segments regardless of state).
    """
    for seg in track.segments:
        if seg.contains(frame_idx):
            return  # already covered by any segment

    for seg in reversed(track.segments):
        if seg.state == state and seg.end_frame == frame_idx - 1:
            seg.end_frame = frame_idx
            return

    track.segments.append(MaskSegment(
        start_frame=frame_idx,
        end_frame=frame_idx,
        state=state,
    ))


# ---------------------------------------------------------------------------
# W4: apply_write_action
# ---------------------------------------------------------------------------

def apply_write_action(
    track: MaskTrack,
    frame_idx: int,
    candidate: CandidateBBox,
    decision: WriteDecision,
) -> None:
    """Apply a WriteDecision to track in-place.

    This is the mutation layer for Phase 4.  It contains no decision logic;
    the caller must produce the decision via decide_write() first.

    Caller responsibility: call track.apply_domain_rules() after all frames
    have been processed to re-sort keyframes and segments.

    Args:
        track:     MaskTrack to mutate.
        frame_idx: Frame index being processed.
        candidate: Auto-detection candidate for this frame.
        decision:  WriteDecision from decide_write().
    """
    action = decision.action

    if action == WriteAction.SKIP:
        return

    if action == WriteAction.WRITE_DETECTED:
        _upsert_keyframe(track, _build_detected_keyframe(frame_idx, candidate))
        return

    if action == WriteAction.WRITE_ANCHORED:
        _upsert_keyframe(track, _build_anchored_keyframe(
            track, frame_idx, candidate, decision.anchor_frame,
        ))
        return

    if action == WriteAction.EXTEND_HELD:
        _extend_segment(track, frame_idx, "held")
        return

    if action == WriteAction.EXTEND_UNCERTAIN:
        _extend_segment(track, frame_idx, "uncertain")
        return


# ---------------------------------------------------------------------------
# W5: merge_held_segments
# ---------------------------------------------------------------------------

_W5_MERGEABLE_STATES: frozenset[str] = frozenset({"held", "uncertain"})


def merge_held_segments(track: MaskTrack) -> None:
    """Normalise held/uncertain segments by merging adjacent or overlapping same-state runs.

    Merge rules:
      - Only "held" and "uncertain" segments are candidates; all other states pass through
        unchanged.
      - Two segments merge iff they share the same state AND are adjacent
        (end_frame + 1 == next_start_frame) OR overlapping (next_start_frame <= end_frame).
      - "held" and "uncertain" are NEVER merged with each other.
      - Separated segments (gap of ≥ 1 frame between them) are never merged.
        Because merging only applies to adjacent/overlapping spans, no keyframe boundary
        is crossed in a way that changes meaning.
      - Keyframes are not mutated; only track.segments is rewritten.
      - Idempotent: calling multiple times yields the same result as calling once.

    Call after all _extend_segment / apply_write_action calls for a detection batch
    are complete — i.e., at track finalisation in the detect pipeline.
    """
    if not track.segments:
        return

    mergeable = [s for s in track.segments if s.state in _W5_MERGEABLE_STATES]
    others = [s for s in track.segments if s.state not in _W5_MERGEABLE_STATES]

    if not mergeable:
        return

    # Deterministic sweep: sort by (start_frame, end_frame).
    mergeable.sort(key=lambda s: (s.start_frame, s.end_frame))

    cur_start: int = mergeable[0].start_frame
    cur_end: int = mergeable[0].end_frame
    cur_state: str = mergeable[0].state
    out: list[MaskSegment] = []

    for seg in mergeable[1:]:
        if seg.state == cur_state and seg.start_frame <= cur_end + 1:
            # Same state, adjacent or overlapping — extend the current run.
            cur_end = max(cur_end, seg.end_frame)
        else:
            # Different state or separated gap — emit current run, start a new one.
            out.append(MaskSegment(start_frame=cur_start, end_frame=cur_end, state=cur_state))
            cur_start = seg.start_frame
            cur_end = seg.end_frame
            cur_state = seg.state

    out.append(MaskSegment(start_frame=cur_start, end_frame=cur_end, state=cur_state))

    # Restore sort order with non-mergeable segments mixed back in.
    combined = out + others
    combined.sort(key=lambda s: (s.start_frame, s.end_frame))
    track.segments = combined


# ---------------------------------------------------------------------------
# W6 internal helpers
# ---------------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from a to b at parameter t in [0, 1]."""
    return a + t * (b - a)


def _lerp_rotation(a_rot: float, b_rot: float, t: float) -> float:
    """Shortest-path linear interpolation between two angles in degrees.

    The signed difference is normalised to (-180, 180] so that interpolation
    always takes the shorter arc and handles 0°/360° wrap-around correctly.
    """
    diff = ((b_rot - a_rot) + 180.0) % 360.0 - 180.0
    return a_rot + t * diff


def _build_interpolated_kf(
    frame_idx: int,
    shape_type: str,
    bbox: list[float],
    rotation: float,
    confidence: float,
    opacity: float,
) -> Keyframe:
    """Build an interpolated Keyframe from geometric components.

    Points are always the four bbox corners (TL → TR → BR → BL) so that
    the points/bbox relationship is consistent for every interpolated frame.
    Source is always "detector" (auto-generated, not user-created).
    """
    x1, y1, w, h = bbox
    points: list[list[float]] = [
        [x1,     y1    ],
        [x1 + w, y1    ],
        [x1 + w, y1 + h],
        [x1,     y1 + h],
    ]
    return Keyframe(
        frame_index=frame_idx,
        shape_type=shape_type,
        points=points,
        bbox=list(bbox),
        confidence=confidence,
        source="detector",
        rotation=rotation,
        opacity=opacity,
    )


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse
# ---------------------------------------------------------------------------

def interpolate_ellipse(
    a: Keyframe,
    b: Keyframe,
    frame_idx: int,
) -> Keyframe:
    """Return an interpolated ellipse Keyframe at frame_idx between a and b.

    Pure function — does not mutate a or b, no side effects.

    Interpolated fields:
      - bbox:       linear (each component independently)
      - rotation:   shortest-path linear (handles 0°/360° wrap-around)
      - confidence: linear
      - opacity:    linear
      - points:     four bbox corners re-derived from the interpolated bbox

    Output source is always "detector".
    Polygon interpolation is out of scope; only "ellipse" shape_type is accepted.

    At the exact endpoint frames (t == 0.0 or t == 1.0) the geometric values
    of the respective anchor are returned verbatim to avoid floating-point or
    rotation-wrapping drift.

    Args:
        a:         Earlier keyframe (must satisfy a.frame_index < b.frame_index).
        b:         Later keyframe.
        frame_idx: Target frame; must be in [a.frame_index, b.frame_index].

    Returns:
        A new Keyframe at frame_idx with interpolated geometry.

    Raises:
        ValueError: If either keyframe has shape_type != "ellipse".
        ValueError: If a.frame_index >= b.frame_index (degenerate or reversed span).
        ValueError: If frame_idx is outside [a.frame_index, b.frame_index].
    """
    if a.shape_type != "ellipse":
        raise ValueError(
            f"interpolate_ellipse: a (frame {a.frame_index}) has shape_type "
            f"'{a.shape_type}', expected 'ellipse'."
        )
    if b.shape_type != "ellipse":
        raise ValueError(
            f"interpolate_ellipse: b (frame {b.frame_index}) has shape_type "
            f"'{b.shape_type}', expected 'ellipse'."
        )
    if a.frame_index >= b.frame_index:
        raise ValueError(
            f"interpolate_ellipse: a.frame_index ({a.frame_index}) must be "
            f"strictly less than b.frame_index ({b.frame_index})."
        )
    if not (a.frame_index <= frame_idx <= b.frame_index):
        raise ValueError(
            f"interpolate_ellipse: frame_idx ({frame_idx}) must be in "
            f"[{a.frame_index}, {b.frame_index}]."
        )

    span = b.frame_index - a.frame_index          # int > 0
    t = (frame_idx - a.frame_index) / span        # float in [0.0, 1.0]

    # Exact endpoint values — preserves anchor geometry without floating-point
    # or rotation-wrapping artefacts when the target frame IS an anchor frame.
    if t == 0.0:
        return _build_interpolated_kf(
            frame_idx, "ellipse", list(a.bbox), a.rotation, a.confidence, a.opacity,
        )
    if t == 1.0:
        return _build_interpolated_kf(
            frame_idx, "ellipse", list(b.bbox), b.rotation, b.confidence, b.opacity,
        )

    ibbox = [
        _lerp(a.bbox[0], b.bbox[0], t),
        _lerp(a.bbox[1], b.bbox[1], t),
        _lerp(a.bbox[2], b.bbox[2], t),
        _lerp(a.bbox[3], b.bbox[3], t),
    ]
    return _build_interpolated_kf(
        frame_idx,
        "ellipse",
        ibbox,
        _lerp_rotation(a.rotation, b.rotation, t),
        _lerp(a.confidence, b.confidence, t),
        _lerp(a.opacity, b.opacity, t),
    )


# ---------------------------------------------------------------------------
# Polygon interpolation helpers (ported from PySide6 interpolation.py)
# ---------------------------------------------------------------------------

def _cumulative_arc_lengths(points: list[list[float]]) -> list[float]:
    """Cumulative arc lengths for a closed polygon.  First entry is 0.0,
    last entry is the total perimeter (includes the closing edge)."""
    n = len(points)
    lengths = [0.0]
    for i in range(1, n):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        lengths.append(lengths[-1] + math.hypot(dx, dy))
    # Closing edge back to first vertex.
    dx = points[0][0] - points[-1][0]
    dy = points[0][1] - points[-1][1]
    lengths.append(lengths[-1] + math.hypot(dx, dy))
    return lengths


def _resample_polygon(
    points: list[list[float]],
    target_count: int,
) -> list[list[float]]:
    """Resample a closed polygon to *target_count* equidistant vertices.

    Arc-length parameterisation ensures that different vertex counts produce
    naturally corresponding vertices for smooth interpolation.
    """
    if len(points) < 2 or target_count < _POLYGON_MIN_VERTICES:
        return [list(pt) for pt in points]
    if len(points) == target_count:
        return [list(pt) for pt in points]

    cum = _cumulative_arc_lengths(points)
    total_len = cum[-1]
    if total_len < 1e-9:
        return [list(points[0]) for _ in range(target_count)]

    step = total_len / target_count
    n = len(points)
    closed_pts = [list(pt) for pt in points] + [list(points[0])]

    result: list[list[float]] = []
    seg_idx = 0

    for i in range(target_count):
        target_len = i * step
        while seg_idx < n and cum[seg_idx + 1] < target_len:
            seg_idx += 1
        if seg_idx >= n:
            seg_idx = n - 1

        seg_start_len = cum[seg_idx]
        seg_end_len = cum[seg_idx + 1]
        seg_span = seg_end_len - seg_start_len

        if seg_span < 1e-12:
            local_t = 0.0
        else:
            local_t = (target_len - seg_start_len) / seg_span

        px = closed_pts[seg_idx][0] + (closed_pts[seg_idx + 1][0] - closed_pts[seg_idx][0]) * local_t
        py = closed_pts[seg_idx][1] + (closed_pts[seg_idx + 1][1] - closed_pts[seg_idx][1]) * local_t
        result.append([px, py])

    return result


def _align_polygon_start(
    points_a: list[list[float]],
    points_b: list[list[float]],
) -> list[list[float]]:
    """Rotate the start vertex of *points_b* to minimise total distance to *points_a*.

    Prevents twist artefacts when interpolating between two polygons.
    """
    n = len(points_a)
    if n != len(points_b) or n == 0:
        return [list(pt) for pt in points_b]

    best_offset = 0
    best_dist = float("inf")

    for offset in range(n):
        total = 0.0
        for i in range(n):
            j = (i + offset) % n
            dx = points_a[i][0] - points_b[j][0]
            dy = points_a[i][1] - points_b[j][1]
            total += dx * dx + dy * dy
        if total < best_dist:
            best_dist = total
            best_offset = offset

    if best_offset == 0:
        return [list(pt) for pt in points_b]

    return [list(pt) for pt in points_b[best_offset:] + points_b[:best_offset]]


def _prepare_polygon_pair(
    points_a: list[list[float]],
    points_b: list[list[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    """Resample both polygons to equal vertex counts and align start vertices.

    Returns a pair of same-length, optimally-aligned vertex lists ready for
    per-vertex linear interpolation.
    """
    if not points_a or not points_b:
        return [list(pt) for pt in points_a], [list(pt) for pt in points_b]

    target = max(len(points_a), len(points_b))
    resampled_a = _resample_polygon(points_a, target)
    resampled_b = _resample_polygon(points_b, target)
    aligned_b = _align_polygon_start(resampled_a, resampled_b)
    return resampled_a, aligned_b


def _bbox_from_points(points: list[list[float]]) -> list[float]:
    """Compute [x, y, w, h] bounding box from a list of [x, y] points."""
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x = min(xs)
    min_y = min(ys)
    return [min_x, min_y, max(xs) - min_x, max(ys) - min_y]


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon
# ---------------------------------------------------------------------------

def interpolate_polygon(
    a: Keyframe,
    b: Keyframe,
    frame_idx: int,
) -> Keyframe:
    """Return an interpolated polygon Keyframe at frame_idx between a and b.

    Pure function — does not mutate a or b, no side effects.

    Interpolated fields:
      - points:     per-vertex linear after resample + alignment
      - bbox:       derived from interpolated points
      - rotation:   shortest-path linear
      - confidence: linear
      - opacity:    linear

    Both keyframes must have shape_type == "polygon" and non-empty points.
    Output source is always "detector".

    At exact endpoint frames the geometry of the respective anchor is returned
    verbatim to avoid floating-point drift.

    Args:
        a:         Earlier keyframe (a.frame_index < b.frame_index).
        b:         Later keyframe.
        frame_idx: Target frame in [a.frame_index, b.frame_index].

    Raises:
        ValueError: on invalid shape_type, ordering, or range.
    """
    if a.shape_type != "polygon":
        raise ValueError(
            f"interpolate_polygon: a (frame {a.frame_index}) has shape_type "
            f"'{a.shape_type}', expected 'polygon'."
        )
    if b.shape_type != "polygon":
        raise ValueError(
            f"interpolate_polygon: b (frame {b.frame_index}) has shape_type "
            f"'{b.shape_type}', expected 'polygon'."
        )
    if not a.points or not b.points:
        raise ValueError(
            "interpolate_polygon: both keyframes must have non-empty points."
        )
    if a.frame_index >= b.frame_index:
        raise ValueError(
            f"interpolate_polygon: a.frame_index ({a.frame_index}) must be "
            f"strictly less than b.frame_index ({b.frame_index})."
        )
    if not (a.frame_index <= frame_idx <= b.frame_index):
        raise ValueError(
            f"interpolate_polygon: frame_idx ({frame_idx}) must be in "
            f"[{a.frame_index}, {b.frame_index}]."
        )

    span = b.frame_index - a.frame_index
    t = (frame_idx - a.frame_index) / span

    # Exact endpoint — return verbatim geometry.
    if t == 0.0:
        return Keyframe(
            frame_index=frame_idx,
            shape_type="polygon",
            points=[list(pt) for pt in a.points],
            bbox=list(a.bbox),
            confidence=a.confidence,
            source="detector",
            rotation=a.rotation,
            opacity=a.opacity,
        )
    if t == 1.0:
        return Keyframe(
            frame_index=frame_idx,
            shape_type="polygon",
            points=[list(pt) for pt in b.points],
            bbox=list(b.bbox),
            confidence=b.confidence,
            source="detector",
            rotation=b.rotation,
            opacity=b.opacity,
        )

    # Resample + align + interpolate.
    aligned_a, aligned_b = _prepare_polygon_pair(a.points, b.points)
    interp_points = [
        [_lerp(pa[0], pb[0], t), _lerp(pa[1], pb[1], t)]
        for pa, pb in zip(aligned_a, aligned_b)
    ]
    interp_bbox = _bbox_from_points(interp_points)

    return Keyframe(
        frame_index=frame_idx,
        shape_type="polygon",
        points=interp_points,
        bbox=interp_bbox,
        confidence=_lerp(a.confidence, b.confidence, t),
        source="detector",
        rotation=_lerp_rotation(a.rotation, b.rotation, t),
        opacity=_lerp(a.opacity, b.opacity, t),
    )


# ---------------------------------------------------------------------------
# W7: resolve_for_render
# ---------------------------------------------------------------------------

def resolve_for_render(
    track: MaskTrack,
    frame_idx: int,
) -> tuple[Keyframe, ResolveReason] | None:
    """Resolve the keyframe to use for export-rendering at frame_idx.

    Pure function — does not mutate track.

    Returns None when frame_idx is outside the renderable span, preserving the
    same export safety gate as MaskTrack.resolve_active_keyframe.

    Within the renderable span the decision is, in priority order:

    1. EXPLICIT        — an exact keyframe exists at frame_idx.
    2. INTERPOLATED    — prior and next keyframes are both ellipses and the span
                         between them is ≤ _INTERPOLATE_MAX_GAP frames.
    3. HELD_FROM_PRIOR — all other cases: return the most recent prior keyframe.

    If no prior keyframe exists while the frame is renderable (data integrity
    anomaly), returns None rather than guessing.

    Held/uncertain segment states do NOT block interpolation; those states
    indicate that auto-detection was poor, but the surrounding explicit keyframes
    remain the authoritative shape source.

    Polygon interpolation is out of scope: shape_type must be "ellipse" for both
    surrounding keyframes for INTERPOLATED to apply.
    """
    # ── Renderable-span gate (export safety) ──────────────────────────────
    if not track.frame_is_renderable(frame_idx):
        return None

    # ── Single-pass search: prior kf, exact match, next kf ────────────────
    # track.keyframes is sorted ascending by apply_domain_rules.
    prior_kf: Keyframe | None = None
    next_kf: Keyframe | None = None

    for kf in track.keyframes:
        if kf.frame_index < frame_idx:
            prior_kf = kf
        elif kf.frame_index == frame_idx:
            return (kf, ResolveReason.EXPLICIT)
        else:                                   # kf.frame_index > frame_idx
            next_kf = kf
            break                              # sorted, so no earlier next exists

    if prior_kf is None:
        # Renderable but no prior keyframe — data integrity anomaly; safe default.
        return None

    # ── Interpolation check ───────────────────────────────────────────────
    if (
        next_kf is not None
        and prior_kf.shape_type == next_kf.shape_type
        and (next_kf.frame_index - prior_kf.frame_index) <= _INTERPOLATE_MAX_GAP
    ):
        if prior_kf.shape_type == "ellipse":
            return (interpolate_ellipse(prior_kf, next_kf, frame_idx), ResolveReason.INTERPOLATED)
        if (
            prior_kf.shape_type == "polygon"
            and prior_kf.points
            and next_kf.points
            and len(prior_kf.points) >= _POLYGON_MIN_VERTICES
            and len(next_kf.points) >= _POLYGON_MIN_VERTICES
        ):
            return (interpolate_polygon(prior_kf, next_kf, frame_idx), ResolveReason.INTERPOLATED)

    # ── Held from prior ───────────────────────────────────────────────────
    return (prior_kf, ResolveReason.HELD_FROM_PRIOR)


# ---------------------------------------------------------------------------
# W8: resolve_for_editing
# ---------------------------------------------------------------------------

def resolve_for_editing(
    track: MaskTrack,
    frame_idx: int,
) -> tuple[Keyframe, ResolveReason] | None:
    """Resolve the keyframe to display or edit at frame_idx.

    Pure function — does not mutate track.

    Editing resolver — intentionally differs from resolve_for_render in two ways:

    1. The renderable-span gate (frame_is_renderable) is NOT applied.
       Frames outside the export range are still valid editing targets.

    2. After the last keyframe → HELD_FROM_PRIOR (held-editing semantics).
       resolve_for_render would return None there; this resolver returns the
       last keyframe so the user can edit beyond the rendered range.

    Returns None only when:
    - The track has no keyframes.
    - frame_idx is strictly before the first keyframe (no shape established yet).

    Resolution priority within the editable range:
    1. EXPLICIT        — exact keyframe exists at frame_idx.
    2. INTERPOLATED    — both adjacent kfs are ellipses, gap ≤ _INTERPOLATE_MAX_GAP.
    3. HELD_FROM_PRIOR — all other cases, including frames after the last keyframe.
    """
    if not track.keyframes:
        return None

    if frame_idx < track.keyframes[0].frame_index:
        return None

    # Single pass: build prior/next and check for exact match.
    # Keyframes are sorted ascending (guaranteed by apply_domain_rules).
    prior_kf: Keyframe | None = None
    next_kf: Keyframe | None = None

    for kf in track.keyframes:
        if kf.frame_index < frame_idx:
            prior_kf = kf
        elif kf.frame_index == frame_idx:
            return (kf, ResolveReason.EXPLICIT)
        else:                               # kf.frame_index > frame_idx
            next_kf = kf
            break

    # prior_kf is non-None at this point:
    # ∙ frame_idx >= first_kf.frame_index  (None returned above if not)
    # ∙ frame_idx != first_kf.frame_index  (EXPLICIT returned in loop if equal)
    # ∙ therefore frame_idx > first_kf.frame_index, and the first loop iteration
    #   set prior_kf = first_kf.

    # ── Interpolation check (same conditions as resolve_for_render) ───────
    if (
        next_kf is not None
        and prior_kf is not None          # for type narrowing; always True (see above)
        and prior_kf.shape_type == next_kf.shape_type
        and (next_kf.frame_index - prior_kf.frame_index) <= _INTERPOLATE_MAX_GAP
    ):
        if prior_kf.shape_type == "ellipse":
            return (interpolate_ellipse(prior_kf, next_kf, frame_idx), ResolveReason.INTERPOLATED)
        if (
            prior_kf.shape_type == "polygon"
            and prior_kf.points
            and next_kf.points
            and len(prior_kf.points) >= _POLYGON_MIN_VERTICES
            and len(next_kf.points) >= _POLYGON_MIN_VERTICES
        ):
            return (interpolate_polygon(prior_kf, next_kf, frame_idx), ResolveReason.INTERPOLATED)

    # ── Held from prior (including after last keyframe) ───────────────────
    # prior_kf is the last keyframe when frame_idx is beyond all keyframes.
    return (prior_kf, ResolveReason.HELD_FROM_PRIOR)  # type: ignore[return-value]
