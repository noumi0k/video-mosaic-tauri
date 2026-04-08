import type { ExportOptions, ExportQueueItem, ProjectDocument } from "./types";

const DEFAULT_EXPORT_OPTIONS: ExportOptions = {
  mosaic_strength: 12,
  audio_mode: "mux_if_possible",
};

export function normalizePersistedExportOptions(value: unknown): ExportOptions {
  if (!value || typeof value !== "object") {
    return DEFAULT_EXPORT_OPTIONS;
  }
  const candidate = value as Partial<ExportOptions>;
  return {
    mosaic_strength:
      typeof candidate.mosaic_strength === "number"
        ? Math.min(Math.max(candidate.mosaic_strength, 2), 64)
        : DEFAULT_EXPORT_OPTIONS.mosaic_strength,
    audio_mode: candidate.audio_mode === "video_only" ? "video_only" : DEFAULT_EXPORT_OPTIONS.audio_mode
  };
}

export function normalizePersistedQueueItem(value: unknown): ExportQueueItem | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const item = value as Partial<ExportQueueItem>;
  if (
    typeof item.queue_id !== "string" ||
    typeof item.job_id !== "string" ||
    typeof item.project_path !== "string" ||
    typeof item.project_name !== "string" ||
    typeof item.output_path !== "string"
  ) {
    return null;
  }
  const state =
    item.state === "queued" ||
    item.state === "running" ||
    item.state === "interrupted" ||
    item.state === "completed" ||
    item.state === "failed" ||
    item.state === "cancelled"
      ? item.state
      : "failed";
  return {
    queue_id: item.queue_id,
    job_id: item.job_id,
    project_path: item.project_path,
    project_name: item.project_name,
    output_path: item.output_path,
    options: normalizePersistedExportOptions(item.options),
    state,
    progress: typeof item.progress === "number" ? Math.min(Math.max(item.progress, 0), 100) : 0,
    status_text: typeof item.status_text === "string" ? item.status_text : state,
    warnings: Array.isArray(item.warnings) ? item.warnings.filter((entry): entry is string => typeof entry === "string") : [],
    audio_status: typeof item.audio_status === "string" ? item.audio_status : null
  };
}

export function hydratePersistedExportQueue(queue: ExportQueueItem[]) {
  const hydratedQueue = queue.map((item) =>
    item.state === "running"
      ? {
          ...item,
          state: "interrupted" as const,
          progress: 0,
          status_text: "前回セッション終了時に中断されました",
        }
      : item
  );
  return {
    queue: hydratedQueue,
    recoveredInterrupted: hydratedQueue.some((item) => item.state === "interrupted"),
  };
}

export function shouldScheduleAutosave(args: {
  project: ProjectDocument | null;
  isDirty: boolean;
  mutationBusy: boolean;
  exportBusy: boolean;
  autosaveBusy: boolean;
}) {
  return Boolean(
    args.project &&
      args.project.project_path &&
      args.isDirty &&
      !args.mutationBusy &&
      !args.exportBusy &&
      !args.autosaveBusy
  );
}

export function shouldSaveBeforeExport(project: ProjectDocument | null, isDirty: boolean) {
  return Boolean(project?.project_path && isDirty);
}

export function isHistoryRestoreDirty(project: ProjectDocument | null) {
  return project !== null;
}

export function canOpenVideoWithoutDirtyPrompt(project: ProjectDocument | null, isDirty: boolean) {
  if (!isDirty) {
    return true;
  }
  if (!project) {
    return true;
  }
  return !project.project_path && !project.video && project.tracks.length === 0;
}

export function buildDirtyGuardCopy(projectPath: string | null) {
  return projectPath
    ? {
        saveContextLabel: "保存済み project",
        summary: "この project には、まだディスクへ保存されていない変更があります。",
        beforeUnloadMessage: "この保存済み project には未保存の変更があります。破棄してよい場合のみ終了してください。",
      }
    : {
        saveContextLabel: "未保存 project",
        summary: "この project にはまだ保存先がなく、変更は現在のセッションにしか存在しません。",
        beforeUnloadMessage: "この未保存 project は現在のセッションにしかありません。失ってよい場合のみ終了してください。",
      };
}

export function shouldProceedAfterDirtyDecision(
  decision: "save" | "discard" | "cancel",
  saveSucceeded: boolean
) {
  if (decision === "discard") {
    return true;
  }
  if (decision === "cancel") {
    return false;
  }
  return saveSucceeded;
}
