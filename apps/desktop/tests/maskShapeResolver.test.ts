import test from "node:test";
import assert from "node:assert/strict";

import {
  findExplicitKeyframe,
  findExplicitKeyframeSummary,
  interpolateEllipse,
  planCommitMutation,
  resolveForEditing,
  resolveShapeForEditing,
} from "../src/maskShapeResolver.ts";
import type { Keyframe, KeyframeSummary } from "../src/types.ts";

function kf(frame: number, source: string = "manual"): Keyframe {
  return {
    frame_index: frame,
    shape_type: "polygon",
    points: [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
    bbox: [0.1, 0.1, 0.1, 0.1],
    confidence: 1.0,
    source,
    rotation: 0,
    opacity: 1,
    expand_px: null,
    feather: null,
    is_locked: false,
    contour_points: [],
  };
}

function kfSummary(frame: number, source: string = "manual"): KeyframeSummary {
  return { frame_index: frame, source, shape_type: "polygon" };
}

// ---------------------------------------------------------------------------
// resolveShapeForEditing — mirrors backend MaskTrack.resolve_shape_for_editing
// ---------------------------------------------------------------------------

test("resolveShapeForEditing: empty track returns null", () => {
  assert.equal(resolveShapeForEditing([], 5), null);
  assert.equal(resolveShapeForEditing([], 0), null);
});

test("resolveShapeForEditing: before first keyframe returns null", () => {
  const track = [kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 0), null);
  assert.equal(resolveShapeForEditing(track, 9), null);
});

test("resolveShapeForEditing: at first keyframe returns it", () => {
  const track = [kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 10)?.frame_index, 10);
});

test("resolveShapeForEditing: between keyframes returns most recent prior", () => {
  const track = [kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 11)?.frame_index, 10);
  assert.equal(resolveShapeForEditing(track, 15)?.frame_index, 10);
  assert.equal(resolveShapeForEditing(track, 19)?.frame_index, 10);
});

test("resolveShapeForEditing: at last keyframe returns it", () => {
  const track = [kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 20)?.frame_index, 20);
});

test("resolveShapeForEditing: beyond last keyframe still returns last (held editing)", () => {
  const track = [kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 21)?.frame_index, 20);
  assert.equal(resolveShapeForEditing(track, 500)?.frame_index, 20);
});

test("resolveShapeForEditing: single-keyframe track is held indefinitely", () => {
  const track = [kf(0)];
  assert.equal(resolveShapeForEditing(track, 0)?.frame_index, 0);
  assert.equal(resolveShapeForEditing(track, 999)?.frame_index, 0);
});

test("resolveShapeForEditing: works with unsorted input", () => {
  const track = [kf(30), kf(10), kf(20)];
  assert.equal(resolveShapeForEditing(track, 25)?.frame_index, 20);
  assert.equal(resolveShapeForEditing(track, 35)?.frame_index, 30);
  assert.equal(resolveShapeForEditing(track, 5), null);
});

// ---------------------------------------------------------------------------
// findExplicitKeyframe / findExplicitKeyframeSummary
// ---------------------------------------------------------------------------

test("findExplicitKeyframe: returns null when no exact match", () => {
  const track = [kf(10), kf(20)];
  assert.equal(findExplicitKeyframe(track, 15), null);
  assert.equal(findExplicitKeyframe(track, 9), null);
  assert.equal(findExplicitKeyframe(track, 21), null);
  assert.equal(findExplicitKeyframe([], 0), null);
});

test("findExplicitKeyframe: returns the keyframe at exactly that frame", () => {
  const track = [kf(10), kf(20)];
  assert.equal(findExplicitKeyframe(track, 10)?.frame_index, 10);
  assert.equal(findExplicitKeyframe(track, 20)?.frame_index, 20);
});

test("findExplicitKeyframeSummary: returns summary at exact frame", () => {
  const summaries = [kfSummary(10), kfSummary(20)];
  assert.equal(findExplicitKeyframeSummary(summaries, 10)?.frame_index, 10);
  assert.equal(findExplicitKeyframeSummary(summaries, 15), null);
});

