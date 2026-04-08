import type { DetectJobState, DetectJobSummary } from "./types";

export type DetectJobPhase = DetectJobState;

export type DetectJobStatus = {
  state: DetectJobPhase;
  stage: string;
  percent: number;
  message: string;
  current: number;
  total: number;
  error?: { code?: string; message?: string } | null;
};

export type DetectJobHistorySnapshot = {
  activeJob: DetectJobSummary | null;
  latestFinishedJob: DetectJobSummary | null;
  interruptedJobs: DetectJobSummary[];
};

export function canStartDetectJob(busy: boolean, jobId: string | null) {
  return !busy && !jobId;
}

export function formatDetectProgress(status: DetectJobStatus) {
  const countLabel = status.total > 0 ? ` (${status.current}/${status.total})` : "";
  return `${status.stage} ${status.percent.toFixed(0)}%${countLabel}`;
}

export function isTerminalDetectState(state: DetectJobPhase) {
  return state === "succeeded" || state === "failed" || state === "cancelled" || state === "interrupted";
}

export function summarizeDetectJobs(jobs: DetectJobSummary[]): DetectJobHistorySnapshot {
  const activeJob = jobs.find((job) => job.state === "queued" || job.state === "starting" || job.state === "running") ?? null;
  const interruptedJobs = jobs.filter((job) => job.state === "interrupted");
  const latestFinishedJob =
    jobs.find((job) => job.state === "succeeded" || job.state === "failed" || job.state === "cancelled") ?? null;
  return { activeJob, latestFinishedJob, interruptedJobs };
}

export function formatDetectJobBadge(state: DetectJobState) {
  if (state === "succeeded") return "完了";
  if (state === "failed") return "失敗";
  if (state === "cancelled" || state === "interrupted") return "中断";
  if (state === "running") return "実行中";
  if (state === "starting") return "開始中";
  if (state === "cancelling") return "停止中";
  if (state === "queued") return "待機中";
  return "待機中";
}
