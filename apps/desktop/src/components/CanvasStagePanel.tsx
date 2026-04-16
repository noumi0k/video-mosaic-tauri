import { useEffect, useMemo, useRef, useState } from "react";
import {
  bboxEquals,
  insertPointAfter,
  midpoint,
  moveBBox,
  movePoint,
  movePoints,
  normalizeBBox,
  normalizePoints,
  pointsEqual,
  removePointAt,
  resizeBBox,
  type NormalizedBBox,
  type NormalizedPoint,
  type ResizeHandle,
} from "../ellipseCanvasMath";
import type { ResolveReason } from "../maskShapeResolver";
import type { Keyframe, KeyframeSummary, TrackSummary, UpdateKeyframePayload, VideoMetadata } from "../types";
import { applyKeyframePatchPreview } from "../keyframePreview";
import { resolveOverlayLabel } from "../keyframeResolveDisplay";

type DragState =
  | { mode: "move-ellipse"; originX: number; originY: number; startBBox: NormalizedBBox }
  | { mode: "resize-ellipse"; handle: ResizeHandle; originX: number; originY: number; startBBox: NormalizedBBox }
  | {
      mode: "move-polygon-vertex";
      index: number;
      originX: number;
      originY: number;
      startPoints: NormalizedPoint[];
    }
  | { mode: "move-polygon"; originX: number; originY: number; startPoints: NormalizedPoint[] };

type CanvasStagePanelProps = {
  video: VideoMetadata | null;
  track: TrackSummary | null;
  keyframe: KeyframeSummary | null;
  keyframeDocument: Keyframe | null;
  /** W9: resolve reason for the current frame — threaded for future badge UI. */
  resolvedReason?: ResolveReason | null;
  busy: boolean;
  remoteError: string;
  isVideoPlaying?: boolean;
  mosaicPreviewEnabled?: boolean;
  playbackRate?: number;
  onionSkinEnabled?: boolean;
  /** Previous explicit keyframe (frame_index < currentFrame) of the selected track. */
  onionSkinPrev?: Keyframe | null;
  /** Next explicit keyframe (frame_index > currentFrame) of the selected track. */
  onionSkinNext?: Keyframe | null;
  onPreviewKeyframeChange: (keyframe: Keyframe | null) => void;
  onClearRemoteError: () => void;
  onCommitKeyframePatch: (patch: UpdateKeyframePayload["patch"]) => Promise<boolean>;
};

function toPercent(value: number) {
  return `${Math.max(0, Math.min(value, 1)) * 100}%`;
}

function renderOnionShape(keyframe: Keyframe, variant: "prev" | "next") {
  const className = `canvas-stage__onion-shape canvas-stage__onion-shape--${variant}`;
  if (keyframe.shape_type === "ellipse" && keyframe.bbox?.length === 4) {
    const cx = keyframe.bbox[0]! + keyframe.bbox[2]! / 2;
    const cy = keyframe.bbox[1]! + keyframe.bbox[3]! / 2;
    const rx = keyframe.bbox[2]! / 2;
    const ry = keyframe.bbox[3]! / 2;
    const rotation = keyframe.rotation ?? 0;
    const transform = rotation ? `rotate(${rotation} ${cx} ${cy})` : undefined;
    return (
      <ellipse
        key={`onion-${variant}-${keyframe.frame_index}`}
        className={className}
        cx={cx}
        cy={cy}
        rx={rx}
        ry={ry}
        transform={transform}
        vectorEffect="non-scaling-stroke"
      />
    );
  }
  if (keyframe.shape_type === "polygon" && (keyframe.points?.length ?? 0) >= 3) {
    return (
      <polygon
        key={`onion-${variant}-${keyframe.frame_index}`}
        className={className}
        points={keyframe.points.map((p) => `${p[0]},${p[1]}`).join(" ")}
        vectorEffect="non-scaling-stroke"
      />
    );
  }
  return null;
}

