import type { CommandError } from "./types";

export type BackendParseDiagnostics = {
  command: string;
  stdoutPreview: string;
  stderrTail: string;
  exitStatus: number | null;
};

export function getCommandError(error: unknown): CommandError {
  if (typeof error === "object" && error !== null) {
    return error as CommandError;
  }
  return {};
}

export function getBackendParseDiagnostics(error: unknown): BackendParseDiagnostics | null {
  const commandError = getCommandError(error);
  if (commandError.code !== "BACKEND_JSON_PARSE_FAILED") {
    return null;
  }
  const details = (commandError.details ?? {}) as Record<string, unknown>;
  return {
    command: typeof details.command === "string" ? details.command : "unknown",
    stdoutPreview: typeof details.stdout_preview === "string" ? details.stdout_preview : "",
    stderrTail: typeof details.stderr_tail === "string" ? details.stderr_tail : "",
    exitStatus: typeof details.exit_status === "number" ? details.exit_status : null,
  };
}

export function logBackendParseDiagnostics(error: unknown, context: Record<string, unknown> = {}) {
  const diagnostics = getBackendParseDiagnostics(error);
  if (!diagnostics) {
    return null;
  }
  console.error("[backend-json-parse]", {
    ...context,
    command: diagnostics.command,
    exitStatus: diagnostics.exitStatus,
    stdoutPreview: diagnostics.stdoutPreview,
    stderrTail: diagnostics.stderrTail,
  });
  return diagnostics;
}
