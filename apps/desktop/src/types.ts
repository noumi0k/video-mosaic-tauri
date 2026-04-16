export type CommandResponse<T> = {
  ok: boolean;
  command: string;
  data: T;
  error: unknown;
  warnings: string[];
};

export type CommandErrorDetails = Record<string, unknown>;

export type CommandError = {
  code?: string;
  message?: string;
  details?: CommandErrorDetails;
};

export type VideoMetadata = {
  source_path: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_sec: number;
  readable: boolean;
  warnings: string[];
  errors: string[];
  first_frame_shape: number[] | null;
};

export type KeyframeShapeType = "polygon" | "ellipse";

export type Keyframe = {
  frame_index: number;
  shape_type: KeyframeShapeType;
  points: number[][];
  bbox: number[];
  confidence: number;
  source: string;
  rotation: number;
  opacity: number;
  expand_px: number | null;
  feather: number | null;
  is_locked: boolean;
  contour_points: number[][];
  /** Optional — absent in legacy payloads (undefined/null both treated as absent). */
  source_detail?: string | null;
};

export type MaskSegment = {
  start_frame: number;
  end_frame: number;
  state: "confirmed" | "held" | "predicted" | "interpolated" | "uncertain" | "active" | "detected";
};

export type MaskTrack = {
  track_id: string;
  label: string;
  state: string;
  source: string;
  visible: boolean;
  export_enabled: boolean;
  keyframes: Keyframe[];
  label_group: string;
  user_locked: boolean;
  user_edited: boolean;
  confidence: number;
  style: Record<string, unknown>;
  segments: MaskSegment[];
};

export type ProjectDocument = {
  project_id: string;
  version: string;
  schema_version: number;
  name: string;
  project_path: string | null;
  video: VideoMetadata | null;
  tracks: MaskTrack[];
  detector_config: Record<string, unknown>;
  export_preset: ProjectExportPreset;
  paths: {
    project_dir: string | null;
    export_dir: string | null;
    training_dir: string | null;
  };
};

export type TrackSummary = {
  index: number;
  track_id: string;
  label: string;
  visible: boolean;
  export_enabled: boolean;
  state: string;
  source: string;
  start_frame: number | null;
  end_frame: number | null;
  keyframe_count: number;
  label_group: string;
  user_locked: boolean;
  user_edited: boolean;
  confidence: number;
  keyframes: KeyframeSummary[];
};

export type KeyframeSummary = {
  frame_index: number;
  source: string;
  shape_type: KeyframeShapeType;
};

export type ProjectReadModel = {
  project_id: string;
  project_name: string;
  project_path: string | null;
  video: VideoMetadata | null;
  track_summaries: TrackSummary[];
  track_count: number;
};

export type EditorMode = "read-only" | "select" | "inspect";

export type EditableKeyframe = {
  frame_index: number;
  shape_type: KeyframeShapeType;
  source: string;
};

export type EditableTrack = {
  track_id: string;
  label: string;
  state: string;
  source: string;
  visible: boolean;
  export_enabled: boolean;
  keyframes: EditableKeyframe[];
};

export type EditorSessionState = {
  selectedTrackId: string | null;
  selectedKeyframeFrame: number | null;
  editorMode: EditorMode;
  isDirty: boolean;
  pendingProjectPath: string | null;
  writeTracks: EditableTrack[];
};

export type EditorSelection = {
  track_id: string | null;
  frame_index: number | null;
};

export type MutationCommandData = {
  project_path: string;
  project: ProjectDocument;
  read_model: ProjectReadModel;
  selection: EditorSelection;
};

export type ExportAudioMode = "mux_if_possible" | "video_only";

export type ExportOptions = {
  mosaic_strength: number;
  audio_mode: ExportAudioMode;
};

export type ProjectExportPreset = ExportOptions & {
  last_output_dir: string | null;
};

export type ExportJobStatus = {
  phase: "preparing" | "rendering_frames" | "muxing_audio" | "completed" | "cancelled" | "failed";
  progress: number;
  message: string;
  frames_written: number;
  total_frames: number | null;
  audio_mode: ExportAudioMode | null;
  audio_status: string | null;
  output_path: string | null;
  warnings: string[];
};

export type ExportQueueItemState =
  | "queued"
  | "running"
  | "interrupted"
  | "completed"
  | "failed"
  | "cancelled";

export type ExportQueueItem = {
  queue_id: string;
  job_id: string;
  project_path: string;
  project_name: string;
  output_path: string;
  options: ExportOptions;
  state: ExportQueueItemState;
  progress: number;
  status_text: string;
  warnings: string[];
  audio_status: string | null;
};

export type DetectJobState =
  | "idle"
  | "queued"
  | "starting"
  | "running"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "interrupted";

export type DetectJobSummary = {
  job_id: string;
  state: DetectJobState;
  stage: string;
  percent: number;
  message: string;
  current: number;
  total: number;
  error?: CommandError | null;
  result_available?: boolean;
  has_result?: boolean;
  has_cancel_flag?: boolean;
  result_size_bytes?: number;
  created_at?: string;
  updated_at?: string;
};

export type RuntimeJobState =
  | "queued"
  | "starting"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed";

export type RuntimeJobSummary = {
  job_id: string;
  job_kind: "setup_environment" | "fetch_models" | "open_video" | "setup_erax_convert";
  state: RuntimeJobState;
  title: string;
  stage: string;
  message: string;
  progress_percent: number | null;
  is_indeterminate: boolean;
  can_cancel: boolean;
  current?: number;
  total?: number;
  artifact_path?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  result_available?: boolean;
  created_at?: string;
  updated_at?: string;
  finished_at?: string;
  model_name?: string;
  bytes_downloaded?: number;
  bytes_total?: number | null;
};

export type JobProgressView = {
  job_id: string;
  job_kind: string;
  state: "queued" | "starting" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  title: string;
  stage: string;
  message: string;
  progress_percent: number | null;
  is_indeterminate: boolean;
  can_cancel: boolean;
  subtitle: string;
  output_path?: string | null;
};

export type SelectKeyframePayload = {
  project_path: string;
  track_id: string;
  frame_index: number;
};

export type CreateKeyframePayload = {
  project_path: string;
  track_id: string;
  frame_index: number;
  source: string;
  shape_type: KeyframeShapeType;
  bbox?: number[];
  points?: number[][];
};

export type UpdateKeyframePayload = {
  project_path: string;
  track_id: string;
  frame_index: number;
  patch: Partial<Pick<Keyframe, "source" | "shape_type" | "bbox" | "points">>;
};

export type DeleteKeyframePayload = {
  project_path: string;
  track_id: string;
  frame_index: number;
};

export type MoveKeyframePayload = {
  project_path: string;
  track_id: string;
  frame_index: number;
  target_frame_index: number;
};

export type CreateTrackPayload = {
  project_path: string;
  shape_type: KeyframeShapeType;
  label?: string;
  frame_index?: number;
  bbox?: number[];
  points?: number[][];
  label_group?: string;
};

export type UpdateTrackPayload = {
  project_path: string;
  track_id: string;
  patch: Partial<Pick<MaskTrack, "label" | "state" | "source" | "label_group" | "user_locked" | "user_edited">> & {
    visible?: boolean;
    export_enabled?: boolean;
  };
};
