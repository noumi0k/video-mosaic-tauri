import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCreateTrackPayload,
  buildEllipsePolygonPointsFromBBox,
  buildPolygonPointsFromBBox,
} from "../src/manualTrackFactory.ts";

test("buildPolygonPointsFromBBox expands a bbox into rectangle points", () => {
  assert.deepEqual(buildPolygonPointsFromBBox([0.3, 0.3, 0.2, 0.2]), [
    [0.3, 0.3],
    [0.5, 0.3],
    [0.5, 0.5],
    [0.3, 0.5],
  ]);
});

test("buildEllipsePolygonPointsFromBBox samples an ellipse with the expected count", () => {
  const points = buildEllipsePolygonPointsFromBBox([0.3, 0.3, 0.2, 0.2], 24);
  assert.equal(points.length, 24);
  // First point should sit on the right edge of the bbox (theta=0): cx+rx, cy.
  const [x0, y0] = points[0];
  assert.ok(Math.abs(x0 - 0.5) < 1e-9);
  assert.ok(Math.abs(y0 - 0.4) < 1e-9);
});

test("buildCreateTrackPayload: ellipse button produces a vertex-editable polygon", () => {
  const payload = buildCreateTrackPayload({
    projectPath: "C:/project.mosaic.json",
    frameIndex: 48,
    shapeType: "ellipse",
  });
  assert.equal(payload.project_path, "C:/project.mosaic.json");
  // All masks are polygons internally so every vertex is editable.
  assert.equal(payload.shape_type, "polygon");
  assert.equal(payload.frame_index, 48);
  assert.deepEqual(payload.bbox, [0.3, 0.3, 0.2, 0.2]);
  assert.equal(payload.points?.length, 24);
});

test("buildCreateTrackPayload: polygon button seeds a rectangular polygon", () => {
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

test("buildCreateTrackPayload: inline mode drops project_path and includes project", () => {
  const fakeProject = { project_id: "p", tracks: [] } as unknown as Parameters<
    typeof buildCreateTrackPayload
  >[0]["project"];
  const payload = buildCreateTrackPayload({
    projectPath: null,
    project: fakeProject,
    frameIndex: 0,
    shapeType: "polygon",
  });
  assert.equal("project_path" in payload, false);
  assert.equal(payload.project, fakeProject);
});
