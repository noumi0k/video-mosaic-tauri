import { useRef, useState } from "react";
import type { MaskTrack, ProjectReadModel } from "../types";
import type { DangerousFrame } from "../dangerousFrames";
import { segmentBarClass, kfMarkerClassFull } from "../timelineSegmentDisplay";

type TimelineViewProps = {
  readModel: ProjectReadModel | null;
  /** Full track documents — provides segments and source_detail for visualization. */
  tracks?: MaskTrack[] | null;
  selectedTrackId: string | null;
  selectedKeyframeFrame: number | null;
  currentFrame: number;
  inFrame: number | null;
  outFrame: number | null;
  dangerMarkers: DangerousFrame[];
  /** 確認済み危険フレームのキーセット: `${trackId}-${frameIndex}` */
  confirmedDangerMarkers?: Set<string>;
  busy: boolean;
  onSelectTrack: (trackId: string) => void;
  onSelectKeyframe: (trackId: string, frameIndex: number) => void;
  onMoveSelectedKeyframe: (delta: number) => void;
  onSeekFrame: (frame: number) => void;
};

const ZOOM_STEPS = [1, 1.5, 2, 3, 5, 8, 12, 20];
const LABEL_COL_W = 140;

function snapZoom(z: number, dir: 1 | -1): number {
  if (dir === 1) {
    return ZOOM_STEPS.find((s) => s > z) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1];
  }
  const rev = [...ZOOM_STEPS].reverse();
  return rev.find((s) => s < z) ?? ZOOM_STEPS[0];
}

function generateTicks(totalFrames: number): Array<{ frame: number; label: string }> {
  if (totalFrames <= 0) return [{ frame: 0, label: "0" }];
  const candidates = [1, 2, 5, 10, 15, 20, 24, 25, 30, 50, 60, 100, 120, 150, 200, 250, 300, 500, 600, 1000, 1200];
  const step = candidates.find((c) => totalFrames / c <= 12) ?? Math.ceil(totalFrames / 10);
  const ticks: Array<{ frame: number; label: string }> = [];
  for (let f = 0; f <= totalFrames; f += step) {
    ticks.push({ frame: f, label: String(f) });
  }
  if ((ticks[ticks.length - 1]?.frame ?? 0) !== totalFrames) {
    ticks.push({ frame: totalFrames, label: String(totalFrames) });
  }
  return ticks;
}


