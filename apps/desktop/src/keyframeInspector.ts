import type { CreateKeyframePayload, Keyframe, KeyframeShapeType } from "./types";

export type InspectorPayload = Omit<CreateKeyframePayload, "project_path" | "track_id">;

export type KeyframeInspectorState = {
  shapeType: KeyframeShapeType;
  source: "manual" | "detector";
  frameIndexText: string;
  bboxText: string;
  pointsText: string;
};

export type KeyframeInspectorFieldErrors = {
  frameIndex?: string;
  bbox?: string;
  points?: string;
};

export type ParsedInspectorInput =
  | { error: string; fieldErrors: KeyframeInspectorFieldErrors; value?: undefined }
  | { error?: undefined; fieldErrors: KeyframeInspectorFieldErrors; value: InspectorPayload };

export function buildInspectorState(
  keyframeDocument: Keyframe | null,
  suggestedCreateFrame: number,
): KeyframeInspectorState {
  return {
    shapeType: keyframeDocument?.shape_type ?? "polygon",
    source: (keyframeDocument?.source as "manual" | "detector" | undefined) ?? "manual",
    frameIndexText: String(keyframeDocument?.frame_index ?? suggestedCreateFrame),
    bboxText: keyframeDocument?.bbox.join(", ") ?? "0.25, 0.25, 0.2, 0.2",
    pointsText:
      keyframeDocument !== null
        ? JSON.stringify(keyframeDocument.points)
        : "[[0.25, 0.25], [0.45, 0.25], [0.45, 0.45], [0.25, 0.45]]",
  };
}

export function syncInspectorState(
  previous: KeyframeInspectorState,
  nextBase: KeyframeInspectorState,
  options: { preserveFrameIndex: boolean },
): KeyframeInspectorState {
  return {
    ...nextBase,
    frameIndexText: options.preserveFrameIndex ? previous.frameIndexText : nextBase.frameIndexText,
  };
}

export function parseInspectorInput(
  state: KeyframeInspectorState,
  keyframeDocument: Keyframe | null,
): ParsedInspectorInput {
  const frameIndex = Number(state.frameIndexText.trim());
  if (!Number.isInteger(frameIndex) || frameIndex < 0) {
    return {
      error: "フレーム番号は 0 以上の整数で入力してください。",
      fieldErrors: { frameIndex: "0 以上の整数を入力してください。" },
    };
  }

  const bbox = state.bboxText.split(",").map((item) => Number(item.trim()));
  if (bbox.length !== 4 || bbox.some((item) => Number.isNaN(item))) {
    return {
      error: "BBox は x, y, w, h の 4 値で入力してください。",
      fieldErrors: { bbox: "x, y, w, h の 4 値を入力してください。" },
    };
  }

  let points: number[][];
  if (state.shapeType === "polygon") {
    try {
      points = JSON.parse(state.pointsText) as number[][];
    } catch {
      return {
        error: "頂点 JSON を正しく読み取れませんでした。",
        fieldErrors: { points: "[[0.1,0.1],[0.2,0.1],[0.2,0.2]] のような JSON を入力してください。" },
      };
    }
  } else {
    points = keyframeDocument?.points ?? [
      [bbox[0]!, bbox[1]!],
      [bbox[0]! + bbox[2]!, bbox[1]! + bbox[3]!],
    ];
  }

  return {
    fieldErrors: {},
    value: {
      frame_index: frameIndex,
      source: state.source,
      shape_type: state.shapeType,
      bbox,
      points,
    },
  };
}

export function getBBoxLabel(shapeType: KeyframeShapeType) {
  return shapeType === "ellipse" ? "楕円 BBox [x, y, w, h]" : "BBox [x, y, w, h]";
}

export function getFrameIndexLabel(mode: "create" | "update") {
  return mode === "create" ? "新規キーフレームのフレーム番号" : "編集中キーフレームのフレーム番号";
}

export function getPrimaryActionLabel(shapeType: KeyframeShapeType, mode: "create" | "update", saving: boolean) {
  if (saving) return "保存中...";
  if (mode === "create") {
    return shapeType === "ellipse" ? "楕円キーフレームを作成" : "ポリゴンキーフレームを作成";
  }
  return shapeType === "ellipse" ? "楕円の変更を保存" : "ポリゴンの変更を保存";
}

export function getSecondaryCreateLabel(shapeType: KeyframeShapeType, saving: boolean) {
  if (saving) return "保存中...";
  return shapeType === "ellipse" ? "楕円キーフレームを追加" : "ポリゴンキーフレームを追加";
}
