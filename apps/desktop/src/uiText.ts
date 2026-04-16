export type UiLanguage = "ja" | "en";

export type UiText = {
  app: {
    title: string;
    menu: string;
    newProject: string;
    openProject: string;
    saveProject: string;
    saveProjectAs: string;
    backendReady: string;
    backendNeedsSetup: string;
  };
  actions: {
    openVideo: string;
    setup: string;
    fetchModels: string;
    detect: string;
    export: string;
    cancel: string;
    recheck: string;
    checking: string;
  };
  activity: {
    idle: string;
    notice: string;
    ready: string;
    setupRecommended: string;
    doctorFailed: string;
    newProjectReady: string;
    projectLoaded: string;
    projectSaved: string;
    videoReady: string;
    detectStarted: string;
    detectCompleted: string;
    exportStarted: string;
    exportCompleted: string;
    exportFailed: string;
    savingBeforeEdit: string;
    savingBeforeExport: string;
    jobStarted: (jobKind: string) => string;
  };
  panels: {
    project: string;
    models: string;
    environment: string;
    detect: string;
    export: string;
    timeline: string;
    trackDetail: string;
    keyframeDetail: string;
  };
  project: {
    untitledName: string;
    name: string;
    path: string;
    tracks: string;
    state: string;
    none: string;
    unsaved: string;
    dirty: string;
    saved: string;
  };
  models: {
    ready: string;
    missing: string;
    empty: string;
  };
  preview: {
    emptyTitle: string;
    emptyHint: string;
    frames: string;
    sourcePath: string;
  };
  detect: {
    idle: string;
  };
  export: {
    idle: string;
    preparing: string;
  };
  timeline: {
    empty: string;
  };
  states: {
    ready: string;
    missing: string;
    cuda: string;
    cpuFallback: string;
  };
  jobs: {
    panelTitle: string;
    stage: string;
    progress: string;
    indeterminate: string;
    cancelling: string;
    detectTitle: string;
    exportTitle: string;
  };
  jobStages: {
    queued: string;
    starting: string;
    cancelling: string;
    cancelled: string;
    completed: string;
    failed: string;
    runtime_dirs: string;
    doctor: string;
    ffmpeg: string;
    gpu_probe: string;
    model_check: string;
    model_fetch: string;
    downloading: string;
    verifying: string;
    metadata_probe: string;
    preview_probe: string;
    preview_init: string;
    preparing: string;
    loading_model: string;
    probing_video: string;
    sampling_frames: string;
    running_inference: string;
    building_tracks: string;
    rendering_frames: string;
    muxing_audio: string;
    finalizing: string;
  };
  errors: {
    saveBeforeExport: string;
  };
};

const uiTextJa: UiText = {
  app: {
    title: "Auto Mosaic",
    menu: "File",
    newProject: "新規プロジェクト",
    openProject: "プロジェクトを開く",
    saveProject: "保存",
    saveProjectAs: "名前を付けて保存",
    backendReady: "バックエンド準備完了",
    backendNeedsSetup: "初期セットアップが必要",
  },
  actions: {
    openVideo: "動画を開く",
    setup: "初期環境セットアップ",
    fetchModels: "不足モデル取得",
    detect: "AI自動検出",
    export: "書き出し",
    cancel: "中断",
    recheck: "再確認",
    checking: "確認中...",
  },
  activity: {
    idle: "待機中です。",
    notice: "長時間処理の進捗は共通 Job Panel に表示されます。",
    ready: "初期環境の確認が完了しました。",
    setupRecommended: "初期環境に不足があります。セットアップを実行してください。",
    doctorFailed: "環境確認に失敗しました。",
    newProjectReady: "新しいプロジェクトを作成しました。",
    projectLoaded: "プロジェクトを読み込みました。",
    projectSaved: "プロジェクトを保存しました。",
    videoReady: "動画を読み込みました。",
    detectStarted: "AI自動検出を開始しました。",
    detectCompleted: "AI自動検出が完了しました。",
    exportStarted: "書き出しを開始しました。",
    exportCompleted: "書き出しが完了しました。",
    exportFailed: "書き出しに失敗しました。",
    savingBeforeEdit: "編集の前にプロジェクトを保存しています...",
    savingBeforeExport: "書き出しの前にプロジェクトを保存しています...",
    jobStarted: (jobKind: string) => `${jobKind} を開始しました。`,
  },
  panels: {
    project: "プロジェクト",
    models: "モデル状態",
    environment: "環境",
    detect: "検出ジョブ",
    export: "書き出しジョブ",
    timeline: "タイムライン",
    trackDetail: "トラック詳細",
    keyframeDetail: "キーフレーム詳細",
  },
  project: {
    untitledName: "Untitled Project",
    name: "名前",
    path: "パス",
    tracks: "トラック数",
    state: "状態",
    none: "なし",
    unsaved: "未保存",
    dirty: "未保存の変更あり",
    saved: "保存済み",
  },
  models: {
    ready: "利用可能",
    missing: "不足",
    empty: "必要モデル情報はまだ取得されていません。",
  },
  preview: {
    emptyTitle: "動画を開いてプレビューを開始",
    emptyHint: "日本語パスの動画でも UTF-8 契約を維持したまま読み込みます。",
    frames: "フレーム数",
    sourcePath: "ソース",
  },
  detect: {
    idle: "検出ジョブはありません。",
  },
  export: {
    idle: "書き出しジョブはありません。",
    preparing: "書き出しを準備中です。",
  },
  timeline: {
    empty: "トラックはまだありません。",
  },
  states: {
    ready: "準備完了",
    missing: "不足",
    cuda: "CUDA 利用可",
    cpuFallback: "CPU fallback",
  },
  jobs: {
    panelTitle: "ジョブ進捗",
    stage: "ステージ",
    progress: "進捗",
    indeterminate: "進捗率取得中",
    cancelling: "中断要求を送信しました。",
    detectTitle: "AI自動検出",
    exportTitle: "動画を書き出し中",
  },
  jobStages: {
    queued: "待機中",
    starting: "開始中",
    cancelling: "中断中",
    cancelled: "中断済み",
    completed: "完了",
    failed: "失敗",
    runtime_dirs: "書き込み先を確認中",
    doctor: "環境確認中",
    ffmpeg: "ffmpeg / ffprobe を確認中",
    gpu_probe: "GPU を確認中",
    model_check: "必須モデルを確認中",
    model_fetch: "不足モデルを取得中",
    downloading: "ダウンロード中",
    verifying: "検証中",
    metadata_probe: "動画メタ情報を取得中",
    preview_probe: "先頭フレームを準備中",
    preview_init: "プレビューを初期化中",
    preparing: "準備中",
    loading_model: "検出モデルを読み込み中",
    probing_video: "動画を確認中",
    sampling_frames: "フレームをサンプリング中",
    running_inference: "推論実行中",
    building_tracks: "トラックを構築中",
    rendering_frames: "フレームを書き出し中",
    muxing_audio: "音声を結合中",
    finalizing: "完了処理中",
  },
  errors: {
    saveBeforeExport: "書き出しの前にプロジェクトを保存してください。",
  },
};