export function TimelineView({
  readModel,
  tracks,
  selectedTrackId,
  selectedKeyframeFrame,
  currentFrame,
  inFrame,
  outFrame,
  dangerMarkers,
  confirmedDangerMarkers,
  busy,
  onSelectTrack,
  onSelectKeyframe,
  onMoveSelectedKeyframe,
  onSeekFrame,
}: TimelineViewProps) {
  const [zoom, setZoom] = useState(1);
  const bodyRef = useRef<HTMLDivElement>(null);
  const rulerScrollRef = useRef<HTMLDivElement>(null);

  // Build a fast lookup from track_id → MaskTrack for segment/source_detail access.
  const tracksMap = new Map<string, MaskTrack>();
  if (tracks) {
    for (const t of tracks) tracksMap.set(t.track_id, t);
  }

  const totalFrames = readModel?.video?.frame_count ?? 0;
  const fps = readModel?.video?.fps ?? 0;

  function framePct(frame: number): string {
    if (totalFrames <= 0) return "0%";
    return `${Math.min((frame / totalFrames) * 100, 100)}%`;
  }

  function pctToFrame(pct: number): number {
    if (totalFrames <= 0) return 0;
    return Math.max(0, Math.min(Math.round(pct * totalFrames), totalFrames - 1));
  }

  function handleBodyScroll() {
    if (rulerScrollRef.current && bodyRef.current) {
      rulerScrollRef.current.scrollLeft = bodyRef.current.scrollLeft;
    }
  }

  function handleRulerClick(e: React.MouseEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const xInVisible = e.clientX - rect.left;
    const xInContent = xInVisible + el.scrollLeft;
    onSeekFrame(pctToFrame(xInContent / (el.scrollWidth || 1)));
  }

  function handleLaneClick(e: React.MouseEvent<HTMLDivElement>, trackId: string) {
    e.stopPropagation();
    const bodyEl = bodyRef.current;
    if (!bodyEl) return;
    const rect = bodyEl.getBoundingClientRect();
    const xInContent = e.clientX - rect.left + bodyEl.scrollLeft - LABEL_COL_W;
    const laneWidth = bodyEl.scrollWidth - LABEL_COL_W;
    onSelectTrack(trackId);
    onSeekFrame(pctToFrame(xInContent / Math.max(laneWidth, 1)));
  }

  const ticks = generateTicks(totalFrames);
  const playheadPct = framePct(currentFrame);
  const inPct = inFrame !== null ? framePct(inFrame) : null;
  const outPct = outFrame !== null ? framePct(outFrame) : null;

  // Time display: F123 / 00:04.10 when fps is known
  let timeDisplay = `F ${currentFrame}`;
  if (fps > 0) {
    const secs = currentFrame / fps;
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    const f = Math.round((secs - Math.floor(secs)) * fps);
    timeDisplay = `F ${currentFrame}  ${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(f).padStart(2, "0")}`;
  }

  return (
    <div className="nle-tlv">
      {/* ── Header ── */}
      <div className="nle-timeline__header">
        <div className="nle-timeline__header-left">タイムライン</div>
        <div className="nle-tlv__transport">
          <button
            className="nle-btn nle-btn--small"
            onClick={() => onMoveSelectedKeyframe(-1)}
            disabled={busy || selectedTrackId === null || selectedKeyframeFrame === null}
            title="選択キーフレームを1フレーム前に移動"
          >
            KF −1
          </button>
          <button
            className="nle-btn nle-btn--small"
            onClick={() => onMoveSelectedKeyframe(1)}
            disabled={busy || selectedTrackId === null || selectedKeyframeFrame === null}
            title="選択キーフレームを1フレーム後に移動"
          >
            KF +1
          </button>
          <span className="nle-tlv__frame-disp">{timeDisplay}</span>
        </div>
        <div className="nle-timeline__header-right">
          <button
            className="nle-btn nle-btn--small"
            onClick={() => setZoom((z) => snapZoom(z, -1))}
            disabled={zoom <= ZOOM_STEPS[0]}
            title="ズームアウト"
          >
            −
          </button>
          <span className="nle-timeline__zoom-label">{zoom}×</span>
          <button
            className="nle-btn nle-btn--small"
            onClick={() => setZoom((z) => snapZoom(z, 1))}
            disabled={zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
            title="ズームイン"
          >
            +
          </button>
        </div>
      </div>

      {/* ── Ruler row ── */}
      <div className="nle-tlv__ruler-row">
        <div className="nle-tlv__col-stub" />
        <div
          className="nle-tlv__ruler-scroll"
          ref={rulerScrollRef}
          onClick={handleRulerClick}
        >
          <div className="nle-tlv__zoom-inner" style={{ width: `${zoom * 100}%` }}>
            <div className="nle-tlv__ruler-area">
              {ticks.map(({ frame, label }) => (
                <div
                  key={frame}
                  className="nle-tlv__tick"
                  style={{ left: framePct(frame) }}
                >
                  {label}
                </div>
              ))}
              {/* Danger frame markers — 確認済みはグレー表示 */}
              {dangerMarkers.map((d, i) => {
                const pct = framePct(d.frameIndex);
                const key = `${d.trackId}-${d.frameIndex}`;
                const confirmed = confirmedDangerMarkers?.has(key) ?? false;
                const color = confirmed
                  ? "#555"
                  : d.reason.includes("gap") ? "#ff9800" : d.reason.includes("Area") ? "#03a9f4" : "#e91e63";
                return (
                  <div
                    key={`danger-${i}`}
                    className="nle-tlv__danger-marker"
                    style={{ left: pct, borderBottomColor: color, opacity: confirmed ? 0.45 : 1 }}
                    title={`F${d.frameIndex}: ${d.reason}${confirmed ? " (確認済み)" : ""}`}
                    onClick={(e) => { e.stopPropagation(); onSeekFrame(d.frameIndex); }}
                  />
                );
              })}
              {/* In/Out range markers */}
              {inPct !== null && <div className="nle-tlv__in-marker" style={{ left: inPct }} title={`In: F${inFrame}`} />}
              {outPct !== null && <div className="nle-tlv__out-marker" style={{ left: outPct }} title={`Out: F${outFrame}`} />}
              {inPct !== null && outPct !== null && (
                <div className="nle-tlv__range-highlight" style={{ left: inPct, width: `calc(${outPct} - ${inPct})` }} />
              )}
              {/* Playhead indicator on ruler */}
              <div className="nle-tlv__playhead-head" style={{ left: playheadPct }} />
            </div>
          </div>
        </div>
      </div>

      {/* ── Body: track rows ── */}
      <div className="nle-tlv__body" ref={bodyRef} onScroll={handleBodyScroll}>
        <div className="nle-tlv__zoom-inner" style={{ width: `${zoom * 100}%` }}>
          {!readModel?.track_summaries.length ? (
            <div className="nle-timeline__empty">
              タイムラインに表示できるトラックはまだありません。
            </div>
          ) : (
            readModel.track_summaries.map((track) => {
              const selected = track.track_id === selectedTrackId;
              const hasRange = track.start_frame != null && track.end_frame != null;
              const activeNow =
                !hasRange ||
                (currentFrame >= (track.start_frame ?? 0) &&
                  currentFrame <= (track.end_frame ?? totalFrames));

              const rowClass = [
                "nle-tl-row",
                selected ? "nle-tl-row--selected" : "",
                !track.visible ? "nle-tl-row--hidden" : "",
                !track.export_enabled ? "nle-tl-row--export-disabled" : "",
                !selected && !activeNow ? "nle-tl-row--inactive" : "",
              ]
                .filter(Boolean)
                .join(" ");

              const barLeft = framePct(track.start_frame ?? 0);
              const barWidth = hasRange
                ? `${(Math.max((track.end_frame ?? 0) - (track.start_frame ?? 0) + 1, 1) / Math.max(totalFrames, 1)) * 100}%`
                : "0%";

              return (
                <div
                  key={track.track_id}
                  className={rowClass}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelectTrack(track.track_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onSelectTrack(track.track_id);
                  }}
                >
                  {/* Label — sticky on horizontal scroll */}
                  <div className="nle-tl-row__label">
                    <span
                      className="nle-tl-row__vis-icon"
                      title={track.visible ? "表示中" : "非表示"}
                    >
                      {track.visible ? "●" : "○"}
                    </span>
                    <span className="nle-tl-row__name" title={track.label}>
                      {track.label}
                    </span>
                    {!track.export_enabled && (
                      <span
                        className="nle-tl-row__export-badge"
                        title="書き出し対象外"
                      >
                        書き出し外
                      </span>
                    )}
                    <span className="nle-tl-row__label-meta">{track.keyframe_count}kf</span>
                  </div>

                  {/* Lane */}
                  <div
                    className="nle-tl-row__lane"
                    onClick={(e) => handleLaneClick(e, track.track_id)}
                  >
                    {(() => {
                      const trackDoc = tracksMap.get(track.track_id);
                      const segs = trackDoc?.segments;
                      if (segs && segs.length > 0) {
                        // Segment-colored bars replace the single active-range bar.
                        return segs.map((seg, i) => {
                          const segLeft = framePct(seg.start_frame);
                          const segWidth = `${(Math.max(seg.end_frame - seg.start_frame + 1, 1) / Math.max(totalFrames, 1)) * 100}%`;
                          return (
                            <div
                              key={i}
                              className={`nle-tl-seg ${segmentBarClass(seg.state)}${!track.visible ? " nle-tl-seg--hidden" : ""}`}
                              style={{ left: segLeft, width: segWidth }}
                              title={seg.state}
                            />
                          );
                        });
                      }
                      // Fallback: single bar for legacy / no-segment tracks.
                      return hasRange ? (
                        <div
                          className={`nle-tl-row__bar${!track.visible ? " nle-tl-row__bar--hidden" : ""}`}
                          style={{ left: barLeft, width: barWidth }}
                        />
                      ) : null;
                    })()}

                    {/* Keyframe markers — use source_detail when available */}
                    {track.keyframes.map((kf) => {
                      const isSelKf = selected && selectedKeyframeFrame === kf.frame_index;
                      const trackDoc = tracksMap.get(track.track_id);
                      const fullKf = trackDoc?.keyframes.find((k) => k.frame_index === kf.frame_index);
                      const markerClass = kfMarkerClassFull(kf.source, fullKf?.source_detail);
                      const detailHint = fullKf?.source_detail ? ` | ${fullKf.source_detail}` : "";
                      return (
                        <div
                          key={kf.frame_index}
                          className={[
                            "nle-tl-row__marker",
                            markerClass,
                            isSelKf ? "nle-tl-row__marker--selected" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          style={{ left: framePct(kf.frame_index) }}
                          title={`F${kf.frame_index} | ${kf.shape_type} | ${kf.source}${detailHint}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectKeyframe(track.track_id, kf.frame_index);
                            onSeekFrame(kf.frame_index);
                          }}
                        />
                      );
                    })}

                    {/* Playhead line crossing this lane */}
                    <div
                      className="nle-tlv__playhead-lane"
                      style={{ left: playheadPct }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ── Legend ── */}
      <div className="nle-tl-legend">
        <span className="nle-tl-legend__separator">KF:</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--manual">手動</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--auto">自動</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--auto-anchored">anchored</span>
        <span className="nle-tl-legend__separator">セグメント:</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--seg-confirmed">確定</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--seg-held">held</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--seg-uncertain">uncertain</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--seg-interpolated">補間</span>
        <span className="nle-tl-legend__separator">状態:</span>
        <span className="nle-tl-legend__item nle-tl-legend__item--export-disabled">書き出し外</span>
      </div>
    </div>
  );
}
