import React from "react";

import {
  buildDetectorOptionStatuses,
  DETECTOR_CATEGORIES,
  isCategorySupportedByBackend,
  isModelInstalled,
  unsupportedCategoryReason,
  type DetectorAvailability,
  type DetectorBackendKey,
  type DetectorCategoryKey,
} from "../detectorCatalog";

type Props = {
  open: boolean;
  selectedBackend: DetectorBackendKey;
  selectedDevice: string;
  threshold: number;
  sampleEvery: number;
  maxSamples: number;
  inferenceResolution: number;
  batchSize: number;
  contourMode: string;
  vramSavingMode: boolean;
  overwriteManualTracks: boolean;
  trackCount: number;
  manualTrackCount: number;
  selectedCategories: DetectorCategoryKey[];
  availableModels: DetectorAvailability[];
  requiredModels: DetectorAvailability[];
  optionalModels: DetectorAvailability[];
  hasCuda: boolean;
  hasDirectMl: boolean;
  hasSam2: boolean;
  onnxVersion: string | null;
  modelFetchBusy: boolean;
  eraxState: "missing" | "downloaded_pt" | "ready";
  eraxConvertible: boolean;
  eraxConvertBusy: boolean;
  onSelectBackend: (value: DetectorBackendKey) => void;
  onSelectDevice: (value: string) => void;
  onThresholdChange: (value: number) => void;
  onSampleEveryChange: (value: number) => void;
  onMaxSamplesChange: (value: number) => void;
  onInferenceResolutionChange: (value: number) => void;
  onBatchSizeChange: (value: number) => void;
  onContourModeChange: (value: string) => void;
  onVramSavingModeChange: (value: boolean) => void;
  onOverwriteManualTracksChange: (value: boolean) => void;
  onToggleCategory: (value: DetectorCategoryKey) => void;
  onRun: () => void;
  onFetchRequired: () => void;
  onFetchErax: () => void;
  onRecheck: () => void;
  onClose: () => void;
};

