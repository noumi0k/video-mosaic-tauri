/**
 * Unit tests for keyframeResolveDisplay pure helpers.
 *
 * Tests the exact logic used by KeyframeDetailPanel to:
 *  - choose the CSS badge variant (explicit / held / interpolated)
 *  - produce the text label
 *  - format source_detail for compact display
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  resolveReasonBadgeVariant,
  resolveReasonLabel,
  resolveOverlayLabel,
  sourceDetailLabel,
} from "../src/keyframeResolveDisplay.ts";

// ---------------------------------------------------------------------------
// resolveReasonBadgeVariant
// ---------------------------------------------------------------------------

test("badge variant: 'explicit' reason -> 'explicit'", () => {
  assert.equal(resolveReasonBadgeVariant("explicit"), "explicit");
});

test("badge variant: 'interpolated' reason -> 'interpolated'", () => {
  assert.equal(resolveReasonBadgeVariant("interpolated"), "interpolated");
});

test("badge variant: 'held_from_prior' reason -> 'held'", () => {
  assert.equal(resolveReasonBadgeVariant("held_from_prior"), "held");
});

test("badge variant: null reason -> 'held' (safe default)", () => {
  assert.equal(resolveReasonBadgeVariant(null), "held");
});

test("badge variant: undefined reason -> 'held' (safe default)", () => {
  assert.equal(resolveReasonBadgeVariant(undefined), "held");
});

// ---------------------------------------------------------------------------
// resolveReasonLabel
// ---------------------------------------------------------------------------

test("reason label: 'explicit' -> 'explicit'", () => {
  assert.equal(resolveReasonLabel("explicit"), "explicit");
});

test("reason label: 'interpolated' -> 'interpolated'", () => {
  assert.equal(resolveReasonLabel("interpolated"), "interpolated");
});

test("reason label: 'held_from_prior' -> 'held'", () => {
  assert.equal(resolveReasonLabel("held_from_prior"), "held");
});

test("reason label: null -> null", () => {
  assert.equal(resolveReasonLabel(null), null);
});

test("reason label: undefined -> null", () => {
  assert.equal(resolveReasonLabel(undefined), null);
});

// ---------------------------------------------------------------------------
// sourceDetailLabel
// ---------------------------------------------------------------------------

test("source detail: 'detector_accepted' -> 'accepted'", () => {
  assert.equal(sourceDetailLabel("detector_accepted"), "accepted");
});

test("source detail: 'detector_anchored' -> 'anchored'", () => {
  assert.equal(sourceDetailLabel("detector_anchored"), "anchored");
});

test("source detail: null -> null (don't render)", () => {
  assert.equal(sourceDetailLabel(null), null);
});

test("source detail: undefined -> null (don't render)", () => {
  assert.equal(sourceDetailLabel(undefined), null);
});

test("source detail: empty string -> null (don't render)", () => {
  assert.equal(sourceDetailLabel(""), null);
});

test("source detail: unknown string without detector_ prefix -> returned as-is", () => {
  assert.equal(sourceDetailLabel("manual_edit"), "manual_edit");
});

test("source detail: 'detector_' prefix only -> empty string (edge case)", () => {
  // "detector_" with nothing after it → empty string (falsy edge case)
  const result = sourceDetailLabel("detector_");
  assert.equal(result, "");
});

// ---------------------------------------------------------------------------
// resolveOverlayLabel — canvas overlay label composition
// ---------------------------------------------------------------------------

test("overlay label: 'explicit', no source_detail -> 'explicit'", () => {
  assert.equal(resolveOverlayLabel("explicit"), "explicit");
});

test("overlay label: 'held_from_prior', no source_detail -> 'held'", () => {
  assert.equal(resolveOverlayLabel("held_from_prior"), "held");
});

test("overlay label: 'interpolated', no source_detail -> 'interpolated'", () => {
  assert.equal(resolveOverlayLabel("interpolated"), "interpolated");
});

test("overlay label: null reason -> null (don't render)", () => {
  assert.equal(resolveOverlayLabel(null), null);
});

test("overlay label: undefined reason -> null (don't render)", () => {
  assert.equal(resolveOverlayLabel(undefined), null);
});

test("overlay label: 'explicit' + detector_accepted -> 'explicit · accepted'", () => {
  assert.equal(resolveOverlayLabel("explicit", "detector_accepted"), "explicit · accepted");
});

test("overlay label: 'explicit' + detector_anchored -> 'explicit · anchored'", () => {
  assert.equal(resolveOverlayLabel("explicit", "detector_anchored"), "explicit · anchored");
});

test("overlay label: 'held_from_prior' + detector_accepted -> 'held · accepted'", () => {
  assert.equal(resolveOverlayLabel("held_from_prior", "detector_accepted"), "held · accepted");
});

test("overlay label: 'held_from_prior' + null source_detail -> 'held' (legacy-safe)", () => {
  assert.equal(resolveOverlayLabel("held_from_prior", null), "held");
});

test("overlay label: 'held_from_prior' + undefined source_detail -> 'held' (legacy-safe)", () => {
  assert.equal(resolveOverlayLabel("held_from_prior", undefined), "held");
});

test("overlay label: 'interpolated' + any source_detail -> no suffix (interpolated kf has no source_detail)", () => {
  // Interpolated kfs don't carry source_detail; passing one for robustness.
  assert.equal(resolveOverlayLabel("interpolated", "detector_accepted"), "interpolated · accepted");
});

test("overlay label: 'explicit' + empty string source_detail -> 'explicit' (no suffix)", () => {
  // Empty string is falsy → sourceDetailLabel returns null → no suffix.
  assert.equal(resolveOverlayLabel("explicit", ""), "explicit");
});
