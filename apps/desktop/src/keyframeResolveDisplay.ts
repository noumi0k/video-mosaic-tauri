/**
 * Pure display helpers for ResolveReason and source_detail.
 *
 * No JSX — safe to import in Node test runner.
 */
import type { ResolveReason } from "./maskShapeResolver";

/**
 * Return the CSS modifier suffix for the nle-mode-badge element.
 * Falls back to "held" when reason is absent.
 */
export function resolveReasonBadgeVariant(
  reason: ResolveReason | null | undefined,
): "explicit" | "held" | "interpolated" {
  if (reason === "explicit") return "explicit";
  if (reason === "interpolated") return "interpolated";
  return "held"; // held_from_prior or null/undefined → held
}

/**
 * Return the short display label for a ResolveReason, or null when absent.
 */
export function resolveReasonLabel(
  reason: ResolveReason | null | undefined,
): "explicit" | "held" | "interpolated" | null {
  if (reason === "explicit") return "explicit";
  if (reason === "interpolated") return "interpolated";
  if (reason === "held_from_prior") return "held";
  return null;
}

/**
 * Convert a source_detail value to a compact display string.
 * Strips the "detector_" prefix for brevity.
 *
 * "detector_accepted" → "accepted"
 * "detector_anchored" → "anchored"
 * null / undefined     → null (caller should not render)
 * any other string     → returned as-is
 */
export function sourceDetailLabel(
  sourceDetail: string | null | undefined,
): string | null {
  if (!sourceDetail) return null;
  const prefix = "detector_";
  return sourceDetail.startsWith(prefix)
    ? sourceDetail.slice(prefix.length)
    : sourceDetail;
}

/**
 * Compose a compact single-line label for the canvas overlay.
 * Returns null when the state is unavailable (no badge should be shown).
 *
 * Format examples:
 *   "explicit"
 *   "held"
 *   "interpolated"
 *   "held · accepted"
 *   "explicit · anchored"
 *
 * source_detail null / undefined → no suffix (legacy-safe).
 */
export function resolveOverlayLabel(
  reason: ResolveReason | null | undefined,
  sourceDetail?: string | null,
): string | null {
  const label = resolveReasonLabel(reason);
  if (label === null) return null;
  const detail = sourceDetailLabel(sourceDetail);
  return detail ? `${label} · ${detail}` : label;
}
