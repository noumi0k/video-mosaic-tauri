export type NormalizedBBox = [number, number, number, number];
export type NormalizedPoint = [number, number];

export type ResizeHandle = "nw" | "ne" | "sw" | "se";

export const MIN_SIZE = 0.02;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function normalizeBBox(bbox: number[]): NormalizedBBox {
  const [rawX = 0.25, rawY = 0.25, rawW = 0.2, rawH = 0.2] = bbox;
  const width = clamp(rawW, MIN_SIZE, 1);
  const height = clamp(rawH, MIN_SIZE, 1);
  const x = clamp(rawX, 0, 1 - width);
  const y = clamp(rawY, 0, 1 - height);
  return [x, y, width, height];
}

export function moveBBox(bbox: NormalizedBBox, deltaX: number, deltaY: number): NormalizedBBox {
  const [x, y, width, height] = bbox;
  return [
    clamp(x + deltaX, 0, 1 - width),
    clamp(y + deltaY, 0, 1 - height),
    width,
    height
  ];
}

export function resizeBBox(bbox: NormalizedBBox, handle: ResizeHandle, deltaX: number, deltaY: number): NormalizedBBox {
  let [x, y, width, height] = bbox;
  let left = x;
  let top = y;
  let right = x + width;
  let bottom = y + height;

  if (handle.includes("w")) {
    left = clamp(left + deltaX, 0, right - MIN_SIZE);
  }
  if (handle.includes("e")) {
    right = clamp(right + deltaX, left + MIN_SIZE, 1);
  }
  if (handle.includes("n")) {
    top = clamp(top + deltaY, 0, bottom - MIN_SIZE);
  }
  if (handle.includes("s")) {
    bottom = clamp(bottom + deltaY, top + MIN_SIZE, 1);
  }

  return [left, top, right - left, bottom - top];
}

export function bboxEquals(left: number[] | null, right: number[] | null, epsilon = 0.0001) {
  if (!left || !right || left.length !== 4 || right.length !== 4) {
    return false;
  }
  return left.every((value, index) => Math.abs(value - right[index]!) <= epsilon);
}

export function normalizePoint(point: number[]): NormalizedPoint {
  const [rawX = 0.5, rawY = 0.5] = point;
  return [clamp(rawX, 0, 1), clamp(rawY, 0, 1)];
}

export function normalizePoints(points: number[][]): NormalizedPoint[] {
  return points.map((point) => normalizePoint(point));
}

export function movePoint(point: NormalizedPoint, nextX: number, nextY: number): NormalizedPoint {
  return [clamp(nextX, 0, 1), clamp(nextY, 0, 1)];
}

export function movePoints(points: NormalizedPoint[], deltaX: number, deltaY: number): NormalizedPoint[] {
  if (!points.length) {
    return points;
  }

  const minX = Math.min(...points.map(([x]) => x));
  const maxX = Math.max(...points.map(([x]) => x));
  const minY = Math.min(...points.map(([, y]) => y));
  const maxY = Math.max(...points.map(([, y]) => y));

  const clampedDeltaX = clamp(deltaX, -minX, 1 - maxX);
  const clampedDeltaY = clamp(deltaY, -minY, 1 - maxY);

  return points.map(([x, y]) => [x + clampedDeltaX, y + clampedDeltaY]);
}

export function midpoint(left: NormalizedPoint, right: NormalizedPoint): NormalizedPoint {
  return [(left[0] + right[0]) / 2, (left[1] + right[1]) / 2];
}

export function insertPointAfter(points: NormalizedPoint[], index: number, point: NormalizedPoint): NormalizedPoint[] {
  const next = [...points];
  next.splice(index + 1, 0, point);
  return next;
}

export function removePointAt(points: NormalizedPoint[], index: number): NormalizedPoint[] {
  return points.filter((_, pointIndex) => pointIndex !== index);
}

export function pointsEqual(left: number[][] | null, right: number[][] | null, epsilon = 0.0001) {
  if (!left || !right || left.length !== right.length) {
    return false;
  }
  return left.every((point, index) => {
    const other = right[index];
    if (!other || point.length !== 2 || other.length !== 2) {
      return false;
    }
    return Math.abs(point[0]! - other[0]!) <= epsilon && Math.abs(point[1]! - other[1]!) <= epsilon;
  });
}
