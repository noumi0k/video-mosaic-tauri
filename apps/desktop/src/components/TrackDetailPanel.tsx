import type { ProjectReadModel, TrackSummary } from "../types";

type TrackDetailPanelProps = {
  readModel: ProjectReadModel | null;
  track: TrackSummary | null;
  selectedKeyframeFrame: number | null;
  onSelectKeyframe: (trackId: string, frameIndex: number) => void;
  onToggleVisible: () => void;
  onToggleExportEnabled: () => void;
  onDeleteTrack?: () => void;
  onDuplicateTrack?: () => void;
  onSplitTrack?: () => void;
};

export function TrackDetailPanel({
  readModel,
  track,
  selectedKeyframeFrame,
  onSelectKeyframe,
  onToggleVisible,
  onToggleExportEnabled,
  onDeleteTrack,
  onDuplicateTrack,
  onSplitTrack,
}: TrackDetailPanelProps) {
  if (!track) {
    return <div className="nle-empty">トラックを選択すると詳細を表示できます。</div>;
  }

  const totalFrames = readModel?.video?.frame_count ?? 0;
  const coveredFrames =
    track.start_frame !== null && track.end_frame !== null ? Math.max(track.end_frame - track.start_frame + 1, 0) : 0;
  const coveragePercent = totalFrames > 0 ? (coveredFrames / totalFrames) * 100 : 0;

  return (
    <div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">ID</span><span className="nle-meta-row__value">{track.track_id}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">ラベル</span><span className="nle-meta-row__value">{track.label}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">表示</span><span className="nle-meta-row__value">{track.visible ? "表示中" : "非表示"}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">書き出し</span><span className="nle-meta-row__value">{track.export_enabled ? "対象" : "対象外"}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">状態</span><span className="nle-meta-row__value">{track.state}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">ソース</span><span className="nle-meta-row__value">{track.source}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">範囲</span><span className="nle-meta-row__value">{track.start_frame ?? "-"} - {track.end_frame ?? "-"}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">キーフレーム</span><span className="nle-meta-row__value">{track.keyframe_count}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">カバー率</span><span className="nle-meta-row__value">{coveragePercent.toFixed(2)}%</span></div>
      <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
        <button className="nle-btn nle-btn--small" onClick={onToggleVisible}>
          {track.visible ? "トラックを非表示" : "トラックを表示"}
        </button>
        <button className="nle-btn nle-btn--small" onClick={onToggleExportEnabled}>
          {track.export_enabled ? "書き出し対象外にする" : "書き出し対象にする"}
        </button>
        {onDuplicateTrack && (
          <button className="nle-btn nle-btn--small" onClick={onDuplicateTrack}>
            複製
          </button>
        )}
        {onSplitTrack && (
          <button className="nle-btn nle-btn--small" onClick={onSplitTrack}>
            分割
          </button>
        )}
        {onDeleteTrack && (
          <button className="nle-btn nle-btn--small" onClick={onDeleteTrack} style={{ color: "#e55" }}>
            削除
          </button>
        )}
      </div>
      <div style={{ marginTop: 10 }}>
        <strong style={{ display: "block", marginBottom: 6 }}>キーフレーム一覧</strong>
        {track.keyframes.length ? (
          <div className="nle-kf-list">
            {track.keyframes.map((keyframe) => (
              <button
                key={`${track.track_id}-${keyframe.frame_index}`}
                className={`nle-kf-item ${selectedKeyframeFrame === keyframe.frame_index ? "nle-kf-item--selected" : ""}`}
                onClick={() => onSelectKeyframe(track.track_id, keyframe.frame_index)}
              >
                F{keyframe.frame_index} / {keyframe.shape_type} / {keyframe.source}
              </button>
            ))}
          </div>
        ) : (
          <div className="nle-empty">キーフレームはまだありません。</div>
        )}
      </div>
    </div>
  );
}