// ---------------------------------------------------------------------------
// planCommitMutation — the single source of truth for commit branching
// ---------------------------------------------------------------------------

test("planCommitMutation: empty track is unavailable", () => {
  assert.deepEqual(planCommitMutation([], 5), { kind: "unavailable" });
  assert.deepEqual(planCommitMutation([], 0), { kind: "unavailable" });
});

test("planCommitMutation: before first keyframe is unavailable", () => {
  const track = [kf(10), kf(20)];
  assert.deepEqual(planCommitMutation(track, 9), { kind: "unavailable" });
});

test("planCommitMutation: on an explicit keyframe → update-existing", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 20);
  assert.equal(plan.kind, "update-existing");
  if (plan.kind === "update-existing") {
    assert.equal(plan.frameIndex, 20);
    assert.equal(plan.existing.frame_index, 20);
  }
});

test("planCommitMutation: between keyframes → create-held with prior as base", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 15);
  assert.equal(plan.kind, "create-held");
  if (plan.kind === "create-held") {
    assert.equal(plan.frameIndex, 15);
    assert.equal(plan.base.frame_index, 10);
  }
});

test("planCommitMutation: beyond last keyframe → create-held with last as base", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 100);
  assert.equal(plan.kind, "create-held");
  if (plan.kind === "create-held") {
    assert.equal(plan.frameIndex, 100);
    assert.equal(plan.base.frame_index, 20);
  }
});

test("planCommitMutation: at first keyframe → update-existing (not create-held)", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 10);
  assert.equal(plan.kind, "update-existing");
});

test("planCommitMutation: single-keyframe track → held creation everywhere after first", () => {
  const track = [kf(0)];
  const planAtFirst = planCommitMutation(track, 0);
  assert.equal(planAtFirst.kind, "update-existing");
  const planAfter = planCommitMutation(track, 50);
  assert.equal(planAfter.kind, "create-held");
  if (planAfter.kind === "create-held") {
    assert.equal(planAfter.frameIndex, 50);
    assert.equal(planAfter.base.frame_index, 0);
  }
});

// ---------------------------------------------------------------------------
// Worker A / Worker C invariant: no-keyframe track stays non-editable
// ---------------------------------------------------------------------------

test("invariant: no-keyframe track is never editable at any frame", () => {
  for (const frame of [0, 1, 10, 100, 1000]) {
    assert.equal(resolveShapeForEditing([], frame), null);
    assert.equal(planCommitMutation([], frame).kind, "unavailable");
  }
});

// ---------------------------------------------------------------------------
// Worker A / Worker C invariant: held editing past last KF creates at currentFrame
// (the bug Worker C was supposed to fix; verifies the resolved base is the
// LAST keyframe, not whatever marker the user previously clicked)
// ---------------------------------------------------------------------------

test("invariant: drag at frame 21 with KFs at [10,20] creates at 21 with base=KF20", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 21);
  assert.equal(plan.kind, "create-held");
  if (plan.kind === "create-held") {
    assert.equal(plan.frameIndex, 21);
    assert.equal(plan.base.frame_index, 20);
  }
});

test("invariant: drag at explicit frame 20 with KFs at [10,20] updates F20 (never F10)", () => {
  const track = [kf(10), kf(20)];
  const plan = planCommitMutation(track, 20);
  assert.equal(plan.kind, "update-existing");
  if (plan.kind === "update-existing") {
    assert.equal(plan.frameIndex, 20);
  }
});

// ---------------------------------------------------------------------------
// W9: interpolateEllipse
// ---------------------------------------------------------------------------

function ellipseKf(
  frame: number,
  options: { rotation?: number; bbox?: number[]; confidence?: number; opacity?: number } = {},
): Keyframe {
  const { rotation = 0, bbox = [0.1, 0.1, 0.2, 0.2], confidence = 0.9, opacity = 1.0 } = options;
  const [x1, y1, w, h] = bbox as [number, number, number, number];
  return {
    frame_index: frame,
    shape_type: "ellipse",
    points: [[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]],
    bbox,
    confidence,
    source: "manual",
    rotation,
    opacity,
    expand_px: null,
    feather: null,
    is_locked: false,
    contour_points: [],
  };
}

