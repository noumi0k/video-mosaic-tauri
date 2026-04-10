import { useState } from "react";
import type { DangerousFrame } from "../dangerousFrames";

type DangerWarningsPanelProps = {
  warnings: DangerousFrame[];
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

export function DangerWarningsPanel({ warnings, onSeekFrame }: DangerWarningsPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [confirmed, setConfirmed] = useState<Set<number>>(new Set());

  if (!warnings.length) return null;

  const unconfirmedCount = warnings.filter((_, i) => !confirmed.has(i)).length;

  return (
    <section className="nle-panel-section">
      <div
        className="nle-panel-header"
        style={{ cursor: "pointer", display: "flex", justifyContent: "space-between" }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span>{collapsed ? "▶" : "▼"} 危険フレーム ({unconfirmedCount}/{warnings.length})</span>
      </div>
      {!collapsed && (
        <div className="nle-panel-body" style={{ maxHeight: 200, overflowY: "auto" }}>
          <ul className="nle-track-list" style={{ margin: 0, padding: 0 }}>
            {warnings.map((w, i) => (
              <li
                key={`${w.trackId}-${w.frameIndex}-${i}`}
                className="nle-track-item"
                style={{
                  cursor: "pointer",
                  opacity: confirmed.has(i) ? 0.5 : 1,
                  borderLeft: `3px solid ${reasonColor(w.reason)}`,
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
                    setConfirmed((prev) => {
                      const next = new Set(prev);
                      if (next.has(i)) next.delete(i); else next.add(i);
                      return next;
                    });
                  }}
                >
                  {confirmed.has(i) ? "✓ 確認済み" : "確認"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
