import type { Keyframe, KeyframeShapeType, KeyframeSummary, MaskSegment, MaskTrack } from "./types";

// Mirrors backend _INTERPOLATE_MAX_GAP / _FRAME_GAP_REJECT
const _INTERPOLATE_MAX_GAP = 30;

/** Minimum polygon vertex count for interpolation. */
const _POLYGON_MIN_VERTICES = 3;

/**
 * Mirrors backend ResolveReason enum.
 * "explicit"       — frame_index has an exact keyframe entry.
 * "interpolated"   — frame is between two same-type keyframes with gap ≤ 30.
 * "held_from_prior" — no exact match; shape is held from the preceding keyframe.
 */
export type ResolveReason = "explicit" | "interpolated" | "held_from_prior";

const _RENDERABLE_SEGMENT_STATES = new Set<MaskSegment["state"]>([
  "confirmed",
  "held",
  "predicted",
  "interpolated",
  "uncertain",
  "active",
  "detected",
]);

/**
 * Return the most recent keyframe at or before frame_index.
 *
 * Mirrors the backend's MaskTrack.resolve_shape_for_editing semantics:
 * - Returns null when the track has no keyframes.
 * - Returns null when frame_index is before the track's first keyframe
 *   (the track has not "started" yet).
 * - Otherwise returns the keyframe with the largest frame_index <= frame_index.
 *
 * Robust to unsorted input — does not assume the keyframe list is sorted.
 *
 * Used for both display ("what shape is visible at this frame") and as the
 * base when creating a new keyframe via held editing.
 */
export function resolveShapeForEditing(
  keyframes: readonly Keyframe[],
  frameIndex: number,
): Keyframe | null {
  if (keyframes.length === 0) return null;
  let resolved: Keyframe | null = null;
  for (const kf of keyframes) {
    if (kf.frame_index <= frameIndex) {
      if (!resolved || kf.frame_index > resolved.frame_index) {
        resolved = kf;
      }
    }
  }
  return resolved;
}

/**
 * Find an explicit keyframe at exactly frame_index. Returns null if none.
 */
export function findExplicitKeyframe(
  keyframes: readonly Keyframe[],
  frameIndex: number,
): Keyframe | null {
  for (const kf of keyframes) {
    if (kf.frame_index === frameIndex) return kf;
  }
  return null;
}

/**
 * Find an explicit keyframe summary at exactly frame_index. Returns null if none.
 */
export function findExplicitKeyframeSummary(
  keyframes: readonly KeyframeSummary[],
  frameIndex: number,
): KeyframeSummary | null {
  for (const kf of keyframes) {
    if (kf.frame_index === frameIndex) return kf;
  }
  return null;
}

/**
 * The mutation that should be issued when committing an edit at the current
 * playhead frame.
 *
 * - "update-existing": currentFrame coincides with an explicit keyframe →
 *   commit becomes an update-keyframe call against that frame.
 * - "create-held": currentFrame has no explicit keyframe but a prior keyframe
 *   resolves a held shape → commit becomes a create-keyframe call at
 *   currentFrame, using the resolved keyframe as the shape base.
 * - "unavailable": the track has no keyframes (or currentFrame is before the
 *   first keyframe) — no shape exists to display or edit, commit must abort.
 */
export type CommitPlan =
  | { kind: "update-existing"; frameIndex: number; existing: Keyframe }
  | { kind: "create-held"; frameIndex: number; base: Keyframe }
  | { kind: "unavailable" };

/**
 * Decide what mutation to issue for an edit committed at currentFrame.
 *
 * The single source of truth that drives:
 * - whether the canvas/inspector are editable (kind !== "unavailable")
 * - whether the inspector shows EDIT-explicit, HELD, or NEW
 * - whether commit calls update-keyframe or create-keyframe
 *
 * `selectedKeyframeFrame` (the sticky timeline marker) intentionally does NOT
 * influence this decision — once the playhead moves, edits target the new
 * playhead frame regardless of which marker is highlighted.
 *
 * Uses resolveForEditing so that `base` reflects the same keyframe the
 * display and inspector are showing — including interpolated shapes.
 * Both "held" and "interpolated" frames produce `create-held`: committing
 * either materialises a new explicit keyframe at currentFrame.
 */
