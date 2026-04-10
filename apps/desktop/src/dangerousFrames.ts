/**
 * Dangerous frame detection — identifies frames where the mosaic may be
 * unreliable due to long keyframe gaps, sudden area changes, or low confidence.
 *
 * Aligned with PySide6 DangerousFrameDetector logic.
 */
import type { ProjectDocument, MaskTrack } from "./types";

export type DangerousFrame = {
  trackId: string;
  trackLabel: string;
  frameIndex: number;
  reason: string;
};

const MAX_SAFE_KF_GAP = 30;
const AREA_JUMP_RATIO = 2.5;
const MIN_CONFIDENCE = 0.3;

function bboxArea(bbox: number[]): number {
  if (bbox.length < 4) return 0;
  return Math.max(bbox[2], 0) * Math.max(bbox[3], 0);
}

function analyzeTrack(track: MaskTrack): DangerousFrame[] {
  const warnings: DangerousFrame[] = [];
  if (!track.visible || track.keyframes.length < 2) return warnings;

  const sorted = [...track.keyframes].sort((a, b) => a.frame_index - b.frame_index);

  for (let i = 1; i < sorted.length; i++) {
    const prev = sorted[i - 1]!;
    const curr = sorted[i]!;
    const gap = curr.frame_index - prev.frame_index;

    // Long keyframe gap
    if (gap > MAX_SAFE_KF_GAP) {
      warnings.push({
        trackId: track.track_id,
        trackLabel: track.label,
        frameIndex: prev.frame_index,
        reason: `${gap} frame gap (>${MAX_SAFE_KF_GAP})`,
      });
    }

    // Sudden area change
    const areaA = bboxArea(prev.bbox);
    const areaB = bboxArea(curr.bbox);
    if (areaA > 0 && areaB > 0) {
      const ratio = Math.max(areaA, areaB) / Math.min(areaA, areaB);
      if (ratio > AREA_JUMP_RATIO) {
        warnings.push({
          trackId: track.track_id,
          trackLabel: track.label,
          frameIndex: curr.frame_index,
          reason: `Area jump ${ratio.toFixed(1)}x (>${AREA_JUMP_RATIO}x)`,
        });
      }
    }

    // Low confidence
    if (curr.confidence < MIN_CONFIDENCE && curr.source !== "manual") {
      warnings.push({
        trackId: track.track_id,
        trackLabel: track.label,
        frameIndex: curr.frame_index,
        reason: `Low confidence ${(curr.confidence * 100).toFixed(0)}% (<${MIN_CONFIDENCE * 100}%)`,
      });
    }
  }

  return warnings;
}

export function detectDangerousFrames(project: ProjectDocument): DangerousFrame[] {
  const all: DangerousFrame[] = [];
  for (const track of project.tracks) {
    all.push(...analyzeTrack(track));
  }
  return all.sort((a, b) => a.frameIndex - b.frameIndex);
}
