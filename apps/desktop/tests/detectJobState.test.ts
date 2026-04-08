import test from "node:test";
import assert from "node:assert/strict";

import {
  canStartDetectJob,
  formatDetectJobBadge,
  formatDetectProgress,
  isTerminalDetectState,
  summarizeDetectJobs,
} from "../src/detectJobState.ts";

test("detect progress formatter includes stage percent and counts", () => {
  assert.equal(
    formatDetectProgress({
      state: "running",
      stage: "running_inference",
      percent: 42,
      message: "Running detector inference",
      current: 21,
      total: 50,
    }),
    "running_inference 42% (21/50)",
  );
});

test("detect job start guard blocks double start", () => {
  assert.equal(canStartDetectJob(false, null), true);
  assert.equal(canStartDetectJob(true, null), false);
  assert.equal(canStartDetectJob(false, "detect-123"), false);
});

test("terminal detect states are recognized", () => {
  assert.equal(isTerminalDetectState("queued"), false);
  assert.equal(isTerminalDetectState("running"), false);
  assert.equal(isTerminalDetectState("succeeded"), true);
  assert.equal(isTerminalDetectState("failed"), true);
  assert.equal(isTerminalDetectState("cancelled"), true);
  assert.equal(isTerminalDetectState("interrupted"), true);
});

test("detect history summary prefers active jobs and interrupted notices", () => {
  const snapshot = summarizeDetectJobs([
    {
      job_id: "detect-running",
      state: "running",
      stage: "running_inference",
      percent: 30,
      message: "running",
      current: 3,
      total: 10,
      updated_at: "2026-04-07T12:00:00Z",
    },
    {
      job_id: "detect-interrupted",
      state: "interrupted",
      stage: "running_inference",
      percent: 40,
      message: "interrupted",
      current: 4,
      total: 10,
      updated_at: "2026-04-07T11:59:00Z",
    },
    {
      job_id: "detect-succeeded",
      state: "succeeded",
      stage: "finalizing",
      percent: 100,
      message: "done",
      current: 10,
      total: 10,
      updated_at: "2026-04-07T11:58:00Z",
    },
  ]);

  assert.equal(snapshot.activeJob?.job_id, "detect-running");
  assert.equal(snapshot.interruptedJobs.length, 1);
  assert.equal(snapshot.latestFinishedJob?.job_id, "detect-succeeded");
});

test("detect job badge labels include interrupted", () => {
  assert.equal(formatDetectJobBadge("running"), "実行中");
  assert.equal(formatDetectJobBadge("interrupted"), "中断");
});