export function planCommitMutation(
  keyframes: readonly Keyframe[],
  currentFrame: number,
): CommitPlan {
  const explicit = findExplicitKeyframe(keyframes, currentFrame);
  if (explicit !== null) {
    return { kind: "update-existing", frameIndex: currentFrame, existing: explicit };
  }
  const resolved = resolveForEditing(keyframes, currentFrame);
  if (resolved !== null) {
    return { kind: "create-held", frameIndex: currentFrame, base: resolved.keyframe };
  }
  return { kind: "unavailable" };
}

// ---------------------------------------------------------------------------
// W9: resolveForEditing — mirrors backend resolve_for_editing (W8)
// ---------------------------------------------------------------------------

function _lerp(a: number, b: number, t: number): number {
  return a + t * (b - a);
}

function _lerpRotation(a: number, b: number, t: number): number {
  // Use double-modulo to handle JS remainder semantics (% can return negative).
  const diff = (((b - a) + 180.0) % 360.0 + 360.0) % 360.0 - 180.0;
  return a + t * diff;
}

function _buildInterpolatedKf(
  frameIndex: number,
  shapeType: KeyframeShapeType,
  bbox: number[],
  rotation: number,
  confidence: number,
  opacity: number,
): Keyframe {
  const [x1, y1, w, h] = bbox as [number, number, number, number];
  return {
    frame_index: frameIndex,
    shape_type: shapeType,
    points: [[x1, y1], [x1 + w, y1], [x1 + w, y1 + h], [x1, y1 + h]],
    bbox: [...bbox],
    confidence,
    source: "detector",
    rotation,
    opacity,
    expand_px: null,
    feather: null,
    is_locked: false,
    contour_points: [],
  };
}

/**
 * Linearly interpolate between two ellipse keyframes at frameIdx.
 *
 * Mirrors backend interpolate_ellipse (W6):
 * - Raises if either keyframe is not ellipse.
 * - Raises if a.frame_index >= b.frame_index.
 * - Raises if frameIdx is outside [a.frame_index, b.frame_index].
 * - At t=0 returns a verbatim; at t=1 returns b verbatim (avoids float artefacts).
 * - Rotation uses shortest-path interpolation.
 */
export function interpolateEllipse(a: Keyframe, b: Keyframe, frameIdx: number): Keyframe {
  if (a.shape_type !== "ellipse" || b.shape_type !== "ellipse") {
    throw new Error("interpolateEllipse: both keyframes must be ellipse");
  }
  if (a.frame_index >= b.frame_index) {
    throw new Error("interpolateEllipse: a.frame_index must be < b.frame_index");
  }
  if (frameIdx < a.frame_index || frameIdx > b.frame_index) {
    throw new Error("interpolateEllipse: frameIdx out of range");
  }
  const span = b.frame_index - a.frame_index;
  const t = (frameIdx - a.frame_index) / span;
  if (t === 0.0) return { ...a };
  if (t === 1.0) return { ...b };
  const [ax1, ay1, aw, ah] = a.bbox as [number, number, number, number];
  const [bx1, by1, bw, bh] = b.bbox as [number, number, number, number];
  const bbox = [_lerp(ax1, bx1, t), _lerp(ay1, by1, t), _lerp(aw, bw, t), _lerp(ah, bh, t)];
  const rotation = _lerpRotation(a.rotation, b.rotation, t);
  const confidence = _lerp(a.confidence, b.confidence, t);
  const opacity = _lerp(a.opacity, b.opacity, t);
  return _buildInterpolatedKf(frameIdx, "ellipse", bbox, rotation, confidence, opacity);
}

