import type { Keyframe, KeyframeShapeType, KeyframeSummary } from "./types";

// Mirrors backend _INTERPOLATE_MAX_GAP / _FRAME_GAP_REJECT
const _INTERPOLATE_MAX_GAP = 30;

/**
 * Mirrors backend ResolveReason enum.
 * "explicit"       — frame_index has an exact keyframe entry.
 * "interpolated"   — frame is between two ellipse keyframes with gap ≤ 30.
 * "held_from_prior" — no exact match; shape is held from the preceding keyframe.
 */
export type ResolveReason = "explicit" | "interpolated" | "held_from_prior";

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

/**
 * Return the resolved keyframe and reason for a given frame during editing.
 *
 * Mirrors backend resolve_for_editing (W8):
 * - Returns null for empty track or frameIndex before first keyframe.
 * - Returns { reason: "explicit" } if an exact keyframe exists at frameIndex.
 * - Returns { reason: "interpolated" } if frameIndex lies between two ellipse
 *   keyframes whose gap is ≤ _INTERPOLATE_MAX_GAP (30 frames).
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
    prior.shape_type === "ellipse" &&
    nextKf.shape_type === "ellipse" &&
    nextKf.frame_index - prior.frame_index <= _INTERPOLATE_MAX_GAP
  ) {
    return { keyframe: interpolateEllipse(prior, nextKf, frameIndex), reason: "interpolated" };
  }

  return { keyframe: prior, reason: "held_from_prior" };
}
