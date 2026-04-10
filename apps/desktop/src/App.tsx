import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { CanvasStagePanel } from "./components/CanvasStagePanel";
import { DetectorSettingsModal } from "./components/DetectorSettingsModal";
import { JobPanel } from "./components/JobPanel";
import { KeyframeDetailPanel } from "./components/KeyframeDetailPanel";
import { TimelineView } from "./components/TimelineView";
import { TrackDetailPanel } from "./components/TrackDetailPanel";
import {
  DETECTOR_OPTIONS,
  isCategorySupportedByBackend,
  type DetectorAvailability,
  type DetectorBackendKey,
  type DetectorCategoryKey,
} from "./detectorCatalog";
import {
  cancelDetectJob,
  cancelExportJob,
  cancelRuntimeJob,
  collectDetectJobResult,
  collectRuntimeJobResult,
  createExportJobId,
  pollDetectJobStatus,
  pollExportJobStatus,
  pollRuntimeJobStatus,
  startDetectJob,
  startRuntimeJob,
  type BackendInvoker,
} from "./jobClient";
import { normalizeDetectJob, normalizeExportJob, normalizeRuntimeJob, sortJobs } from "./jobProgress";
import {
  findExplicitKeyframeSummary,
  planCommitMutation,
  resolveForEditing,
  type ResolveReason,
} from "./maskShapeResolver";
import {
  createHistorySnapshot,
  pushHistory,
  resetHistory,
  undoHistory,
  redoHistory,
  type EditorHistoryState,
} from "./editorHistory";
import { detectDangerousFrames } from "./dangerousFrames";
import { assertRawFilePathForBackend } from "./pathUtils";
import { uiText } from "./uiText";
import type {
  CommandResponse,
  CreateKeyframePayload,
  DetectJobSummary,
  ExportJobStatus,
  JobProgressView,
  Keyframe,
  MutationCommandData,
  ProjectDocument,
  ProjectReadModel,
  RuntimeJobSummary,
  UpdateKeyframePayload,
  VideoMetadata,
} from "./types";

type DoctorModelEntry = { name: string; exists: boolean; path: string; auto_fetch?: boolean };

type DoctorData = {
  ready: boolean;
  ffmpeg?: { found?: boolean; path?: string | null };
  ffprobe?: { found?: boolean; path?: string | null };
  models?: {
    required?: DoctorModelEntry[];
    optional?: DoctorModelEntry[];
  };
  onnxruntime?: {
    installed?: boolean;
    version?: string | null;
    providers?: string[];
    // cuda_session_ok: set by doctor when CUDAExecutionProvider is listed.
    // True only if an actual InferenceSession with CUDA was created successfully.
    // More reliable than checking providers[] alone (provider can be listed even
    // when CUDA DLLs are missing). Undefined on CPU-only systems.
    cuda_session_ok?: boolean;
  };
  erax?: {
    state: "missing" | "downloaded_pt" | "ready";
    convertible: boolean;
    ready_for_backend: boolean;
    pt_exists: boolean;
    onnx_exists: boolean;
  };
};

type MutationResult = {
  project: ProjectDocument;
  read_model: ProjectReadModel;
};

const DEFAULT_EXPORT_OPTIONS = {
  mosaic_strength: 12,
  audio_mode: "mux_if_possible" as const,
  resolution: "source" as string,
  bitrate_kbps: null as number | null,
};

function fileNameFromPath(value: string | null | undefined) {
  if (!value) return "";
  return value.split(/[\\/]/).pop() ?? value;
}

