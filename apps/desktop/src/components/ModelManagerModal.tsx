import { useEffect } from "react";
import { isModelInstalled, type DetectorAvailability } from "../detectorCatalog";

type InstalledModelEntry = {
  name: string;
  path: string;
  size_bytes: number;
  status: "missing" | "broken" | "installed";
  known: boolean;
  required: boolean;
  description: string | null;
  source_label: string | null;
  model_id: string | null;
};

type DoctorData = {
  ffmpeg?: { found?: boolean; path?: string | null };
  ffprobe?: { found?: boolean; path?: string | null };
  models?: {
    required?: DetectorAvailability[];
    optional?: DetectorAvailability[];
  };
  onnxruntime?: {
    version?: string | null;
    providers?: string[];
    cuda_session_ok?: boolean;
  };
};

type ModelManagerModalProps = {
  open: boolean;
  onClose: () => void;
  doctor: DoctorData | null;
  installedModels: InstalledModelEntry[];
  installedModelDir: string | null;
  onDeleteInstalledModel: (name: string) => void;
  onReloadInstalled: () => void;
  onFetchModels: () => void;
};

function modelStatusLabel(model: DetectorAvailability): string {
  if (isModelInstalled(model)) return "導入済み";
  if (model.status === "broken") return "破損";
  return "未導入";
}

function modelStatusColor(model: DetectorAvailability): string {
  if (isModelInstalled(model)) return "#4caf50";
  if (model.status === "broken") return "#e55";
  return "#999";
}

export function ModelManagerModal({
  open,
  onClose,
  doctor,
  installedModels,
  installedModelDir,
  onDeleteInstalledModel,
  onReloadInstalled,
  onFetchModels,
}: ModelManagerModalProps) {
  useEffect(() => {
    if (!open) return;
    onReloadInstalled();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, onReloadInstalled]);

  if (!open) return null;

  const catalogModels = [
    ...(doctor?.models?.required ?? []).map((model) => ({ ...model, required: true })),
    ...(doctor?.models?.optional ?? []).map((model) => ({ ...model, required: false })),
  ];
  const hasCuda = doctor?.onnxruntime?.cuda_session_ok === true;
  const hasDirectMl = (doctor?.onnxruntime?.providers ?? []).includes("DmlExecutionProvider");
  const gpuLabel = hasCuda ? "CUDA" : hasDirectMl ? "DirectML" : "CPU fallback";

  return (
    <div className="nle-modal-overlay" onClick={onClose}>
      <div
        className="nle-modal model-manager-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-manager-title"
      >
        <div className="model-manager-modal__header">
          <div>
            <h3 id="model-manager-title" style={{ margin: 0 }}>モデル管理</h3>
            <div className="model-manager-modal__subhead">
              実行環境、モデルの取得状況、導入済みファイルをまとめて確認できます。
            </div>
          </div>
          <button className="nle-btn nle-btn--small" onClick={onClose} aria-label="閉じる" type="button">
            閉じる
          </button>
        </div>

        <div className="model-manager-modal__content">
          <section className="model-manager-modal__section">
            <div className="model-manager-modal__section-header">
              <h4>環境情報</h4>
            </div>
            <div className="model-manager-modal__grid">
              <div className="model-manager-modal__cell">
                <span className="model-manager-modal__label">ffmpeg</span>
                <span className="model-manager-modal__value">{doctor?.ffmpeg?.found ? "ready" : "missing"}</span>
              </div>
              <div className="model-manager-modal__cell">
                <span className="model-manager-modal__label">ffprobe</span>
                <span className="model-manager-modal__value">{doctor?.ffprobe?.found ? "ready" : "missing"}</span>
              </div>
              <div className="model-manager-modal__cell">
                <span className="model-manager-modal__label">GPU</span>
                <span className="model-manager-modal__value">{gpuLabel}</span>
              </div>
              <div className="model-manager-modal__cell">
                <span className="model-manager-modal__label">ONNX Runtime</span>
                <span className="model-manager-modal__value">{doctor?.onnxruntime?.version ?? "--"}</span>
              </div>
            </div>
          </section>

          <section className="model-manager-modal__section">
            <div className="model-manager-modal__section-header">
              <h4>カタログモデル</h4>
              <button className="nle-btn nle-btn--small" onClick={onFetchModels} type="button">
                不足モデルを取得
              </button>
            </div>
            {!catalogModels.length ? (
              <div className="nle-empty">モデル情報はまだ取得されていません。</div>
            ) : (
              <ul className="model-manager-modal__list">
                {catalogModels.map((model) => (
                  <li key={model.name} className="model-manager-modal__item">
                    <div className="model-manager-modal__item-main">
                      <div className="model-manager-modal__title">
                        {model.name}
                        {"required" in model && model.required ? <span className="model-manager-modal__required">*</span> : null}
                      </div>
                      <div className="model-manager-modal__meta">
                        <span style={{ color: modelStatusColor(model) }}>{modelStatusLabel(model)}</span>
                        {model.source ? <span>ソース: {model.source}</span> : null}
                      </div>
                      {model.note ? <div className="model-manager-modal__note">{model.note}</div> : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="model-manager-modal__section">
            <div className="model-manager-modal__section-header">
              <h4>導入済みモデル</h4>
              <button className="nle-btn nle-btn--small" onClick={onReloadInstalled} type="button">
                再読み込み
              </button>
            </div>
            {installedModelDir ? (
              <div className="model-manager-modal__dir">{installedModelDir}</div>
            ) : null}
            {!installedModels.length ? (
              <div className="nle-empty">導入済みモデルはありません。</div>
            ) : (
              <ul className="model-manager-modal__list">
                {installedModels.map((model) => {
                  const sizeMb = (model.size_bytes / (1024 * 1024)).toFixed(1);
                  const statusColor =
                    model.status === "installed" ? "#4caf50" : model.status === "broken" ? "#e55" : "#999";
                  return (
                    <li key={model.name} className="model-manager-modal__item">
                      <div className="model-manager-modal__item-main">
                        <div className="model-manager-modal__title">
                          {model.name}
                          {model.required ? <span className="model-manager-modal__required">*</span> : null}
                          {!model.known ? <span className="model-manager-modal__unknown">(未登録)</span> : null}
                        </div>
                        <div className="model-manager-modal__meta">
                          <span>{sizeMb} MB</span>
                          <span style={{ color: statusColor }}>{model.status}</span>
                          {model.source_label ? <span>{model.source_label}</span> : null}
                        </div>
                      </div>
                      <button className="nle-btn nle-btn--small" onClick={() => onDeleteInstalledModel(model.name)} type="button">
                        削除
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
