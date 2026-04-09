/**
 * Tests for source_detail and ResolveReason plumbing.
 *
 * Verifies:
 *  - Keyframe type accepts source_detail as optional (undefined / null / string).
 *  - Legacy keyframes without source_detail still work through the resolver.
 *  - source_detail is preserved when Keyframe objects are spread/cloned.
 *  - resolveForEditing preserves source_detail on the returned keyframe.
 *  - Interpolated keyframes have source_detail undefined (not fabricated).
 *  - resolvedReason derivation matches the resolver output for all scenarios.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { resolveForEditing } from "../src/maskShapeResolver.ts";
import type { ResolveReason } from "../src/maskShapeResolver.ts";
import type { Keyframe } from "../src/types.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function kf(
  frame: number,
  overrides: Partial<Keyframe> = {},
): Keyframe {
  return {
    frame_index: frame,
    shape_type: "polygon",
    points: [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
    bbox: [0.1, 0.1, 0.1, 0.1],
    confidence: 1.0,
    source: "manual",
    rotation: 0,
    opacity: 1,
    expand_px: null,
    feather: null,
    is_locked: false,
    contour_points: [],
    ...overrides,
  };
}

function ellipseKf(frame: number, overrides: Partial<Keyframe> = {}): Keyframe {
  return kf(frame, {
    shape_type: "ellipse",
    bbox: [0.1, 0.1, 0.2, 0.2],
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// source_detail type compatibility
// ---------------------------------------------------------------------------

test("source_detail: undefined is valid (legacy keyframe without source_detail)", () => {
  const k = kf(0);  // no source_detail key
  assert.equal(k.source_detail, undefined);
});

test("source_detail: null is valid", () => {
  const k = kf(0, { source_detail: null });
  assert.equal(k.source_detail, null);
});

test("source_detail: string value is valid", () => {
  const k = kf(0, { source_detail: "detector_accepted" });
  assert.equal(k.source_detail, "detector_accepted");
});

test("source_detail: 'detector_anchored' is valid", () => {
  const k = kf(0, { source_detail: "detector_anchored" });
  assert.equal(k.source_detail, "detector_anchored");
});

// ---------------------------------------------------------------------------
// source_detail preserved through resolveForEditing
// ---------------------------------------------------------------------------

test("resolveForEditing: source_detail on explicit kf is preserved in result", () => {
  const k = kf(5, { source_detail: "detector_accepted" });
  const result = resolveForEditing([k], 5);
  assert.equal(result?.reason, "explicit");
  assert.equal(result?.keyframe.source_detail, "detector_accepted");
});

test("resolveForEditing: source_detail=null on kf is preserved (legacy-compatible)", () => {
  const k = kf(5, { source_detail: null });
  const result = resolveForEditing([k], 5);
  assert.equal(result?.reason, "explicit");
  assert.equal(result?.keyframe.source_detail, null);
});

test("resolveForEditing: source_detail absent on legacy kf is preserved (undefined)", () => {
  const k = kf(5);  // no source_detail
  const result = resolveForEditing([k], 5);
  assert.equal(result?.reason, "explicit");
  assert.equal(result?.keyframe.source_detail, undefined);
});

test("resolveForEditing: held_from_prior preserves source_detail from prior kf", () => {
  const k = kf(0, { source_detail: "detector_anchored" });
  const result = resolveForEditing([k], 10);
  assert.equal(result?.reason, "held_from_prior");
  assert.equal(result?.keyframe.source_detail, "detector_anchored");
});

// ---------------------------------------------------------------------------
// Interpolated keyframes have no source_detail (not fabricated)
// ---------------------------------------------------------------------------

test("resolveForEditing: interpolated kf has no source_detail (undefined)", () => {
  const a = ellipseKf(0, { source_detail: "detector_accepted" });
  const b = ellipseKf(10, { source_detail: "detector_accepted" });
  const result = resolveForEditing([a, b], 5);
  assert.equal(result?.reason, "interpolated");
  // Interpolated keyframes are synthetic — source_detail is not carried over.
  assert.equal(result?.keyframe.source_detail, undefined);
});

// ---------------------------------------------------------------------------
// source_detail preserved through object spread (applyKeyframePatchPreview pattern)
// ---------------------------------------------------------------------------

test("spread: source_detail is preserved in object spread (simulates applyKeyframePatchPreview)", () => {
  const original = kf(0, { source_detail: "detector_accepted" });
  const cloned = { ...original, confidence: 0.8 };
  assert.equal(cloned.source_detail, "detector_accepted");
});

test("spread: absent source_detail remains absent after spread", () => {
  const original = kf(0);  // no source_detail
  const cloned = { ...original, confidence: 0.8 };
  assert.equal(cloned.source_detail, undefined);
});

// ---------------------------------------------------------------------------
// resolvedReason derivation pattern (mirrors App.tsx consumer)
// ---------------------------------------------------------------------------

test("resolvedReason: explicit frame gives 'explicit'", () => {
  const result = resolveForEditing([kf(3)], 3);
  const resolvedReason: ResolveReason | null = result?.reason ?? null;
  assert.equal(resolvedReason, "explicit");
});

test("resolvedReason: held editing (after last kf) gives 'held_from_prior'", () => {
  const result = resolveForEditing([kf(0)], 20);
  const resolvedReason: ResolveReason | null = result?.reason ?? null;
  assert.equal(resolvedReason, "held_from_prior");
});

test("resolvedReason: interpolated ellipse gives 'interpolated'", () => {
  const result = resolveForEditing([ellipseKf(0), ellipseKf(10)], 5);
  const resolvedReason: ResolveReason | null = result?.reason ?? null;
  assert.equal(resolvedReason, "interpolated");
});

test("resolvedReason: null when track is empty", () => {
  const result = resolveForEditing([], 5);
  const resolvedReason: ResolveReason | null = result?.reason ?? null;
  assert.equal(resolvedReason, null);
});

test("resolvedReason: null when frame is before first kf", () => {
  const result = resolveForEditing([kf(10)], 5);
  const resolvedReason: ResolveReason | null = result?.reason ?? null;
  assert.equal(resolvedReason, null);
});
