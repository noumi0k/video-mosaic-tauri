import test from "node:test";
import assert from "node:assert/strict";

import {
  findExplicitKeyframe,
  findExplicitKeyframeSummary,
  planCommitMutation,
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
