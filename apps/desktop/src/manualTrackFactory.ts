import type { CreateTrackPayload, KeyframeShapeType } from "./types";

const DEFAULT_MANUAL_TRACK_BBOX = [0.3, 0.3, 0.2, 0.2] as const;

export function buildPolygonPointsFromBBox(bbox: readonly [number, number, number, number]): number[][] {
  const [x, y, width, height] = bbox;
  return [
    [x, y],
    [x + width, y],
    [x + width, y + height],
    [x, y + height],
  ];
}

export function buildCreateTrackPayload(args: {
  projectPath: string;
  frameIndex: number;
  shapeType: KeyframeShapeType;
}): CreateTrackPayload {
  const bbox: [number, number, number, number] = [...DEFAULT_MANUAL_TRACK_BBOX];
  return {
    project_path: args.projectPath,
    shape_type: args.shapeType,
    frame_index: args.frameIndex,
    bbox,
    points: args.shapeType === "polygon" ? buildPolygonPointsFromBBox(bbox) : undefined,
  };
}