test("interpolateEllipse: t=0 returns a verbatim", () => {
  const a = ellipseKf(10);
  const b = ellipseKf(20);
  assert.deepEqual(interpolateEllipse(a, b, 10), a);
});

test("interpolateEllipse: t=1 returns b verbatim", () => {
  const a = ellipseKf(10);
  const b = ellipseKf(20);
  assert.deepEqual(interpolateEllipse(a, b, 20), b);
});

test("interpolateEllipse: midpoint interpolates bbox and confidence", () => {
  const a = ellipseKf(0, { bbox: [0.1, 0.1, 0.2, 0.2], confidence: 0.6, opacity: 0.4 });
  const b = ellipseKf(10, { bbox: [0.3, 0.3, 0.4, 0.4], confidence: 1.0, opacity: 0.8 });
  const result = interpolateEllipse(a, b, 5);
  assert.equal(result.frame_index, 5);
  assert.equal(result.shape_type, "ellipse");
  assert.equal(result.source, "detector");
  assert.ok(Math.abs(result.bbox[0]! - 0.2) < 1e-10, "bbox[0] midpoint");
  assert.ok(Math.abs(result.bbox[1]! - 0.2) < 1e-10, "bbox[1] midpoint");
  assert.ok(Math.abs(result.bbox[2]! - 0.3) < 1e-10, "bbox[2] midpoint");
  assert.ok(Math.abs(result.bbox[3]! - 0.3) < 1e-10, "bbox[3] midpoint");
  assert.ok(Math.abs(result.confidence - 0.8) < 1e-10, "confidence midpoint");
  assert.ok(Math.abs(result.opacity - 0.6) < 1e-10, "opacity midpoint");
});

test("interpolateEllipse: rotation straight (no wrap-around)", () => {
  const a = ellipseKf(0, { rotation: 10 });
  const b = ellipseKf(10, { rotation: 30 });
  const result = interpolateEllipse(a, b, 5);
  assert.ok(Math.abs(result.rotation - 20.0) < 1e-10);
});

test("interpolateEllipse: rotation shortest-path wrap-around (350° → 10°)", () => {
  // Shortest path: 350 + 20° = 360° at t=0.5
  const a = ellipseKf(0, { rotation: 350 });
  const b = ellipseKf(10, { rotation: 10 });
  const result = interpolateEllipse(a, b, 5);
  assert.ok(Math.abs(result.rotation - 360.0) < 1e-10, `expected 360, got ${result.rotation}`);
});

test("interpolateEllipse: rotation shortest-path wrap-around (10° → 350°)", () => {
  // Shortest path: 10 − 20° = 0° at t=0.5
  const a = ellipseKf(0, { rotation: 10 });
  const b = ellipseKf(10, { rotation: 350 });
  const result = interpolateEllipse(a, b, 5);
  assert.ok(Math.abs(result.rotation - 0.0) < 1e-10, `expected 0, got ${result.rotation}`);
});

test("interpolateEllipse: throws on non-ellipse keyframe", () => {
  const poly = kf(10);
  const ell = ellipseKf(20);
  assert.throws(() => interpolateEllipse(poly, ell, 15), /ellipse/);
  assert.throws(() => interpolateEllipse(ell, poly, 15), /ellipse/);
});

test("interpolateEllipse: throws when a.frame_index >= b.frame_index", () => {
  const a = ellipseKf(20);
  const b = ellipseKf(10);
  assert.throws(() => interpolateEllipse(a, b, 15));
  assert.throws(() => interpolateEllipse(a, a, 20)); // equal
});

test("interpolateEllipse: throws when frameIdx out of range", () => {
  const a = ellipseKf(10);
  const b = ellipseKf(20);
  assert.throws(() => interpolateEllipse(a, b, 5));
  assert.throws(() => interpolateEllipse(a, b, 25));
});

