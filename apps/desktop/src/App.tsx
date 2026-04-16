import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { message as tauriMessage, open, save } from "@tauri-apps/plugin-dialog";
import { CanvasStagePanel } from "./components/CanvasStagePanel";
import { DetectorSettingsModal } from "./components/DetectorSettingsModal";
import { ExportSettingsModal, type ExportSettings } from "./components/ExportSettingsModal";
import { JobPanel } from "./components/JobPanel";
import { MosaicPreviewCanvas } from "./components/MosaicPreviewCanvas";
import { KeyframeDetailPanel } from "./components/KeyframeDetailPanel";
import { TimelineView } from "./components/TimelineView";
import { TrackDetailPanel } from "./components/TrackDetailPanel";
import {
  DETECTOR_OPTIONS,
  isModelInstalled,
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
import { detectDangerousFrames, type DangerousFrame } from "./dangerousFrames";
import { DangerWarningsPanel } from "./components/DangerWarningsPanel";
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

type DoctorModelEntry = {
  name: string;
  exists: boolean;
  valid?: boolean;
  status?: "missing" | "broken" | "installed";
  path: string;
  auto_fetch?: boolean;
  downloadable?: boolean;
  source?: string;
  note?: string | null;
};

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

type RecoverySnapshot = {
  id: string;
  project: ProjectDocument;
  readModel: ProjectReadModel | null;
  timestamp: string;
};

const DEFAULT_EXPORT_OPTIONS = {
  mosaic_strength: 12,
  audio_mode: "mux_if_possible" as const,
  resolution: "source" as string,
  bitrate_kbps: null as number | null,
};

const RECOVERY_KEY_PREFIX = "auto-mosaic-recovery:";
const LEGACY_RECOVERY_KEY = "auto-mosaic-recovery";

function fileNameFromPath(value: string | null | undefined) {
  if (!value) return "";
  return value.split(/[\\/]/).pop() ?? value;
}

function recoverySnapshotId(project: ProjectDocument) {
  return String(project.project_id || project.project_path || project.video?.source_path || "unsaved");
}

function recoveryStorageKey(id: string) {
  return `${RECOVERY_KEY_PREFIX}${id}`;
}

function loadRecoverySnapshots(): RecoverySnapshot[] {
  const snapshots: RecoverySnapshot[] = [];
  const seen = new Set<string>();

  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (!key?.startsWith(RECOVERY_KEY_PREFIX)) continue;
    try {
      const parsed = JSON.parse(localStorage.getItem(key) ?? "") as Partial<RecoverySnapshot>;
      if (!parsed.project) continue;
      const id = parsed.id || key.slice(RECOVERY_KEY_PREFIX.length);
      snapshots.push({
        id,
        project: parsed.project,
        readModel: parsed.readModel ?? null,
        timestamp: parsed.timestamp ?? new Date().toISOString(),
      });
      seen.add(id);
    } catch {
      localStorage.removeItem(key);
    }
  }

  const legacy = localStorage.getItem(LEGACY_RECOVERY_KEY);
  if (legacy) {
    try {
      const parsed = JSON.parse(legacy) as { project?: ProjectDocument; readModel?: ProjectReadModel; timestamp?: string };
      if (parsed.project) {
        const id = recoverySnapshotId(parsed.project);
        if (!seen.has(id)) {
          snapshots.push({
            id,
            project: parsed.project,
            readModel: parsed.readModel ?? null,
            timestamp: parsed.timestamp ?? new Date().toISOString(),
          });
        }
      }
    } catch {
      localStorage.removeItem(LEGACY_RECOVERY_KEY);
    }
  }

  return snapshots.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
}

function saveRecoverySnapshot(project: ProjectDocument, readModel: ProjectReadModel | null) {
  const snapshot: RecoverySnapshot = {
    id: recoverySnapshotId(project),
    project,
    readModel,
    timestamp: new Date().toISOString(),
  };
  localStorage.setItem(recoveryStorageKey(snapshot.id), JSON.stringify(snapshot));
}