const uiTextEn: UiText = {
  app: {
    title: "Auto Mosaic",
    menu: "File",
    newProject: "New Project",
    openProject: "Open Project",
    saveProject: "Save",
    saveProjectAs: "Save As...",
    backendReady: "Backend ready",
    backendNeedsSetup: "Initial setup required",
  },
  actions: {
    openVideo: "Open Video",
    setup: "Run Initial Setup",
    fetchModels: "Fetch Missing Models",
    detect: "AI Detect",
    export: "Export",
    cancel: "Cancel",
    recheck: "Re-check",
    checking: "Checking...",
  },
  activity: {
    idle: "Idle.",
    notice: "Long-running progress is shown in the shared Job Panel.",
    ready: "Initial environment check completed.",
    setupRecommended: "Initial environment is incomplete. Run setup.",
    doctorFailed: "Environment check failed.",
    newProjectReady: "Created a new project.",
    projectLoaded: "Loaded the project.",
    projectSaved: "Saved the project.",
    videoReady: "Loaded the video.",
    detectStarted: "AI detection started.",
    detectCompleted: "AI detection completed.",
    exportStarted: "Export started.",
    exportCompleted: "Export completed.",
    exportFailed: "Export failed.",
    savingBeforeEdit: "Saving project before edit...",
    savingBeforeExport: "Saving project before export...",
    jobStarted: (jobKind: string) => `Started ${jobKind}.`,
  },
  panels: {
    project: "Project",
    models: "Models",
    environment: "Environment",
    detect: "Detect Jobs",
    export: "Export Jobs",
    timeline: "Timeline",
    trackDetail: "Track Detail",
    keyframeDetail: "Keyframe Detail",
  },
  project: {
    untitledName: "Untitled Project",
    name: "Name",
    path: "Path",
    tracks: "Tracks",
    state: "State",
    none: "none",
    unsaved: "unsaved",
    dirty: "Unsaved changes",
    saved: "Saved",
  },
  models: {
    ready: "available",
    missing: "missing",
    empty: "Required model info not loaded yet.",
  },
  preview: {
    emptyTitle: "Open a video to start preview",
    emptyHint: "Non-ASCII paths are loaded under the UTF-8 contract.",
    frames: "Frames",
    sourcePath: "Source",
  },
  detect: {
    idle: "No detect jobs.",
  },
  export: {
    idle: "No export jobs.",
    preparing: "Preparing export...",
  },
  timeline: {
    empty: "No tracks yet.",
  },
  states: {
    ready: "ready",
    missing: "missing",
    cuda: "CUDA available",
    cpuFallback: "CPU fallback",
  },
  jobs: {
    panelTitle: "Job progress",
    stage: "Stage",
    progress: "Progress",
    indeterminate: "Acquiring progress",
    cancelling: "Cancellation requested.",
    detectTitle: "AI detection",
    exportTitle: "Exporting video",
  },
  jobStages: {
    queued: "Queued",
    starting: "Starting",
    cancelling: "Cancelling",
    cancelled: "Cancelled",
    completed: "Completed",
    failed: "Failed",
    runtime_dirs: "Checking runtime dirs",
    doctor: "Checking environment",
    ffmpeg: "Checking ffmpeg / ffprobe",
    gpu_probe: "Probing GPU",
    model_check: "Checking required models",
    model_fetch: "Fetching missing models",
    downloading: "Downloading",
    verifying: "Verifying",
    metadata_probe: "Probing video metadata",
    preview_probe: "Preparing first frame",
    preview_init: "Initializing preview",
    preparing: "Preparing",
    loading_model: "Loading detection model",
    probing_video: "Probing video",
    sampling_frames: "Sampling frames",
    running_inference: "Running inference",
    building_tracks: "Building tracks",
    rendering_frames: "Rendering frames",
    muxing_audio: "Muxing audio",
    finalizing: "Finalizing",
  },
  errors: {
    saveBeforeExport: "Save the project before exporting.",
  },
};

export function getUiText(language: UiLanguage): UiText {
  return language === "en" ? uiTextEn : uiTextJa;
}

/** Default export is the Japanese dictionary for backwards compatibility. */
export const uiText: UiText = uiTextJa;
