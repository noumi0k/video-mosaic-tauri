/**
 * Unit tests for timelineSegmentDisplay pure helpers.
 *
 * Tests the exact logic used by TimelineView to:
 *  - choose the CSS class for a segment bar
 *  - choose the CSS class for a keyframe marker (with source_detail)
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  segmentBarClass,
  kfMarkerClassFull,
} from "../src/timelineSegmentDisplay.ts";

// ---------------------------------------------------------------------------
// segmentBarClass
// ---------------------------------------------------------------------------

test("segmentBarClass: 'confirmed' -> '--confirmed'", () => {
  assert.equal(segmentBarClass("confirmed"), "nle-tl-seg--confirmed");
});

test("segmentBarClass: 'held' -> '--held'", () => {
  assert.equal(segmentBarClass("held"), "nle-tl-seg--held");
});

test("segmentBarClass: 'uncertain' -> '--uncertain'", () => {
  assert.equal(segmentBarClass("uncertain"), "nle-tl-seg--uncertain");
});

test("segmentBarClass: 'interpolated' -> '--interpolated'", () => {
  assert.equal(segmentBarClass("interpolated"), "nle-tl-seg--interpolated");
});

test("segmentBarClass: 'predicted' -> '--predicted'", () => {
  assert.equal(segmentBarClass("predicted"), "nle-tl-seg--predicted");
});

test("segmentBarClass: unknown state -> '--confirmed' (safe fallback)", () => {
  assert.equal(segmentBarClass("bogus_state"), "nle-tl-seg--confirmed");
});

test("segmentBarClass: empty string -> '--confirmed' (safe fallback)", () => {
  assert.equal(segmentBarClass(""), "nle-tl-seg--confirmed");
});

// ---------------------------------------------------------------------------
// kfMarkerClassFull
// ---------------------------------------------------------------------------

test("kfMarkerClassFull: manual source -> '--manual'", () => {
  assert.equal(kfMarkerClassFull("manual"), "nle-tl-row__marker--manual");
});

test("kfMarkerClassFull: manual with null source_detail -> '--manual'", () => {
  assert.equal(kfMarkerClassFull("manual", null), "nle-tl-row__marker--manual");
});

test("kfMarkerClassFull: detector, no source_detail -> '--auto'", () => {
  assert.equal(kfMarkerClassFull("detector"), "nle-tl-row__marker--auto");
});

test("kfMarkerClassFull: detector + detector_accepted -> '--auto'", () => {
  assert.equal(kfMarkerClassFull("detector", "detector_accepted"), "nle-tl-row__marker--auto");
});

test("kfMarkerClassFull: detector + detector_anchored -> '--auto-anchored'", () => {
  assert.equal(kfMarkerClassFull("detector", "detector_anchored"), "nle-tl-row__marker--auto-anchored");
});

test("kfMarkerClassFull: 'auto' source alias -> '--auto'", () => {
  assert.equal(kfMarkerClassFull("auto"), "nle-tl-row__marker--auto");
});

test("kfMarkerClassFull: 'auto' + detector_anchored -> '--auto-anchored'", () => {
  assert.equal(kfMarkerClassFull("auto", "detector_anchored"), "nle-tl-row__marker--auto-anchored");
});

test("kfMarkerClassFull: interpolated source -> '--interpolated'", () => {
  assert.equal(kfMarkerClassFull("interpolated"), "nle-tl-row__marker--interpolated");
});

test("kfMarkerClassFull: predicted source -> '--predicted'", () => {
  assert.equal(kfMarkerClassFull("predicted"), "nle-tl-row__marker--predicted");
});

test("kfMarkerClassFull: unknown source -> '' (no class)", () => {
  assert.equal(kfMarkerClassFull("unknown_source"), "");
});

test("kfMarkerClassFull: detector + null source_detail -> '--auto' (not anchored)", () => {
  assert.equal(kfMarkerClassFull("detector", null), "nle-tl-row__marker--auto");
});

test("kfMarkerClassFull: detector + undefined source_detail -> '--auto' (not anchored)", () => {
  assert.equal(kfMarkerClassFull("detector", undefined), "nle-tl-row__marker--auto");
});
