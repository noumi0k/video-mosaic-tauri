import type { CreateTrackPayload, KeyframeShapeType, ProjectDocument } from "./types";

const DEFAULT_MANUAL_TRACK_BBOX = [0.3, 0.3, 0.2, 0.2] as const;

// Number of points used when approximating an ellipse with a polygon.
// 24 points give a smooth ellipse outline while keeping vertex editing
// manageable. All masks are stored as polygons so users can freely edit
// any vertex regardless of the initial shape button.
const ELLIPSE_POLYGON_SAMPLES = 24;

export function buildPolygonPointsFromBBox(bbox: readonly [number, number, number, number]): number[][] {
  const [x, y, width, height] = bbox;
  return [
    [x, y],
    [x + width, y],
    [x + width, y + height],
    [x, y + height],
  ];
}

/**
 * Sample an ellipse inscribed in the bbox with `samples` evenly-spaced
 * points. Used when the user picks the "ellipse" button but we still store
 * the shape as a polygon so every vertex is editable.
 */
export function buildEllipsePolygonPointsFromBBox(
  bbox: readonly [number, number, number, number],
  samples: number = ELLIPSE_POLYGON_SAMPLES,
): number[][] {
  const [x, y, width, height] = bbox;
  const cx = x + width / 2;
  const cy = y + height / 2;
  const rx = width / 2;
  const ry = height / 2;
  const points: number[][] = [];
  for (let i = 0; i < samples; i += 1) {
    const theta = (i / samples) * Math.PI * 2;
    // Start at theta=0 (rightmost point) and go counter-clockwise.
    points.push([cx + Math.cos(theta) * rx, cy + Math.sin(theta) * ry]);
  }
  return points;
}

export function buildCreateTrackPayload(args: {
  projectPath: string | null;
  project?: ProjectDocument;
  frameIndex: number;
  shapeType: KeyframeShapeType;
}): CreateTrackPayload & { project?: ProjectDocument } {
  const bbox: [number, number, number, number] = [...DEFAULT_MANUAL_TRACK_BBOX];
  // All masks are polygons internally — vertex editing must work on every
  // track regardless of the starting shape the user picks.
  const points = args.shapeType === "ellipse"
    ? buildEllipsePolygonPointsFromBBox(bbox)
    : buildPolygonPointsFromBBox(bbox);
  const common: CreateTrackPayload & { project?: ProjectDocument } = {
    project_path: args.projectPath ?? "",
    // Force polygon so the backend / frontend pipeline treats the mask as
    // a vertex-editable polygon even when the user clicked the ellipse button.
    shape_type: "polygon",
    frame_index: args.frameIndex,
    bbox,
    points,
  };
  // Inline-project mode: when project has no saved path, send the full
  // document so the backend can mutate it in memory (path=None response).
  if (!args.projectPath && args.project) {
    // Backend ignores project_path when project payload is present and no
    // path is supplied; an empty string is rejected by load_project_for_mutation
    // so we drop the field explicitly here.
    delete (common as { project_path?: string }).project_path;
    common.project = args.project;
  }
  return common;
}
