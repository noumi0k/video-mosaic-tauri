import type { Keyframe, KeyframeSummary } from "./types";

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
 */
export function planCommitMutation(
  keyframes: readonly Keyframe[],
  currentFrame: number,
): CommitPlan {
  const explicit = findExplicitKeyframe(keyframes, currentFrame);
  if (explicit !== null) {
    return { kind: "update-existing", frameIndex: currentFrame, existing: explicit };
  }
  const resolved = resolveShapeForEditing(keyframes, currentFrame);
  if (resolved !== null) {
    return { kind: "create-held", frameIndex: currentFrame, base: resolved };
  }
  return { kind: "unavailable" };
}