test("interpolateEllipse: points match interpolated bbox corners", () => {
  const a = ellipseKf(0, { bbox: [0.0, 0.0, 0.2, 0.2] });
  const b = ellipseKf(10, { bbox: [0.2, 0.2, 0.4, 0.4] });
  const result = interpolateEllipse(a, b, 5);
  // midpoint bbox = [0.1, 0.1, 0.3, 0.3]
  const [x1, y1, w, h] = [0.1, 0.1, 0.3, 0.3];
  const expected = [[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]];
  assert.equal(result.points.length, 4);
  for (let i = 0; i < 4; i++) {
    assert.ok(Math.abs(result.points[i]![0]! - expected[i]![0]!) < 1e-10, `pt[${i}][0]`);
    assert.ok(Math.abs(result.points[i]![1]! - expected[i]![1]!) < 1e-10, `pt[${i}][1]`);
  }
});

// ---------------------------------------------------------------------------
// W9: resolveForEditing
// ---------------------------------------------------------------------------

test("resolveForEditing: empty track returns null", () => {
  assert.equal(resolveForEditing([], 5), null);
  assert.equal(resolveForEditing([], 0), null);
});

test("resolveForEditing: before first keyframe returns null", () => {
  assert.equal(resolveForEditing([kf(10)], 0), null);
  assert.equal(resolveForEditing([kf(10), kf(20)], 9), null);
});

test("resolveForEditing: at explicit polygon keyframe → explicit", () => {
  const result = resolveForEditing([kf(10), kf(20)], 10);
  assert.equal(result?.reason, "explicit");
  assert.equal(result?.keyframe.frame_index, 10);
});

test("resolveForEditing: between polygon keyframes → held_from_prior", () => {
  const result = resolveForEditing([kf(10), kf(20)], 15);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 10);
});

test("resolveForEditing: after last keyframe → held_from_prior (no segment gate)", () => {
  const result = resolveForEditing([kf(10), kf(20)], 100);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 20);
});

test("resolveForEditing: at last keyframe → explicit", () => {
  const result = resolveForEditing([kf(10), kf(20)], 20);
  assert.equal(result?.reason, "explicit");
  assert.equal(result?.keyframe.frame_index, 20);
});

test("resolveForEditing: between ellipse kfs gap=30 (at limit) → interpolated", () => {
  const a = ellipseKf(0);
  const b = ellipseKf(30); // gap = 30, exactly at limit
  const result = resolveForEditing([a, b], 15);
  assert.equal(result?.reason, "interpolated");
  assert.equal(result?.keyframe.frame_index, 15);
  assert.equal(result?.keyframe.shape_type, "ellipse");
});

test("resolveForEditing: between ellipse kfs gap=31 (over limit) → held_from_prior", () => {
  const a = ellipseKf(0);
  const b = ellipseKf(31); // gap = 31, one over limit
  const result = resolveForEditing([a, b], 15);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 0);
});

test("resolveForEditing: between mixed-type kfs polygon/ellipse → held_from_prior", () => {
  const result = resolveForEditing([kf(0), ellipseKf(20)], 10);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 0);
});

test("resolveForEditing: between mixed-type kfs ellipse/polygon → held_from_prior", () => {
  const result = resolveForEditing([ellipseKf(0), kf(20)], 10);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 0);
});

test("resolveForEditing: single ellipse keyframe held after it", () => {
  const result = resolveForEditing([ellipseKf(5)], 100);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.frame_index, 5);
});

test("resolveForEditing: handles unsorted input", () => {
  // Unsorted: [20, 0] — should sort to [0, 20] and interpolate at 10
  const a = ellipseKf(20);
  const b = ellipseKf(0);
  const result = resolveForEditing([a, b], 10);
  assert.equal(result?.reason, "interpolated");
  assert.equal(result?.keyframe.frame_index, 10);
});

test("resolveForEditing: interpolated kf has correct source", () => {
  const result = resolveForEditing([ellipseKf(0), ellipseKf(10)], 5);
  assert.equal(result?.reason, "interpolated");
  assert.equal(result?.keyframe.source, "detector");
});

