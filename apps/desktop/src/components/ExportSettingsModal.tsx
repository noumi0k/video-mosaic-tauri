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
  // M-B03 extended settings.
  fps_mode?: "source" | "custom";
  fps_custom?: number | null;
  bitrate_mode?: "auto" | "manual" | "target_size";
  target_size_mb?: number | null;
  video_codec?: "h264" | "vp9";
  container?: "auto" | "mp4" | "mov" | "webm";
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
  const [bitrateMode, setBitrateMode] = useState<"auto" | "manual" | "target_size">(
    defaultSettings.bitrate_mode ?? (defaultSettings.bitrate_kbps ? "manual" : "auto"),
  );
  const [bitrateKbps, setBitrateKbps] = useState(defaultSettings.bitrate_kbps ?? 16000);
  const [targetSizeMb, setTargetSizeMb] = useState(defaultSettings.target_size_mb ?? 500);
  const [encoder, setEncoder] = useState<"auto" | "gpu" | "cpu">(defaultSettings.encoder ?? "auto");
  const [fpsMode, setFpsMode] = useState<"source" | "custom">(defaultSettings.fps_mode ?? "source");
  const [fpsCustom, setFpsCustom] = useState<number>(defaultSettings.fps_custom ?? 30);
  const [videoCodec, setVideoCodec] = useState<"h264" | "vp9">(defaultSettings.video_codec ?? "h264");
  const [container, setContainer] = useState<"auto" | "mp4" | "mov" | "webm">(
    defaultSettings.container ?? "auto",
  );
  const [selectedPreset, setSelectedPreset] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    setResolution(defaultSettings.resolution);
    setMosaicStrength(defaultSettings.mosaic_strength);
    setAudioMode(defaultSettings.audio_mode);
    setBitrateMode(defaultSettings.bitrate_mode ?? (defaultSettings.bitrate_kbps ? "manual" : "auto"));
    setBitrateKbps(defaultSettings.bitrate_kbps ?? 16000);
    setTargetSizeMb(defaultSettings.target_size_mb ?? 500);
    setEncoder(defaultSettings.encoder ?? "auto");
    setFpsMode(defaultSettings.fps_mode ?? "source");
    setFpsCustom(defaultSettings.fps_custom ?? 30);
    setVideoCodec(defaultSettings.video_codec ?? "h264");
    setContainer(defaultSettings.container ?? "auto");
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
    setBitrateMode(s.bitrate_mode ?? (s.bitrate_kbps ? "manual" : "auto"));
    setBitrateKbps(s.bitrate_kbps ?? 16000);
    setTargetSizeMb(s.target_size_mb ?? 500);
    if (s.encoder) setEncoder(s.encoder);
    if (s.fps_mode) setFpsMode(s.fps_mode);
    if (typeof s.fps_custom === "number") setFpsCustom(s.fps_custom);
    if (s.video_codec) setVideoCodec(s.video_codec);
    if (s.container) setContainer(s.container);
  }

  function currentSettings(): ExportSettings {
    return {
      resolution,
      mosaic_strength: mosaicStrength,
      audio_mode: audioMode,
      bitrate_kbps: bitrateMode === "manual" ? bitrateKbps : null,
      encoder,
      fps_mode: fpsMode,
      fps_custom: fpsMode === "custom" ? fpsCustom : null,
      bitrate_mode: bitrateMode,
      target_size_mb: bitrateMode === "target_size" ? targetSizeMb : null,
      video_codec: videoCodec,
      container,
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
          <label className="nle-form-label">コーデック</label>
          <select
            className="nle-select"
            value={videoCodec}
            onChange={(e) => {
              const next = e.target.value as "h264" | "vp9";
              setVideoCodec(next);
              // Keep container compatible: VP9 only works with webm; flip
              // container automatically when the current choice conflicts.
              if (next === "vp9" && container !== "auto" && container !== "webm") {
                setContainer("webm");
              } else if (next === "h264" && container === "webm") {
                setContainer("auto");
              }
            }}
          >
            <option value="h264">H.264 (libx264 / NVENC)</option>
            <option value="vp9">VP9 (libvpx-vp9)</option>
          </select>
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">コンテナ</label>
          <select
            className="nle-select"
            value={container}
            onChange={(e) => setContainer(e.target.value as "auto" | "mp4" | "mov" | "webm")}
          >
            <option value="auto">自動 (出力拡張子)</option>
            <option value="mp4" disabled={videoCodec === "vp9"}>mp4</option>
            <option value="mov" disabled={videoCodec === "vp9"}>mov</option>
            <option value="webm" disabled={videoCodec === "h264"}>webm</option>
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
            <option value="mux_if_possible">音声を含む (AAC 再エンコード)</option>
            <option value="copy_if_possible">音声コピー (再エンコードなし)</option>
            <option value="encode">音声エンコード (192k)</option>
            <option value="video_only">映像のみ</option>
          </select>
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">FPS</label>
          <select
            className="nle-select"
            value={fpsMode}
            onChange={(e) => setFpsMode(e.target.value as "source" | "custom")}
          >
            <option value="source">ソース (元の FPS)</option>
            <option value="custom">カスタム</option>
          </select>
          {fpsMode === "custom" && (
            <>
              <input
                type="number" min={1} max={240} step={1}
                value={fpsCustom}
                onChange={(e) => setFpsCustom(Number(e.target.value))}
                style={{ width: 80 }}
              />
              <span>fps</span>
            </>
          )}
        </div>

        <div className="nle-form-row">
          <label className="nle-form-label">ビットレート</label>
          <select
            className="nle-select"
            value={bitrateMode}
            onChange={(e) => setBitrateMode(e.target.value as "auto" | "manual" | "target_size")}
          >
            <option value="auto">自動 (解像度依存)</option>
            <option value="manual">手動 (kbps 指定)</option>
            <option value="target_size">目標ファイルサイズ (MB)</option>
          </select>
          {bitrateMode === "manual" && (
            <>
              <input
                type="number" min={1000} max={100000} step={1000}
                value={bitrateKbps}
                onChange={(e) => setBitrateKbps(Number(e.target.value))}
                style={{ width: 90 }}
              />
              <span>kbps</span>
            </>
          )}
          {bitrateMode === "target_size" && (
            <>
              <input
                type="number" min={1} max={100000} step={1}
                value={targetSizeMb}
                onChange={(e) => setTargetSizeMb(Number(e.target.value))}
                style={{ width: 90 }}
              />
              <span>MB</span>
            </>
          )}
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
