import test from "node:test";
import assert from "node:assert/strict";

import { buildDetectorOptionStatuses } from "../src/detectorCatalog.ts";

test("detector catalog marks required default model as available", () => {
  const statuses = buildDetectorOptionStatuses([
    { name: "320n.onnx", exists: true },
    { name: "640m.onnx", exists: false },
    { name: "erax_nsfw_yolo11s.pt", exists: false },
  ]);

  const defaultDetector = statuses.find((item) => item.key === "nudenet_320n");
  const highQualityDetector = statuses.find((item) => item.key === "nudenet_640m");

  assert.equal(defaultDetector?.available, true);
  assert.equal(defaultDetector?.statusLabel, "同梱済み");
  assert.equal(highQualityDetector?.available, false);
  assert.equal(highQualityDetector?.statusLabel, "未取得");
});

test("detector catalog treats EraX onnx as usable, pt-only as not ready", () => {
  // ONNX present → available
  const statusesOnnx = buildDetectorOptionStatuses([{ name: "erax_nsfw_yolo11s.onnx", exists: true }]);
  const eraxOnnx = statusesOnnx.find((item) => item.key === "erax_v1_1");
  assert.equal(eraxOnnx?.available, true);

  // PT only (no ONNX) → not available; backend requires ONNX to run inference
  const statusesPt = buildDetectorOptionStatuses([{ name: "erax_nsfw_yolo11s.pt", exists: true }]);
  const eraxPt = statusesPt.find((item) => item.key === "erax_v1_1");
  assert.equal(eraxPt?.available, false);
});

test("detector catalog does not treat broken model files as available", () => {
  const statuses = buildDetectorOptionStatuses([
    { name: "320n.onnx", exists: true, valid: false, status: "broken" },
  ]);

  const defaultDetector = statuses.find((item) => item.key === "nudenet_320n");
  assert.equal(defaultDetector?.available, false);
  assert.equal(defaultDetector?.statusLabel, "破損");
});
