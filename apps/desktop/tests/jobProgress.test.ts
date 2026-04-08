import test from "node:test";
import assert from "node:assert/strict";

import { normalizeDetectJob, normalizeExportJob, normalizeRuntimeJob } from "../src/jobProgress.ts";

test("runtime job normalization preserves japanese progress metadata", () => {
  const normalized = normalizeRuntimeJob({
    job_id: "open-video-1",
    job_kind: "open_video",
    state: "running",
    title: "動画を読み込み中",
    stage: "metadata_probe",
    message: "動画メタ情報を取得中",
    progress_percent: 35,
    is_indeterminate: false,
    can_cancel: true,
    current: 1,
    total: 3,
  });

  assert.equal(normalized.title, "動画を読み込み中");
  assert.equal(normalized.message, "動画メタ情報を取得中");
  assert.equal(normalized.subtitle, "1 / 3");
});

test("detect normalization maps succeeded into completed", () => {
  const normalized = normalizeDetectJob({
    job_id: "detect-1",
    state: "succeeded",
    stage: "finalizing",
    percent: 100,
    message: "done",
    current: 10,
    total: 10,
  });

  assert.equal(normalized.state, "completed");
});

test("export normalization maps queue progress into shared job shape", () => {
  const normalized = normalizeExportJob({
    jobId: "export-1",
    cancelling: false,
    status: {
      phase: "rendering_frames",
      progress: 0.5,
      message: "Rendering mosaic frames",
      frames_written: 50,
      total_frames: 100,
      audio_mode: "video_only",
      audio_status: "video-only",
      output_path: "H:/tmp/out.mp4",
      warnings: [],
    },
  });

  assert.equal(normalized.progress_percent, 50);
  assert.equal(normalized.subtitle, "50 / 100");
});
