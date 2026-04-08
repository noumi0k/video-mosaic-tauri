export type DetectorBackendKey =
  | "nudenet_320n"
  | "nudenet_640m"
  | "erax_v1_1"
  | "composite";

// P1-1: product-facing category set. Only these 5 items should appear in the
// UI. What each backend can actually detect is declared on DetectorOption via
// `supportedCategories`; the modal greys out anything not in that set.
export type DetectorCategoryKey =
  | "male_genitalia"
  | "female_genitalia"
  | "intercourse"
  | "male_face"
  | "female_face";

export type DetectorAvailability = {
  name: string;
  exists: boolean;
  downloadable?: boolean;
  source?: string;
  note?: string | null;
  path?: string;
};

export type DetectorOption = {
  key: DetectorBackendKey;
  title: string;
  variant: string;
  required: boolean;
  // bundled: true means the model ships with the app and needs no download.
  bundled?: boolean;
  modelNames: string[];
  description: string;
  supportedCategories: DetectorCategoryKey[];
  // P1-3: composite backends need ALL constituent models present before they
  // can be offered as "available". Single-backend entries keep the legacy
  // "any one model present = available" behavior.
  requiresAllModels?: boolean;
};

export type DetectorOptionStatus = DetectorOption & {
  available: boolean;
  missingCount: number;
  statusLabel: string;
  reason: string;
};

export const DETECTOR_OPTIONS: DetectorOption[] = [
  {
    key: "nudenet_320n",
    title: "NudeNet 320n",
    variant: "標準",
    required: true,
    bundled: true,
    modelNames: ["320n.onnx"],
    description: "初回導線で使う既定の検出モデルです。",
    // NudeNet v3 classes map cleanly to genitalia + female face only.
    supportedCategories: ["male_genitalia", "female_genitalia", "female_face"],
  },
  {
    key: "nudenet_640m",
    title: "NudeNet 640m",
    variant: "高精度",
    required: false,
    modelNames: ["640m.onnx"],
    description: "320n より高精度ですが、推論は重めです。",
    supportedCategories: ["male_genitalia", "female_genitalia", "female_face"],
  },
  {
    key: "erax_v1_1",
    title: "EraX v1.1",
    variant: "代替",
    required: false,
    modelNames: ["erax_nsfw_yolo11s.onnx"],
    description: "追加の代替モデルです。ONNX ファイルが必要です (PT 取得後に変換)。",
    // EraX covers genitalia + intercourse but not faces.
    supportedCategories: ["male_genitalia", "female_genitalia", "intercourse"],
  },
  {
    key: "composite",
    title: "複合 (NudeNet + EraX)",
    variant: "推奨",
    required: false,
    // Composite needs both NudeNet and EraX ONNX available at runtime; the
    // frame sampler shares one pass across both detectors.
    modelNames: ["320n.onnx", "erax_nsfw_yolo11s.onnx"],
    description: "顔は NudeNet、性交/接合部は EraX で分担。5 カテゴリを広くカバー。",
    supportedCategories: [
      "male_genitalia",
      "female_genitalia",
      "intercourse",
      "female_face",
    ],
    requiresAllModels: true,
  },
];

export const DETECTOR_CATEGORIES: Array<{
  key: DetectorCategoryKey;
  label: string;
  description: string;
}> = [
  {
    key: "male_genitalia",
    label: "男性器",
    description: "男性性器の露出を対象にします。",
  },
  {
    key: "female_genitalia",
    label: "女性器",
    description: "女性性器の露出を対象にします。",
  },
  {
    key: "intercourse",
    label: "性交 / 接合部",
    description: "接合部や性交シーンを対象にします。対応モデルでのみ検出されます。",
  },
  {
    key: "male_face",
    label: "男性の顔",
    description: "男性の顔を対象にします。対応モデルでのみ検出されます。",
  },
  {
    key: "female_face",
    label: "女性の顔",
    description: "女性の顔を対象にします。",
  },
];

export function isCategorySupportedByBackend(
  backend: DetectorBackendKey,
  category: DetectorCategoryKey,
): boolean {
  const option = DETECTOR_OPTIONS.find((item) => item.key === backend);
  if (!option) return false;
  return option.supportedCategories.includes(category);
}

export function unsupportedCategoryReason(backend: DetectorBackendKey): string {
  const option = DETECTOR_OPTIONS.find((item) => item.key === backend);
  if (!option) return "選択中のモデルでは未対応です。";
  return `${option.title} では未対応のカテゴリです。別の検出モデルを選択してください。`;
}

export function buildDetectorOptionStatuses(
  availableModels: DetectorAvailability[],
): DetectorOptionStatus[] {
  return DETECTOR_OPTIONS.map((option) => {
    const related = availableModels.filter((item) => option.modelNames.includes(item.name));
    const existingCount = related.filter((item) => item.exists).length;
    // Composite backends need every constituent model; single-backend entries
    // stay happy with any one of their accepted filenames being present.
    const available = option.requiresAllModels
      ? existingCount === option.modelNames.length && option.modelNames.length > 0
      : related.some((item) => item.exists);
    const missingCount = option.modelNames.length - existingCount;

    return {
      ...option,
      available,
      missingCount,
      statusLabel: option.bundled ? "同梱済み" : available ? "利用可能" : "未取得",
      reason: available
        ? option.description
        : related.find((item) => item.note)?.note ??
          "モデル取得後にこの検出器を選択できます。",
    };
  });
}
