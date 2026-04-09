/**
 * Pure display helpers for timeline segment bars and keyframe markers.
 *
 * No JSX — safe to import in Node test runner.
 */
import type { MaskSegment } from "./types";

/**
 * Return the CSS modifier class for a segment bar element.
 * Unknown states fall back to "confirmed" (safe default).
 */
export function segmentBarClass(state: MaskSegment["state"] | string): string {
  switch (state) {
    case "confirmed":    return "nle-tl-seg--confirmed";
    case "held":         return "nle-tl-seg--held";
    case "uncertain":    return "nle-tl-seg--uncertain";
    case "interpolated": return "nle-tl-seg--interpolated";
    case "predicted":    return "nle-tl-seg--predicted";
    default:             return "nle-tl-seg--confirmed";
  }
}

/**
 * Return the CSS modifier class for a keyframe marker, taking both
 * source and source_detail into account.
 *
 * source_detail === "detector_anchored" gets its own visual variant so
 * anchored keyframes are distinguishable from plain accepted ones.
 */
export function kfMarkerClassFull(
  source: string,
  sourceDetail?: string | null,
): string {
  switch (source) {
    case "manual":
      return "nle-tl-row__marker--manual";
    case "detector":
    case "auto":
      if (sourceDetail === "detector_anchored") {
        return "nle-tl-row__marker--auto-anchored";
      }
      return "nle-tl-row__marker--auto";
    case "interpolated":
      return "nle-tl-row__marker--interpolated";
    case "predicted":
      return "nle-tl-row__marker--predicted";
    default:
      return "";
  }
}
