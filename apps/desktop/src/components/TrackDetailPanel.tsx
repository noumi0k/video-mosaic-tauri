import type { ProjectReadModel, TrackSummary } from "../types";

type TrackDetailPanelProps = {
  readModel: ProjectReadModel | null;
  track: TrackSummary | null;
  selectedKeyframeFrame: number | null;
  onSelectKeyframe: (trackId: string, frameIndex: number) => void;
  onToggleVisible: () => void;
};

export function TrackDetailPanel({
  readModel,
  track,
  selectedKeyframeFrame,
  onSelectKeyframe,
  onToggleVisible,
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
      <div className="nle-meta-row"><span className="nle-meta-row__label">状態</span><span className="nle-meta-row__value">{track.state}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">ソース</span><span className="nle-meta-row__value">{track.source}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">範囲</span><span className="nle-meta-row__value">{track.start_frame ?? "-"} - {track.end_frame ?? "-"}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">キーフレーム</span><span className="nle-meta-row__value">{track.keyframe_count}</span></div>
      <div className="nle-meta-row"><span className="nle-meta-row__label">カバー率</span><span className="nle-meta-row__value">{coveragePercent.toFixed(2)}%</span></div>
      <div style={{ marginTop: 8 }}>
        <button className="nle-btn nle-btn--small" onClick={onToggleVisible}>
          {track.visible ? "トラックを非表示" : "トラックを表示"}
        </button>
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