export function DetectorSettingsModal(props: Props) {
  if (!props.open) {
    return null;
  }

  const detectorOptions = buildDetectorOptionStatuses(props.availableModels);
  const selectedOption =
    detectorOptions.find((option) => option.key === props.selectedBackend) ?? detectorOptions[0];
  const missingRequiredCount = props.requiredModels.filter((item) => !isModelInstalled(item)).length;
  const missingOptionalCount = props.optionalModels.filter((item) => !isModelInstalled(item)).length;

  return (
    <div className="guard-modal-backdrop" role="presentation">
      <section className="guard-modal detect-modal" role="dialog" aria-modal="true" aria-labelledby="detect-modal-title">
        <p className="eyebrow">AI Detect</p>
        <h2 id="detect-modal-title">検出設定</h2>

        <div className="detect-modal__statusbar">
          <div className={`detect-modal__status-chip detect-modal__status-chip--${props.hasCuda ? "ready" : "warning"}`}>
            {props.hasCuda ? "GPU 利用可能 (CUDA)" : props.hasDirectMl ? "GPU 利用可能 (DirectML)" : "CPU fallback"}
          </div>
          <div className={`detect-modal__status-chip detect-modal__status-chip--${missingRequiredCount === 0 ? "ready" : "warning"}`}>
            必須モデル: {missingRequiredCount === 0 ? "OK" : `${missingRequiredCount} 件不足`}
          </div>
          <div className={`detect-modal__status-chip detect-modal__status-chip--${missingOptionalCount === 0 ? "neutral" : "warning"}`}>
            任意モデル: {missingOptionalCount === 0 ? "OK" : `${missingOptionalCount} 件未導入`}
          </div>
          <div className={`detect-modal__status-chip detect-modal__status-chip--${props.hasSam2 ? "ready" : "warning"}`}>
            SAM2: {props.hasSam2 ? "利用可能" : "未導入 / フォールバック"}
          </div>
          {props.onnxVersion ? (
            <div className="detect-modal__status-chip detect-modal__status-chip--neutral">
              ONNX Runtime {props.onnxVersion}
            </div>
          ) : null}
        </div>

        <div className="detect-modal__section">
          <div className="detect-modal__section-header">
            <span>推論デバイス</span>
            <span className="detect-modal__section-note">GPU が使えない環境でも CPU で継続できます。</span>
          </div>
          <div className="detect-modal__device-grid">
            <button
              className={`detect-modal__choice ${props.selectedDevice === "auto" ? "detect-modal__choice--selected" : ""}`}
              onClick={() => props.onSelectDevice("auto")}
              type="button"
            >
              <strong>自動</strong>
              <span>{props.hasCuda || props.hasDirectMl ? "利用可能な GPU を優先します" : "CPU で実行します"}</span>
            </button>
            <button
              className={`detect-modal__choice ${props.selectedDevice === "cuda" ? "detect-modal__choice--selected" : ""}`}
              onClick={() => props.onSelectDevice("cuda")}
              disabled={!props.hasCuda}
              type="button"
            >
              <strong>CUDA</strong>
              <span>{props.hasCuda ? "GPU で高速に推論します" : "この環境では利用できません"}</span>
            </button>
            <button
              className={`detect-modal__choice ${props.selectedDevice === "cpu" ? "detect-modal__choice--selected" : ""}`}
              onClick={() => props.onSelectDevice("cpu")}
              type="button"
            >
              <strong>CPU</strong>
              <span>互換性優先で実行します</span>
            </button>
          </div>
        </div>

        <div className="detect-modal__section">
          <div className="detect-modal__section-header">
            <span>検出モデル</span>
            <span className="detect-modal__section-note">必須モデルと任意モデルを分けて表示します。</span>
          </div>
          <div className="detect-modal__model-groups">
            <div className="detect-modal__model-group">
              <div className="detect-modal__group-title">必須</div>
              {detectorOptions.filter((item) => item.required).map((option) => (
                <button
                  key={option.key}
                  className={`detect-modal__model-card ${props.selectedBackend === option.key ? "detect-modal__model-card--selected" : ""}`}
                  onClick={() => props.onSelectBackend(option.key)}
                  disabled={!option.available}
                  type="button"
                >
                  <div className="detect-modal__model-topline">
                    <strong>{option.title}</strong>
                    <span className="detect-modal__model-state detect-modal__model-state--ready">
                      {option.statusLabel}
                    </span>
                  </div>
                  <div className="detect-modal__model-subline">{option.variant}</div>
                  <div className="detect-modal__model-description">{option.reason}</div>
                </button>
              ))}
            </div>
            <div className="detect-modal__model-group">
              <div className="detect-modal__group-title">任意</div>
              {detectorOptions.filter((item) => !item.required).map((option) => {
                const isErax = option.key === "erax_v1_1";
                const eraxStatusLabel = isErax
                  ? props.eraxState === "ready"
                    ? "利用可能"
                    : props.eraxState === "downloaded_pt"
                      ? "PT 導入済み"
                      : "未導入"
                  : option.statusLabel;
                const eraxStateClass = isErax
                  ? props.eraxState === "ready"
                    ? "ready"
                    : "warning"
                  : option.available
                    ? "ready"
                    : "warning";
                return (
                  <div key={option.key} className="detect-modal__model-card-wrap">
                    <button
                      className={`detect-modal__model-card ${props.selectedBackend === option.key ? "detect-modal__model-card--selected" : ""}`}
                      onClick={() => props.onSelectBackend(option.key)}
                      disabled={!option.available}
                      type="button"
                    >
                      <div className="detect-modal__model-topline">
                        <strong>{option.title}</strong>
                        <span className={`detect-modal__model-state detect-modal__model-state--${eraxStateClass}`}>
                          {eraxStatusLabel}
                        </span>
                      </div>
                      <div className="detect-modal__model-subline">{option.variant}</div>
                      <div className="detect-modal__model-description">{option.reason}</div>
                    </button>
                    {isErax && props.eraxState === "missing" ? (
                      <button
                        className="nle-btn nle-btn--sm"
                        onClick={props.onFetchErax}
                        disabled={props.modelFetchBusy}
                        type="button"
                      >
                        PT を取得
                      </button>
                    ) : null}
                    {isErax && props.eraxState === "downloaded_pt" ? (
                      <>
                        {props.eraxConvertBusy ? (
                          <p className="detect-modal__inline-note">ONNX 自動変換中...</p>
                        ) : props.eraxConvertible ? (
                          <p className="detect-modal__inline-note">ONNX 自動変換を準備中...</p>
                        ) : (
                          <p className="detect-modal__inline-note">
                            ONNX 自動変換には <code>ultralytics</code> が必要です。<code>pip install ultralytics</code> を導入後に再チェックしてください。
                          </p>
                        )}
                      </>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
          {!selectedOption.available ? (
            <p className="detect-modal__warn">
              選択中のモデルは未取得です。近くの「不足モデルを取得」から必須モデルを取得してください。
            </p>
          ) : null}
        </div>

        <div className="detect-modal__section">
          <div className="detect-modal__section-header">
            <span>検出パラメータ</span>
            <span className="detect-modal__section-note">数値入力の並びと単位を揃えています。</span>
          </div>
          <div className="detect-modal__param-grid">
            <label className="detect-modal__param-card">
              <span>検出間隔</span>
              <div className="detect-modal__param-input">
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={props.sampleEvery}
                  onChange={(event) =>
                    props.onSampleEveryChange(Math.max(1, Math.min(30, event.currentTarget.valueAsNumber || 1)))
                  }
                />
                <em>frame</em>
              </div>
            </label>
            <label className="detect-modal__param-card">
              <span>最大サンプル数</span>
              <div className="detect-modal__param-input">
                <input
                  type="number"
                  min={10}
                  max={9999}
                  value={props.maxSamples}
                  onChange={(event) =>
                    props.onMaxSamplesChange(Math.max(10, Math.min(9999, event.currentTarget.valueAsNumber || 120)))
                  }
                />
                <em>frames</em>
              </div>
            </label>
            <label className="detect-modal__param-card">
              <span>推論解像度</span>
              <div className="detect-modal__param-input">
                <select value={props.inferenceResolution} onChange={(event) => props.onInferenceResolutionChange(Number(event.currentTarget.value))}>
                  <option value={320}>320</option>
                  <option value={640}>640</option>
                </select>
                <em>px</em>
              </div>
            </label>
            <label className="detect-modal__param-card">
              <span>バッチサイズ</span>
              <div className="detect-modal__param-input">
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={props.batchSize}
                  onChange={(event) =>
                    props.onBatchSizeChange(Math.max(1, Math.min(16, event.currentTarget.valueAsNumber || 1)))
                  }
                />
                <em>items</em>
              </div>
            </label>
            <label className="detect-modal__param-card detect-modal__param-card--wide">
              <span>信頼度</span>
              <div className="detect-modal__threshold">
                <input
                  type="range"
                  min={0.1}
                  max={0.9}
                  step={0.01}
                  value={props.threshold}
                  onChange={(event) => props.onThresholdChange(parseFloat(event.currentTarget.value))}
                />
                <strong>{props.threshold.toFixed(2)}</strong>
              </div>
            </label>
            <label className="detect-modal__toggle-row">
              <input
                type="checkbox"
                checked={props.vramSavingMode}
                onChange={(event) => props.onVramSavingModeChange(event.currentTarget.checked)}
              />
              <span>VRAM 節約モード</span>
            </label>
            <label className="detect-modal__toggle-row">
              <input
                type="checkbox"
                checked={props.overwriteManualTracks}
                onChange={(event) => props.onOverwriteManualTracksChange(event.currentTarget.checked)}
              />
              <span>手動編集トラックも上書きする</span>
            </label>
          </div>
          {props.trackCount > 0 ? (
            <p className="detect-modal__section-note detect-modal__section-note--hint">
              現在 {props.trackCount} 件のトラックがあります。うち手動編集は {props.manualTrackCount} 件です。
              {props.overwriteManualTracks
                ? " このまま再検出すると手動編集も置き換えます。"
                : " オフのままなら手動編集トラックは保護されます。"}
            </p>
          ) : null}
        </div>

        <div className="detect-modal__section">
          <div className="detect-modal__section-header">
            <span>検出対象カテゴリ</span>
            <span className="detect-modal__section-note">クリック領域を広くして 2 列グリッドで整理しています。</span>
          </div>
          <div className="detect-modal__categories-grid">
            {DETECTOR_CATEGORIES.map((category) => {
              const supported = isCategorySupportedByBackend(props.selectedBackend, category.key);
              const checked = supported && props.selectedCategories.includes(category.key);
              const rowClass = [
                "detect-modal__category-row",
                checked ? "detect-modal__category-row--selected" : "",
                supported ? "" : "detect-modal__category-row--disabled",
              ]
                .filter(Boolean)
                .join(" ");
              const description = supported
                ? category.description
                : unsupportedCategoryReason(props.selectedBackend);
              return (
                <label key={category.key} className={rowClass} aria-disabled={!supported}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!supported}
                    onChange={() => {
                      if (supported) props.onToggleCategory(category.key);
                    }}
                  />
                  <span className="detect-modal__category-copy">
                    <strong>{category.label}</strong>
                    <em>{description}</em>
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        <div className="detect-modal__section">
          <div className="detect-modal__section-header">
            <span>輪郭モード</span>
            <span className="detect-modal__section-note">SAM2 がない場合は標準輪郭へフォールバックします。</span>
          </div>
          <div className="detect-modal__param-grid">
            <label className="detect-modal__param-card detect-modal__param-card--wide">
              <span>輪郭モード</span>
              <div className="detect-modal__param-input">
                <select value={props.contourMode} onChange={(event) => props.onContourModeChange(event.currentTarget.value)}>
                  <option value="none">なし (最速 / 輪郭抽出なし)</option>
                  <option value="fast">高速輪郭 (軽量 / 顔向け)</option>
                  <option value="balanced">標準輪郭 (既定 / 速度と形状のバランス)</option>
                  <option value="quality">高精度輪郭 (重い / SAM2 使用)</option>
                </select>
                <em>mode</em>
              </div>
            </label>
            {!props.hasSam2 && props.contourMode === "quality" ? (
              <p className="detect-modal__section-note detect-modal__section-note--hint">
                SAM2 encoder/decoder が未導入です。「不足モデルを取得」で導入してください。現状のまま実行すると標準輪郭で処理します。
              </p>
            ) : (
              <p className="detect-modal__section-note detect-modal__section-note--hint">
                輪郭抽出に失敗した場合は自動で前段のマスクへ戻ります。高精度輪郭は検出結果が安定している素材向けです。
              </p>
            )}
          </div>
        </div>

        <div className="detect-modal__section detect-modal__section--actions">
          <div className="detect-modal__section-header">
            <span>検出アクション</span>
            <span className="detect-modal__section-note">不足時は取得と再チェックへすぐ進めます。</span>
          </div>
          <div className="guard-modal__actions detect-modal__actions">
            <button className="nle-btn nle-btn--accent" onClick={props.onRun} disabled={!selectedOption.available}>
              検出を開始
            </button>
            <button className="nle-btn nle-btn--gold" onClick={props.onFetchRequired} disabled={props.modelFetchBusy}>
              不足モデルを取得
            </button>
            <button className="nle-btn" onClick={props.onRecheck}>
              再チェック
            </button>
            <button className="nle-btn" onClick={props.onClose}>
              閉じる
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