// ---------------------------------------------------------------------------
// W6b: interpolatePolygon — mirrors backend interpolate_polygon
// ---------------------------------------------------------------------------

function _cumulativeArcLengths(points: number[][]): number[] {
  const n = points.length;
  const lengths = [0.0];
  for (let i = 1; i < n; i++) {
    const dx = points[i]![0]! - points[i - 1]![0]!;
    const dy = points[i]![1]! - points[i - 1]![1]!;
    lengths.push(lengths[lengths.length - 1]! + Math.hypot(dx, dy));
  }
  const dx = points[0]![0]! - points[n - 1]![0]!;
  const dy = points[0]![1]! - points[n - 1]![1]!;
  lengths.push(lengths[lengths.length - 1]! + Math.hypot(dx, dy));
  return lengths;
}

function _resamplePolygon(points: number[][], targetCount: number): number[][] {
  if (points.length < 2 || targetCount < _POLYGON_MIN_VERTICES) return points.map((p) => [...p]);
  if (points.length === targetCount) return points.map((p) => [...p]);

  const cum = _cumulativeArcLengths(points);
  const totalLen = cum[cum.length - 1]!;
  if (totalLen < 1e-9) return Array.from({ length: targetCount }, () => [...points[0]!]);

  const step = totalLen / targetCount;
  const n = points.length;
  const closed = [...points.map((p) => [...p]), [...points[0]!]];
  const result: number[][] = [];
  let segIdx = 0;

  for (let i = 0; i < targetCount; i++) {
    const targetLen = i * step;
    while (segIdx < n && cum[segIdx + 1]! < targetLen) segIdx++;
    if (segIdx >= n) segIdx = n - 1;

    const segStartLen = cum[segIdx]!;
    const segEndLen = cum[segIdx + 1]!;
    const segSpan = segEndLen - segStartLen;
    const localT = segSpan < 1e-12 ? 0.0 : (targetLen - segStartLen) / segSpan;

    result.push([
      closed[segIdx]![0]! + (closed[segIdx + 1]![0]! - closed[segIdx]![0]!) * localT,
      closed[segIdx]![1]! + (closed[segIdx + 1]![1]! - closed[segIdx]![1]!) * localT,
    ]);
  }
  return result;
}

function _alignPolygonStart(pointsA: number[][], pointsB: number[][]): number[][] {
  const n = pointsA.length;
  if (n !== pointsB.length || n === 0) return pointsB.map((p) => [...p]);

  let bestOffset = 0;
  let bestDist = Infinity;
  for (let offset = 0; offset < n; offset++) {
    let total = 0.0;
    for (let i = 0; i < n; i++) {
      const j = (i + offset) % n;
      const dx = pointsA[i]![0]! - pointsB[j]![0]!;
      const dy = pointsA[i]![1]! - pointsB[j]![1]!;
      total += dx * dx + dy * dy;
    }
    if (total < bestDist) {
      bestDist = total;
      bestOffset = offset;
    }
  }
  if (bestOffset === 0) return pointsB.map((p) => [...p]);
  const rotated = [...pointsB.slice(bestOffset), ...pointsB.slice(0, bestOffset)];
  return rotated.map((p) => [...p]);
}

function _preparePolygonPair(
  pointsA: number[][],
  pointsB: number[][],
): [number[][], number[][]] {
  if (!pointsA.length || !pointsB.length) {
    return [pointsA.map((p) => [...p]), pointsB.map((p) => [...p])];
  }
  const target = Math.max(pointsA.length, pointsB.length);
  const resampledA = _resamplePolygon(pointsA, target);
  const resampledB = _resamplePolygon(pointsB, target);
  const alignedB = _alignPolygonStart(resampledA, resampledB);
  return [resampledA, alignedB];
}

function _bboxFromPoints(points: number[][]): number[] {
  const xs = points.map((p) => p[0]!);
  const ys = points.map((p) => p[1]!);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return [minX, minY, Math.max(...xs) - minX, Math.max(...ys) - minY];
}

