import test from "node:test";
import assert from "node:assert/strict";

import { getBackendParseDiagnostics } from "../src/backendDiagnostics.ts";

test("backend parse diagnostics extracts preview fields", () => {
  const diagnostics = getBackendParseDiagnostics({
    code: "BACKEND_JSON_PARSE_FAILED",
    details: {
      command: "detect-video",
      stdout_preview: "noise {",
      stderr_tail: "traceback",
      exit_status: 1,
    },
  });

  assert.deepEqual(diagnostics, {
    command: "detect-video",
    stdoutPreview: "noise {",
    stderrTail: "traceback",
    exitStatus: 1,
  });
});

test("backend parse diagnostics ignores other errors", () => {
  assert.equal(getBackendParseDiagnostics({ code: "MODEL_NOT_FOUND", details: {} }), null);
});
