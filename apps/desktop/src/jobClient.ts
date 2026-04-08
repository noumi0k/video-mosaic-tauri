import type { CommandResponse, DetectJobSummary, ExportJobStatus, RuntimeJobSummary } from "./types";

export type BackendInvoker = <T>(command: string, payload?: Record<string, unknown>) => Promise<CommandResponse<T>>;

export async function startRuntimeJob(
  run: BackendInvoker,
  jobKind: RuntimeJobSummary["job_kind"],
  payload: Record<string, unknown>,
) {
  return run<{ job_id: string; status: RuntimeJobSummary }>("start-runtime-job", { job_kind: jobKind, ...payload });
}

export async function pollRuntimeJobStatus(run: BackendInvoker, jobId: string) {
  const response = await run<{ job_id: string; status: RuntimeJobSummary }>("get-runtime-job-status", { job_id: jobId });
  return response.ok ? response.data.status : null;
}

export async function collectRuntimeJobResult(run: BackendInvoker, jobId: string) {
  const response = await run<{ job_id: string; result: CommandResponse<unknown> }>("get-runtime-job-result", { job_id: jobId });
  return response.ok ? response.data.result : null;
}

export async function cancelRuntimeJob(run: BackendInvoker, jobId: string) {
  return run("cancel-runtime-job", { job_id: jobId });
}

export async function startDetectJob(run: BackendInvoker, payload: Record<string, unknown>) {
  return run<{ job_id: string; status: DetectJobSummary }>("start-detect-job", payload);
}

export async function pollDetectJobStatus(run: BackendInvoker, jobId: string) {
  const response = await run<{ job_id: string; status: DetectJobSummary }>("get-detect-status", { job_id: jobId });
  return response.ok ? response.data.status : null;
}

export async function collectDetectJobResult(run: BackendInvoker, jobId: string) {
  const response = await run<{ job_id: string; result: CommandResponse<unknown> }>("get-detect-result", { job_id: jobId });
  return response.ok ? response.data.result : null;
}

export async function cancelDetectJob(run: BackendInvoker, jobId: string) {
  return run("cancel-detect-job", { job_id: jobId });
}

export function createExportJobId() {
  return `export-${Date.now()}`;
}

export async function pollExportJobStatus(run: BackendInvoker, jobId: string) {
  const response = await run<{ job_id: string; status: ExportJobStatus }>("get-export-status", { job_id: jobId });
  return response.ok ? response.data.status : null;
}

export async function cancelExportJob(run: BackendInvoker, jobId: string) {
  return run("cancel-export", { job_id: jobId });
}