function removeRecoverySnapshot(id: string) {
  localStorage.removeItem(recoveryStorageKey(id));
  localStorage.removeItem(LEGACY_RECOVERY_KEY);
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
  return isTerminalDetectState(job.state) && job.state === "succeeded";
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
  const [recoveryCandidates, setRecoveryCandidates] = useState<RecoverySnapshot[]>([]);
  const [recoveryModalOpen, setRecoveryModalOpen] = useState(false);
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
  // Refs that mirror state so the window-close handler can read current
  // values without being re-registered every time state changes.
  const detectJobsRef = useRef(detectJobs);
  const projectRef = useRef(project);
  const readModelRef = useRef(readModel);
  const projectDirtyRef = useRef(projectDirty);
  const recoveryDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [activeExportJobId, setActiveExportJobId] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState<ExportJobStatus | null>(null);
  const [exportCancelling, setExportCancelling] = useState(false);
  const [lastExportOutputPath, setLastExportOutputPath] = useState<string | null>(null);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportSettings, setExportSettings] = useState<ExportSettings>({
    resolution: "source",
    mosaic_strength: 12,
    audio_mode: "mux_if_possible",
    bitrate_kbps: null,
    encoder: "auto",
  });

  // In/Out frame markers for range detection
  const [inFrame, setInFrame] = useState<number | null>(null);
  const [outFrame, setOutFrame] = useState<number | null>(null);

  // Dangerous frame warnings (updated when project tracks change)
  const dangerWarnings = useMemo<DangerousFrame[]>(
    () => (project ? detectDangerousFrames(project) : []),
    [project],
  );
  // 確認済み危険フレーム: key = `${trackId}-${frameIndex}`
  // DangerWarningsPanel と TimelineView が共有する。プロジェクト変更時にリセット。
  const [confirmedDangerFrames, setConfirmedDangerFrames] = useState<Set<string>>(new Set());

  // 全体検出前の上書き確認モーダル
  // resolve が null でない間はモーダルが開いている。
  const overwriteResolveRef = useRef<((mode: "protected" | "overwrite_all" | "cancel") => void) | null>(null);
  const [overwriteConfirmOpen, setOverwriteConfirmOpen] = useState(false);
  const [overwriteConfirmInfo, setOverwriteConfirmInfo] = useState<{
    trackCount: number;
    manualCount: number;
  } | null>(null);

  // ジョブ通知の dismiss 管理
  const [dismissedJobIds, setDismissedJobIds] = useState<Set<string>>(new Set());
  const scheduledDismissRef = useRef<Set<string>>(new Set());
  const dismissTimersRef = useRef<Map<string, ReturnType<typeof window.setTimeout>>>(new Map());

  // モザイクプレビュートグル
  const [mosaicPreviewEnabled, setMosaicPreviewEnabled] = useState(false);

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
  const [detectContourMode, setDetectContourMode] = useState("quality");
  const [detectPreciseFaceContour, setDetectPreciseFaceContour] = useState(false);
  const [detectVramSavingMode, setDetectVramSavingMode] = useState(false);
  const detectDefaultsAppliedRef = useRef(false);
  const [detectSelectedCategories, setDetectSelectedCategories] = useState<DetectorCategoryKey[]>(
    ["male_genitalia", "female_genitalia", "female_face"],
  );

  const currentVideo = readModel?.video ?? project?.video ?? null;
  const requiredModelNames = useMemo(
    () => (doctor?.models?.required ?? []).filter((item) => !isModelInstalled(item)).map((item) => item.name),
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
    // プロジェクトが置き換わったら危険フレームの確認状態をリセットする。
    setConfirmedDangerFrames(new Set());
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

  function resetEditorToBlank() {
    setProject(null);
    setReadModel(null);
    setPreviewSrc(null);
    setProjectDirty(false);
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setCurrentFrame(0);
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
    setConfirmedDangerFrames(new Set());
    setHistory(resetHistory(null));
  }

  function restoreRecoverySnapshot(snapshot: RecoverySnapshot) {
    setProject(snapshot.project);
    setReadModel(snapshot.readModel);
    setProjectDirty(true);
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setCurrentFrame(0);
    setPreviewKeyframeOverride(null);
    setKeyframeRemoteError("");
    setConfirmedDangerFrames(new Set());
    setHistory(resetHistory(null));
    const sourcePath = snapshot.project.video?.source_path ?? null;
    if (sourcePath) {
      try {
        assertRawFilePathForBackend(sourcePath, "recovery-preview");
        setPreviewSrc(convertFileSrc(sourcePath));
      } catch {
        setPreviewSrc(null);
      }
    } else {
      setPreviewSrc(null);
    }
    setRecoveryModalOpen(false);
    setActivity("前回のセッションを復元しました");
  }

  function deleteRecoverySnapshot(snapshot: RecoverySnapshot) {
    removeRecoverySnapshot(snapshot.id);
    setRecoveryCandidates((current) => {
      const next = current.filter((item) => item.id !== snapshot.id);
      if (!next.length) setRecoveryModalOpen(false);
      return next;
    });
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
      video: null,
      tracks: [],
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    syncProjectState(response.data, { dirty: false, previewPath: null });
    setSelectedTrackId(null);
    setSelectedKeyframeFrame(null);
    setCurrentFrame(0);
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

  async function handleDuplicateTrack() {
    if (!selectedTrackId || !project) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const sourceTrack = project.tracks.find((t) => t.track_id === selectedTrackId);
    if (!sourceTrack) return;
    const newTrackId = `track-dup-${Date.now()}`;
    const duplicated = {
      ...structuredClone(sourceTrack),
      track_id: newTrackId,
      label: `${sourceTrack.label} (copy)`,
    };
    const updatedProject = { ...project, tracks: [...project.tracks, duplicated] };
    const response = await backend<MutationCommandData>("save-project", {
      project_path: projectPath,
      project: updatedProject,
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    applyMutationResult(response.data);
    setSelectedTrackId(newTrackId);
  }

  async function handleSplitTrack() {
    if (!selectedTrackId || !project) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const sourceTrack = project.tracks.find((t) => t.track_id === selectedTrackId);
    if (!sourceTrack || sourceTrack.keyframes.length < 2) {
      setErrorMessage("Split requires at least 2 keyframes.");
      return;
    }
    // Split at the current frame: keyframes before → track A, keyframes at/after → track B.
    const before = sourceTrack.keyframes.filter((kf) => kf.frame_index < currentFrame);
    const after = sourceTrack.keyframes.filter((kf) => kf.frame_index >= currentFrame);
    if (before.length === 0 || after.length === 0) {
      setErrorMessage("Cannot split: all keyframes are on one side of the playhead.");
      return;
    }
    const newTrackId = `track-split-${Date.now()}`;
    const trackA = { ...structuredClone(sourceTrack), keyframes: before };
    const trackB = {
      ...structuredClone(sourceTrack),
      track_id: newTrackId,
      label: `${sourceTrack.label} (B)`,
      keyframes: after,
    };
    const updatedTracks = project.tracks.map((t) => (t.track_id === selectedTrackId ? trackA : t));
    updatedTracks.push(trackB);
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

  async function handleToggleTrackExportEnabled() {
    if (!selectedTrackId || !readModel) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const selectedTrack = readModel.track_summaries.find((track) => track.track_id === selectedTrackId);
    if (!selectedTrack) return;
    const response = await backend<MutationCommandData>("update-track", {
      project_path: projectPath,
      track_id: selectedTrackId,
      patch: { export_enabled: !selectedTrack.export_enabled },
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
    if (!project) return false;
    // project_path がある場合はファイルから読み書き、なければ inline project を渡して
    // ディスク書き込みをスキップする in-memory 編集モード。
    const projectRef = project.project_path
      ? { project_path: project.project_path }
      : { project };

    if (commitPlan.kind === "update-existing") {
      // currentFrame coincides with an explicit keyframe → update in place.
      const response = await backend<MutationCommandData>("update-keyframe", {
        ...projectRef,
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
      ...projectRef,
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

  async function handleDuplicateKeyframe() {
    // Duplicate the selected keyframe to the current frame.
    if (!selectedTrackId || selectedKeyframeFrame === null) return;
    if (selectedKeyframeFrame === currentFrame) return; // same frame, no-op
    const sourceKf = selectedTrackDocument?.keyframes.find((kf) => kf.frame_index === selectedKeyframeFrame);
    if (!sourceKf) return;
    const projectPath = await ensureEditableProjectPath();
    if (!projectPath) return;
    const response = await backend<MutationCommandData>("create-keyframe", {
      project_path: projectPath,
      track_id: selectedTrackId,
      frame_index: currentFrame,
      source: "manual",
      shape_type: sourceKf.shape_type,
      bbox: sourceKf.bbox,
      points: sourceKf.points,
      rotation: sourceKf.rotation,
      opacity: sourceKf.opacity,
      expand_px: sourceKf.expand_px,
      feather: sourceKf.feather,
    });
    if (!response.ok) {
      setKeyframeRemoteError(prettyError(response.error));
      return;
    }
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
      .filter((m) => m.auto_fetch && !isModelInstalled(m))
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

  async function handleDetectCurrentFrame() {
    if (!project) return;
    const categories = detectSelectedCategories.filter((cat) =>
      isCategorySupportedByBackend(detectBackend, cat),
    );
    const response = await startDetectJob(backend, {
      project_path: project.project_path,
      project: project.project_path ? undefined : project,
      backend: detectBackend,
      device: detectDevice,
      confidence_threshold: detectThreshold,
      inference_resolution: detectInferenceResolution,
      contour_mode: detectContourMode,
      vram_saving_mode: detectVramSavingMode,
      enabled_label_categories: categories,
      sample_every: 1,
      max_samples: 1,
      start_frame: currentFrame,
      end_frame: currentFrame,
    });
    if (!response.ok) {
      setErrorMessage(prettyError(response.error));
      return;
    }
    setDetectJobs((current) => {
      const next = Object.fromEntries(
        Object.entries(current).filter(([, job]) => isActiveDetectState(job.state)),
      );
      next[response.data.job_id] = response.data.status;
      return next;
    });
    setActivity("Detecting current frame...");
  }

  async function handleDetect() {
    if (!project) return;

    // 既存トラックがある場合: 上書き確認モーダルを出す
    let overwriteManualTracks = false;
    if (project.tracks.length > 0) {
      const manualCount = project.tracks.filter((t) => t.user_edited || t.source === "manual").length;
      setOverwriteConfirmInfo({ trackCount: project.tracks.length, manualCount });
      const mode = await new Promise<"protected" | "overwrite_all" | "cancel">((resolve) => {
        overwriteResolveRef.current = resolve;
        setOverwriteConfirmOpen(true);
      });
      setOverwriteConfirmOpen(false);
      overwriteResolveRef.current = null;
      if (mode === "cancel") return;
      overwriteManualTracks = mode === "overwrite_all";
    }

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
      overwrite_manual_tracks: overwriteManualTracks,
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

  function handleExportClick() {
    if (!project) return;
    setExportModalOpen(true);
  }

  async function handleExportWithSettings(settings: ExportSettings) {
    setExportModalOpen(false);
    setExportSettings(settings);
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
    // 常に最新編集を保存してからエクスポートする
    setActivity(uiText.activity.savingBeforeExport);
    const projectPath = await handleSaveProject(false);
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
        mosaic_strength: settings.mosaic_strength,
        audio_mode: settings.audio_mode,
        resolution: settings.resolution,
        bitrate_kbps: settings.bitrate_kbps,
        encoder: settings.encoder,
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

  // Keep refs in sync so the close handler always sees current state.
  useEffect(() => { detectJobsRef.current = detectJobs; }, [detectJobs]);
  useEffect(() => { projectRef.current = project; }, [project]);
  useEffect(() => { readModelRef.current = readModel; }, [readModel]);
  useEffect(() => { projectDirtyRef.current = projectDirty; }, [projectDirty]);

  // On main window close: prompt to save unsaved changes, cancel active jobs, then exit.
  useEffect(() => {
    let unlisten: (() => void) | null = null;
    const win = getCurrentWindow();
    win.onCloseRequested(async (event) => {
      event.preventDefault();

      const proj = projectRef.current;
      const rm = readModelRef.current;
      const dirty = projectDirtyRef.current;

      if (dirty && proj) {
        const decision = await tauriMessage(
          "未保存の変更があります。保存してから終了しますか？",
          {
            title: "終了確認",
            kind: "warning",
            buttons: { yes: "保存して終了", no: "保存せずに終了", cancel: "キャンセル" },
          },
        );

        if (decision === "Cancel") return;

        if (decision === "Yes" && proj.project_path) {
          await invoke("run_backend_command", {
            command: "save-project",
            payload: { project_path: proj.project_path, project: proj },
          });
        }

        saveRecoverySnapshot(proj, rm);
      }

      const activeJobs = Object.values(detectJobsRef.current).filter(
        (j) => isActiveDetectState(j.state),
      );
      await Promise.race([
        Promise.allSettled(
          activeJobs.map((j) => cancelDetectJob(backend, j.job_id)),
        ),
        new Promise((resolve) => setTimeout(resolve, 3000)),
      ]);
      await invoke("exit_app");
    }).then((fn) => { unlisten = fn; });
    return () => { unlisten?.(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // Ctrl+D: Duplicate keyframe / Ctrl+Shift+D: Detect current frame
      if (ctrl && e.key === "d" && !shift) { e.preventDefault(); void handleDuplicateKeyframe(); return; }
      if (ctrl && e.key === "D") { e.preventDefault(); void handleDetectCurrentFrame(); return; }
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
      // F1: Show keyboard shortcuts
      if (e.key === "F1") {
        e.preventDefault();
        window.alert(
          "キーボードショートカット一覧\n" +
          "──────────────────────\n" +
          "Ctrl+Z: 元に戻す\n" +
          "Ctrl+Shift+Z / Ctrl+Y: やり直す\n" +
          "Ctrl+S: 保存\n" +
          "Ctrl+Shift+S: 名前を付けて保存\n" +
          "Ctrl+D: キーフレームを複製\n" +
          "Ctrl+Shift+D: 現在フレームを検出\n" +
          "← / →: ±1 フレーム (Shift: ±10)\n" +
          "Space: 再生 / 一時停止\n" +
          "K: キーフレーム追加\n" +
          "Shift+K: キーフレーム削除\n" +
          "[ / ]: 前 / 次のキーフレーム\n" +
          "H: トラック表示切替\n" +
          "N: 新規トラック\n" +
          "I: イン点を設定\n" +
          "O: アウト点を設定\n" +
          "Delete: トラック削除\n" +
          "F1: このヘルプ"
        );
        return;
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  // Autosave: save to disk every 60 seconds when dirty and project has a path.
  // Also stores a recovery snapshot in localStorage for crash recovery.
  const autosaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (autosaveTimerRef.current) {
      clearInterval(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    if (!project || !projectDirty) return;
    // Store recovery snapshot immediately on first dirty change.
    try {
      saveRecoverySnapshot(project, readModel);
    } catch { /* localStorage quota exceeded — ignore */ }

    if (!project.project_path) return;
    autosaveTimerRef.current = setInterval(() => {
      if (project?.project_path && projectDirty) {
        void handleSaveProject(false);
      }
    }, 60_000);
    return () => {
      if (autosaveTimerRef.current) clearInterval(autosaveTimerRef.current);
    };
  }, [project?.project_path, projectDirty]);

  // Clear recovery snapshot after successful save.
  useEffect(() => {
    if (project && !projectDirty) {
      removeRecoverySnapshot(recoverySnapshotId(project));
    }
  }, [project, projectDirty]);

  // Debounced recovery snapshot: update localStorage when project content
  // changes while dirty, so force-kill loses at most ~5 seconds of work.
  useEffect(() => {
    if (!project || !projectDirty) return;
    if (recoveryDebounceRef.current) clearTimeout(recoveryDebounceRef.current);
    recoveryDebounceRef.current = setTimeout(() => {
      recoveryDebounceRef.current = null;
      try { saveRecoverySnapshot(project, readModel); } catch { /* quota — ignore */ }
    }, 5_000);
    return () => {
      if (recoveryDebounceRef.current) {
        clearTimeout(recoveryDebounceRef.current);
        recoveryDebounceRef.current = null;
      }
    };
  }, [project, readModel, projectDirty]);

  // Startup: check for recovery snapshot.
  useEffect(() => {
    const raw = "";
    if (!raw) return;
    try {
      const recovery = JSON.parse(raw) as { project: ProjectDocument; readModel: ProjectReadModel; timestamp: string };
      if (!recovery.project) return;
      const ts = new Date(recovery.timestamp).toLocaleString();
      if (window.confirm(`前回のセッション (${ts}) から未保存のプロジェクトが見つかりました。\n\n復元しますか？`)) {
        setProject(recovery.project);
        setReadModel(recovery.readModel);
        setProjectDirty(true);
        const sourcePath = recovery.project.video?.source_path ?? null;
        if (sourcePath) {
          try {
            assertRawFilePathForBackend(sourcePath, "recovery-preview");
            setPreviewSrc(convertFileSrc(sourcePath));
          } catch { /* ignore */ }
        }
        setActivity("前回のセッションを復元しました");
      } else {
        localStorage.removeItem("auto-mosaic-recovery");
      }
    } catch {
      localStorage.removeItem("auto-mosaic-recovery");
    }
  }, []);

  useEffect(() => {
    const snapshots = loadRecoverySnapshots();
    resetEditorToBlank();
    if (!snapshots.length) return;
    setRecoveryCandidates(snapshots);
    setRecoveryModalOpen(true);
  }, []);

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
            if (status.job_kind === "fetch_models" || status.job_kind === "setup_erax_convert") void runDoctor();
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
            const status = await pollDetectJobStatus(backend, jobId);
            if (!status) return;

            setDetectJobs((current) => ({ ...current, [jobId]: status }));

            // Can we collect the result?
            if (!isTerminalDetectState(status.state)) return;
            // For non-succeeded terminal states, show the error and stop.
            if (status.state !== "succeeded") {
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
  const hasDirectMl = (doctor?.onnxruntime?.providers ?? []).includes("DmlExecutionProvider");

  useEffect(() => {
    if (!doctor?.onnxruntime || detectDefaultsAppliedRef.current) return;
    detectDefaultsAppliedRef.current = true;
    setDetectDevice("auto");
    if (hasCuda) {
      setDetectInferenceResolution(640);
      setDetectBatchSize(4);
      setDetectSampleEvery(1);
      setDetectMaxSamples(240);
      setDetectVramSavingMode(false);
      return;
    }
    if (hasDirectMl) {
      setDetectInferenceResolution(320);
      setDetectBatchSize(2);
      setDetectSampleEvery(1);
      setDetectMaxSamples(180);
      setDetectVramSavingMode(true);
      return;
    }
    setDetectInferenceResolution(320);
    setDetectBatchSize(1);
    setDetectSampleEvery(2);
    setDetectMaxSamples(120);
    setDetectVramSavingMode(true);
  }, [doctor?.onnxruntime, hasCuda, hasDirectMl]);
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
  const hasSam2 = useMemo(() => {
    const optionals = doctor?.models?.optional ?? [];
    const encoder = optionals.find((m) => m.name === "sam2_tiny_encoder.onnx");
    const decoder = optionals.find((m) => m.name === "sam2_tiny_decoder.onnx");
    return Boolean(encoder && decoder && isModelInstalled(encoder) && isModelInstalled(decoder));
  }, [doctor]);

  // Auto-trigger EraX ONNX conversion when PT is downloaded and ultralytics
  // is available.  This removes the need for a manual "Convert to ONNX" button
  // — the conversion fires as soon as the doctor check reports the conditions.
  const eraxAutoConvertFiredRef = useRef(false);
  useEffect(() => {
    if (eraxState === "downloaded_pt" && eraxConvertible && !eraxConvertBusy && !eraxAutoConvertFiredRef.current) {
      eraxAutoConvertFiredRef.current = true;
      void handleConvertErax();
    }
    // Reset the guard when the state changes away from downloaded_pt so that
    // a fresh download can trigger conversion again.
    if (eraxState !== "downloaded_pt") {
      eraxAutoConvertFiredRef.current = false;
    }
  }, [eraxState, eraxConvertible, eraxConvertBusy]);

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
  // export 完了はフォルダを開くボタンが見えるよう長めに設定
  function getDismissDelay(item: JobProgressView): number | undefined {
    if (item.state === "completed") return item.job_kind === "export" ? 12000 : 3000;
    if (item.state === "cancelled") return 4000;
    if (item.state === "failed") return 6000;
    return undefined;
  }
  useEffect(() => {
    for (const item of jobPanelItems) {
      const delay = getDismissDelay(item);
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

  function handleOpenFolder(job: JobProgressView) {
    if (!job.output_path) return;
    void invoke("reveal_path_in_explorer", { path: job.output_path }).catch(() => {
      // フォルダを開けなかった場合は静かに無視する
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

  // Show splash screen while the initial doctor check is running.
  if (!doctor) {
    return (
      <main className="app-shell app-shell--splash">
        <div className="startup-splash">
          <p className="startup-splash__eyebrow">Auto Mosaic</p>
          <h1 className="startup-splash__title">起動中です</h1>
          <p className="startup-splash__body">
            バックエンドの環境を確認しています。しばらくお待ちください…
          </p>
        </div>
      </main>
    );
  }

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
          <button className="nle-btn" onClick={() => void handleCreateTrack()} disabled={!project} title="手動トラック追加 (N)">+ トラック</button>
          <button className="nle-btn" onClick={handleUndo} disabled={!canUndo} title="元に戻す (Ctrl+Z)">戻す{canUndo ? ` (${history.past.length})` : ""}</button>
          <button className="nle-btn" onClick={handleRedo} disabled={!canRedo} title="やり直す (Ctrl+Shift+Z)">やり直す{canRedo ? ` (${history.future.length})` : ""}</button>
          <button className="nle-btn" onClick={() => setDetectModalOpen(true)} disabled={!project || Boolean(activeDetectJob)}>{uiText.actions.detect}</button>
          <button className="nle-btn nle-btn--accent" onClick={handleExportClick} disabled={!project || Boolean(activeExportJobId)}>{uiText.actions.export}</button>
        </div>
        {(inFrame !== null || outFrame !== null) && (
          <div className="nle-header__group" style={{ fontSize: "0.85em", gap: 4 }}>
            <span>I:{inFrame ?? "-"}</span>
            <span>O:{outFrame ?? "-"}</span>
            <button className="nle-btn nle-btn--small" onClick={() => { setInFrame(null); setOutFrame(null); }} title="範囲をクリア">クリア</button>
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
        <DangerWarningsPanel
          warnings={dangerWarnings}
          confirmedKeys={confirmedDangerFrames}
          onToggleConfirmed={(key) =>
            setConfirmedDangerFrames((prev) => {
              const next = new Set(prev);
              if (next.has(key)) next.delete(key); else next.add(key);
              return next;
            })
          }
          onSeekFrame={handleSeekFrame}
        />
        <section className="nle-panel-section nle-panel-section--grow">
          <div className="nle-panel-header">{uiText.panels.models}</div>
          <div className="nle-panel-body">
            {(() => {
              const allModels = [
                ...(doctor?.models?.required ?? []).map((m) => ({ ...m, _required: true })),
                ...(doctor?.models?.optional ?? []).map((m) => ({ ...m, _required: false })),
              ];
              if (!allModels.length) return <div className="nle-empty">{uiText.models.empty}</div>;
              return (
                <ul className="nle-track-list">
                  {allModels.map((item) => {
                    const installed = isModelInstalled(item);
                    const statusLabel = installed
                      ? uiText.models.ready
                      : item.status === "broken"
                      ? "破損"
                      : uiText.models.missing;
                    return (
                      <li key={item.name} className="nle-track-item">
                        <span className="nle-track-item__name">
                          {item.name}
                          {item._required && <span style={{ color: "#e55", marginLeft: 4, fontSize: "0.8em" }}>*</span>}
                        </span>
                        <span className="nle-track-item__meta" style={{ color: installed ? "#4caf50" : item.status === "broken" ? "#e55" : "#999" }}>
                          {statusLabel}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              );
            })()}
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
                  className={`nle-preview-stage__video${mosaicPreviewEnabled ? " nle-preview-stage__video--hidden" : ""}`}
                  src={previewSrc}
                  onTimeUpdate={handleVideoTimeUpdate}
                />
                {currentVideo && (
                  <MosaicPreviewCanvas
                    videoRef={videoRef}
                    tracks={project?.tracks ?? []}
                    currentFrame={currentFrame}
                    videoMeta={currentVideo}
                    enabled={mosaicPreviewEnabled}
                    cellPx={exportSettings.mosaic_strength}
                  />
                )}
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
              <button
                className={`nle-btn nle-btn--small nle-preview__mosaic-toggle${mosaicPreviewEnabled ? " nle-preview__mosaic-toggle--active" : ""}`}
                onClick={() => setMosaicPreviewEnabled((v) => !v)}
                title={mosaicPreviewEnabled ? "モザイクプレビューを無効化" : "モザイクプレビューを有効化"}
              >
                {mosaicPreviewEnabled ? "モザイク ON" : "モザイク OFF"}
              </button>
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
                onToggleExportEnabled={() => void handleToggleTrackExportEnabled()}
                onDuplicateTrack={() => void handleDuplicateTrack()}
                onSplitTrack={() => void handleSplitTrack()}
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

      <div className="nle-transport">
        <button className="nle-transport__btn" onClick={() => { setCurrentFrame(0); handleSeekFrame(0); }} title="先頭へ">⏮</button>
        <button className="nle-transport__btn" onClick={() => { const f = Math.max(0, currentFrame - 1); setCurrentFrame(f); handleSeekFrame(f); }} title="1フレーム戻す">⏪</button>
        <button className="nle-transport__btn nle-transport__btn--play" onClick={() => { if (videoRef.current) { videoRef.current.paused ? videoRef.current.play() : videoRef.current.pause(); } }} title="再生 / 一時停止">
          {videoRef.current && !videoRef.current.paused ? "⏸" : "▶"}
        </button>
        <button className="nle-transport__btn" onClick={() => { const max = (currentVideo?.frame_count ?? 1) - 1; const f = Math.min(max, currentFrame + 1); setCurrentFrame(f); handleSeekFrame(f); }} title="1フレーム送る">⏩</button>
        <button className="nle-transport__btn" onClick={() => { const last = (currentVideo?.frame_count ?? 1) - 1; setCurrentFrame(last); handleSeekFrame(last); }} title="末尾へ">⏭</button>
        <span className="nle-transport__time">F{currentFrame}{currentVideo?.fps ? ` / ${(currentFrame / currentVideo.fps).toFixed(2)}s` : ""}</span>
      </div>

      <section className="nle-timeline">
        <TimelineView
          readModel={readModel}
          tracks={project?.tracks ?? null}
          selectedTrackId={selectedTrackId}
          selectedKeyframeFrame={selectedKeyframeFrame}
          currentFrame={currentFrame}
          inFrame={inFrame}
          outFrame={outFrame}
          dangerMarkers={dangerWarnings}
          confirmedDangerMarkers={confirmedDangerFrames}
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

      <JobPanel jobs={visibleJobPanelItems} onCancel={(job) => void handleCancelJob(job)} onDismiss={handleDismissJob} onOpenFolder={handleOpenFolder} />

      {recoveryModalOpen && recoveryCandidates.length ? (
        <div className="guard-modal-backdrop" role="presentation">
          <section className="guard-modal recovery-modal" role="dialog" aria-modal="true" aria-labelledby="recovery-modal-title">
            <p className="eyebrow">Session Recovery</p>
            <h2 id="recovery-modal-title">前回のセッションの復元候補</h2>
            <p className="guard-modal__body">
              未保存のプロジェクト候補が見つかりました。復元する候補を選ぶか、不要な候補を削除してください。
            </p>
            <div className="recovery-modal__list">
              {recoveryCandidates.map((candidate) => {
                const videoPath = candidate.project.video?.source_path ?? "動画なし";
                const updatedAt = new Date(candidate.timestamp).toLocaleString();
                return (
                  <article key={candidate.id} className="recovery-modal__item">
                    <div className="recovery-modal__copy">
                      <strong>{candidate.project.name || uiText.project.untitledName}</strong>
                      <span>{updatedAt}</span>
                      <span>{videoPath}</span>
                    </div>
                    <div className="recovery-modal__actions">
                      <button className="nle-btn nle-btn--accent" onClick={() => restoreRecoverySnapshot(candidate)}>
                        復元
                      </button>
                      <button className="nle-btn nle-btn--cancel" onClick={() => deleteRecoverySnapshot(candidate)}>
                        削除
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
            <div className="guard-modal__actions">
              <button className="nle-btn" onClick={() => setRecoveryModalOpen(false)}>
                また後にする
              </button>
              <button className="nle-btn" onClick={() => setRecoveryModalOpen(false)}>
                閉じる
              </button>
            </div>
          </section>
        </div>
      ) : null}

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
        hasDirectMl={hasDirectMl}
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
        onRecheck={() => void runDoctor()}
        onClose={() => setDetectModalOpen(false)}
      />

      <ExportSettingsModal
        open={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        onExport={(s) => void handleExportWithSettings(s)}
        defaultSettings={exportSettings}
      />

      {/* 全体検出前の上書き確認モーダル */}
      {overwriteConfirmOpen && overwriteConfirmInfo && (
        <div className="guard-modal-backdrop" role="presentation">
          <section className="guard-modal" role="dialog" aria-modal="true" aria-labelledby="overwrite-confirm-title">
            <h2 id="overwrite-confirm-title">既存トラックの扱い</h2>
            <p className="guard-modal__body">
              {overwriteConfirmInfo.manualCount > 0
                ? `${overwriteConfirmInfo.trackCount} 件のトラックが存在します（手動編集 ${overwriteConfirmInfo.manualCount} 件含む）。再検出時の処理を選択してください。`
                : `${overwriteConfirmInfo.trackCount} 件の AI 検出トラックが存在します。再検出すると上書きされます。`}
            </p>
            <div className="guard-modal__actions" style={{ flexDirection: "column", gap: 8 }}>
              <button
                className="nle-btn nle-btn--accent"
                onClick={() => overwriteResolveRef.current?.("protected")}
              >
                手動編集を保護して再検出
              </button>
              {overwriteConfirmInfo.manualCount > 0 && (
                <button
                  className="nle-btn nle-btn--cancel"
                  onClick={() => overwriteResolveRef.current?.("overwrite_all")}
                >
                  全上書きで再検出（手動編集も削除）
                </button>
              )}
              <button
                className="nle-btn"
                onClick={() => overwriteResolveRef.current?.("cancel")}
              >
                キャンセル
              </button>
            </div>
          </section>
        </div>
      )}

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