// ---------------------------------------------------------------------------
// W9 parity: resolveForEditing vs resolveShapeForEditing (polygon tracks)
// ---------------------------------------------------------------------------

test("parity: resolveForEditing frame_index matches resolveShapeForEditing for polygon track", () => {
  const track = [kf(10), kf(20), kf(30)];
  for (const frame of [9, 10, 15, 20, 25, 30, 35, 100]) {
    const newResult = resolveForEditing(track, frame);
    const oldResult = resolveShapeForEditing(track, frame);
    if (oldResult === null) {
      assert.equal(newResult, null, `frame ${frame}: expected null`);
    } else {
      assert.equal(
        newResult?.keyframe.frame_index,
        oldResult.frame_index,
        `frame ${frame}: frame_index mismatch`,
      );
    }
  }
});

// ---------------------------------------------------------------------------
// App.tsx caller integration: verifies the exact consumption pattern used in
// App.tsx after switching from resolveShapeForEditing to resolveForEditing.
//
// Pattern used in App.tsx:
//   const _resolved = resolveForEditing(keyframes, currentFrame);
//   const resolvedKeyframeDocument = _resolved?.keyframe ?? null;
//   const resolvedReason = _resolved?.reason ?? null;
//   const displayedKeyframeDocument = previewOverride ?? resolvedKeyframeDocument;
// ---------------------------------------------------------------------------

test("caller: explicit frame -> reason 'explicit', kf is the exact keyframe", () => {
  const result = resolveForEditing([kf(5), kf(10)], 5);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  assert.equal(resolvedReason, "explicit");
  assert.equal(resolvedKeyframeDocument?.frame_index, 5);
});

test("caller: between ellipse kfs (gap ≤ 30) -> reason 'interpolated'", () => {
  const result = resolveForEditing([ellipseKf(0), ellipseKf(10)], 5);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  assert.equal(resolvedReason, "interpolated");
  assert.ok(resolvedKeyframeDocument !== null);
  // Interpolated frame_index must equal the requested frame.
  assert.equal(resolvedKeyframeDocument?.frame_index, 5);
});

test("caller: after last kf -> reason 'held_from_prior', kf is the last kf", () => {
  const result = resolveForEditing([kf(0), kf(8)], 20);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  assert.equal(resolvedReason, "held_from_prior");
  assert.equal(resolvedKeyframeDocument?.frame_index, 8);
});

test("caller: empty track -> resolvedKeyframeDocument null, resolvedReason null", () => {
  const result = resolveForEditing([], 5);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  assert.equal(resolvedKeyframeDocument, null);
  assert.equal(resolvedReason, null);
});

test("caller: before first kf -> both null", () => {
  const result = resolveForEditing([kf(10)], 5);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  assert.equal(resolvedKeyframeDocument, null);
  assert.equal(resolvedReason, null);
});

test("caller: preview override replaces displayedKeyframeDocument; resolvedReason is unchanged", () => {
  const result = resolveForEditing([kf(0)], 5);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const resolvedReason = result?.reason ?? null;
  // Simulate canvas drag: previewKeyframeOverride is set.
  const previewOverride: typeof resolvedKeyframeDocument = kf(99);
  const displayedKeyframeDocument = previewOverride ?? resolvedKeyframeDocument;
  // The override replaces what is displayed…
  assert.equal(displayedKeyframeDocument?.frame_index, 99);
  // …but the reason for the underlying frame is still available.
  assert.equal(resolvedReason, "held_from_prior");
});

test("caller: no preview override -> displayedKeyframeDocument equals resolvedKeyframeDocument", () => {
  const result = resolveForEditing([kf(0)], 0);
  const resolvedKeyframeDocument = result?.keyframe ?? null;
  const previewOverride: typeof resolvedKeyframeDocument = null;
  const displayedKeyframeDocument = previewOverride ?? resolvedKeyframeDocument;
  assert.equal(displayedKeyframeDocument?.frame_index, 0);
  assert.equal(result?.reason, "explicit");
});

