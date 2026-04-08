import type { DetectJobSummary, ExportJobStatus, JobProgressView, RuntimeJobSummary } from "./types";
import { uiText } from "./uiText.js";

function clampProgress(value: number | null | undefined): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function subtitleFromCounts(current?: number | null, total?: number | null): string {
  if (typeof current === "number" && typeof total === "number" && total > 0) {
    return `${current} / ${total}`;
  }
  return "";
}

export function normalizeRuntimeJob(job: RuntimeJobSummary): JobProgressView {
  const subtitle = job.job_kind === "fetch_models" && job.bytes_total
    ? `${Math.round((job.bytes_downloaded ?? 0) / 1024 / 1024)} / ${Math.round(job.bytes_total / 1024 / 1024)} MB`
    : subtitleFromCounts(job.current, job.total);
  return {
    job_id: job.job_id,
    job_kind: job.job_kind,
    state: job.state,
    title: job.title,
    stage: job.stage,
    message: job.message,
    progress_percent: clampProgress(job.progress_percent),
    is_indeterminate: job.is_indeterminate,
    can_cancel: job.can_cancel && (job.state === "queued" || job.state === "starting" || job.state === "running"),
    subtitle,
  };
}

export function normalizeDetectJob(job: DetectJobSummary): JobProgressView {
  const state =
    job.state === "succeeded"
      ? "completed"
      : job.state === "interrupted"
        ? "failed"
        : job.state === "idle"
          ? "queued"
          : job.state;
  return {
    job_id: job.job_id,
    job_kind: "detect",
    state,
    title: uiText.jobs.detectTitle,
    stage: job.stage,
    message: job.message,
    progress_percent: clampProgress(job.percent),
    is_indeterminate: false,
    can_cancel: state === "queued" || state === "starting" || state === "running",
    subtitle: subtitleFromCounts(job.current, job.total),
  };
}

export function normalizeExportJob(params: { jobId: string; status: ExportJobStatus | null; cancelling: boolean }): JobProgressView {
  const status = params.status;
  const stage = status?.phase ?? "preparing";
  const runningState = params.cancelling ? "cancelling" : "running";
  const state =
    stage === "completed" ? "completed" :
    stage === "cancelled" ? "cancelled" :
    stage === "failed" ? "failed" :
    runningState;
  return {
    job_id: params.jobId,
    job_kind: "export",
    state,
    title: uiText.jobs.exportTitle,
    stage,
    message: status?.message ?? (params.cancelling ? uiText.jobs.cancelling : uiText.export.preparing),
    progress_percent: clampProgress(typeof status?.progress === "number" ? status.progress * 100 : null),
    is_indeterminate: false,
    can_cancel: !params.cancelling && state !== "completed" && state !== "cancelled" && state !== "failed",
    subtitle: subtitleFromCounts(status?.frames_written ?? null, status?.total_frames ?? null),
  };
}

export function sortJobs(items: JobProgressView[]): JobProgressView[] {
  const priority = new Map([
    ["cancelling", 0],
    ["running", 1],
    ["starting", 2],
    ["queued", 3],
    ["failed", 4],
    ["cancelled", 5],
    ["completed", 6],
  ]);
  const deduped: JobProgressView[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    if (seen.has(item.job_id)) continue;
    seen.add(item.job_id);
    deduped.push(item);
  }
  return deduped.sort((a, b) => (priority.get(a.state) ?? 99) - (priority.get(b.state) ?? 99));
}
