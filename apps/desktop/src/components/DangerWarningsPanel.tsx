import type { DangerousFrame } from "../dangerousFrames";

export type DangerWarningsPanelProps = {
  warnings: DangerousFrame[];
  /** key = `${trackId}-${frameIndex}` */
  confirmedKeys: Set<string>;
  onToggleConfirmed: (key: string) => void;
  onSeekFrame: (frame: number) => void;
};

const REASON_COLORS: Record<string, string> = {
  "gap": "#ff9800",
  "area": "#03a9f4",
  "confidence": "#e91e63",
};

function reasonColor(reason: string): string {
  if (reason.includes("gap")) return REASON_COLORS.gap!;
  if (reason.includes("Area")) return REASON_COLORS.area!;
  return REASON_COLORS.confidence!;
}

function warningKey(w: DangerousFrame): string {
  return `${w.trackId}-${w.frameIndex}`;
}

export function DangerWarningsPanel({ warnings, confirmedKeys, onToggleConfirmed, onSeekFrame }: DangerWarningsPanelProps) {
  if (!warnings.length) return null;

  const unconfirmedCount = warnings.filter((w) => !confirmedKeys.has(warningKey(w))).length;

  return (
    <section className="nle-panel-section">
      <div
        className="nle-panel-header"
        style={{ cursor: "default", display: "flex", justifyContent: "space-between" }}
      >
        <span>危険フレーム ({unconfirmedCount}/{warnings.length})</span>
      </div>
      <div className="nle-panel-body" style={{ maxHeight: 200, overflowY: "auto" }}>
        <ul className="nle-track-list" style={{ margin: 0, padding: 0 }}>
          {warnings.map((w) => {
            const key = warningKey(w);
            const isConfirmed = confirmedKeys.has(key);
            return (
              <li
                key={key}
                className="nle-track-item"
                style={{
                  cursor: "pointer",
                  opacity: isConfirmed ? 0.45 : 1,
                  borderLeft: `3px solid ${isConfirmed ? "#555" : reasonColor(w.reason)}`,
                  paddingLeft: 6,
                }}
                onClick={() => onSeekFrame(w.frameIndex)}
              >
                <span className="nle-track-item__name" style={{ fontSize: "0.85em" }}>
                  F{w.frameIndex} {w.reason}
                </span>
                <button
                  className="nle-btn nle-btn--small"
                  style={{ fontSize: "0.75em", padding: "1px 4px" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleConfirmed(key);
                  }}
                >
                  {isConfirmed ? "✓ 確認済み" : "確認"}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