/**
 * Linearly interpolate between two polygon keyframes at frameIdx.
 *
 * Mirrors backend interpolate_polygon (W6b):
 * - Resamples both polygons to equal vertex counts.
 * - Aligns start vertices to minimise twist.
 * - Per-vertex linear interpolation.
 * - bbox derived from interpolated points.
 */
export function interpolatePolygon(a: Keyframe, b: Keyframe, frameIdx: number): Keyframe {
  if (a.shape_type !== "polygon" || b.shape_type !== "polygon") {
    throw new Error("interpolatePolygon: both keyframes must be polygon");
  }
  if (!a.points.length || !b.points.length) {
    throw new Error("interpolatePolygon: both keyframes must have non-empty points");
  }
  if (a.frame_index >= b.frame_index) {
    throw new Error("interpolatePolygon: a.frame_index must be < b.frame_index");
  }
  if (frameIdx < a.frame_index || frameIdx > b.frame_index) {
    throw new Error("interpolatePolygon: frameIdx out of range");
  }
  const span = b.frame_index - a.frame_index;
  const t = (frameIdx - a.frame_index) / span;
  if (t === 0.0) return { ...a, points: a.points.map((p) => [...p]), bbox: [...a.bbox] };
  if (t === 1.0) return { ...b, points: b.points.map((p) => [...p]), bbox: [...b.bbox] };

  const [alignedA, alignedB] = _preparePolygonPair(a.points, b.points);
  const interpPoints = alignedA.map((pa, i) => [
    _lerp(pa[0]!, alignedB[i]![0]!, t),
    _lerp(pa[1]!, alignedB[i]![1]!, t),
  ]);
  const interpBbox = _bboxFromPoints(interpPoints);

  return {
    frame_index: frameIdx,
    shape_type: "polygon",
    points: interpPoints,
    bbox: interpBbox,
    confidence: _lerp(a.confidence, b.confidence, t),
    source: "detector",
    rotation: _lerpRotation(a.rotation, b.rotation, t),
    opacity: _lerp(a.opacity, b.opacity, t),
    expand_px: null,
    feather: null,
    is_locked: false,
    contour_points: [],
  };
}

/**
 * Return the resolved keyframe and reason for a given frame during editing.
 *
 * Mirrors backend resolve_for_editing (W8):
 * - Returns null for empty track or frameIndex before first keyframe.
 * - Returns { reason: "explicit" } if an exact keyframe exists at frameIndex.
 * - Returns { reason: "interpolated" } if frameIndex lies between two same-type
 *   keyframes (ellipse or polygon) whose gap is ≤ _INTERPOLATE_MAX_GAP (30 frames).
 * - Returns { reason: "held_from_prior" } otherwise, including frames beyond the
 *   last keyframe (unlike resolve_for_render, no segment gate is applied here).
 *
 * Robust to unsorted input.
 */
export function resolveForEditing(
  keyframes: readonly Keyframe[],
  frameIndex: number,
): { keyframe: Keyframe; reason: ResolveReason } | null {
  if (keyframes.length === 0) return null;
  const sorted = [...keyframes].sort((a, b) => a.frame_index - b.frame_index);
  if (frameIndex < sorted[0]!.frame_index) return null;

  let priorKf: Keyframe | null = null;
  let nextKf: Keyframe | null = null;

  for (const kf of sorted) {
    if (kf.frame_index === frameIndex) {
      return { keyframe: kf, reason: "explicit" };
    }
    if (kf.frame_index < frameIndex) {
      priorKf = kf;
    } else if (nextKf === null) {
      nextKf = kf;
      break;
    }
  }

  // priorKf is non-null: frameIndex >= sorted[0].frame_index and no exact match,
  // so at least one keyframe is strictly before frameIndex.
  const prior = priorKf!;

  if (
    nextKf !== null &&
    prior.shape_type === nextKf.shape_type &&
    nextKf.frame_index - prior.frame_index <= _INTERPOLATE_MAX_GAP
  ) {
    if (prior.shape_type === "ellipse") {
      return { keyframe: interpolateEllipse(prior, nextKf, frameIndex), reason: "interpolated" };
    }
    if (
      prior.shape_type === "polygon" &&
      prior.points.length >= _POLYGON_MIN_VERTICES &&
      nextKf.points.length >= _POLYGON_MIN_VERTICES
    ) {
      return { keyframe: interpolatePolygon(prior, nextKf, frameIndex), reason: "interpolated" };
    }
  }

  return { keyframe: prior, reason: "held_from_prior" };
}

