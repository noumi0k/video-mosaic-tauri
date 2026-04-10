import { useState } from "react";

type ExportSettingsModalProps = {
  open: boolean;
  onClose: () => void;
  onExport: (settings: ExportSettings) => void;
  defaultSettings: ExportSettings;
};

export type ExportSettings = {
  resolution: string;
  mosaic_strength: number;
  audio_mode: string;
  bitrate_kbps: number | null;
};

export function ExportSettingsModal({ open, onClose, onExport, defaultSettings }: ExportSettingsModalProps) {
  const [resolution, setResolution] = useState(defaultSettings.resolution);
  const [mosaicStrength, setMosaicStrength] = useState(defaultSettings.mosaic_strength);
  const [audioMode, setAudioMode] = useState(defaultSettings.audio_mode);
  const [bitrateMode, setBitrateMode] = useState<"auto" | "manual">(defaultSettings.bitrate_kbps ? "manual" : "auto");
  const [bitrateKbps, setBitrateKbps] = useState(defaultSettings.bitrate_kbps ?? 16000);

  if (!open) return null;

  function handleSubmit() {
    onExport({
      resolution,
      mosaic_strength: mosaicStrength,
      audio_mode: audioMode,
      bitrate_kbps: bitrateMode === "manual" ? bitrateKbps : null,
    });
  }

  return (
    <div className="nle-modal-overlay" onClick={onClose}>
      <div className="nle-modal" onClick={(e) => e.stopPropagation()} style={{ minWidth: 360 }}>
        <h3 style={{ margin: "0 0 12px" }}>書き出し設定</h3>

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

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
          <button className="nle-btn" onClick={onClose}>キャンセル</button>
          <button className="nle-btn nle-btn--accent" onClick={handleSubmit}>書き出し</button>
        </div>
      </div>
    </div>
  );
}
