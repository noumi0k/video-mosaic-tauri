"""
Tests for domain/mask_continuity.py — W1, W2, W3, W4, W6.

Covers:
  - evaluate_continuity: all 6 axes at pass / fail / hard-reject boundaries
  - get_active_manual_anchor: no manual, latest wins, decay timeout
  - decide_write: full decision matrix including manual protection and shape mismatch
  - apply_write_action: mutation layer for all WriteAction variants
  - interpolate_ellipse: bbox/rotation/confidence/opacity linear interpolation
"""
from __future__ import annotations

import pytest

from auto_mosaic.domain.project import Keyframe, MaskSegment, MaskTrack
from auto_mosaic.domain.mask_continuity import (
    ANCHOR_DECAY_FRAMES,
    CandidateBBox,
    ContinuityVerdict,
    ResolveReason,
    WriteAction,
    WriteDecision,
    apply_write_action,
    decide_write,
    evaluate_continuity,
    get_active_manual_anchor,
    interpolate_ellipse,
    interpolate_polygon,
    resolve_for_editing,
    resolve_for_render,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _kf(
    frame: int,
    source: str = "manual",
    shape_type: str = "polygon",
    bbox: list[float] | None = None,
    confidence: float = 0.9,
) -> Keyframe:
    return Keyframe(
        frame_index=frame,
        shape_type=shape_type,
        points=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
        bbox=bbox if bbox is not None else [0.1, 0.1, 0.2, 0.2],
        confidence=confidence,
        source=source,
    )


def _track(*kfs: Keyframe) -> MaskTrack:
    return MaskTrack(
        track_id="t1",
        label="Test",
        state="active",
        source="manual" if any(k.source == "manual" for k in kfs) else "detector",
        keyframes=list(kfs),
    )


def _anchor(
    shape_type: str = "polygon",
    bbox: list[float] | None = None,
) -> Keyframe:
    """Anchor keyframe with a square bbox at (0.1, 0.1, 0.2, 0.2)."""
    return _kf(frame=0, source="manual", shape_type=shape_type, bbox=bbox)


def _candidate(
    shape_type: str = "polygon",
    bbox: tuple[float, float, float, float] = (0.1, 0.1, 0.2, 0.2),
    confidence: float = 0.8,
) -> CandidateBBox:
    return CandidateBBox(bbox=bbox, confidence=confidence, shape_type=shape_type)


# ---------------------------------------------------------------------------
# W1: evaluate_continuity — shared perfect candidate
# ---------------------------------------------------------------------------

_PERFECT_ANCHOR = _anchor(bbox=[0.1, 0.1, 0.2, 0.2])  # 0.2×0.2 square at (0.1,0.1)
_PERFECT_CAND = _candidate(bbox=(0.1, 0.1, 0.2, 0.2), confidence=0.9)  # identical
_GAP_PASS = 4  # within _FRAME_GAP_PASS=8


class TestEvaluateContinuityShapeType:
    def test_same_shape_type_allowed(self):
        verdict = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert verdict == ContinuityVerdict.ACCEPT

    def test_polygon_vs_ellipse_always_reject(self):
        anchor = _anchor(shape_type="polygon")
        cand = _candidate(shape_type="ellipse")
        verdict = evaluate_continuity(anchor, cand, _GAP_PASS)
        assert verdict == ContinuityVerdict.REJECT

    def test_ellipse_vs_polygon_always_reject(self):
        anchor = _anchor(shape_type="ellipse")
        cand = _candidate(shape_type="polygon")
        verdict = evaluate_continuity(anchor, cand, _GAP_PASS)
        assert verdict == ContinuityVerdict.REJECT


class TestEvaluateContinuityIoU:
    """Anchor bbox [0.1,0.1,0.2,0.2].  Shift candidate horizontally to control IoU."""

    def test_identical_bbox_iou_is_one(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT

    def test_iou_just_above_reject_threshold(self):
        # Move right by 0.18 → small overlap ~0.02/0.38 ≈ 0.05 < 0.1 → REJECT
        # But let's use iou = 0.11 by careful offset: shift by 0.177 → iou ≈ 0.115
        # Easier: shift by 0.17 → overlap width = 0.03
        # intersection=0.03*0.2=0.006, union≈0.04+0.04-0.006=0.074; iou≈0.08 < 0.1 → REJECT
        cand = _candidate(bbox=(0.27, 0.1, 0.2, 0.2))  # no overlap at all
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_iou_at_hard_reject_boundary(self):
        # IoU exactly 0.0 (no overlap) — must be REJECT
        cand = _candidate(bbox=(0.5, 0.5, 0.2, 0.2))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_marginal_iou_below_pass_but_above_reject(self):
        # IoU between 0.1 and 0.5 — should be a soft-fail (not hard-reject)
        # shift by 0.12: anchor (0.1,0.1,0.2,0.2), cand (0.22,0.1,0.2,0.2)
        # overlap = (0.30-0.22)×0.2 = 0.08×0.2 = 0.016; union = 0.04+0.04-0.016=0.064; iou=0.25
        cand = _candidate(bbox=(0.22, 0.1, 0.2, 0.2), confidence=0.9)
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # iou=0.25 — soft-fail for iou axis only; other axes near-perfect → ACCEPT_ANCHORED
        assert v == ContinuityVerdict.ACCEPT_ANCHORED


class TestEvaluateContinuityCenterDistance:
    def test_same_center_passes(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT

    def test_large_center_shift_reject(self):
        # anchor center = (0.2, 0.2), diag≈0.283
        # shift by 2.0 * diag ≈ 0.57 → far beyond _CENTER_DIST_REJECT=1.0
        # cand bbox (0.8, 0.8, 0.2, 0.2): center=(0.9,0.9), dist=hypot(0.7,0.7)≈0.99
        # cdr = 0.99 / max(0.283, 0.283) ≈ 3.5 > 1.0 → REJECT
        cand = _candidate(bbox=(0.8, 0.8, 0.2, 0.2))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_moderate_center_shift_soft_fail(self):
        # anchor center=(0.2,0.2), diag=0.283
        # shift to (0.25,0.1,0.2,0.2): center=(0.35,0.2), dist=0.15, cdr=0.15/0.283≈0.53
        # 0.53 > _CENTER_DIST_PASS(0.25) but < _CENTER_DIST_REJECT(1.0) → soft-fail
        cand = _candidate(bbox=(0.25, 0.1, 0.2, 0.2))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # Only center-dist axis fails softly → ACCEPT_ANCHORED
        assert v == ContinuityVerdict.ACCEPT_ANCHORED


class TestEvaluateContinuityAreaRatio:
    def test_same_area_passes(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT

    def test_area_too_small_hard_reject(self):
        # anchor area = 0.04; cand area = 0.04 * 0.3 = 0.012 → ratio=0.3 < _AREA_RATIO_REJECT_MIN=0.4
        # w=h=sqrt(0.012)≈0.11
        cand = _candidate(bbox=(0.1, 0.1, 0.109, 0.109))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_area_too_large_hard_reject(self):
        # anchor area=0.04; need ratio > 2.5 → area > 0.1 → side > 0.316
        cand = _candidate(bbox=(0.1, 0.1, 0.35, 0.35))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_area_ratio_soft_fail_just_outside_pass(self):
        # ratio slightly above _AREA_RATIO_PASS_MAX=1.43 but below reject=2.5
        # need area_c / area_a = 1.6 → side = 0.2*sqrt(1.6)≈0.253
        cand = _candidate(bbox=(0.1, 0.1, 0.253, 0.253))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # area ratio ~1.6 → soft-fail; only this axis fails → ACCEPT_ANCHORED
        assert v == ContinuityVerdict.ACCEPT_ANCHORED

    def test_area_ratio_within_pass(self):
        # ratio = 1.2 (within [0.7, 1.43])
        cand = _candidate(bbox=(0.1, 0.1, 0.219, 0.219))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT


class TestEvaluateContinuityAspectRatio:
    def test_same_aspect_passes(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT

    def test_extreme_aspect_change_reject(self):
        # anchor: 0.2×0.2, aspect=1.0
        # cand: 0.4×0.05, aspect=8.0 → ratio=8.0 > _ASPECT_RATIO_REJECT_MAX=2.0 → REJECT
        cand = _candidate(bbox=(0.1, 0.1, 0.4, 0.05))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_moderate_aspect_change_soft_fail(self):
        # anchor aspect=1.0; need ratio in (1.25, 2.0) for soft-fail
        # ratio=1.5 → cand aspect=1.5 → e.g. 0.24×0.16
        cand = _candidate(bbox=(0.1, 0.1, 0.24, 0.16))
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # aspect_ratio soft-fail only → ACCEPT_ANCHORED
        assert v == ContinuityVerdict.ACCEPT_ANCHORED


class TestEvaluateContinuityConfidence:
    def test_high_confidence_passes(self):
        cand = _candidate(confidence=0.9)
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT

    def test_confidence_at_reject_threshold(self):
        # conf = 0.2 is exactly _CONFIDENCE_REJECT → should reject (< condition)
        # 0.2 is NOT < 0.2, so it should NOT hard-reject
        cand = _candidate(confidence=0.20)
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # 0.20 is not < 0.20 → no hard reject; but it's < pass threshold 0.5 → soft-fail
        assert v == ContinuityVerdict.ACCEPT_ANCHORED

    def test_confidence_below_reject_threshold(self):
        # conf = 0.19 < 0.20 → hard REJECT
        cand = _candidate(confidence=0.19)
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.REJECT

    def test_confidence_between_reject_and_pass(self):
        # conf = 0.35 → not hard-reject, not passing → soft-fail
        cand = _candidate(confidence=0.35)
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT_ANCHORED


class TestEvaluateContinuityFrameGap:
    def test_gap_within_pass_threshold(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, frame_gap=8)
        assert v == ContinuityVerdict.ACCEPT

    def test_gap_one_above_pass(self):
        # gap=9 > _FRAME_GAP_PASS=8 → soft-fail for gap axis only
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, frame_gap=9)
        assert v == ContinuityVerdict.ACCEPT_ANCHORED

    def test_gap_at_reject_threshold(self):
        # gap=30 is _FRAME_GAP_REJECT; condition is > 30, so 30 is NOT a hard reject
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, frame_gap=30)
        assert v == ContinuityVerdict.ACCEPT_ANCHORED  # soft-fail (gap > 8), not hard reject

    def test_gap_above_reject_threshold(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, frame_gap=31)
        assert v == ContinuityVerdict.REJECT

    def test_gap_zero(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, frame_gap=0)
        assert v == ContinuityVerdict.ACCEPT


class TestEvaluateContinuityMultipleAxes:
    def test_three_soft_fails_yields_reject(self):
        # Make iou, area, confidence all soft-fail simultaneously
        # iou ≈ 0.25 (shift right), area ratio 1.6 (bigger), confidence 0.35
        # shift right by 0.12: cand (0.22, 0.1, ?, ?)
        # use 0.253 side (area ratio ~1.6) and confidence=0.35
        cand = CandidateBBox(
            bbox=(0.22, 0.1, 0.253, 0.253),
            confidence=0.35,
            shape_type="polygon",
        )
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, _GAP_PASS)
        # iou soft-fail, area soft-fail, confidence soft-fail = 3 fails → REJECT
        assert v == ContinuityVerdict.REJECT

    def test_two_soft_fails_yields_accept_anchored(self):
        # confidence soft-fail + frame_gap soft-fail; bbox identical → iou/center/area/aspect all pass
        # Note: any horizontal shift of bbox causes BOTH iou AND center_dist to soft-fail,
        # so we isolate exactly 2 fails using gap=9 (> _FRAME_GAP_PASS=8) and low confidence.
        cand = CandidateBBox(
            bbox=(0.1, 0.1, 0.2, 0.2),  # identical to anchor → 4 axes pass
            confidence=0.35,             # soft-fail: 0.20 ≤ 0.35 < 0.50
            shape_type="polygon",
        )
        v = evaluate_continuity(_PERFECT_ANCHOR, cand, 9)  # gap=9 > 8 → soft-fail
        # 2 soft-fails (confidence + gap) → ACCEPT_ANCHORED
        assert v == ContinuityVerdict.ACCEPT_ANCHORED

    def test_all_axes_perfect_yields_accept(self):
        v = evaluate_continuity(_PERFECT_ANCHOR, _PERFECT_CAND, _GAP_PASS)
        assert v == ContinuityVerdict.ACCEPT


# ---------------------------------------------------------------------------
# W2: get_active_manual_anchor
# ---------------------------------------------------------------------------

class TestGetActiveManualAnchor:
    def test_empty_track_returns_none(self):
        track = _track()
        assert get_active_manual_anchor(track, 100) is None

    def test_no_manual_keyframes_returns_none(self):
        track = _track(_kf(10, "detector"), _kf(20, "detector"))
        assert get_active_manual_anchor(track, 25) is None

    def test_single_manual_kf_at_same_frame(self):
        kf = _kf(10, "manual")
        track = _track(kf)
        result = get_active_manual_anchor(track, 10)
        assert result is kf

    def test_single_manual_kf_before_query(self):
        kf = _kf(10, "manual")
        track = _track(kf)
        result = get_active_manual_anchor(track, 20)
        assert result is kf

    def test_latest_prior_manual_wins_over_older(self):
        kf_old = _kf(10, "manual")
        kf_new = _kf(20, "manual")
        track = _track(kf_old, kf_new)
        result = get_active_manual_anchor(track, 25)
        assert result is kf_new

    def test_manual_after_query_frame_not_included(self):
        kf = _kf(30, "manual")
        track = _track(kf)
        # query frame is 20, anchor is at 30 > 20 → no anchor before query
        result = get_active_manual_anchor(track, 20)
        assert result is None

    def test_detector_kf_more_recent_does_not_shadow_manual(self):
        kf_m = _kf(10, "manual")
        kf_d = _kf(20, "detector")
        track = _track(kf_m, kf_d)
        # most-recent manual is at 10; detector at 20 is more recent but not manual
        result = get_active_manual_anchor(track, 25)
        assert result is kf_m

    def test_decay_exactly_at_limit_returns_anchor(self):
        kf = _kf(0, "manual")
        track = _track(kf)
        result = get_active_manual_anchor(track, ANCHOR_DECAY_FRAMES)
        assert result is kf

    def test_decay_one_beyond_limit_returns_none(self):
        kf = _kf(0, "manual")
        track = _track(kf)
        result = get_active_manual_anchor(track, ANCHOR_DECAY_FRAMES + 1)
        assert result is None

    def test_decay_parameter_override(self):
        kf = _kf(0, "manual")
        track = _track(kf)
        # custom decay of 10 frames
        assert get_active_manual_anchor(track, 10, decay_frames=10) is kf
        assert get_active_manual_anchor(track, 11, decay_frames=10) is None

    def test_only_most_recent_manual_checked_for_decay(self):
        kf_old = _kf(0, "manual")
        kf_new = _kf(50, "manual")
        track = _track(kf_old, kf_new)
        # query at 55: kf_new is at 50, gap=5 ≤ ANCHOR_DECAY_FRAMES → kf_new returned
        assert get_active_manual_anchor(track, 55) is kf_new
        # query at 0+ANCHOR_DECAY_FRAMES+1=61: kf_new (50) → gap=11 ≤ 60 → still valid
        assert get_active_manual_anchor(track, 61) is kf_new


# ---------------------------------------------------------------------------
# W3: decide_write
# ---------------------------------------------------------------------------

def _mk_track(*specs: tuple[int, str]) -> MaskTrack:
    """Build a track from (frame_index, source) tuples."""
    kfs = [_kf(f, s) for f, s in specs]
    return _track(*kfs)


class TestDecideWriteManualProtection:
    def test_manual_kf_at_exact_frame_returns_skip(self):
        track = _mk_track((10, "manual"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.SKIP

    def test_manual_kf_at_different_frame_not_blocked(self):
        track = _mk_track((10, "manual"))
        cand = _candidate()
        decision = decide_write(track, 20, cand, ContinuityVerdict.ACCEPT)
        # No manual at frame 20; manual at 10 is active anchor → WRITE_ANCHORED
        assert decision.action == WriteAction.WRITE_ANCHORED

    def test_detector_kf_at_exact_frame_not_protected(self):
        track = _mk_track((10, "detector"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        # detector kf at 10 can be overwritten
        assert decision.action == WriteAction.WRITE_DETECTED


class TestDecideWriteNoAnchorNoContext:
    """Empty track or track with no prior keyframes."""

    def test_empty_track_accept_returns_write_detected(self):
        track = _mk_track()
        cand = _candidate()
        decision = decide_write(track, 0, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_DETECTED

    def test_empty_track_reject_returns_skip(self):
        track = _mk_track()
        cand = _candidate()
        decision = decide_write(track, 0, cand, ContinuityVerdict.REJECT)
        assert decision.action == WriteAction.SKIP

    def test_empty_track_accept_anchored_returns_write_detected(self):
        # No prior context to anchor to → fallback to WRITE_DETECTED
        track = _mk_track()
        cand = _candidate()
        decision = decide_write(track, 5, cand, ContinuityVerdict.ACCEPT_ANCHORED)
        assert decision.action == WriteAction.WRITE_DETECTED


class TestDecideWriteWithManualAnchor:
    """Manual anchor active — accept / accept_anchored → WRITE_ANCHORED, reject → EXTEND_UNCERTAIN."""

    def _anchored_track(self, anchor_frame: int = 10) -> MaskTrack:
        return _mk_track((anchor_frame, "manual"))

    def test_accept_with_active_manual_anchor_returns_write_anchored(self):
        track = self._anchored_track(10)
        cand = _candidate()
        decision = decide_write(track, 20, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_ANCHORED
        assert decision.anchor_frame == 10

    def test_accept_anchored_with_active_manual_anchor_returns_write_anchored(self):
        track = self._anchored_track(10)
        cand = _candidate()
        decision = decide_write(track, 20, cand, ContinuityVerdict.ACCEPT_ANCHORED)
        assert decision.action == WriteAction.WRITE_ANCHORED
        assert decision.anchor_frame == 10

    def test_reject_with_active_manual_anchor_returns_extend_uncertain(self):
        track = self._anchored_track(10)
        cand = _candidate()
        decision = decide_write(track, 20, cand, ContinuityVerdict.REJECT)
        assert decision.action == WriteAction.EXTEND_UNCERTAIN

    def test_anchor_frame_points_to_most_recent_manual(self):
        track = _mk_track((5, "manual"), (15, "manual"))
        cand = _candidate()
        decision = decide_write(track, 20, cand, ContinuityVerdict.ACCEPT)
        assert decision.anchor_frame == 15  # most recent manual

    def test_expired_manual_anchor_no_longer_gates(self):
        # manual at frame 0, query at ANCHOR_DECAY_FRAMES+10 → anchor expired
        track = _mk_track((0, "manual"))
        cand = _candidate()
        far_frame = ANCHOR_DECAY_FRAMES + 10
        decision = decide_write(track, far_frame, cand, ContinuityVerdict.ACCEPT)
        # anchor expired → treat as no-anchor path → WRITE_DETECTED
        assert decision.action == WriteAction.WRITE_DETECTED


class TestDecideWriteDetectorAnchor:
    """No manual anchor; last prior kf is detector."""

    def test_accept_no_anchor_returns_write_detected(self):
        track = _mk_track((5, "detector"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_DETECTED

    def test_accept_anchored_with_detector_prior_returns_write_anchored(self):
        track = _mk_track((5, "detector"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT_ANCHORED)
        assert decision.action == WriteAction.WRITE_ANCHORED
        assert decision.anchor_frame == 5

    def test_reject_with_detector_prior_returns_extend_held(self):
        track = _mk_track((5, "detector"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.REJECT)
        assert decision.action == WriteAction.EXTEND_HELD


class TestDecideWriteShapeMismatch:
    """Shape-type mismatch overrides verdict toward REJECT semantics."""

    def test_shape_mismatch_with_manual_anchor_returns_extend_uncertain(self):
        # Prior kf is polygon, candidate is ellipse → mismatch → treat as REJECT
        # Manual anchor active → EXTEND_UNCERTAIN
        kf_m = _kf(5, "manual", shape_type="polygon")
        track = _track(kf_m)
        cand = _candidate(shape_type="ellipse")
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.EXTEND_UNCERTAIN

    def test_shape_mismatch_with_detector_prior_returns_extend_held(self):
        kf_d = _kf(5, "detector", shape_type="polygon")
        track = _track(kf_d)
        cand = _candidate(shape_type="ellipse")
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.EXTEND_HELD

    def test_shape_mismatch_no_prior_returns_skip(self):
        # no prior kf, shape mismatch → treat as REJECT + no prior → SKIP
        # But there IS no prior kf here; last_prior is None
        # shape mismatch check requires last_prior to be non-None to trigger
        # with no prior: skip applies through reject + no prior path
        track = _mk_track()
        cand = _candidate(shape_type="ellipse")
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        # No prior kf, so shape mismatch check does NOT trigger (last_prior=None)
        # Verdict stays ACCEPT → WRITE_DETECTED
        assert decision.action == WriteAction.WRITE_DETECTED

    def test_same_shape_type_not_rejected_by_mismatch(self):
        kf_d = _kf(5, "detector", shape_type="polygon")
        track = _track(kf_d)
        cand = _candidate(shape_type="polygon")
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_DETECTED


class TestDecideWriteAnchorFrameValue:
    """Verify anchor_frame is None when not applicable."""

    def test_write_detected_has_no_anchor_frame(self):
        track = _mk_track()
        cand = _candidate()
        decision = decide_write(track, 0, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_DETECTED
        assert decision.anchor_frame is None

    def test_extend_held_has_no_anchor_frame(self):
        track = _mk_track((5, "detector"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.REJECT)
        assert decision.action == WriteAction.EXTEND_HELD
        assert decision.anchor_frame is None

    def test_extend_uncertain_has_no_anchor_frame(self):
        track = _mk_track((5, "manual"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.REJECT)
        assert decision.action == WriteAction.EXTEND_UNCERTAIN
        assert decision.anchor_frame is None

    def test_write_anchored_has_anchor_frame(self):
        track = _mk_track((5, "manual"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.WRITE_ANCHORED
        assert decision.anchor_frame == 5


class TestDecideWriteSkip:
    def test_skip_returns_none_anchor_frame(self):
        track = _mk_track((10, "manual"))
        cand = _candidate()
        decision = decide_write(track, 10, cand, ContinuityVerdict.ACCEPT)
        assert decision.action == WriteAction.SKIP
        assert decision.anchor_frame is None


# ---------------------------------------------------------------------------
# W4: apply_write_action — helpers
# ---------------------------------------------------------------------------

def _seg(start: int, end: int, state: str = "held") -> MaskSegment:
    return MaskSegment(start_frame=start, end_frame=end, state=state)


def _decision(action: WriteAction, anchor_frame: int | None = None) -> WriteDecision:
    return WriteDecision(action=action, anchor_frame=anchor_frame)


def _find_kf(track: MaskTrack, frame_idx: int) -> Keyframe | None:
    """Find a keyframe in track by frame_index (order-independent)."""
    for kf in track.keyframes:
        if kf.frame_index == frame_idx:
            return kf
    return None


def _find_seg(track: MaskTrack, frame_idx: int) -> MaskSegment | None:
    """Find the first segment in track that contains frame_idx."""
    for seg in track.segments:
        if seg.contains(frame_idx):
            return seg
    return None


# ---------------------------------------------------------------------------
# W4: apply_write_action — SKIP
# ---------------------------------------------------------------------------

class TestApplyWriteActionSkip:
    def test_skip_empty_track_is_noop(self):
        track = _mk_track()
        cand = _candidate()
        apply_write_action(track, 5, cand, _decision(WriteAction.SKIP))
        assert track.keyframes == []
        assert track.segments == []

    def test_skip_nonempty_track_is_noop(self):
        kf = _kf(5, "detector")
        track = _track(kf)
        original_kf_count = len(track.keyframes)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.SKIP))
        assert len(track.keyframes) == original_kf_count
        assert track.segments == []


# ---------------------------------------------------------------------------
# W4: apply_write_action — WRITE_DETECTED
# ---------------------------------------------------------------------------

class TestApplyWriteActionWriteDetected:
    def test_adds_keyframe_to_empty_track(self):
        track = _mk_track()
        cand = _candidate(bbox=(0.1, 0.1, 0.2, 0.2), confidence=0.85)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_DETECTED))
        assert len(track.keyframes) == 1
        kf = track.keyframes[0]
        assert kf.frame_index == 10

    def test_keyframe_fields_are_correct(self):
        track = _mk_track()
        cand = _candidate(
            shape_type="ellipse",
            bbox=(0.2, 0.3, 0.15, 0.1),
            confidence=0.77,
        )
        apply_write_action(track, 7, cand, _decision(WriteAction.WRITE_DETECTED))
        kf = _find_kf(track, 7)
        assert kf is not None
        assert kf.source == "detector"
        assert kf.shape_type == "ellipse"
        assert kf.bbox == [0.2, 0.3, 0.15, 0.1]
        assert kf.confidence == 0.77

    def test_bbox_corners_are_derived_from_candidate(self):
        track = _mk_track()
        cand = _candidate(bbox=(0.1, 0.2, 0.3, 0.4))
        apply_write_action(track, 5, cand, _decision(WriteAction.WRITE_DETECTED))
        kf = _find_kf(track, 5)
        assert kf is not None
        x1, y1, w, h = 0.1, 0.2, 0.3, 0.4
        expected_points = [
            [x1,     y1    ],
            [x1 + w, y1    ],
            [x1 + w, y1 + h],
            [x1,     y1 + h],
        ]
        assert kf.points == expected_points

    def test_adds_to_nonempty_track(self):
        prior = _kf(5, "detector")
        track = _track(prior)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_DETECTED))
        assert len(track.keyframes) == 2
        assert _find_kf(track, 5) is not None
        assert _find_kf(track, 10) is not None

    def test_replaces_existing_detector_kf_at_same_frame(self):
        old_kf = _kf(10, "detector", confidence=0.5)
        track = _track(old_kf)
        cand = _candidate(confidence=0.9)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_DETECTED))
        assert len(track.keyframes) == 1
        assert _find_kf(track, 10).confidence == 0.9

    def test_does_not_replace_manual_kf(self):
        manual = _kf(10, "manual", confidence=1.0)
        track = _track(manual)
        cand = _candidate(confidence=0.9)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_DETECTED))
        assert len(track.keyframes) == 1
        assert _find_kf(track, 10).source == "manual"
        assert _find_kf(track, 10).confidence == 1.0


# ---------------------------------------------------------------------------
# W4: apply_write_action — WRITE_ANCHORED
# ---------------------------------------------------------------------------

class TestApplyWriteActionWriteAnchored:
    def _anchor_track(self, frame: int = 5) -> MaskTrack:
        kf = Keyframe(
            frame_index=frame,
            shape_type="polygon",
            points=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
            bbox=[0.1, 0.1, 0.2, 0.2],
            confidence=0.95,
            source="manual",
            rotation=15.0,
            opacity=0.8,
        )
        return _track(kf)

    def test_preserves_anchor_points(self):
        track = self._anchor_track(5)
        cand = _candidate(bbox=(0.4, 0.4, 0.2, 0.2), confidence=0.7)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        new_kf = _find_kf(track, 10)
        assert new_kf is not None
        anchor_kf = _find_kf(track, 5)
        assert new_kf.points == anchor_kf.points

    def test_uses_candidate_bbox(self):
        track = self._anchor_track(5)
        cand = _candidate(bbox=(0.5, 0.5, 0.15, 0.15), confidence=0.72)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        new_kf = _find_kf(track, 10)
        assert new_kf.bbox == [0.5, 0.5, 0.15, 0.15]

    def test_preserves_anchor_rotation(self):
        track = self._anchor_track(5)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        new_kf = _find_kf(track, 10)
        assert new_kf.rotation == 15.0

    def test_preserves_anchor_opacity(self):
        track = self._anchor_track(5)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        new_kf = _find_kf(track, 10)
        assert new_kf.opacity == 0.8

    def test_source_is_detector(self):
        track = self._anchor_track(5)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        new_kf = _find_kf(track, 10)
        assert new_kf.source == "detector"

    def test_anchor_points_are_deep_copied(self):
        # Mutating the new kf's points must not affect the anchor.
        track = self._anchor_track(5)
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=5))
        anchor_kf = _find_kf(track, 5)
        new_kf = _find_kf(track, 10)
        new_kf.points[0][0] = 999.0
        assert anchor_kf.points[0][0] != 999.0

    def test_fallback_to_detected_when_anchor_frame_missing(self):
        # anchor_frame=99 does not exist in the track → degrade to detected.
        track = self._anchor_track(5)
        cand = _candidate(bbox=(0.4, 0.4, 0.2, 0.2), confidence=0.7)
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=99))
        new_kf = _find_kf(track, 10)
        assert new_kf is not None
        assert new_kf.bbox == [0.4, 0.4, 0.2, 0.2]
        # Points are bbox-derived (fallback), not the anchor's custom points
        assert new_kf.points != [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]]

    def test_fallback_to_detected_when_anchor_frame_none(self):
        track = self._anchor_track(5)
        cand = _candidate(bbox=(0.2, 0.2, 0.1, 0.1), confidence=0.6)
        # anchor_frame=None → should fall back to detected
        apply_write_action(track, 10, cand, _decision(WriteAction.WRITE_ANCHORED, anchor_frame=None))
        new_kf = _find_kf(track, 10)
        assert new_kf is not None
        assert new_kf.bbox == [0.2, 0.2, 0.1, 0.1]


# ---------------------------------------------------------------------------
# W4: apply_write_action — EXTEND_HELD
# ---------------------------------------------------------------------------

class TestApplyWriteActionExtendHeld:
    def test_creates_single_frame_segment_on_empty_track(self):
        track = _mk_track()
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 1
        seg = track.segments[0]
        assert seg.start_frame == 10
        assert seg.end_frame == 10
        assert seg.state == "held"

    def test_extends_contiguous_held_segment(self):
        track = _mk_track()
        track.segments.append(_seg(5, 9, "held"))
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 1
        assert track.segments[0].end_frame == 10

    def test_does_not_extend_noncontiguous_segment(self):
        # Segment ends at 8, frame is 10 (gap at 9) → new segment created.
        track = _mk_track()
        track.segments.append(_seg(5, 8, "held"))
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 2

    def test_noop_when_frame_already_covered(self):
        track = _mk_track()
        track.segments.append(_seg(5, 15, "held"))
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 1
        assert track.segments[0].end_frame == 15  # unchanged

    def test_repeated_calls_produce_single_segment(self):
        track = _mk_track()
        cand = _candidate()
        for frame in range(10, 15):
            apply_write_action(track, frame, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 1
        seg = track.segments[0]
        assert seg.start_frame == 10
        assert seg.end_frame == 14
        assert seg.state == "held"

    def test_does_not_extend_segment_of_different_state(self):
        # Contiguous but state is "uncertain", not "held" → new segment.
        track = _mk_track()
        track.segments.append(_seg(5, 9, "uncertain"))
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_HELD))
        assert len(track.segments) == 2
        held_segs = [s for s in track.segments if s.state == "held"]
        assert len(held_segs) == 1
        assert held_segs[0].start_frame == 10


# ---------------------------------------------------------------------------
# W4: apply_write_action — EXTEND_UNCERTAIN
# ---------------------------------------------------------------------------

class TestApplyWriteActionExtendUncertain:
    def test_creates_single_frame_segment_on_empty_track(self):
        track = _mk_track()
        cand = _candidate()
        apply_write_action(track, 20, cand, _decision(WriteAction.EXTEND_UNCERTAIN))
        assert len(track.segments) == 1
        seg = track.segments[0]
        assert seg.start_frame == 20
        assert seg.end_frame == 20
        assert seg.state == "uncertain"

    def test_extends_contiguous_uncertain_segment(self):
        track = _mk_track()
        track.segments.append(_seg(10, 14, "uncertain"))
        cand = _candidate()
        apply_write_action(track, 15, cand, _decision(WriteAction.EXTEND_UNCERTAIN))
        assert len(track.segments) == 1
        assert track.segments[0].end_frame == 15

    def test_does_not_merge_with_contiguous_held_segment(self):
        # Contiguous held segment at [5,9]; extend_uncertain at 10 must NOT merge.
        track = _mk_track()
        track.segments.append(_seg(5, 9, "held"))
        cand = _candidate()
        apply_write_action(track, 10, cand, _decision(WriteAction.EXTEND_UNCERTAIN))
        assert len(track.segments) == 2
        uncertain_segs = [s for s in track.segments if s.state == "uncertain"]
        assert len(uncertain_segs) == 1
        assert uncertain_segs[0].start_frame == 10


# ---------------------------------------------------------------------------
# W4: apply_write_action — segment boundary invariants
# ---------------------------------------------------------------------------

class TestApplyWriteActionSegmentBoundaries:
    def test_single_extend_yields_start_eq_end(self):
        track = _mk_track()
        apply_write_action(track, 7, _candidate(), _decision(WriteAction.EXTEND_HELD))
        seg = track.segments[0]
        assert seg.start_frame <= seg.end_frame

    def test_multi_extend_yields_start_le_end(self):
        track = _mk_track()
        for f in range(5, 10):
            apply_write_action(track, f, _candidate(), _decision(WriteAction.EXTEND_HELD))
        seg = track.segments[0]
        assert seg.start_frame == 5
        assert seg.end_frame == 9

    def test_held_and_uncertain_stay_separate_with_gap(self):
        # EXTEND_HELD at 5, then gap, then EXTEND_UNCERTAIN at 10 → two segments, no overlap.
        track = _mk_track()
        apply_write_action(track, 5, _candidate(), _decision(WriteAction.EXTEND_HELD))
        apply_write_action(track, 10, _candidate(), _decision(WriteAction.EXTEND_UNCERTAIN))
        assert len(track.segments) == 2
        for seg in track.segments:
            assert seg.start_frame <= seg.end_frame

    def test_no_segment_overlap_after_mixed_actions(self):
        track = _mk_track()
        cand = _candidate()
        for f in range(5, 8):
            apply_write_action(track, f, cand, _decision(WriteAction.EXTEND_HELD))
        for f in range(10, 13):
            apply_write_action(track, f, cand, _decision(WriteAction.EXTEND_UNCERTAIN))
        assert len(track.segments) == 2
        segs = sorted(track.segments, key=lambda s: s.start_frame)
        assert segs[0].end_frame < segs[1].start_frame  # no overlap


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — helper
# ---------------------------------------------------------------------------

def _ellipse_kf(
    frame: int,
    rotation: float = 0.0,
    bbox: list[float] | None = None,
    confidence: float = 0.9,
    opacity: float = 1.0,
    source: str = "manual",
) -> Keyframe:
    """Build an ellipse Keyframe for interpolation tests."""
    b = bbox if bbox is not None else [0.1, 0.1, 0.2, 0.2]
    x1, y1, w, h = b
    return Keyframe(
        frame_index=frame,
        shape_type="ellipse",
        points=[[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]],
        bbox=list(b),
        confidence=confidence,
        source=source,
        rotation=rotation,
        opacity=opacity,
    )


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — endpoint behavior
# ---------------------------------------------------------------------------

class TestInterpolateEllipseEndpoints:
    def test_at_frame_a_returns_a_geometry(self):
        a = _ellipse_kf(10, rotation=10.0, bbox=[0.1, 0.1, 0.2, 0.2], confidence=0.8)
        b = _ellipse_kf(20, rotation=90.0, bbox=[0.5, 0.5, 0.3, 0.3], confidence=1.0)
        result = interpolate_ellipse(a, b, 10)
        assert result.frame_index == 10
        assert result.bbox == pytest.approx(a.bbox)
        assert result.rotation == pytest.approx(a.rotation)
        assert result.confidence == pytest.approx(a.confidence)
        assert result.opacity == pytest.approx(a.opacity)

    def test_at_frame_b_returns_b_geometry(self):
        a = _ellipse_kf(10, rotation=10.0, bbox=[0.1, 0.1, 0.2, 0.2], confidence=0.8)
        b = _ellipse_kf(20, rotation=90.0, bbox=[0.5, 0.5, 0.3, 0.3], confidence=1.0)
        result = interpolate_ellipse(a, b, 20)
        assert result.frame_index == 20
        assert result.bbox == pytest.approx(b.bbox)
        assert result.rotation == pytest.approx(b.rotation)
        assert result.confidence == pytest.approx(b.confidence)
        assert result.opacity == pytest.approx(b.opacity)


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — bbox interpolation
# ---------------------------------------------------------------------------

class TestInterpolateEllipseBbox:
    def test_midpoint_bbox_is_average(self):
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.4, 0.4, 0.4, 0.4])
        result = interpolate_ellipse(a, b, 5)
        assert result.bbox == pytest.approx([0.2, 0.2, 0.3, 0.3])

    def test_quarter_point_bbox(self):
        # t = 1/4
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.0, 0.0])
        b = _ellipse_kf(4, bbox=[1.0, 1.0, 1.0, 1.0])
        result = interpolate_ellipse(a, b, 1)
        assert result.bbox == pytest.approx([0.25, 0.25, 0.25, 0.25])

    def test_three_quarter_point_bbox(self):
        # t = 3/4
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.0, 0.0])
        b = _ellipse_kf(4, bbox=[1.0, 1.0, 1.0, 1.0])
        result = interpolate_ellipse(a, b, 3)
        assert result.bbox == pytest.approx([0.75, 0.75, 0.75, 0.75])

    def test_all_four_bbox_components_interpolated_independently(self):
        a = _ellipse_kf(0, bbox=[0.1, 0.2, 0.3, 0.4])
        b = _ellipse_kf(10, bbox=[0.5, 0.6, 0.7, 0.8])
        result = interpolate_ellipse(a, b, 5)
        assert result.bbox == pytest.approx([0.3, 0.4, 0.5, 0.6])


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — rotation interpolation
# ---------------------------------------------------------------------------