function prettyError(error: unknown) {
  if (!error) return "";
  if (typeof error === "string") return error;
  if (typeof error === "object" && error && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return String(error);
}

function isActiveRuntimeState(state: RuntimeJobSummary["state"]) {
  return state === "queued" || state === "starting" || state === "running" || state === "cancelling";
}

function isTerminalRuntimeState(state: RuntimeJobSummary["state"]) {
  return state === "completed" || state === "cancelled" || state === "failed";
}

function isActiveDetectState(state: DetectJobSummary["state"]) {
  return state === "queued" || state === "starting" || state === "running" || state === "cancelling";
}

function isTerminalDetectState(state: DetectJobSummary["state"]) {
  return state === "succeeded" || state === "failed" || state === "cancelled" || state === "interrupted";
}

function hasCollectableDetectResult(job: DetectJobSummary) {
  return (
    isTerminalDetectState(job.state) &&
    (job.state === "succeeded" || Boolean(job.result_available) || Boolean(job.has_result))
  );
}

export function App() {
  const run = async <T,>(command: string, payload: Record<string, unknown> = {}): Promise<CommandResponse<T>> => {
    try {
      return await invoke<CommandResponse<T>>("run_backend_command", { command, payload });
    } catch (error) {
      return {
        ok: false,
        command,
        data: null as T,
        error: {
          code: "TAURI_BRIDGE_ERROR",
          message: error instanceof Error ? error.message : String(error),
          details: {},
        },
        warnings: [],
      };
    }
  };

  const backend: BackendInvoker = run;
  const processedRuntimeJobsRef = useRef<Set<string>>(new Set());
  const processedDetectJobsRef = useRef<Set<string>>(new Set());
  const collectingDetectJobsRef = useRef<Set<string>>(new Set());

  const [activity, setActivity] = useState<string>(uiText.activity.idle);
  const [errorMessage, setErrorMessage] = useState("");
  const [doctor, setDoctor] = useState<DoctorData | null>(null);
  const [doctorWarnings, setDoctorWarnings] = useState<string[]>([]);
  const [doctorBusy, setDoctorBusy] = useState(false);

  const [project, setProject] = useState<ProjectDocument | null>(null);
  const [readModel, setReadModel] = useState<ProjectReadModel | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [projectDirty, setProjectDirty] = useState(false);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [selectedKeyframeFrame, setSelectedKeyframeFrame] = useState<number | null>(null);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [previewKeyframeOverride, setPreviewKeyframeOverride] = useState<Keyframe | null>(null);
  const [keyframeRemoteError, setKeyframeRemoteError] = useState("");

  // Undo/Redo history (project snapshot stack)
  const [history, setHistory] = useState<EditorHistoryState>({ past: [], present: null, future: [] });
  const canUndo = history.past.length > 0;
  const canRedo = history.future.length > 0;

  const [runtimeJobs, setRuntimeJobs] = useState<Record<string, RuntimeJobSummary>>({});
  const [detectJobs, setDetectJobs] = useState<Record<string, DetectJobSummary>>({});
  const [activeExportJobId, setActiveExportJobId] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<ExportJobStatus | null>(null);
  const [exportCancelling, setExportCancelling] = useState(false);
  const [lastExportOutputPath, setLastExportOutputPath] = useState<string | null>(null);
  const [exportResolution, setExportResolution] = useState("source");
  const [exportMosaicStrength, setExportMosaicStrength] = useState(12);

  // In/Out frame markers for range detection
  const [inFrame, setInFrame] = useState<number | null>(null);
  const [outFrame, setOutFrame] = useState<number | null>(null);

  // ジョブ通知の dismiss 管理
  const [dismissedJobIds, setDismissedJobIds] = useState<Set<string>>(new Set());
  const scheduledDismissRef = useRef<Set<string>>(new Set());
  const dismissTimersRef = useRef<Map<string, ReturnType<typeof window.setTimeout>>>(new Map());

  // 動画プレーヤー ref（再生位置同期用）
  const videoRef = useRef<HTMLVideoElement>(null);

  // Detector settings modal state
  const [detectModalOpen, setDetectModalOpen] = useState(false);
  const [detectBackend, setDetectBackend] = useState<DetectorBackendKey>("nudenet_320n");
  const [detectDevice, setDetectDevice] = useState("auto");
  const [detectThreshold, setDetectThreshold] = useState(0.28);
  const [detectSampleEvery, setDetectSampleEvery] = useState(2);
  const [detectMaxSamples, setDetectMaxSamples] = useState(120);
  const [detectInferenceResolution, setDetectInferenceResolution] = useState(320);
  const [detectBatchSize, setDetectBatchSize] = useState(1);
  const [detectContourMode, setDetectContourMode] = useState("none");
  const [detectPreciseFaceContour, setDetectPreciseFaceContour] = useState(false);
  const [detectVramSavingMode, setDetectVramSavingMode] = useState(false);
  const [detectSelectedCategories, setDetectSelectedCategories] = useState<DetectorCategoryKey[]>(
    ["male_genitalia", "female_genitalia", "female_face"],
  );

  const currentVideo = readModel?.video ?? project?.video ?? null;
  const requiredModelNames = useMemo(
    () => (doctor?.models?.required ?? []).filter((item) => !item.exists).map((item) => item.name),
    [doctor],
  );

  async function runDoctor() {
    setDoctorBusy(true);
    const response = await backend<DoctorData>("doctor", {});
    setDoctorBusy(false);
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      setActivity(uiText.activity.doctorFailed);
      return;
    }
    setDoctor(response.data);
    setDoctorWarnings(response.warnings);
    setActivity(response.data.ready ? uiText.activity.ready : uiText.activity.setupRecommended);
  }

  function syncProjectState(result: MutationResult, options?: { dirty?: boolean; previewPath?: string | null }) {
    // Push current state to history before sync (e.g. detect result apply).
    if (project && readModel && options?.dirty) {
      const snapshot = createHistorySnapshot(project, readModel, {
        trackId: selectedTrackId,
        frameIndex: selectedKeyframeFrame,
      });
      setHistory((prev) => pushHistory(prev, snapshot));
    }
    setProject(result.project);
    setReadModel(result.read_model);
    setProjectDirty(Boolean(options?.dirty));
    const sourcePath = options?.previewPath ?? result.project.video?.source_path ?? null;
    if (!sourcePath) {
      setPreviewSrc(null);
      return;
    }
    try {
      assertRawFilePathForBackend(sourcePath, "preview");
      setPreviewSrc(convertFileSrc(sourcePath));
    } catch (error) {
      setPreviewSrc(null);
      setErrorMessage(prettyError(error));
    }
  }

  function applyMutationResult(result: MutationCommandData) {
    // Push current state to history before applying mutation.
    if (project && readModel) {
      const snapshot = createHistorySnapshot(project, readModel, {
        trackId: selectedTrackId,
        frameIndex: selectedKeyframeFrame,
      });
      setHistory((prev) => pushHistory(prev, snapshot));
    }
    setProject(result.project);
    setReadModel(result.read_model);
    setSelectedTrackId(result.selection.track_id);
    setSelectedKeyframeFrame(result.selection.frame_index);
    if (result.selection.frame_index !== null) {
      setCurrentFrame(result.selection.frame_index);
    }
    setProjectDirty(true);
  }

  function handleUndo() {
    if (!canUndo) return;
    const next = undoHistory(history);
    setHistory(next);
    if (next.present) {
      setProject(next.present.project);
      setReadModel(next.present.readModel);
      setSelectedTrackId(next.present.selection.trackId);
      setSelectedKeyframeFrame(next.present.selection.frameIndex);
      setProjectDirty(true);
    }
  }

  function handleRedo() {
    if (!canRedo) return;
    // Push current state before redo (already handled by redoHistory).
    const next = redoHistory(history);
    setHistory(next);
    if (next.present) {
      setProject(next.present.project);
      setReadModel(next.present.readModel);
      setSelectedTrackId(next.present.selection.trackId);
      setSelectedKeyframeFrame(next.present.selection.frameIndex);
      setProjectDirty(true);
    }
  }

  async function createProjectFromVideo(video: VideoMetadata) {
    const response = await backend<MutationResult>("create-project", {
      name: fileNameFromPath(video.source_path).replace(/\.[^/.]+$/, "") || uiText.project.untitledName,
      video,
      tracks: [],
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    syncProjectState(response.data, { dirty: true, previewPath: video.source_path });
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setActivity(uiText.activity.videoReady);
  }

  function confirmDiscardIfDirty(): boolean {
    if (!projectDirty) return true;
    return window.confirm("未保存の変更があります。破棄してよろしいですか？");
  }

  async function handleNewProject() {
    if (!confirmDiscardIfDirty()) return;
    const response = await backend<MutationResult>("create-project", {
      name: uiText.project.untitledName,
      video: currentVideo,
      tracks: project?.tracks ?? [],
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    syncProjectState(response.data, { dirty: Boolean(currentVideo), previewPath: currentVideo?.source_path ?? null });
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setActivity(uiText.activity.newProjectReady);
  }

  async function handleOpenProject() {
    if (!confirmDiscardIfDirty()) return;
    const selected = await open({ filters: [{ name: "Project", extensions: ["json"] }], multiple: false });
    if (typeof selected !== "string") return;
    assertRawFilePathForBackend(selected, "load-project");
    const response = await backend<MutationResult>("load-project", { project_path: selected });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    syncProjectState(response.data, { dirty: false });
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setActivity(uiText.activity.projectLoaded);
  }

  async function handleSaveProject(saveAs = false): Promise<string | null> {
    if (!project) return null;
    let projectPath = saveAs ? null : project.project_path;
    if (!projectPath) {
      const selected = await save({
        defaultPath: `${project.name || uiText.project.untitledName}.json`,
        filters: [{ name: "Project", extensions: ["json"] }],
      });
      if (typeof selected !== "string") return null;
      projectPath = selected;
    }
    assertRawFilePathForBackend(projectPath, "save-project");
    const response = await backend<MutationResult & { project_path: string }>("save-project", {
      project_path: projectPath,
      project,
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return null;
    }
    syncProjectState(response.data, { dirty: false });
    setActivity(uiText.activity.projectSaved);
    return response.data.project_path;
  }

  async function ensureEditableProjectPath() {
    if (project?.project_path) {
      return project.project_path;
    }
    setActivity(uiText.activity.savingBeforeEdit);
    return handleSaveProject(false);
  }

  async function handleCreateTrack() {
    if (!project) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const response = await backend<MutationCommandData>("create-track", {
      project_path: projectPath,
      shape_type: "ellipse",
      frame_index: currentFrame,
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    applyMutationResult(response.data);
  }

  async function handleDeleteTrack() {
    if (!selectedTrackId || !project) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    // Remove track by filtering it out and saving
    const updatedTracks = project.tracks.filter((t) => t.track_id !== selectedTrackId);
    const updatedProject = { ...project, tracks: updatedTracks };
    const response = await backend<MutationCommandData>("save-project", {
      project_path: projectPath,
      project: updatedProject,
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    applyMutationResult(response.data);
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
  }

  async function handleToggleTrackVisible() {
    if (!selectedTrackId || !readModel) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const selectedTrack = readModel.track_summaries.find((track) => track.track_id === selectedTrackId);
    if (!selectedTrack) return;
    const response = await backend<MutationCommandData>("update-track", {
      project_path: projectPath,
      track_id: selectedTrackId,
      patch: { visible: !selectedTrack.visible },
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    applyMutationResult(response.data);
  }

  async function handleMoveSelectedKeyframe(delta: number) {
    if (!selectedTrackId || selectedKeyframeFrame === null) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const response = await backend<MutationCommandData>("move-keyframe", {
      project_path: projectPath,
      track_id: selectedTrackId,
      frame_index: selectedKeyframeFrame,
      target_frame_index: Math.max(0, selectedKeyframeFrame + delta),
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    applyMutationResult(response.data);
  }

  async function handleCommitKeyframePatch(patch: UpdateKeyframePayload["patch"]) {
    if (!selectedTrackId) return false;
    if (commitPlan.kind === "unavailable") return false;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return false;

    if (commitPlan.kind === "update-existing") {
      // currentFrame coincides with an explicit keyframe → update in place.
      const response = await backend<MutationCommandData>("update-keyframe", {
        project_path: projectPath,
        track_id: selectedTrackId,
        frame_index: commitPlan.frameIndex,
        patch,
      });
      if (!response.ok) {
        setKeyframeRemoteError(prettyError(response.error));
        return false;
      }
      setPreviewKeyframeOverride(null);
      setKeyframeRemoteError("");
      applyMutationResult(response.data);
      return true;
    }

    // create-held: currentFrame has no explicit keyframe but a resolved/held
    // shape exists. Create a new keyframe at currentFrame, using the resolved
    // shape as base and overriding with the incoming patch.
    const base = commitPlan.base;
    const response = await backend<MutationCommandData>("create-keyframe", {
      project_path: projectPath,
      track_id: selectedTrackId,
      frame_index: commitPlan.frameIndex,
      source: "manual",
      shape_type: patch.shape_type ?? base.shape_type,
      ...(patch.bbox !== undefined
        ? { bbox: patch.bbox }
        : base.bbox?.length
          ? { bbox: base.bbox }
          : {}),
      ...(patch.points !== undefined
        ? { points: patch.points }
        : base.points?.length
          ? { points: base.points }
          : {}),
    });
    if (!response.ok) {
      setKeyframeRemoteError(prettyError(response.error));
      return false;
    }
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
    // applyMutationResult re-syncs selectedKeyframeFrame from the backend's
    // selection (which echoes the newly-created keyframe's frame_index).
    applyMutationResult(response.data);
    return true;
  }

  async function handleCreateKeyframe(payload: Omit<CreateKeyframePayload, "project_path" | "track_id">) {
    if (!selectedTrackId) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const response = await backend<MutationCommandData>("create-keyframe", {
      project_path: projectPath,
      track_id: selectedTrackId,
      ...payload,
    });
    if (!response.ok) {
      setKeyframeRemoteError(prettyError(response.error));
      return;
    }
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
    applyMutationResult(response.data);
  }

  async function handleDeleteKeyframe() {
    if (!selectedTrackId || selectedKeyframeFrame === null) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const response = await backend<MutationCommandData>("delete-keyframe", {
      project_path: projectPath,
      track_id: selectedTrackId,
      frame_index: selectedKeyframeFrame,
    });
    if (!response.ok) {
      setKeyframeRemoteError(prettyError(response.error));
      return;
    }
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
    applyMutationResult(response.data);
  }

  async function startRuntime(kind: RuntimeJobSummary["job_kind"], payload: Record<string, unknown>) {
    setErrorMessage("");
    const response = await startRuntimeJob(backend, kind, payload);
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    setRuntimeJobs((current) => ({ ...current, [response.data.job_id]: response.data.status }));
    setActivity(uiText.activity.jobStarted(kind));
  }

  async function handleSetupEnvironment() {
    // P0-2: env_only mode never downloads models. "Fetch missing models" is
    // the separate action for that. This keeps the two buttons from looking
    // like duplicates of each other.
    await startRuntime("setup_environment", { mode: "env_only", auto_fetch_required: false, fetch_optional: false });
  }

  async function handleFetchModels() {
    const requiredMissing = requiredModelNames.length ? requiredModelNames : ["320n.onnx"];
    const autoFetchMissing = (doctor?.models?.optional ?? [])
      .filter((m) => m.auto_fetch && !m.exists)
      .map((m) => m.name);
    const modelNames = [...new Set([...requiredMissing, ...autoFetchMissing])];
    await startRuntime("fetch_models", { model_names: modelNames });
  }

  async function handleFetchErax() {
    await startRuntime("fetch_models", { model_names: ["erax_nsfw_yolo11s.pt"] });
  }

  async function handleConvertErax() {
    await startRuntime("setup_erax_convert", {});
  }

  async function handleOpenVideo() {
    if (!confirmDiscardIfDirty()) return;
    const selected = await open({
      filters: [{ name: "Video", extensions: ["mp4", "mov", "mkv", "avi", "webm"] }],
      multiple: false,
    });
    if (typeof selected !== "string") return;
    assertRawFilePathForBackend(selected, "open-video");
    await startRuntime("open_video", { video_path: selected });
  }

  async function handleDetect() {
    if (!project) return;
    // Only send categories the selected backend actually supports
    const categories = detectSelectedCategories.filter((cat) =>
      isCategorySupportedByBackend(detectBackend, cat),
    );
    const detectPayload: Record<string, unknown> = {
      project_path: project.project_path,
      project: project.project_path ? undefined : project,
      backend: detectBackend,
      device: detectDevice,
      confidence_threshold: detectThreshold,
      sample_every: detectSampleEvery,
      max_samples: detectMaxSamples,
      inference_resolution: detectInferenceResolution,
      batch_size: detectBatchSize,
      contour_mode: detectContourMode,
      precise_face_contour: detectPreciseFaceContour,
      vram_saving_mode: detectVramSavingMode,
      enabled_label_categories: categories,
    };
    // Range detection: pass in/out frame to limit detection scope.
    if (inFrame !== null && outFrame !== null && inFrame < outFrame) {
      detectPayload.start_frame = inFrame;
      detectPayload.end_frame = outFrame;
    }
    const response = await startDetectJob(backend, detectPayload);
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    setDetectModalOpen(false);
    setErrorMessage("");
    setDetectJobs((current) => {
      const next = Object.fromEntries(
        Object.entries(current).filter(([, job]) => isActiveDetectState(job.state)),
      );
      next[response.data.job_id] = response.data.status;
      return next;
    });
    setActivity(uiText.activity.detectStarted);
  }

  async function handleExport() {
    if (!project) return;
    // Pre-export safety check: warn about dangerous frames.
    const dangers = detectDangerousFrames(project);
    if (dangers.length > 0) {
      const summary = dangers.slice(0, 5).map((d) => `F${d.frameIndex}: ${d.reason} (${d.trackLabel})`).join("\n");
      const extra = dangers.length > 5 ? `\n... and ${dangers.length - 5} more` : "";
      if (!window.confirm(`${dangers.length} dangerous frame(s) detected:\n\n${summary}${extra}\n\nExport anyway?`)) {
        return;
      }
    }
    const projectPath = project.project_path ?? (await (async () => {
      setActivity(uiText.activity.savingBeforeExport);
      return handleSaveProject(false);
    })());
    if (!projectPath) {
      setErrorMessage(uiText.errors.saveBeforeExport);
      return;
    }

    const outputPath = await save({
      defaultPath: `${project.name || "auto-mosaic"}-export.mp4`,
      filters: [{ name: "Video", extensions: ["mp4"] }],
    });
    if (typeof outputPath !== "string") return;
    assertRawFilePathForBackend(projectPath, "export-video");
    assertRawFilePathForBackend(outputPath, "export-video");

    const jobId = createExportJobId();
    setActiveExportJobId(jobId);
    setExportStatus({
      phase: "preparing",
      progress: 0,
      message: uiText.export.preparing,
      frames_written: 0,
      total_frames: currentVideo?.frame_count ?? null,
      audio_mode: DEFAULT_EXPORT_OPTIONS.audio_mode,
      audio_status: null,
      output_path: outputPath,
      warnings: [],
    });
    setExportCancelling(false);
    setLastExportOutputPath(outputPath);
    setActivity(uiText.activity.exportStarted);

    void backend<{ output_path: string; audio: string }>("export-video", {
      project_path: projectPath,
      output_path: outputPath,
      job_id: jobId,
      options: {
        ...DEFAULT_EXPORT_OPTIONS,
        mosaic_strength: exportMosaicStrength,
        resolution: exportResolution,
      },
    }).then((response) => {
      if (!response.ok) setErrorMessage(prettyError(response.error));
      setActivity(response.ok ? uiText.activity.exportCompleted : uiText.activity.exportFailed);
    });
  }

  async function handleCancelJob(job: JobProgressView) {
    if (job.job_kind === "export") {
      if (!activeExportJobId) return;
      setExportCancelling(true);
      await cancelExportJob(backend, activeExportJobId);
      return;
    }
    if (job.job_kind === "detect") {
      await cancelDetectJob(backend, job.job_id);
      return;
    }
    await cancelRuntimeJob(backend, job.job_id);
  }

  // video.currentTime → currentFrame（再生中の自動追従）
  function handleVideoTimeUpdate() {
    const video = videoRef.current;
    const fps = currentVideo?.fps ?? 0;
    if (!video || fps <= 0) return;
    setCurrentFrame(Math.round(video.currentTime * fps));
  }

  // タイムライン / キーフレーム選択 → currentFrame + video.currentTime を同時更新
  function handleSeekFrame(frame: number) {
    setCurrentFrame(frame);
    const fps = currentVideo?.fps ?? 0;
    if (videoRef.current && fps > 0) {
      videoRef.current.currentTime = frame / fps;
    }
  }

  useEffect(() => {
    void runDoctor();
  }, []);

  // Keyboard shortcuts (aligned with PySide6 MainWindow.keyPressEvent)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const ctrl = e.ctrlKey || e.metaKey;
      const shift = e.shiftKey;
      const tag = (e.target as HTMLElement)?.tagName;
      // Don't intercept when typing in inputs/selects.
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      // Ctrl+Z: Undo
      if (ctrl && e.key === "z" && !shift) { e.preventDefault(); handleUndo(); return; }
      // Ctrl+Shift+Z / Ctrl+Y: Redo
      if (ctrl && (e.key === "Z" || e.key === "y")) { e.preventDefault(); handleRedo(); return; }
      // Ctrl+S: Save
      if (ctrl && e.key === "s" && !shift) { e.preventDefault(); void handleSaveProject(false); return; }
      // Ctrl+Shift+S: Save As
      if (ctrl && e.key === "S") { e.preventDefault(); void handleSaveProject(true); return; }

      // The following shortcuts require an active project.
      if (!project) return;

      // Arrow Left/Right: ±1 frame (Shift: ±10)
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        const step = shift ? 10 : 1;
        const next = Math.max(0, currentFrame - step);
        setCurrentFrame(next);
        handleSeekFrame(next);
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        const step = shift ? 10 : 1;
        const max = (currentVideo?.frame_count ?? 1) - 1;
        const next = Math.min(max, currentFrame + step);
        setCurrentFrame(next);
        handleSeekFrame(next);
        return;
      }
      // Space: play/pause video
      if (e.key === " ") {
        e.preventDefault();
        if (videoRef.current) {
          if (videoRef.current.paused) videoRef.current.play();
          else videoRef.current.pause();
        }
        return;
      }
      // K: Add keyframe at current frame
      if (e.key === "k" && !ctrl && !shift) {
        e.preventDefault();
        if (selectedTrackId && commitPlan.kind === "create-held") {
          void handleCreateKeyframe({
            frame_index: currentFrame,
            source: "manual",
            shape_type: commitPlan.base.shape_type,
            bbox: commitPlan.base.bbox,
            points: commitPlan.base.points,
          });
        }
        return;
      }
      // Shift+K: Delete keyframe
      if (e.key === "K" && !ctrl) {
        e.preventDefault();
        void handleDeleteKeyframe();
        return;
      }
      // [: Previous keyframe
      if (e.key === "[") {
        e.preventDefault();
        void handleMoveSelectedKeyframe(-1);
        return;
      }
      // ]: Next keyframe
      if (e.key === "]") {
        e.preventDefault();
        void handleMoveSelectedKeyframe(1);
        return;
      }
      // H: Toggle track visibility
      if (e.key === "h" && !ctrl) {
        e.preventDefault();
        void handleToggleTrackVisible();
        return;
      }
      // N: New ellipse track / Shift+N: New polygon track
      if (e.key === "n" && !ctrl && !shift) {
        e.preventDefault();
        void handleCreateTrack();
        return;
      }
      // I: Set in frame
      if (e.key === "i" && !ctrl && !shift) {
        e.preventDefault();
        setInFrame(currentFrame);
        return;
      }
      // O: Set out frame
      if (e.key === "o" && !ctrl && !shift) {
        e.preventDefault();
        setOutFrame(currentFrame);
        return;
      }
      // Delete: Delete selected track
      if (e.key === "Delete" && selectedTrackId) {
        e.preventDefault();
        void handleDeleteTrack();
        return;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  // Autosave: save to disk every 60 seconds when dirty and project has a path.
  const autosaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (autosaveTimerRef.current) {
      clearInterval(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    if (!project?.project_path || !projectDirty) return;
    autosaveTimerRef.current = setInterval(() => {
      if (project?.project_path && projectDirty) {
        void handleSaveProject(false);
      }
    }, 60_000);
    return () => {
      if (autosaveTimerRef.current) clearInterval(autosaveTimerRef.current);
    };
  }, [project?.project_path, projectDirty]);

  useEffect(() => {
    const activeJobIds = Object.values(runtimeJobs).filter((job) => isActiveRuntimeState(job.state)).map((job) => job.job_id);
    if (!activeJobIds.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(
        activeJobIds.map(async (jobId) => {
          const status = await pollRuntimeJobStatus(backend, jobId);
          if (!status) return;
          setRuntimeJobs((current) => ({ ...current, [jobId]: status }));
          if (!isTerminalRuntimeState(status.state) || processedRuntimeJobsRef.current.has(jobId)) return;
          processedRuntimeJobsRef.current.add(jobId);
          const result = await collectRuntimeJobResult(backend, jobId);
          if (!result?.ok) {
            if (status.error_message) setErrorMessage(status.error_message);
            if (status.job_kind === "fetch_models") void runDoctor();
            return;
          }
          if (status.job_kind === "open_video") {
            const video = (result.data as { video?: VideoMetadata }).video;
            if (video) void createProjectFromVideo(video);
          } else {
            void runDoctor();
          }
        }),
      );
    }, 500);
    return () => window.clearInterval(timer);
  }, [backend, runtimeJobs]);

  useEffect(() => {
    // Collect jobs that still need attention: either actively running, or
    // terminal but not yet processed (result not applied to UI state).
    const pendingJobIds = Object.values(detectJobs)
      .filter(
        (job) =>
          isActiveDetectState(job.state) ||
          (isTerminalDetectState(job.state) && !processedDetectJobsRef.current.has(job.job_id)),
      )
      .map((job) => job.job_id);
    if (!pendingJobIds.length) return;
    const timer = window.setInterval(() => {
      void Promise.all(
        pendingJobIds.map(async (jobId) => {
          try {
            if (processedDetectJobsRef.current.has(jobId)) return;
            // Always re-poll status for unprocessed jobs.  Backend
            // reconcile_job_state may upgrade "interrupted" → "succeeded"
            // when it discovers result.json after the worker exits.
            const status = await pollDetectJobStatus(backend, jobId);
            if (!status) return;
            setDetectJobs((current) => ({ ...current, [jobId]: status }));

            // Can we collect the result?
            if (!isTerminalDetectState(status.state)) return;
            // For non-succeeded terminal states without a result, show the
            // error and stop.  "interrupted" with no result_available will be
            // re-polled next interval (reconcile may fix it).
            if (status.state !== "succeeded" && !status.result_available && !status.has_result) {
              // Only surface the error once — skip if we already showed it.
              if (status.error && !collectingDetectJobsRef.current.has(jobId)) {
                setErrorMessage(prettyError(status.error) || `Detection ${status.state}`);
              }
              return;
            }
            if (collectingDetectJobsRef.current.has(jobId)) return;
            collectingDetectJobsRef.current.add(jobId);
            try {
              const result = await collectDetectJobResult(backend, jobId);
              if (!result?.ok) {
                console.error("[detect] collectDetectJobResult failed", { jobId, error: result?.error });
                setErrorMessage(prettyError(result?.error) || "detect result fetch failed");
                return;
              }
              const data = result.data as MutationResult & {
                selection?: { track_id: string | null; frame_index: number | null };
              };
              if (!data?.project || !data?.read_model) {
                console.error("[detect] malformed result.data — missing project/read_model", { jobId, data });
                setErrorMessage("Detection returned an unexpected payload.");
                processedDetectJobsRef.current.add(jobId);
                return;
              }
              syncProjectState(data, { dirty: true });
              if (data.selection) {
                setSelectedTrackId(data.selection.track_id);
                setSelectedKeyframeFrame(data.selection.frame_index);
                if (data.selection.frame_index !== null) {
                  setCurrentFrame(data.selection.frame_index);
                }
              }
              processedDetectJobsRef.current.add(jobId);
              setErrorMessage("");
              setActivity(uiText.activity.detectCompleted);
            } finally {
              collectingDetectJobsRef.current.delete(jobId);
            }
          } catch (error) {
            console.error("[detect] poll/apply threw", { jobId, error });
            setErrorMessage(prettyError(error) || "Unexpected detect polling error");
          }
        }),
      );
    }, 500);
    return () => window.clearInterval(timer);
  }, [backend, detectJobs]);

  useEffect(() => {
    if (!activeExportJobId) return;
    const timer = window.setInterval(() => {
      void pollExportJobStatus(backend, activeExportJobId).then((status) => {
        if (!status) return;
        setExportStatus(status);
        if (status.phase === "completed" || status.phase === "failed" || status.phase === "cancelled") {
          window.clearInterval(timer);
          setActiveExportJobId(null);
          setExportCancelling(false);
        }
      });
    }, 400);
    return () => window.clearInterval(timer);
  }, [activeExportJobId, backend]);

  const startupReady = Boolean(doctor?.ready);
  // hasCuda: use the doctor's actual CUDA session test result when available.
  // Falls back to provider-list check only when the session test result is
  // absent (e.g. older backend). This prevents the CUDA button from being
  // enabled when the provider is listed but sessions actually fall back to CPU.
  const hasCuda = doctor?.onnxruntime?.cuda_session_ok === true
    ? true
    : (doctor?.onnxruntime?.cuda_session_ok === undefined &&
       (doctor?.onnxruntime?.providers ?? []).includes("CUDAExecutionProvider"));
  const selectedTrackDocument = useMemo(
    () => project?.tracks.find((track) => track.track_id === selectedTrackId) ?? null,
    [project, selectedTrackId],
  );
  const selectedTrack = useMemo(
    () => readModel?.track_summaries.find((track) => track.track_id === selectedTrackId) ?? null,
    [readModel, selectedTrackId],
  );
  // Display, inspector mode, and commit branching all derive from currentFrame
  // (the playhead), not from selectedKeyframeFrame (the sticky timeline marker).
  // selectedKeyframeFrame remains valid for highlighting markers and for
  // delete/move operations against an explicitly clicked keyframe.
  // W9: resolveForEditing returns { keyframe, reason } | null.
  // reason is carried through state for future UI use (not yet rendered).
  const _resolvedForEditing = useMemo(
    () => resolveForEditing(selectedTrackDocument?.keyframes ?? [], currentFrame),
    [selectedTrackDocument, currentFrame],
  );
  const resolvedKeyframeDocument = _resolvedForEditing?.keyframe ?? null;
  const resolvedReason: ResolveReason | null = _resolvedForEditing?.reason ?? null;
  const commitPlan = useMemo(
    () => planCommitMutation(selectedTrackDocument?.keyframes ?? [], currentFrame),
    [selectedTrackDocument, currentFrame],
  );
  const currentFrameKeyframeSummary = useMemo(
    () => findExplicitKeyframeSummary(selectedTrack?.keyframes ?? [], currentFrame),
    [selectedTrack, currentFrame],
  );
  const displayedKeyframeDocument = previewKeyframeOverride ?? resolvedKeyframeDocument;
  const suggestedCreateFrame = selectedKeyframeFrame ?? currentFrame;
  const activeRuntimeByKind = useMemo(() => {
    const index = new Map<RuntimeJobSummary["job_kind"], RuntimeJobSummary>();
    for (const job of Object.values(runtimeJobs)) {
      if (isActiveRuntimeState(job.state)) index.set(job.job_kind, job);
    }
    return index;
  }, [runtimeJobs]);
  const activeDetectJob = useMemo(
    () => Object.values(detectJobs).find((job) => isActiveDetectState(job.state)) ?? null,
    [detectJobs],
  );
  const keyframeEditorBusy = Boolean(activeExportJobId || activeDetectJob);

  // Derived detector-modal values from doctor state
  const onnxVersion = doctor?.onnxruntime?.version ?? null;
  const detectAvailableModels: DetectorAvailability[] = useMemo(
    () => [
      ...(doctor?.models?.required ?? []),
      ...(doctor?.models?.optional ?? []),
    ],
    [doctor],
  );
  const detectRequiredModels: DetectorAvailability[] = useMemo(
    () => doctor?.models?.required ?? [],
    [doctor],
  );
  const detectOptionalModels: DetectorAvailability[] = useMemo(
    () => doctor?.models?.optional ?? [],
    [doctor],
  );
  const modelFetchBusy = Boolean(activeRuntimeByKind.get("fetch_models"));
  const eraxState = doctor?.erax?.state ?? "missing";
  const eraxConvertible = Boolean(doctor?.erax?.convertible);
  const eraxConvertBusy = Boolean(activeRuntimeByKind.get("setup_erax_convert"));
  // SAM2 は encoder と decoder の両方が揃って初めて利用可能とする。
  const hasSam2 = useMemo(() => {
    const optionals = doctor?.models?.optional ?? [];
    const enc = optionals.find((m) => m.name === "sam2_tiny_encoder.onnx");
    const dec = optionals.find((m) => m.name === "sam2_tiny_decoder.onnx");
    return Boolean(enc?.exists && dec?.exists);
  }, [doctor]);

  // Auto-deselect categories not supported by the newly selected backend
  useEffect(() => {
    const option = DETECTOR_OPTIONS.find((item) => item.key === detectBackend);
    if (!option) return;
    setDetectSelectedCategories((current) =>
      current.filter((cat) => option.supportedCategories.includes(cat)),
    );
  }, [detectBackend]);
  const jobPanelItems = useMemo(() => {
    const items: JobProgressView[] = Object.values(runtimeJobs).map(normalizeRuntimeJob);
    items.push(...Object.values(detectJobs).map(normalizeDetectJob));
    if (activeExportJobId || exportStatus) {
      items.push(normalizeExportJob({
        jobId: activeExportJobId ?? "export-last",
        status: exportStatus,
        cancelling: exportCancelling,
      }));
    }
    return sortJobs(items);
  }, [activeExportJobId, detectJobs, exportCancelling, exportStatus, runtimeJobs]);

  // terminal 状態のジョブを自動で dismiss するタイマーをスケジュール
  const DISMISS_DELAYS: Record<string, number> = { completed: 3000, cancelled: 4000, failed: 6000 };
  useEffect(() => {
    for (const item of jobPanelItems) {
      const delay = DISMISS_DELAYS[item.state];
      if (delay && !scheduledDismissRef.current.has(item.job_id)) {
        scheduledDismissRef.current.add(item.job_id);
        const timer = window.setTimeout(() => {
          dismissTimersRef.current.delete(item.job_id);
          setDismissedJobIds((prev) => new Set([...prev, item.job_id]));
          // Also drop the job from detectJobs so the polling effect and
          // the jobPanelItems memo don't keep the stale terminal state
          // around.  Without this, a session that accumulates several
          // runs ends up with multiple ghost cards that reappear after
          // any unrelated re-render.
          setDetectJobs((current) => {
            if (!(item.job_id in current)) return current;
            const next = { ...current };
            delete next[item.job_id];
            return next;
          });
        }, delay);
        dismissTimersRef.current.set(item.job_id, timer);
      }
    }
  }, [jobPanelItems]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleDismissJob(jobId: string) {
    const timer = dismissTimersRef.current.get(jobId);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      dismissTimersRef.current.delete(jobId);
    }
    scheduledDismissRef.current.add(jobId);
    setDismissedJobIds((prev) => new Set([...prev, jobId]));
    // Also drop from detectJobs — see auto-dismiss effect above for why.
    setDetectJobs((current) => {
      if (!(jobId in current)) return current;
      const next = { ...current };
      delete next[jobId];
      return next;
    });
  }

  const visibleJobPanelItems = useMemo(
    () => jobPanelItems.filter((item) => !dismissedJobIds.has(item.job_id)),
    [jobPanelItems, dismissedJobIds],
  );

  useEffect(() => {
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
  }, [selectedTrackId, selectedKeyframeFrame]);

  return (
    <main className="app-shell">
      <nav className="nle-menubar">
        <div className="nle-menu">
          <button className="nle-menu__trigger" type="button">{uiText.app.menu}</button>
          <div className="nle-menu__dropdown">
            <button className="nle-menu__item" onClick={() => void handleNewProject()} type="button">{uiText.app.newProject}</button>
            <button className="nle-menu__item" onClick={() => void handleOpenProject()} type="button">{uiText.app.openProject}</button>
            <button className="nle-menu__item" onClick={() => void handleSaveProject(false)} disabled={!project} type="button">{uiText.app.saveProject}</button>
            <button className="nle-menu__item" onClick={() => void handleSaveProject(true)} disabled={!project} type="button">{uiText.app.saveProjectAs}</button>
          </div>
        </div>
      </nav>

      <header className="nle-header">
        <div className="nle-header__brand">{uiText.app.title}</div>
        <div className="nle-header__group">
          <button className="nle-btn" onClick={() => void handleOpenVideo()} disabled={Boolean(activeRuntimeByKind.get("open_video"))}>{uiText.actions.openVideo}</button>
          <button className="nle-btn" onClick={() => void handleSetupEnvironment()} disabled={Boolean(activeRuntimeByKind.get("setup_environment"))}>{uiText.actions.setup}</button>
          <button className="nle-btn" onClick={() => void handleFetchModels()} disabled={Boolean(activeRuntimeByKind.get("fetch_models"))}>{uiText.actions.fetchModels}</button>
          <button className="nle-btn" onClick={() => void handleCreateTrack()} disabled={!project} title="Add manual track">+ Track</button>
          <button className="nle-btn" onClick={handleUndo} disabled={!canUndo} title="Undo (Ctrl+Z)">Undo</button>
          <button className="nle-btn" onClick={handleRedo} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)">Redo</button>
          <button className="nle-btn" onClick={() => setDetectModalOpen(true)} disabled={!project || Boolean(activeDetectJob)}>{uiText.actions.detect}</button>
          <select className="nle-select" value={exportResolution} onChange={(e) => setExportResolution(e.target.value)} title="Export resolution">
            <option value="source">Source</option>
            <option value="720p">720p</option>
            <option value="1080p">1080p</option>
            <option value="4k">4K</option>
          </select>
          <button className="nle-btn nle-btn--accent" onClick={() => void handleExport()} disabled={!project || Boolean(activeExportJobId)}>{uiText.actions.export}</button>
        </div>
        {(inFrame !== null || outFrame !== null) && (
          <div className="nle-header__group" style={{ fontSize: "0.85em", gap: 4 }}>
            <span>I:{inFrame ?? "-"}</span>
            <span>O:{outFrame ?? "-"}</span>
            <button className="nle-btn nle-btn--small" onClick={() => { setInFrame(null); setOutFrame(null); }} title="Clear I/O range">Clear</button>
          </div>
        )}
        <div className="nle-header__spacer" />
        <span className={`nle-header__badge ${startupReady ? "nle-header__badge--ready" : "nle-header__badge--warning"}`}>
          {startupReady ? uiText.app.backendReady : uiText.app.backendNeedsSetup}
        </span>
      </header>

      <section className={`nle-notice ${errorMessage ? "nle-notice--warning" : ""}`}>
        <div className="nle-notice__copy">
          <strong>{activity}</strong>
          <span>{errorMessage || doctorWarnings[0] || uiText.activity.notice}</span>
        </div>
        <div className="nle-notice__actions">
          <button className="nle-btn nle-btn--small" onClick={() => void runDoctor()} disabled={doctorBusy}>
            {doctorBusy ? uiText.actions.checking : uiText.actions.recheck}
          </button>
        </div>
      </section>

      <aside className="nle-left">
        <section className="nle-panel-section">
          <div className="nle-panel-header">{uiText.panels.project}</div>
          <div className="nle-panel-body">
            <div className="nle-video-info">
              <div className="nle-video-info__row"><span className="nle-video-info__label">{uiText.project.name}</span><span className="nle-video-info__value">{project?.name ?? uiText.project.none}</span></div>
              <div className="nle-video-info__row"><span className="nle-video-info__label">{uiText.project.path}</span><span className="nle-video-info__value">{project?.project_path ?? uiText.project.unsaved}</span></div>
              <div className="nle-video-info__row"><span className="nle-video-info__label">{uiText.project.tracks}</span><span className="nle-video-info__value">{readModel?.track_count ?? 0}</span></div>
              <div className="nle-video-info__row"><span className="nle-video-info__label">{uiText.project.state}</span><span className="nle-video-info__value">{projectDirty ? uiText.project.dirty : uiText.project.saved}</span></div>
            </div>
          </div>
        </section>
        <section className="nle-panel-section nle-panel-section--grow">
          <div className="nle-panel-header">{uiText.panels.models}</div>
          <div className="nle-panel-body">
            {(doctor?.models?.required ?? []).length ? (
              <ul className="nle-track-list">
                {(doctor?.models?.required ?? []).map((item) => (
                  <li key={item.name} className="nle-track-item">
                    <span className="nle-track-item__name">{item.name}</span>
                    <span className="nle-track-item__meta">{item.exists ? uiText.models.ready : uiText.models.missing}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="nle-empty">{uiText.models.empty}</div>
            )}
          </div>
        </section>
      </aside>

      <section className="nle-preview">
        {!previewSrc ? (
          <div className="nle-preview__empty" onClick={() => void handleOpenVideo()} role="button" tabIndex={0}>
            <div className="nle-preview__empty-icon">+</div>
            <p className="nle-preview__empty-title">{uiText.preview.emptyTitle}</p>
            <p className="nle-preview__empty-hint">{uiText.preview.emptyHint}</p>
          </div>
        ) : (
          <>
            <div className="nle-preview__workspace">
              <div className="nle-preview-stage">
                <video
                  ref={videoRef}
                  className="nle-preview-stage__video"
                  src={previewSrc}
                  controls
                  onTimeUpdate={handleVideoTimeUpdate}
                />
                <CanvasStagePanel
                  video={currentVideo}
                  track={selectedTrack}
                  keyframe={currentFrameKeyframeSummary}
                  keyframeDocument={displayedKeyframeDocument}
                  resolvedReason={resolvedReason}
                  busy={keyframeEditorBusy}
                  remoteError={keyframeRemoteError}
                  onPreviewKeyframeChange={setPreviewKeyframeOverride}
                  onClearRemoteError={() => setKeyframeRemoteError("")}
                  onCommitKeyframePatch={handleCommitKeyframePatch}
                />
              </div>
            </div>
            <div className="nle-preview__info-bar">
              <span>{uiText.preview.sourcePath}</span>
              <span>{currentVideo?.source_path ?? uiText.project.none}</span>
            </div>
          </>
        )}
      </section>

      <aside className="nle-right">
        <div className="nle-right__scroll">
          <details className="nle-inspector-section" open>
            <summary className="nle-inspector-section__header">{uiText.panels.environment}</summary>
            <div className="nle-inspector-section__body">
              <div className="nle-meta-row"><span className="nle-meta-row__label">ffmpeg</span><span className="nle-meta-row__value">{doctor?.ffmpeg?.found ? uiText.states.ready : uiText.states.missing}</span></div>
              <div className="nle-meta-row"><span className="nle-meta-row__label">ffprobe</span><span className="nle-meta-row__value">{doctor?.ffprobe?.found ? uiText.states.ready : uiText.states.missing}</span></div>
              <div className="nle-meta-row"><span className="nle-meta-row__label">GPU</span><span className="nle-meta-row__value">{hasCuda ? uiText.states.cuda : uiText.states.cpuFallback}</span></div>
              <div className="nle-meta-row"><span className="nle-meta-row__label">ONNX Runtime</span><span className="nle-meta-row__value">{doctor?.onnxruntime?.version ?? "--"}</span></div>
            </div>
          </details>
          <details className="nle-inspector-section" open>
            <summary className="nle-inspector-section__header">{uiText.panels.detect}</summary>
            <div className="nle-inspector-section__body">
              {activeDetectJob ? (
                <>
                  <div className="nle-meta-row"><span className="nle-meta-row__label">{uiText.jobs.stage}</span><span className="nle-meta-row__value">{activeDetectJob.stage}</span></div>
                  <div className="nle-meta-row"><span className="nle-meta-row__label">{uiText.jobs.progress}</span><span className="nle-meta-row__value">{activeDetectJob.percent.toFixed(0)}%</span></div>
                  <p>{activeDetectJob.message}</p>
                </>
              ) : (
                <div className="nle-empty">{uiText.detect.idle}</div>
              )}
            </div>
          </details>
          <details className="nle-inspector-section" open>
            <summary className="nle-inspector-section__header">{uiText.panels.export}</summary>
            <div className="nle-inspector-section__body">
              {exportStatus ? (
                <>
                  <div className="nle-meta-row"><span className="nle-meta-row__label">{uiText.jobs.stage}</span><span className="nle-meta-row__value">{exportStatus.phase}</span></div>
                  <div className="nle-meta-row"><span className="nle-meta-row__label">{uiText.jobs.progress}</span><span className="nle-meta-row__value">{Math.round(exportStatus.progress * 100)}%</span></div>
                  <p>{exportStatus.message}</p>
                  {lastExportOutputPath ? <p>{lastExportOutputPath}</p> : null}
                </>
              ) : (
                <div className="nle-empty">{uiText.export.idle}</div>
              )}
            </div>
          </details>
          <details className="nle-inspector-section" open>
            <summary className="nle-inspector-section__header">{uiText.panels.trackDetail}</summary>
            <div className="nle-inspector-section__body">
              <TrackDetailPanel
                readModel={readModel}
                track={selectedTrack}
                selectedKeyframeFrame={selectedKeyframeFrame}
                onSelectKeyframe={(trackId, frameIndex) => {
                  setSelectedTrackId(trackId);
                  setSelectedKeyframeFrame(frameIndex);
                  handleSeekFrame(frameIndex);
                }}
                onToggleVisible={() => void handleToggleTrackVisible()}
                onDeleteTrack={() => void handleDeleteTrack()}
              />
            </div>
          </details>
          <details className="nle-inspector-section" open>
            <summary className="nle-inspector-section__header">{uiText.panels.keyframeDetail}</summary>
            <div className="nle-inspector-section__body">
              <KeyframeDetailPanel
                track={selectedTrack}
                keyframe={currentFrameKeyframeSummary}
                keyframeDocument={displayedKeyframeDocument}
                resolvedReason={resolvedReason}
                suggestedCreateFrame={suggestedCreateFrame}
                onCreateKeyframe={(payload) => handleCreateKeyframe(payload)}
                onDeleteKeyframe={() => void handleDeleteKeyframe()}
                onSaveKeyframe={(patch) => handleCommitKeyframePatch(patch)}
                onReportError={setErrorMessage}
                onClearRemoteError={() => setKeyframeRemoteError("")}
                busy={keyframeEditorBusy}
                remoteError={keyframeRemoteError}
              />
            </div>
          </details>
        </div>
      </aside>

      <section className="nle-timeline">
        <TimelineView
          readModel={readModel}
          tracks={project?.tracks ?? null}
          selectedTrackId={selectedTrackId}
          selectedKeyframeFrame={selectedKeyframeFrame}
          currentFrame={currentFrame}
          inFrame={inFrame}
          outFrame={outFrame}
          busy={keyframeEditorBusy}
          onSelectTrack={(trackId) => {
            setSelectedTrackId(trackId);
            setSelectedKeyframeFrame(null);
          }}
          onSelectKeyframe={(trackId, frameIndex) => {
            setSelectedTrackId(trackId);
            setSelectedKeyframeFrame(frameIndex);
            handleSeekFrame(frameIndex);
          }}
          onMoveSelectedKeyframe={(delta) => void handleMoveSelectedKeyframe(delta)}
          onSeekFrame={handleSeekFrame}
        />
      </section>

      <JobPanel jobs={visibleJobPanelItems} onCancel={(job) => void handleCancelJob(job)} onDismiss={handleDismissJob} />

      <DetectorSettingsModal
        open={detectModalOpen}
        selectedBackend={detectBackend}
        selectedDevice={detectDevice}
        threshold={detectThreshold}
        sampleEvery={detectSampleEvery}
        maxSamples={detectMaxSamples}
        inferenceResolution={detectInferenceResolution}
        batchSize={detectBatchSize}
        contourMode={detectContourMode}
        vramSavingMode={detectVramSavingMode}
        selectedCategories={detectSelectedCategories}
        availableModels={detectAvailableModels}
        requiredModels={detectRequiredModels}
        optionalModels={detectOptionalModels}
        hasCuda={hasCuda}
        hasSam2={hasSam2}
        onnxVersion={onnxVersion}
        modelFetchBusy={modelFetchBusy}
        eraxState={eraxState}
        eraxConvertible={eraxConvertible}
        eraxConvertBusy={eraxConvertBusy}
        onSelectBackend={setDetectBackend}
        onSelectDevice={setDetectDevice}
        onThresholdChange={setDetectThreshold}
        onSampleEveryChange={setDetectSampleEvery}
        onMaxSamplesChange={setDetectMaxSamples}
        onInferenceResolutionChange={setDetectInferenceResolution}
        onBatchSizeChange={setDetectBatchSize}
        onContourModeChange={setDetectContourMode}
        onVramSavingModeChange={setDetectVramSavingMode}
        onToggleCategory={(cat) =>
          setDetectSelectedCategories((current) =>
            current.includes(cat) ? current.filter((c) => c !== cat) : [...current, cat],
          )
        }
        onRun={() => void handleDetect()}
        onFetchRequired={() => void handleFetchModels()}
        onFetchErax={() => void handleFetchErax()}
        onConvertErax={() => void handleConvertErax()}
        onRecheck={() => void runDoctor()}
        onClose={() => setDetectModalOpen(false)}
      />

      <footer className="nle-statusbar">
        <span className="nle-statusbar__item">{project?.name ?? uiText.project.none}</span>
        <span className="nle-statusbar__item">{projectDirty ? uiText.project.dirty : uiText.project.saved}</span>
        <span className="nle-statusbar__item">{currentVideo ? `${currentVideo.width} x ${currentVideo.height}` : "--"}</span>
        <span className="nle-statusbar__item">{currentVideo ? `${currentVideo.fps.toFixed(2)} fps` : "--"}</span>
        <span className="nle-statusbar__item">{currentVideo ? `${currentVideo.frame_count} fr` : "--"}</span>
        <div className="nle-statusbar__spacer" />
        <span className="nle-statusbar__item">{activity}</span>
      </footer>
    </main>
  );
}
