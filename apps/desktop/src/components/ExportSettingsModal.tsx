import { useEffect, useState } from "react";

export type ExportPreset = {
  name: string;
  settings: ExportSettings;
};

type ExportSettingsModalProps = {
  open: boolean;
  onClose: () => void;
  onExport: (settings: ExportSettings) => void;
  defaultSettings: ExportSettings;
  presets?: ExportPreset[];
  onSavePreset?: (name: string, settings: ExportSettings) => Promise<void> | void;
  onDeletePreset?: (name: string) => Promise<void> | void;
};

export type ExportSettings = {
  resolution: string;
  mosaic_strength: number;
  audio_mode: string;
  bitrate_kbps: number | null;
  encoder: "auto" | "gpu" | "cpu";
};

export function ExportSettingsModal({
  open,
  onClose,
  onExport,
  defaultSettings,
  presets = [],
  onSavePreset,
  onDeletePreset,
}: ExportSettingsModalProps) {
  const [resolution, setResolution] = useState(defaultSettings.resolution);
  const [mosaicStrength, setMosaicStrength] = useState(defaultSettings.mosaic_strength);
  const [audioMode, setAudioMode] = useState(defaultSettings.audio_mode);
  const [bitrateMode, setBitrateMode] = useState<"auto" | "manual">(defaultSettings.bitrate_kbps ? "manual" : "auto");
  const [bitrateKbps, setBitrateKbps] = useState(defaultSettings.bitrate_kbps ?? 16000);
  const [encoder, setEncoder] = useState<"auto" | "gpu" | "cpu">(defaultSettings.encoder ?? "auto");
  const [selectedPreset, setSelectedPreset] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    setResolution(defaultSettings.resolution);
    setMosaicStrength(defaultSettings.mosaic_strength);
    setAudioMode(defaultSettings.audio_mode);
    setBitrateMode(defaultSettings.bitrate_kbps ? "manual" : "auto");
    setBitrateKbps(defaultSettings.bitrate_kbps ?? 16000);
    setEncoder(defaultSettings.encoder ?? "auto");
    setSelectedPreset("");
  }, [defaultSettings, open]);

  if (!open) return null;

  function applyPreset(name: string) {
    setSelectedPreset(name);
    if (!name) return;
    const preset = presets.find((p) => p.name === name);
    if (!preset) return;
    const s = preset.settings;
    if (s.resolution) setResolution(s.resolution);
    if (typeof s.mosaic_strength === "number") setMosaicStrength(s.mosaic_strength);
    if (s.audio_mode) setAudioMode(s.audio_mode);
    setBitrateMode(s.bitrate_kbps ? "manual" : "auto");
    setBitrateKbps(s.bitrate_kbps ?? 16000);
    if (s.encoder) setEncoder(s.encoder);
  }

  function currentSettings(): ExportSettings {
    return {
      resolution,
      mosaic_strength: mosaicStrength,
      audio_mode: audioMode,
      bitrate_kbps: bitrateMode === "manual" ? bitrateKbps : null,
      encoder,
    };
  }

  function handleSubmit() {
    onExport(currentSettings());
  }

  async function handleSavePreset() {
    if (!onSavePreset) return;
    const name = window.prompt("プリセット名を入力してください");
    if (!name) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    await onSavePreset(trimmed, currentSettings());
    setSelectedPreset(trimmed);
  }

  async function handleDeletePreset() {
    if (!onDeletePreset || !selectedPreset) return;
    if (!window.confirm(`プリセット "${selectedPreset}" を削除しますか?`)) return;
    await onDeletePreset(selectedPreset);
    setSelectedPreset("");
  }

  return (
    <div className="nle-modal-overlay" onClick={onClose}>
      <div className="nle-modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 360 }}>
        <h3 style={{ margin: "0 0 12px" }}>書き出し設定</h3>

        {onSavePreset ? (
          <div className="nle-form-row">
            <label className="nle-form-label">プリセット</label>
            <select
              className="nle-select"
              value={selectedPreset}
              onChange={(e) => applyPreset(e.target.value)}
            >
              <option value="">(現在の設定を使用)</option>
              {presets.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
            <button className="nle-btn nle-btn--small" onClick={() => void handleSavePreset()}>
              現在の設定を保存
            </button>
            {selectedPreset ? (
              <button className="nle-btn nle-btn--small" onClick={() => void handleDeletePreset()}>
                削除
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="nle-form-row">
          <label className="nle-form-label">解像度</label>
          <select className="nle-select" value={resolution} onChange={(e) => setResolution(e.target.value)}>
            <option value="source">ソース (元の解像度)</option>
            <option value="720p">720p</option>
            <option value="1080p">1080p</option>
            <option value="4k">4K</option>
          </select>
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">モザイク強度</label>
          <input
            type="range" min={2} max={64} step={1}
            value={mosaicStrength}
            onChange={(e) => setMosaicStrength(Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ minWidth: 30, textAlign: "right" }}>{mosaicStrength}</span>
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">音声</label>
          <select className="nle-select" value={audioMode} onChange={(e) => setAudioMode(e.target.value)}>
            <option value="mux_if_possible">音声を含む</option>
            <option value="video_only">映像のみ</option>
          </select>
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">ビットレート</label>
          <select className="nle-select" value={bitrateMode} onChange={(e) => setBitrateMode(e.target.value as "auto" | "manual")}>
            <option value="auto">自動</option>
            <option value="manual">手動</option>
          </select>
          {bitrateMode === "manual" && (
            <input
              type="number" min={1000} max={100000} step={1000}
              value={bitrateKbps}
              onChange={(e) => setBitrateKbps(Number(e.target.value))}
              style={{ width: 80 }}
            />
          )}
          {bitrateMode === "manual" && <span>kbps</span>}
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">エンコーダー</label>
          <select className="nle-select" value={encoder} onChange={(e) => setEncoder(e.target.value as "auto" | "gpu" | "cpu")}>
            <option value="auto">自動 (GPU優先→CPU)</option>
            <option value="gpu">GPU (NVENC/QSV/AMF)</option>
            <option value="cpu">CPU (libx264)</option>
          </select>
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="nle-btn" onClick={onClose}>キャンセル</button>
          <button className="nle-btn nle-btn--accent" onClick={handleSubmit}>書き出し</button>
        </div>
      </div>
    </div>
  );
}
