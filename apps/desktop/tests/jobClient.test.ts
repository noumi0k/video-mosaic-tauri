import test from "node:test";
import assert from "node:assert/strict";

import { createExportJobId, startRuntimeJob } from "../src/jobClient.ts";
import type { CommandResponse, RuntimeJobSummary } from "../src/types.ts";

test("startRuntimeJob sends job kind through common helper", async () => {
  let captured: { command: string; payload: Record<string, unknown> } | null = null;
  const fakeRun = async <T,>(command: string, payload: Record<string, unknown> = {}): Promise<CommandResponse<T>> => {
    captured = { command, payload };
    return {
      ok: true,
      command,
      data: {
        job_id: "setup_environment-1",
        status: {
          job_id: "setup_environment-1",
          job_kind: "setup_environment",
          state: "queued",
          title: "初期環境をセットアップ中",
          stage: "queued",
          message: "queued",
          progress_percent: 0,
          is_indeterminate: true,
          can_cancel: true,
        } satisfies RuntimeJobSummary,
      } as T,
      error: null,
      warnings: [],
    };
  };

  const response = await startRuntimeJob(fakeRun, "setup_environment", { auto_fetch_required: true });

  assert.equal(response.ok, true);
  assert.deepEqual(captured, {
    command: "start-runtime-job",
    payload: {
      job_kind: "setup_environment",
      auto_fetch_required: true,
    },
  });
});

test("createExportJobId returns export-prefixed ids", () => {
  assert.match(createExportJobId(), /^export-\d+$/);
});
