import test from "node:test";
import assert from "node:assert/strict";

import { buildCreateTrackPayload, buildPolygonPointsFromBBox } from "../src/manualTrackFactory.ts";

test("buildPolygonPointsFromBBox expands a bbox into rectangle points", () => {
  assert.deepEqual(buildPolygonPointsFromBBox([0.3, 0.3, 0.2, 0.2]), [
    [0.3, 0.3],
    [0.5, 0.3],
    [0.5, 0.5],
    [0.3, 0.5],
  ]);
});

test("buildCreateTrackPayload keeps ellipse creation minimal", () => {
  assert.deepEqual(
    buildCreateTrackPayload({
      projectPath: "C:/project.mosaic.json",
      frameIndex: 48,
      shapeType: "ellipse",
    }),
    {
      project_path: "C:/project.mosaic.json",
      shape_type: "ellipse",
      frame_index: 48,
      bbox: [0.3, 0.3, 0.2, 0.2],
      points: undefined,
    },
  );
});

test("buildCreateTrackPayload seeds polygon creation with a rectangular polygon", () => {
  assert.deepEqual(
    buildCreateTrackPayload({
      projectPath: "C:/project.mosaic.json",
      frameIndex: 12,
      shapeType: "polygon",
    }),
    {
      project_path: "C:/project.mosaic.json",
      shape_type: "polygon",
      frame_index: 12,
      bbox: [0.3, 0.3, 0.2, 0.2],
      points: [
        [0.3, 0.3],
        [0.5, 0.3],
        [0.5, 0.5],
        [0.3, 0.5],
      ],
    },
  );
});