class TestInterpolateEllipseRotation:
    def test_midpoint_rotation_forward(self):
        # 10° → 90°: midpoint = 50°
        a = _ellipse_kf(0, rotation=10.0)
        b = _ellipse_kf(10, rotation=90.0)
        result = interpolate_ellipse(a, b, 5)
        assert result.rotation == pytest.approx(50.0)

    def test_rotation_wraps_through_zero(self):
        # 350° → 10°: shortest path is +20°; midpoint = 360° ≡ 0°
        a = _ellipse_kf(0, rotation=350.0)
        b = _ellipse_kf(10, rotation=10.0)
        result = interpolate_ellipse(a, b, 5)
        # 350 + 0.5 * 20 = 360 ≡ 0° (mod 360)
        assert result.rotation % 360.0 == pytest.approx(0.0, abs=1e-9)

    def test_rotation_takes_shorter_path_backward(self):
        # 10° → 350°: shortest path is −20°; midpoint = 0°
        a = _ellipse_kf(0, rotation=10.0)
        b = _ellipse_kf(10, rotation=350.0)
        result = interpolate_ellipse(a, b, 5)
        assert result.rotation == pytest.approx(0.0, abs=1e-9)

    def test_zero_rotation_unchanged(self):
        a = _ellipse_kf(0, rotation=0.0)
        b = _ellipse_kf(10, rotation=0.0)
        result = interpolate_ellipse(a, b, 5)
        assert result.rotation == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — shape_type guard
