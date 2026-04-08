import type { Keyframe, UpdateKeyframePayload } from "./types";

function deriveBBoxFromPoints(points: number[][]): number[] {
  if (!points.length) {
    return [0.25, 0.25, 0.2, 0.2];
  }
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return [minX, minY, Math.max(maxX - minX, 0.001), Math.max(maxY - minY, 0.001)];
}

export function applyKeyframePatchPreview(
  keyframe: Keyframe | null,
  patch: UpdateKeyframePayload["patch"]
): Keyframe | null {
  if (!keyframe) {
    return null;
  }

  const nextPoints = patch.points
    ? patch.points.map((point) => [point[0]!, point[1]!])
    : keyframe.points.map((point) => [point[0]!, point[1]!]);
  const nextShapeType = patch.shape_type ?? keyframe.shape_type;
  const nextBBox =
    patch.bbox?.map((value) => value) ??
    (nextShapeType === "polygon" ? deriveBBoxFromPoints(nextPoints) : keyframe.bbox.map((value) => value));

  return {
    ...keyframe,
    source: patch.source ?? keyframe.source,
    shape_type: nextShapeType,
    bbox: nextBBox,
    points: nextPoints
  };
}