export function CanvasStagePanel({
  video,
  track,
  keyframe,
  keyframeDocument,
  resolvedReason,
  busy,
  remoteError,
  isVideoPlaying = false,
  mosaicPreviewEnabled = false,
  playbackRate = 1,
  onionSkinEnabled = false,
  onionSkinPrev = null,
  onionSkinNext = null,
  onPreviewKeyframeChange,
  onClearRemoteError,
  onCommitKeyframePatch,
}: CanvasStagePanelProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const draftBBoxRef = useRef<NormalizedBBox | null>(null);
  const draftPointsRef = useRef<NormalizedPoint[] | null>(null);
  const [draftBBox, setDraftBBox] = useState<NormalizedBBox | null>(null);
  const [draftPoints, setDraftPoints] = useState<NormalizedPoint[] | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [selectedVertexIndex, setSelectedVertexIndex] = useState<number | null>(null);
  const [vertexMenu, setVertexMenu] = useState<{ index: number; x: number; y: number } | null>(null);
  const [localError, setLocalError] = useState<string>("");

  const committedBBox = useMemo(() => {
    if (keyframeDocument?.bbox?.length === 4) {
      return normalizeBBox(keyframeDocument.bbox);
    }
    return null;
  }, [keyframeDocument]);

  const committedPoints = useMemo(() => {
    if (keyframeDocument?.points?.length) {
      return normalizePoints(keyframeDocument.points);
    }
    return null;
  }, [keyframeDocument]);

  const isEditableEllipse = keyframeDocument?.shape_type === "ellipse" && committedBBox !== null;
  const isEditablePolygon = keyframeDocument?.shape_type === "polygon" && (committedPoints?.length ?? 0) >= 3;
  const activeBBox = draftBBox ?? committedBBox;
  const activePoints = draftPoints ?? committedPoints;

  useEffect(() => {
    if (dragState) return;
    setDraftBBox(committedBBox);
    draftBBoxRef.current = committedBBox;
    setDraftPoints(committedPoints);
    draftPointsRef.current = committedPoints;
    setSelectedVertexIndex(null);
    setVertexMenu(null);
    setLocalError("");
    onPreviewKeyframeChange(null);
  }, [committedBBox, committedPoints, dragState, keyframeDocument?.frame_index, onPreviewKeyframeChange, track?.track_id]);

  async function commitPolygonPoints(nextPoints: NormalizedPoint[], nextSelectedVertexIndex: number | null) {
    setLocalError("");
    onClearRemoteError();
    setDraftPoints(nextPoints);
    draftPointsRef.current = nextPoints;
    onPreviewKeyframeChange(applyKeyframePatchPreview(keyframeDocument, { points: nextPoints }));
    const saved = await onCommitKeyframePatch({ points: nextPoints });
    if (!saved) {
      setDraftPoints(committedPoints);
      draftPointsRef.current = committedPoints;
      onPreviewKeyframeChange(null);
      return false;
    }
    setSelectedVertexIndex(nextSelectedVertexIndex);
    return true;
  }

  useEffect(() => {
    if (!dragState) return undefined;
    const activeDrag = dragState;

    function readPointer(event: PointerEvent) {
      const rect = stageRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) return null;
      return {
        x: (event.clientX - rect.left) / rect.width,
        y: (event.clientY - rect.top) / rect.height,
      };
    }

    function handlePointerMove(event: PointerEvent) {
      const point = readPointer(event);
      if (!point) return;

      if (activeDrag.mode === "move-polygon-vertex") {
        const deltaX = point.x - activeDrag.originX;
        const deltaY = point.y - activeDrag.originY;
        const nextPoints = activeDrag.startPoints.map((entry, index) =>
          index === activeDrag.index ? movePoint(entry, entry[0] + deltaX, entry[1] + deltaY) : entry,
        );
        draftPointsRef.current = nextPoints;
        setDraftPoints(nextPoints);
        onPreviewKeyframeChange(applyKeyframePatchPreview(keyframeDocument, { points: nextPoints }));
        return;
      }

      if (activeDrag.mode === "move-polygon") {
        const deltaX = point.x - activeDrag.originX;
        const deltaY = point.y - activeDrag.originY;
        const nextPoints = movePoints(activeDrag.startPoints, deltaX, deltaY);
        draftPointsRef.current = nextPoints;
        setDraftPoints(nextPoints);
        onPreviewKeyframeChange(applyKeyframePatchPreview(keyframeDocument, { points: nextPoints }));
        return;
      }

      const deltaX = point.x - activeDrag.originX;
      const deltaY = point.y - activeDrag.originY;
      const nextBBox =
        activeDrag.mode === "move-ellipse"
          ? moveBBox(activeDrag.startBBox, deltaX, deltaY)
          : resizeBBox(activeDrag.startBBox, activeDrag.handle, deltaX, deltaY);
      draftBBoxRef.current = nextBBox;
      setDraftBBox(nextBBox);
      onPreviewKeyframeChange(applyKeyframePatchPreview(keyframeDocument, { bbox: nextBBox }));
    }

    async function handleDragEnd() {
      if (activeDrag.mode === "move-polygon-vertex" || activeDrag.mode === "move-polygon") {
        const nextPoints = draftPointsRef.current;
        if (!nextPoints || pointsEqual(nextPoints, activeDrag.startPoints)) {
          setDraftPoints(activeDrag.startPoints);
          draftPointsRef.current = activeDrag.startPoints;
          onPreviewKeyframeChange(null);
          setDragState(null);
          return;
        }

        const nextSelectedVertex =
          activeDrag.mode === "move-polygon-vertex" ? activeDrag.index : selectedVertexIndex;
        const saved = await commitPolygonPoints(nextPoints, nextSelectedVertex);
        if (!saved) {
          setDraftPoints(activeDrag.startPoints);
          draftPointsRef.current = activeDrag.startPoints;
        }
        setDragState(null);
        return;
      }

      const nextBBox = draftBBoxRef.current;
      if (!nextBBox || bboxEquals(nextBBox, activeDrag.startBBox)) {
        setDraftBBox(activeDrag.startBBox);
        draftBBoxRef.current = activeDrag.startBBox;
        onPreviewKeyframeChange(null);
        setDragState(null);
        return;
      }

      onClearRemoteError();
      const saved = await onCommitKeyframePatch({ bbox: nextBBox });
      if (!saved) {
        setDraftBBox(activeDrag.startBBox);
        draftBBoxRef.current = activeDrag.startBBox;
        onPreviewKeyframeChange(null);
      }
      setDragState(null);
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handleDragEnd, { once: true });
    window.addEventListener("pointercancel", handleDragEnd, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handleDragEnd);
      window.removeEventListener("pointercancel", handleDragEnd);
    };
  }, [
    committedBBox,
    committedPoints,
    dragState,
    keyframeDocument,
    onClearRemoteError,
    onCommitKeyframePatch,
    onPreviewKeyframeChange,
    selectedVertexIndex,
  ]);

  function beginMove(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    if (!activeBBox || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    onClearRemoteError();
    setVertexMenu(null);
    setDragState({
      mode: "move-ellipse",
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startBBox: activeBBox,
    });
  }

  function beginResize(handle: ResizeHandle, event: React.PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    if (!activeBBox || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    event.stopPropagation();
    onClearRemoteError();
    setVertexMenu(null);
    setDragState({
      mode: "resize-ellipse",
      handle,
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startBBox: activeBBox,
    });
  }

  function beginVertexDrag(index: number, event: React.PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    if (!activePoints || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setLocalError("");
    setVertexMenu(null);
    setSelectedVertexIndex(index);
    setDragState({
      mode: "move-polygon-vertex",
      index,
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startPoints: activePoints,
    });
  }

  function beginPolygonMove(event: React.PointerEvent<SVGPolygonElement>) {
    if (event.button !== 0) return;
    if (!activePoints || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    setLocalError("");
    setVertexMenu(null);
    setDragState({
      mode: "move-polygon",
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startPoints: activePoints,
    });
  }

  async function handleAddVertex(afterIndex: number) {
    if (!activePoints || busy) return;
    setVertexMenu(null);
    const left = activePoints[afterIndex];
    const right = activePoints[(afterIndex + 1) % activePoints.length];
    if (!left || !right) return;
    const nextPoints = insertPointAfter(activePoints, afterIndex, midpoint(left, right));
    await commitPolygonPoints(nextPoints, afterIndex + 1);
  }

  async function handleDeleteVertex(index: number) {
    if (!activePoints || busy) return;
    setVertexMenu(null);
    if (activePoints.length <= 3) {
      setLocalError("ポリゴンは最低3頂点が必要です。");
      return;
    }
    const nextPoints = removePointAt(activePoints, index);
    const nextSelected = nextPoints.length ? Math.min(index, nextPoints.length - 1) : null;
    await commitPolygonPoints(nextPoints, nextSelected);
  }

  function openVertexMenu(index: number, event: React.MouseEvent<HTMLButtonElement>) {
    if (!activePoints || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    setLocalError("");
    setSelectedVertexIndex(index);
    setVertexMenu({
      index,
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    });
  }

  async function handleDeleteSelectedVertex() {
    if (selectedVertexIndex === null) return;
    await handleDeleteVertex(selectedVertexIndex);
  }

  if (!video) return null;

  return (
    <>
      <div
        ref={stageRef}
        className={`canvas-stage ${dragState ? "canvas-stage--dragging" : ""} ${busy ? "canvas-stage--saving" : ""}`}
        style={{ aspectRatio: `${video.width} / ${video.height}`, maxWidth: "100%", maxHeight: "100%" }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          if ((event.target as HTMLElement).closest(".canvas-stage__context-menu")) return;
          setVertexMenu(null);
        }}
      >
        <div className="canvas-stage__backdrop" />
        {onionSkinEnabled && (onionSkinPrev || onionSkinNext) ? (
          <svg
            className="canvas-stage__onion-svg"
            viewBox="0 0 1 1"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {onionSkinPrev ? renderOnionShape(onionSkinPrev, "prev") : null}
            {onionSkinNext ? renderOnionShape(onionSkinNext, "next") : null}
          </svg>
        ) : null}
        {/* Operation mode badge — top-left */}
        <div className="canvas-stage__mode-badge" aria-live="polite">
          <span
            className={`canvas-stage__mode-chip canvas-stage__mode-chip--${
              isVideoPlaying ? "playing" : "paused"
            }`}
          >
            {isVideoPlaying ? `再生中 ×${playbackRate}` : "停止中"}
          </span>
          <span
            className={`canvas-stage__mode-chip canvas-stage__mode-chip--${
              mosaicPreviewEnabled ? "mosaic-on" : "mosaic-off"
            }`}
          >
            {mosaicPreviewEnabled ? "モザイク ON" : "モザイク OFF"}
          </span>
          {track ? (
            <span className="canvas-stage__mode-chip canvas-stage__mode-chip--track">
              {track.label}
              {!track.visible && <span className="canvas-stage__mode-sub">非表示</span>}
              {!track.export_enabled && <span className="canvas-stage__mode-sub">書き出し外</span>}
              {track.user_locked && <span className="canvas-stage__mode-sub">ロック</span>}
            </span>
          ) : (
            <span className="canvas-stage__mode-chip canvas-stage__mode-chip--no-track">
              トラック未選択
            </span>
          )}
        </div>
        {/* Resolve-state overlay badge — top-right, pointer-events:none inherited */}
        {keyframeDocument !== null && resolveOverlayLabel(resolvedReason, keyframeDocument.source_detail) !== null ? (
          <div className="canvas-stage__resolve-badge">
            {resolveOverlayLabel(resolvedReason, keyframeDocument.source_detail)}
          </div>
        ) : null}
        {activePoints?.length ? (
          <svg className="canvas-stage__svg" viewBox="0 0 1 1" preserveAspectRatio="none">
            <polygon
              className={`canvas-stage__polygon ${isEditablePolygon ? "canvas-stage__polygon--editable" : ""}`}
              points={activePoints.map(([x, y]) => `${x},${y}`).join(" ")}
              onPointerDown={isEditablePolygon ? beginPolygonMove : undefined}
              onDoubleClick={isEditablePolygon ? (event) => {
                // Double-click on polygon edge → add vertex at nearest edge midpoint
                const svg = (event.target as SVGElement).closest("svg");
                if (!svg || !activePoints || activePoints.length < 3) return;
                const rect = svg.getBoundingClientRect();
                const clickX = (event.clientX - rect.left) / rect.width;
                const clickY = (event.clientY - rect.top) / rect.height;
                // Find nearest edge
                let bestIdx = 0;
                let bestDist = Infinity;
                for (let i = 0; i < activePoints.length; i++) {
                  const a = activePoints[i]!;
                  const b = activePoints[(i + 1) % activePoints.length]!;
                  const mx = (a[0] + b[0]) / 2;
                  const my = (a[1] + b[1]) / 2;
                  const d = Math.hypot(clickX - mx, clickY - my);
                  if (d < bestDist) { bestDist = d; bestIdx = i; }
                }
                void handleAddVertex(bestIdx);
              } : undefined}
            />
          </svg>
        ) : null}
        {activeBBox ? (
          <div
            className={`canvas-stage__bbox ${isEditableEllipse ? "canvas-stage__bbox--editable" : ""} ${
              dragState && dragState.mode !== "move-polygon-vertex" ? "canvas-stage__bbox--active" : ""
            }`}
            style={{
              left: toPercent(activeBBox[0]),
              top: toPercent(activeBBox[1]),
              width: toPercent(activeBBox[2]),
              height: toPercent(activeBBox[3]),
            }}
            onPointerDown={isEditableEllipse ? beginMove : undefined}
          >
            <div
              className="canvas-stage__ellipse"
              style={
                isEditableEllipse && keyframeDocument?.rotation
                  ? { transform: `rotate(${keyframeDocument.rotation}deg)` }
                  : undefined
              }
            />
            {isEditableEllipse ? (
              <>
                <button className="canvas-stage__handle canvas-stage__handle--nw" onPointerDown={(event) => beginResize("nw", event)} />
                <button className="canvas-stage__handle canvas-stage__handle--ne" onPointerDown={(event) => beginResize("ne", event)} />
                <button className="canvas-stage__handle canvas-stage__handle--sw" onPointerDown={(event) => beginResize("sw", event)} />
                <button className="canvas-stage__handle canvas-stage__handle--se" onPointerDown={(event) => beginResize("se", event)} />
              </>
            ) : null}
          </div>
        ) : null}
        {isEditablePolygon && activePoints ? (
          <>
            <div className="canvas-stage__edge-layer">
              {activePoints.map((point, index) => {
                const nextPoint = activePoints[(index + 1) % activePoints.length];
                if (!nextPoint) return null;
                const mid = midpoint(point, nextPoint);
                return (
                  <button
                    key={`${keyframe?.frame_index ?? "polygon"}-edge-${index}`}
                    className="canvas-stage__edge-handle"
                    style={{ left: toPercent(mid[0]), top: toPercent(mid[1]) }}
                    title={`辺 ${index} の後ろに頂点を追加`}
                    onClick={() => void handleAddVertex(index)}
                  />
                );
              })}
            </div>
            <div className="canvas-stage__vertex-layer">
              {activePoints.map((point, index) => (
                <button
                  key={`${keyframe?.frame_index ?? "polygon"}-${index}`}
                  className={`canvas-stage__vertex ${
                    selectedVertexIndex === index ? "canvas-stage__vertex--selected" : ""
                  } ${
                    dragState?.mode === "move-polygon-vertex" && dragState.index === index ? "canvas-stage__vertex--active" : ""
                  }`}
                  style={{ left: toPercent(point[0]), top: toPercent(point[1]) }}
                  title={`頂点 ${index} / 右クリックで削除`}
                  onClick={() => {
                    setLocalError("");
                    setVertexMenu(null);
                    setSelectedVertexIndex(index);
                  }}
                  onContextMenu={(event) => openVertexMenu(index, event)}
                  onPointerDown={(event) => beginVertexDrag(index, event)}
                />
              ))}
            </div>
            {vertexMenu ? (
              <div
                className="canvas-stage__context-menu"
                style={{ left: vertexMenu.x, top: vertexMenu.y }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <button type="button" onClick={() => void handleAddVertex(vertexMenu.index)} disabled={busy}>
                  頂点追加
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteVertex(vertexMenu.index)}
                  disabled={busy || (activePoints?.length ?? 0) <= 3}
                >
                  頂点削除
                </button>
              </div>
            ) : null}
          </>
        ) : null}
        {busy ? <div className="canvas-stage__busy">保存中...</div> : null}
        {isEditablePolygon && selectedVertexIndex !== null ? (
          <div style={{ position: "absolute", left: 8, bottom: 8, zIndex: 5 }}>
            <button className="nle-btn nle-btn--small" onClick={() => void handleDeleteSelectedVertex()} disabled={busy}>
              頂点削除
            </button>
          </div>
        ) : null}
      </div>
      {localError ? <p className="canvas-stage__hint" style={{ color: "var(--red)" }}>{localError}</p> : null}
      {remoteError ? <p className="canvas-stage__hint" style={{ color: "var(--red)" }}>{remoteError}</p> : null}
    </>
  );
}