function isRenderableSegment(segment: MaskSegment): boolean {
  return _RENDERABLE_SEGMENT_STATES.has(segment.state);
}

function renderSegments(track: MaskTrack): MaskSegment[] {
  const explicitSegments = track.segments.filter(isRenderableSegment);
  if (explicitSegments.length > 0) {
    if (track.keyframes.length > 0) {
      const firstFrame = track.keyframes[0]!.frame_index;
      const lastFrame = track.keyframes[track.keyframes.length - 1]!.frame_index;
      const keyframeSpanIsCovered = explicitSegments.some(
        (segment) => segment.start_frame <= firstFrame && segment.end_frame >= lastFrame,
      );
      if (!keyframeSpanIsCovered) {
        const state: MaskSegment["state"] = track.keyframes.some((kf) => kf.source === "manual")
          ? "confirmed"
          : "detected";
        return [...explicitSegments, { start_frame: firstFrame, end_frame: lastFrame, state }].sort(
          (a, b) => (a.start_frame - b.start_frame) || (a.end_frame - b.end_frame),
        );
      }
    }
    return explicitSegments;
  }

  if (track.keyframes.length === 0) return [];

  const firstFrame = track.keyframes[0]!.frame_index;
  const lastFrame = track.keyframes[track.keyframes.length - 1]!.frame_index;
  const state: MaskSegment["state"] = track.keyframes.some((kf) => kf.source === "manual")
    ? "confirmed"
    : "detected";
  return [{ start_frame: firstFrame, end_frame: lastFrame, state }];
}

function frameIsRenderable(track: MaskTrack, frameIndex: number): boolean {
  return renderSegments(track).some(
    (segment) => segment.start_frame <= frameIndex && frameIndex <= segment.end_frame,
  );
}

export function resolveForRender(
  track: MaskTrack,
  frameIndex: number,
): { keyframe: Keyframe; reason: ResolveReason } | null {
  if (!frameIsRenderable(track, frameIndex)) return null;

  const sorted = [...track.keyframes].sort((a, b) => a.frame_index - b.frame_index);
  let priorKf: Keyframe | null = null;
  let nextKf: Keyframe | null = null;

  for (const kf of sorted) {
    if (kf.frame_index < frameIndex) {
      priorKf = kf;
    } else if (kf.frame_index === frameIndex) {
      return { keyframe: kf, reason: "explicit" };
    } else {
      nextKf = kf;
      break;
    }
  }

  if (priorKf === null) return null;

  if (
    nextKf !== null &&
    priorKf.shape_type === nextKf.shape_type &&
    nextKf.frame_index - priorKf.frame_index <= _INTERPOLATE_MAX_GAP
  ) {
    if (priorKf.shape_type === "ellipse") {
      return { keyframe: interpolateEllipse(priorKf, nextKf, frameIndex), reason: "interpolated" };
    }
    if (
      priorKf.shape_type === "polygon" &&
      priorKf.points.length >= _POLYGON_MIN_VERTICES &&
      nextKf.points.length >= _POLYGON_MIN_VERTICES
    ) {
      return { keyframe: interpolatePolygon(priorKf, nextKf, frameIndex), reason: "interpolated" };
    }
  }

  return { keyframe: priorKf, reason: "held_from_prior" };
}