// ---------------------------------------------------------------------------
// planCommitMutation × resolveForEditing consistency (post-cleanup)
//
// After the cleanup, planCommitMutation uses resolveForEditing internally so
// CommitPlan.base is always consistent with what the display shows.
// ---------------------------------------------------------------------------

test("planCommitMutation: interpolated ellipse frame → create-held, base is the interpolated kf", () => {
  // Two ellipse kfs at 0 and 10, gap = 10 ≤ 30 → interpolated
  const track = [ellipseKf(0), ellipseKf(10)];
  const plan = planCommitMutation(track, 5);
  assert.equal(plan.kind, "create-held");
  if (plan.kind !== "create-held") return;
  assert.equal(plan.frameIndex, 5);
  // base must match what resolveForEditing shows (the interpolated kf at frame 5)
  assert.equal(plan.base.frame_index, 5);
  assert.equal(plan.base.shape_type, "ellipse");
  // Verify the display resolver agrees
  const display = resolveForEditing(track, 5);
  assert.equal(display?.reason, "interpolated");
  assert.equal(display?.keyframe.frame_index, plan.base.frame_index);
});

test("planCommitMutation: over-gap ellipse frame (gap > 30) → create-held, base is the prior kf", () => {
  // Two ellipse kfs at 0 and 32, gap = 32 > 30 → held_from_prior
  const track = [ellipseKf(0), ellipseKf(32)];
  const plan = planCommitMutation(track, 16);
  assert.equal(plan.kind, "create-held");
  if (plan.kind !== "create-held") return;
  assert.equal(plan.frameIndex, 16);
  // base must be the prior kf (frame 0), not the next kf
  assert.equal(plan.base.frame_index, 0);
  // Verify the display resolver agrees
  const display = resolveForEditing(track, 16);
  assert.equal(display?.reason, "held_from_prior");
  assert.equal(display?.keyframe.frame_index, plan.base.frame_index);
});

test("planCommitMutation: after last ellipse kf → create-held, base consistent with display", () => {
  const track = [ellipseKf(0), ellipseKf(10)];
  const plan = planCommitMutation(track, 50);
  assert.equal(plan.kind, "create-held");
  if (plan.kind !== "create-held") return;
  assert.equal(plan.base.frame_index, 10); // last kf
  const display = resolveForEditing(track, 50);
  assert.equal(display?.reason, "held_from_prior");
  assert.equal(display?.keyframe.frame_index, plan.base.frame_index);
});

test("planCommitMutation: explicit ellipse kf still returns update-existing", () => {
  const track = [ellipseKf(0), ellipseKf(10)];
  const plan = planCommitMutation(track, 10);
  assert.equal(plan.kind, "update-existing");
  if (plan.kind === "update-existing") {
    assert.equal(plan.frameIndex, 10);
  }
  const display = resolveForEditing(track, 10);
  assert.equal(display?.reason, "explicit");
});

test("planCommitMutation: base.frame_index always matches display resolver frame_index", () => {
  // Exhaustive check across polygon, ellipse-held, ellipse-interpolated frames
  const polygonTrack = [kf(0), kf(20)];
  const ellipseTrackNarrow = [ellipseKf(0), ellipseKf(10)];
  const ellipseTrackWide = [ellipseKf(0), ellipseKf(50)];

  const cases: Array<{ track: Keyframe[]; frame: number }> = [
    { track: polygonTrack, frame: 10 },       // held polygon
    { track: polygonTrack, frame: 25 },       // held past last
    { track: ellipseTrackNarrow, frame: 5 },  // interpolated
    { track: ellipseTrackNarrow, frame: 15 }, // held past last
    { track: ellipseTrackWide, frame: 25 },   // gap>30 → held
  ];
  for (const { track, frame } of cases) {
    const plan = planCommitMutation(track, frame);
    const display = resolveForEditing(track, frame);
    if (plan.kind === "create-held" && display !== null) {
      assert.equal(
        plan.base.frame_index,
        display.keyframe.frame_index,
        `frame ${frame}: plan.base.frame_index (${plan.base.frame_index}) !== display.keyframe.frame_index (${display.keyframe.frame_index})`,
      );
    }
  }
});