# ---------------------------------------------------------------------------

class TestInterpolateEllipseShapeTypeGuard:
    def test_polygon_a_raises(self):
        a = _kf(0, shape_type="polygon")
        b = _ellipse_kf(10)
        with pytest.raises(ValueError, match="ellipse"):
            interpolate_ellipse(a, b, 5)

    def test_polygon_b_raises(self):
        a = _ellipse_kf(0)
        b = _kf(10, shape_type="polygon")
        with pytest.raises(ValueError, match="ellipse"):
            interpolate_ellipse(a, b, 5)

    def test_both_polygon_raises(self):
        a = _kf(0, shape_type="polygon")
        b = _kf(10, shape_type="polygon")
        with pytest.raises(ValueError):
            interpolate_ellipse(a, b, 5)

    def test_error_message_names_offending_keyframe(self):
        # Error should mention shape_type so the caller can diagnose quickly.
        a = _kf(0, shape_type="polygon")
        b = _ellipse_kf(10)
        with pytest.raises(ValueError, match="polygon"):
            interpolate_ellipse(a, b, 5)


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — frame range validation
# ---------------------------------------------------------------------------

class TestInterpolateEllipseFrameValidation:
    def test_frame_idx_before_range_raises(self):
        a = _ellipse_kf(5)
        b = _ellipse_kf(15)
        with pytest.raises(ValueError):
            interpolate_ellipse(a, b, 4)

    def test_frame_idx_after_range_raises(self):
        a = _ellipse_kf(5)
        b = _ellipse_kf(15)
        with pytest.raises(ValueError):
            interpolate_ellipse(a, b, 16)

    def test_degenerate_same_frame_raises(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(10)
        with pytest.raises(ValueError):
            interpolate_ellipse(a, b, 10)

    def test_a_after_b_raises(self):
        a = _ellipse_kf(20)
        b = _ellipse_kf(10)
        with pytest.raises(ValueError):
            interpolate_ellipse(a, b, 15)


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — purity guarantees
# ---------------------------------------------------------------------------

class TestInterpolateEllipsePurity:
    def test_does_not_mutate_a(self):
        a = _ellipse_kf(0, bbox=[0.1, 0.1, 0.2, 0.2], rotation=30.0)
        b = _ellipse_kf(10, bbox=[0.5, 0.5, 0.3, 0.3], rotation=90.0)
        orig_bbox = list(a.bbox)
        orig_rot = a.rotation
        interpolate_ellipse(a, b, 5)
        assert a.bbox == orig_bbox
        assert a.rotation == orig_rot

    def test_does_not_mutate_b(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10, bbox=[0.5, 0.5, 0.3, 0.3], rotation=120.0)
        orig_bbox = list(b.bbox)
        orig_rot = b.rotation
        interpolate_ellipse(a, b, 5)
        assert b.bbox == orig_bbox
        assert b.rotation == orig_rot

    def test_deterministic_for_repeated_calls(self):
        a = _ellipse_kf(0, bbox=[0.1, 0.1, 0.2, 0.2], rotation=45.0, confidence=0.7)
        b = _ellipse_kf(10, bbox=[0.5, 0.5, 0.3, 0.3], rotation=135.0, confidence=1.0)
        r1 = interpolate_ellipse(a, b, 5)
        r2 = interpolate_ellipse(a, b, 5)
        assert r1.bbox == r2.bbox
        assert r1.rotation == r2.rotation
        assert r1.confidence == r2.confidence


# ---------------------------------------------------------------------------
# W6: interpolate_ellipse — output field correctness
# ---------------------------------------------------------------------------

class TestInterpolateEllipseOutputFields:
    def test_frame_index_is_target(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(20)
        result = interpolate_ellipse(a, b, 7)
        assert result.frame_index == 7

    def test_shape_type_is_ellipse(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        result = interpolate_ellipse(a, b, 5)
        assert result.shape_type == "ellipse"

    def test_source_is_detector(self):
        a = _ellipse_kf(0, source="manual")
        b = _ellipse_kf(10, source="manual")
        result = interpolate_ellipse(a, b, 5)
        assert result.source == "detector"

    def test_confidence_is_linearly_interpolated(self):
        a = _ellipse_kf(0, confidence=0.6)
        b = _ellipse_kf(10, confidence=1.0)
        result = interpolate_ellipse(a, b, 5)
        assert result.confidence == pytest.approx(0.8)

    def test_opacity_is_linearly_interpolated(self):
        a = _ellipse_kf(0, opacity=0.4)
        b = _ellipse_kf(10, opacity=1.0)
        result = interpolate_ellipse(a, b, 5)
        assert result.opacity == pytest.approx(0.7)

    def test_points_match_interpolated_bbox_corners(self):
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.4, 0.4, 0.4, 0.4])
        result = interpolate_ellipse(a, b, 5)
        x1, y1, w, h = result.bbox
        expected = [
            [x1,     y1    ],
            [x1 + w, y1    ],
            [x1 + w, y1 + h],
            [x1,     y1 + h],
        ]
        # pytest.approx does not support list-of-lists directly; compare per-point.
        assert len(result.points) == len(expected)
        for actual_pt, exp_pt in zip(result.points, expected):
            assert actual_pt == pytest.approx(exp_pt)


# ---------------------------------------------------------------------------
# W7: resolve_for_render — helpers
# ---------------------------------------------------------------------------

def _make_track(kfs, segs=None):
    """Build a MaskTrack with keyframes and optional explicit segments."""
    track = _track(*kfs)
    if segs:
        for s in segs:
            track.segments.append(s)
        track.apply_domain_rules()
    return track


# ---------------------------------------------------------------------------
# W7: resolve_for_render — None (outside renderable span)
# ---------------------------------------------------------------------------

class TestResolveForRenderNone:
    def test_no_keyframes(self):
        track = _mk_track()
        assert resolve_for_render(track, 5) is None

    def test_before_first_keyframe_synthetic_span(self):
        # Synthetic span = [10,20]; frame 5 is before → not renderable
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        assert resolve_for_render(track, 5) is None

    def test_after_last_keyframe_no_explicit_segment(self):
        # Synthetic span = [10,20]; frame 25 is beyond last kf → not renderable
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        assert resolve_for_render(track, 25) is None

    def test_outside_explicit_segment(self):
        # Explicit segment [10,20] only; frame 25 is outside
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _make_track([a, b], [_seg(10, 20, "confirmed")])
        assert resolve_for_render(track, 25) is None

    def test_between_explicit_segments_gap_not_renderable(self):
        # Segments [5,9] and [15,20]; frame 12 falls in the gap → not renderable
        a = _ellipse_kf(5)
        b = _ellipse_kf(12)
        c = _ellipse_kf(20)
        track = _make_track(
            [a, b, c],
            [_seg(5, 9, "confirmed"), _seg(15, 20, "confirmed")],
        )
        assert resolve_for_render(track, 12) is None


# ---------------------------------------------------------------------------
# W7: resolve_for_render — EXPLICIT
# ---------------------------------------------------------------------------

class TestResolveForRenderExplicit:
    def test_exact_keyframe_returns_explicit(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        result = resolve_for_render(track, 10)
        assert result is not None
        kf, reason = result
        assert reason == ResolveReason.EXPLICIT
        assert kf.frame_index == 10

    def test_returns_same_kf_object_not_copy(self):
        a = _ellipse_kf(10)
        track = _track(a, _ellipse_kf(20))
        kf, _ = resolve_for_render(track, 10)
        assert kf is a

    def test_explicit_also_for_polygon_kf(self):
        a = _kf(10, "manual", shape_type="polygon")
        b = _kf(20, "manual", shape_type="polygon")
        track = _track(a, b)
        _, reason = resolve_for_render(track, 10)
        assert reason == ResolveReason.EXPLICIT

    def test_explicit_for_last_keyframe(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        _, reason = resolve_for_render(track, 20)
        assert reason == ResolveReason.EXPLICIT


# ---------------------------------------------------------------------------
# W7: resolve_for_render — INTERPOLATED
# ---------------------------------------------------------------------------

class TestResolveForRenderInterpolated:
    def test_between_ellipse_kfs_valid_gap(self):
        # gap = 10 ≤ 30 → interpolated
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.INTERPOLATED

    def test_interpolated_kf_has_correct_frame_index(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        kf, _ = resolve_for_render(track, 13)
        assert kf.frame_index == 13

    def test_interpolated_bbox_is_lerped(self):
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.4, 0.4, 0.4, 0.4])
        track = _track(a, b)
        kf, reason = resolve_for_render(track, 5)  # t = 0.5
        assert reason == ResolveReason.INTERPOLATED
        assert kf.bbox == pytest.approx([0.2, 0.2, 0.3, 0.3])

    def test_gap_exactly_at_max_limit_still_interpolates(self):
        # gap = 30 == _INTERPOLATE_MAX_GAP → allowed
        a = _ellipse_kf(0)
        b = _ellipse_kf(30)
        track = _track(a, b)
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.INTERPOLATED

    def test_frame_in_held_segment_with_valid_ellipse_kfs_interpolates(self):
        # Held/uncertain segment state does NOT block interpolation.
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _make_track([a, b], [_seg(10, 20, "held")])
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.INTERPOLATED

    def test_frame_in_uncertain_segment_with_valid_ellipse_kfs_interpolates(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _make_track([a, b], [_seg(10, 20, "uncertain")])
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.INTERPOLATED


# ---------------------------------------------------------------------------
# W7: resolve_for_render — HELD_FROM_PRIOR
# ---------------------------------------------------------------------------

class TestResolveForRenderHeldFromPrior:
    def test_gap_one_over_max_returns_held(self):
        # gap = 31 > 30 = _INTERPOLATE_MAX_GAP → held
        a = _ellipse_kf(0)
        b = _ellipse_kf(31)
        track = _track(a, b)
        kf, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert kf is a

    def test_mixed_ellipse_polygon_returns_held(self):
        a = _ellipse_kf(10)
        b = _kf(20, "manual", shape_type="polygon")
        track = _track(a, b)
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_mixed_polygon_ellipse_returns_held(self):
        a = _kf(10, "manual", shape_type="polygon")
        b = _ellipse_kf(20)
        track = _track(a, b)
        _, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_after_last_kf_in_explicit_extended_segment(self):
        # Explicit segment extends past last keyframe — renderable but no next kf.
        kf = _ellipse_kf(10)
        track = _make_track([kf], [_seg(10, 25, "confirmed")])
        result = resolve_for_render(track, 20)
        assert result is not None
        r_kf, reason = result
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert r_kf is kf

    def test_held_from_prior_returns_actual_prior_kf_object(self):
        # Must return the prior kf object directly (not a copy).
        a = _ellipse_kf(0)
        b = _ellipse_kf(31)
        track = _track(a, b)
        kf, _ = resolve_for_render(track, 15)
        assert kf is a

    def test_single_kf_in_extended_segment_returns_held(self):
        # Only one kf, explicit segment extends past it — no next kf → held.
        kf = _kf(5, "manual", shape_type="polygon")
        track = _make_track([kf], [_seg(5, 15, "confirmed")])
        r_kf, reason = resolve_for_render(track, 10)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert r_kf is kf


# ---------------------------------------------------------------------------
# W7: resolve_for_render — export safety
# ---------------------------------------------------------------------------

class TestResolveForRenderExportSafety:
    def test_renderable_span_not_widened_past_synthetic_end(self):
        # Last kf at 20; frame 21 is outside synthetic span → None (not widened).
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        assert resolve_for_render(track, 21) is None

    def test_renderable_span_not_widened_before_synthetic_start(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        assert resolve_for_render(track, 9) is None

    def test_explicit_segment_controls_renderable_span(self):
        # Segment [12,18] — frames outside are not renderable even with kfs.
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _make_track([a, b], [_seg(12, 18, "confirmed")])
        # Frame 11 is outside [12,18] → not renderable
        assert resolve_for_render(track, 11) is None
        # Frame 15 is inside [12,18] → renderable
        result = resolve_for_render(track, 15)
        assert result is not None


# ---------------------------------------------------------------------------
# W7: resolve_for_render - generated segment repair
# ---------------------------------------------------------------------------

class TestResolveForRenderGeneratedSegments:
    def test_held_segment_does_not_hide_accepted_detector_keyframes(self):
        # Detection can create held/uncertain segments for weak frames while
        # accepted keyframes remain the authoritative render span.
        a = _kf(0, "detector", shape_type="polygon")
        b = _kf(6, "detector", shape_type="polygon")
        track = MaskTrack(
            track_id="detector-track",
            label="detector",
            state="detected",
            source="detector",
            keyframes=[a, b],
            segments=[_seg(2, 4, "held")],
        )

        start_result = resolve_for_render(track, 0)
        held_result = resolve_for_render(track, 3)
        end_result = resolve_for_render(track, 6)

        assert start_result is not None
        assert start_result[1] == ResolveReason.EXPLICIT
        assert held_result is not None
        assert end_result is not None
        assert end_result[1] == ResolveReason.EXPLICIT


# ---------------------------------------------------------------------------
# W7: resolve_for_render - purity
# ---------------------------------------------------------------------------

class TestResolveForRenderPurity:
    def test_deterministic_on_repeated_calls(self):
        a = _ellipse_kf(0, bbox=[0.1, 0.1, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.5, 0.5, 0.3, 0.3])
        track = _track(a, b)
        r1 = resolve_for_render(track, 5)
        r2 = resolve_for_render(track, 5)
        kf1, reason1 = r1
        kf2, reason2 = r2
        assert reason1 == reason2
        assert kf1.bbox == kf2.bbox

    def test_does_not_mutate_track_keyframes(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        track = _track(a, b)
        orig_count = len(track.keyframes)
        orig_a_bbox = list(a.bbox)
        resolve_for_render(track, 5)
        assert len(track.keyframes) == orig_count
        assert a.bbox == orig_a_bbox

    def test_does_not_mutate_track_segments(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        track = _make_track([a, b], [_seg(0, 10, "confirmed")])
        orig_seg_count = len(track.segments)
        resolve_for_render(track, 5)
        assert len(track.segments) == orig_seg_count


# ---------------------------------------------------------------------------
# W8: resolve_for_editing — None cases
# ---------------------------------------------------------------------------

class TestResolveForEditingNone:
    def test_no_keyframes_returns_none(self):
        track = _mk_track()
        assert resolve_for_editing(track, 5) is None

    def test_before_first_keyframe_returns_none(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        assert resolve_for_editing(track, 9) is None

    def test_exactly_one_frame_before_first_returns_none(self):
        kf = _ellipse_kf(10)
        track = _track(kf)
        assert resolve_for_editing(track, 9) is None

    def test_zero_frame_before_first_on_empty_track_returns_none(self):
        # Edge: track with no kfs; any frame returns None
        track = _mk_track()
        assert resolve_for_editing(track, 0) is None


# ---------------------------------------------------------------------------
# W8: resolve_for_editing — EXPLICIT
# ---------------------------------------------------------------------------

class TestResolveForEditingExplicit:
    def test_exact_keyframe_returns_explicit(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 10)
        assert reason == ResolveReason.EXPLICIT
        assert kf.frame_index == 10

    def test_returns_same_kf_object_not_copy(self):
        a = _ellipse_kf(10)
        track = _track(a, _ellipse_kf(20))
        kf, _ = resolve_for_editing(track, 10)
        assert kf is a

    def test_explicit_for_polygon_kf(self):
        a = _kf(10, "manual", shape_type="polygon")
        b = _kf(20, "manual", shape_type="polygon")
        track = _track(a, b)
        _, reason = resolve_for_editing(track, 10)
        assert reason == ResolveReason.EXPLICIT

    def test_first_kf_is_explicit(self):
        # Boundary: first keyframe's own frame returns EXPLICIT
        kf = _ellipse_kf(5)
        track = _track(kf)
        _, reason = resolve_for_editing(track, 5)
        assert reason == ResolveReason.EXPLICIT


# ---------------------------------------------------------------------------
# W8: resolve_for_editing — INTERPOLATED
# ---------------------------------------------------------------------------

class TestResolveForEditingInterpolated:
    def test_between_ellipse_kfs_valid_gap(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)  # gap = 10 ≤ 30
        track = _track(a, b)
        _, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.INTERPOLATED

    def test_interpolated_kf_frame_index_correct(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        kf, _ = resolve_for_editing(track, 13)
        assert kf.frame_index == 13

    def test_interpolated_bbox_lerped(self):
        a = _ellipse_kf(0, bbox=[0.0, 0.0, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.4, 0.4, 0.4, 0.4])
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 5)
        assert reason == ResolveReason.INTERPOLATED
        assert kf.bbox == pytest.approx([0.2, 0.2, 0.3, 0.3])

    def test_gap_at_max_limit_interpolates(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(30)
        track = _track(a, b)
        _, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.INTERPOLATED

    def test_outside_explicit_segment_still_interpolates(self):
        # W8 does not call frame_is_renderable — segment state is irrelevant.
        # Frame 12 is outside explicit segment [5,9] and [15,20] but between kfs at 5 and 20.
        a = _ellipse_kf(5)
        b = _ellipse_kf(20)
        track = _make_track(
            [a, b],
            [_seg(5, 9, "confirmed"), _seg(15, 20, "confirmed")],
        )
        # W7 would return None here; W8 must interpolate
        _, reason = resolve_for_editing(track, 12)
        assert reason == ResolveReason.INTERPOLATED


# ---------------------------------------------------------------------------
# W8: resolve_for_editing — HELD_FROM_PRIOR
# ---------------------------------------------------------------------------

class TestResolveForEditingHeldFromPrior:
    def test_gap_over_limit_returns_held(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(31)
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert kf is a

    def test_polygon_gap_over_limit_returns_held(self):
        a = _kf(0, "manual", shape_type="polygon")
        b = _kf(31, "manual", shape_type="polygon")
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert kf is a

    def test_mixed_ellipse_polygon_returns_held(self):
        a = _ellipse_kf(10)
        b = _kf(20, "manual", shape_type="polygon")
        track = _track(a, b)
        _, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_mixed_polygon_ellipse_returns_held(self):
        a = _kf(10, "manual", shape_type="polygon")
        b = _ellipse_kf(20)
        track = _track(a, b)
        _, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_after_last_keyframe_returns_held_not_none(self):
        # KEY DIFFERENCE: W7 returns None here; W8 returns HELD_FROM_PRIOR.
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        result = resolve_for_editing(track, 25)
        assert result is not None
        kf, reason = result
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_after_last_kf_returns_last_kf_object(self):
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        kf, _ = resolve_for_editing(track, 50)
        assert kf is b  # last keyframe is b

    def test_far_after_last_kf_still_held_not_none(self):
        # Even far beyond the last keyframe, editing resolver returns held.
        kf = _ellipse_kf(10)
        track = _track(kf)
        result = resolve_for_editing(track, 10_000)
        assert result is not None
        _, reason = result
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_single_kf_track_after_kf_returns_held(self):
        kf = _kf(5, "manual", shape_type="polygon")
        track = _track(kf)
        r_kf, reason = resolve_for_editing(track, 10)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert r_kf is kf


# ---------------------------------------------------------------------------
# W8 vs W7: explicit semantic difference tests
# ---------------------------------------------------------------------------

class TestResolveForEditingVsRender:
    def test_after_last_kf_w7_none_w8_held(self):
        # After last kf with no extending segment:
        # W7 (export) → None; W8 (editing) → HELD_FROM_PRIOR
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        frame_after = 25
        assert resolve_for_render(track, frame_after) is None
        result = resolve_for_editing(track, frame_after)
        assert result is not None
        _, reason = result
        assert reason == ResolveReason.HELD_FROM_PRIOR

    def test_outside_explicit_segment_w7_none_w8_resolves(self):
        # Frame in gap between two explicit segments:
        # W7 → None; W8 → interpolated or held (not None)
        a = _ellipse_kf(5)
        b = _ellipse_kf(20)
        track = _make_track(
            [a, b],
            [_seg(5, 9, "confirmed"), _seg(15, 20, "confirmed")],
        )
        assert resolve_for_render(track, 12) is None
        result = resolve_for_editing(track, 12)
        assert result is not None

    def test_within_renderable_span_both_agree_explicit(self):
        # When within span and exact kf exists, both resolvers agree.
        a = _ellipse_kf(10)
        b = _ellipse_kf(20)
        track = _track(a, b)
        r_kf, r_reason = resolve_for_render(track, 10)
        e_kf, e_reason = resolve_for_editing(track, 10)
        assert r_reason == e_reason == ResolveReason.EXPLICIT
        assert r_kf is e_kf

    def test_within_renderable_span_both_agree_interpolated(self):
        # Within synthetic span, valid ellipse gap: both resolvers agree.
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        track = _track(a, b)
        r_kf, r_reason = resolve_for_render(track, 5)
        e_kf, e_reason = resolve_for_editing(track, 5)
        assert r_reason == e_reason == ResolveReason.INTERPOLATED
        assert r_kf.bbox == e_kf.bbox


# ---------------------------------------------------------------------------
# W8: resolve_for_editing — purity
# ---------------------------------------------------------------------------

class TestResolveForEditingPurity:
    def test_deterministic_on_repeated_calls(self):
        a = _ellipse_kf(0, bbox=[0.1, 0.1, 0.2, 0.2])
        b = _ellipse_kf(10, bbox=[0.5, 0.5, 0.3, 0.3])
        track = _track(a, b)
        r1 = resolve_for_editing(track, 5)
        r2 = resolve_for_editing(track, 5)
        kf1, reason1 = r1
        kf2, reason2 = r2
        assert reason1 == reason2
        assert kf1.bbox == kf2.bbox

    def test_does_not_mutate_track_keyframes(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        track = _track(a, b)
        orig_count = len(track.keyframes)
        orig_a_bbox = list(a.bbox)
        resolve_for_editing(track, 5)
        assert len(track.keyframes) == orig_count
        assert a.bbox == orig_a_bbox

    def test_does_not_mutate_track_segments(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        track = _make_track([a, b], [_seg(0, 10, "confirmed")])
        orig_seg_count = len(track.segments)
        resolve_for_editing(track, 5)
        assert len(track.segments) == orig_seg_count


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — helper
# ---------------------------------------------------------------------------

def _polygon_kf(
    frame: int,
    points: list[list[float]] | None = None,
    bbox: list[float] | None = None,
    rotation: float = 0.0,
    confidence: float = 0.9,
    opacity: float = 1.0,
    source: str = "manual",
) -> Keyframe:
    """Build a polygon Keyframe for interpolation tests."""
    pts = points if points is not None else [
        [0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3],
    ]
    if bbox is None:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    return Keyframe(
        frame_index=frame,
        shape_type="polygon",
        points=[list(p) for p in pts],
        bbox=list(bbox),
        confidence=confidence,
        source=source,
        rotation=rotation,
        opacity=opacity,
    )


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — endpoint behavior
# ---------------------------------------------------------------------------

class TestInterpolatePolygonEndpoints:
    def test_at_frame_a_returns_a_geometry(self):
        a = _polygon_kf(10, confidence=0.8)
        b = _polygon_kf(20, points=[[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.7]], confidence=1.0)
        result = interpolate_polygon(a, b, 10)
        assert result.frame_index == 10
        for i, pt in enumerate(result.points):
            assert pt == pytest.approx(a.points[i])
        assert result.confidence == pytest.approx(a.confidence)

    def test_at_frame_b_returns_b_geometry(self):
        a = _polygon_kf(10)
        b = _polygon_kf(20, points=[[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.7]], confidence=1.0)
        result = interpolate_polygon(a, b, 20)
        assert result.frame_index == 20
        for i, pt in enumerate(result.points):
            assert pt == pytest.approx(b.points[i])
        assert result.confidence == pytest.approx(b.confidence)


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — midpoint
# ---------------------------------------------------------------------------

class TestInterpolatePolygonMidpoint:
    def test_midpoint_bbox_is_average(self):
        a = _polygon_kf(0, points=[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]])
        b = _polygon_kf(10, points=[[0.6, 0.0], [0.8, 0.0], [0.8, 0.2], [0.6, 0.2]])
        result = interpolate_polygon(a, b, 5)
        assert result.shape_type == "polygon"
        # Midpoint bbox x should be around 0.3
        assert abs(result.bbox[0] - 0.3) < 0.05

    def test_midpoint_points_interpolated(self):
        a = _polygon_kf(0, points=[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]])
        b = _polygon_kf(10, points=[[0.4, 0.0], [0.6, 0.0], [0.6, 0.2], [0.4, 0.2]])
        result = interpolate_polygon(a, b, 5)
        # Same vertex count, no resampling needed.  Midpoint of vertex 0: (0.0+0.4)/2 = 0.2
        assert abs(result.points[0][0] - 0.2) < 1e-6
        assert abs(result.points[0][1] - 0.0) < 1e-6

    def test_midpoint_confidence_interpolated(self):
        a = _polygon_kf(0, confidence=0.6)
        b = _polygon_kf(10, confidence=1.0)
        result = interpolate_polygon(a, b, 5)
        assert result.confidence == pytest.approx(0.8)

    def test_midpoint_opacity_interpolated(self):
        a = _polygon_kf(0, opacity=0.0)
        b = _polygon_kf(10, opacity=1.0)
        result = interpolate_polygon(a, b, 5)
        assert result.opacity == pytest.approx(0.5)

    def test_source_is_detector(self):
        a = _polygon_kf(0)
        b = _polygon_kf(10)
        result = interpolate_polygon(a, b, 5)
        assert result.source == "detector"


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — different vertex counts
# ---------------------------------------------------------------------------

class TestInterpolatePolygonResample:
    def test_different_vertex_count_interpolates(self):
        # Triangle vs pentagon — both get resampled to 5 vertices.
        tri = _polygon_kf(0, points=[[0.0, 0.0], [0.2, 0.0], [0.1, 0.2]])
        pent = _polygon_kf(10, points=[
            [0.4, 0.0], [0.6, 0.0], [0.7, 0.15], [0.5, 0.3], [0.3, 0.15],
        ])
        result = interpolate_polygon(tri, pent, 5)
        assert result.shape_type == "polygon"
        assert len(result.points) == 5

    def test_resampled_midpoint_has_valid_bbox(self):
        tri = _polygon_kf(0, points=[[0.0, 0.0], [0.2, 0.0], [0.1, 0.2]])
        quad = _polygon_kf(10, points=[[0.4, 0.0], [0.6, 0.0], [0.6, 0.2], [0.4, 0.2]])
        result = interpolate_polygon(tri, quad, 5)
        # bbox should be derived from the interpolated points.
        assert len(result.bbox) == 4
        assert result.bbox[2] > 0  # width > 0
        assert result.bbox[3] > 0  # height > 0


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — validation
# ---------------------------------------------------------------------------

class TestInterpolatePolygonValidation:
    def test_rejects_ellipse_a(self):
        a = _ellipse_kf(0)
        b = _polygon_kf(10)
        with pytest.raises(ValueError, match="polygon"):
            interpolate_polygon(a, b, 5)

    def test_rejects_ellipse_b(self):
        a = _polygon_kf(0)
        b = _ellipse_kf(10)
        with pytest.raises(ValueError, match="polygon"):
            interpolate_polygon(a, b, 5)

    def test_rejects_empty_points(self):
        a = _polygon_kf(0, points=[], bbox=[0.0, 0.0, 0.1, 0.1])
        b = _polygon_kf(10)
        with pytest.raises(ValueError, match="non-empty"):
            interpolate_polygon(a, b, 5)

    def test_rejects_reversed_order(self):
        a = _polygon_kf(10)
        b = _polygon_kf(0)
        with pytest.raises(ValueError):
            interpolate_polygon(a, b, 5)

    def test_rejects_frame_out_of_range(self):
        a = _polygon_kf(0)
        b = _polygon_kf(10)
        with pytest.raises(ValueError):
            interpolate_polygon(a, b, 15)


# ---------------------------------------------------------------------------
# W6b: interpolate_polygon — purity
# ---------------------------------------------------------------------------

class TestInterpolatePolygonPurity:
    def test_does_not_mutate_a_or_b(self):
        a = _polygon_kf(0)
        b = _polygon_kf(10, points=[[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.7]])
        orig_a_pts = [list(p) for p in a.points]
        orig_b_pts = [list(p) for p in b.points]
        interpolate_polygon(a, b, 5)
        assert a.points == orig_a_pts
        assert b.points == orig_b_pts


# ---------------------------------------------------------------------------
# Resolve polygon interpolation (W7/W8 with polygon)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# expand_px / feather interpolation
# ---------------------------------------------------------------------------

class TestInterpolateExpandPxFeather:
    def test_ellipse_both_expand_px_interpolated(self):
        a = _ellipse_kf(0)
        a.expand_px = 10
        b = _ellipse_kf(10)
        b.expand_px = 20
        result = interpolate_ellipse(a, b, 5)
        assert result.expand_px == 15

    def test_ellipse_one_expand_px_inherits(self):
        a = _ellipse_kf(0)
        a.expand_px = 10
        b = _ellipse_kf(10)
        b.expand_px = None
        result = interpolate_ellipse(a, b, 5)
        assert result.expand_px == 10

    def test_ellipse_both_none_stays_none(self):
        a = _ellipse_kf(0)
        b = _ellipse_kf(10)
        result = interpolate_ellipse(a, b, 5)
        assert result.expand_px is None
        assert result.feather is None

    def test_ellipse_feather_interpolated(self):
        a = _ellipse_kf(0)
        a.feather = 0
        b = _ellipse_kf(10)
        b.feather = 10
        result = interpolate_ellipse(a, b, 5)
        assert result.feather == 5

    def test_polygon_expand_px_interpolated(self):
        a = _polygon_kf(0)
        a.expand_px = 4
        b = _polygon_kf(10, points=[[0.4, 0.0], [0.6, 0.0], [0.6, 0.2], [0.4, 0.2]])
        b.expand_px = 12
        result = interpolate_polygon(a, b, 5)
        assert result.expand_px == 8

    def test_endpoint_preserves_expand_px(self):
        a = _ellipse_kf(0)
        a.expand_px = 7
        a.feather = 3
        b = _ellipse_kf(10)
        b.expand_px = 20
        b.feather = 10
        result_a = interpolate_ellipse(a, b, 0)
        result_b = interpolate_ellipse(a, b, 10)
        assert result_a.expand_px == 7
        assert result_a.feather == 3
        assert result_b.expand_px == 20
        assert result_b.feather == 10


class TestResolveForRenderPolygonInterpolation:
    def test_polygon_pair_within_gap_returns_interpolated(self):
        a = _polygon_kf(10, points=[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]])
        b = _polygon_kf(20, points=[[0.6, 0.0], [0.8, 0.0], [0.8, 0.2], [0.6, 0.2]])
        track = _track(a, b)
        kf, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.INTERPOLATED
        # Midpoint x should be approximately 0.3
        assert abs(kf.bbox[0] - 0.3) < 0.05

    def test_polygon_gap_over_limit_returns_held(self):
        a = _polygon_kf(0)
        b = _polygon_kf(31)
        track = _track(a, b)
        kf, reason = resolve_for_render(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert kf is a


class TestResolveForEditingPolygonInterpolation:
    def test_polygon_pair_within_gap_returns_interpolated(self):
        a = _polygon_kf(10, points=[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]])
        b = _polygon_kf(20, points=[[0.6, 0.0], [0.8, 0.0], [0.8, 0.2], [0.6, 0.2]])
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.INTERPOLATED
        assert abs(kf.bbox[0] - 0.3) < 0.05

    def test_polygon_gap_over_limit_returns_held(self):
        a = _polygon_kf(0)
        b = _polygon_kf(31)
        track = _track(a, b)
        kf, reason = resolve_for_editing(track, 15)
        assert reason == ResolveReason.HELD_FROM_PRIOR
        assert kf is a
