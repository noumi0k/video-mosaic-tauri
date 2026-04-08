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
import type { Keyframe, KeyframeSummary, TrackSummary, UpdateKeyframePayload, VideoMetadata } from "../types";
import { applyKeyframePatchPreview } from "../keyframePreview";

type DragState =
  | { mode: "move-ellipse"; originX: number; originY: number; startBBox: NormalizedBBox }
  | { mode: "resize-ellipse"; handle: ResizeHandle; originX: number; originY: number; startBBox: NormalizedBBox }
  | { mode: "move-polygon-vertex"; index: number }
  | { mode: "move-polygon"; originX: number; originY: number; startPoints: NormalizedPoint[] };

type CanvasStagePanelProps = {
  video: VideoMetadata | null;
  track: TrackSummary | null;
  keyframe: KeyframeSummary | null;
  keyframeDocument: Keyframe | null;
  busy: boolean;
  remoteError: string;
  onPreviewKeyframeChange: (keyframe: Keyframe | null) => void;
  onClearRemoteError: () => void;
  onCommitKeyframePatch: (patch: UpdateKeyframePayload["patch"]) => Promise<boolean>;
};

function toPercent(value: number) {
  return `${Math.max(0, Math.min(value, 1)) * 100}%`;
}

export function CanvasStagePanel({
  video,
  track,
  keyframe,
  keyframeDocument,
  busy,
  remoteError,
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
    setDraftBBox(committedBBox);
    draftBBoxRef.current = committedBBox;
    setDraftPoints(committedPoints);
    draftPointsRef.current = committedPoints;
    setSelectedVertexIndex(null);
    setLocalError("");
    onPreviewKeyframeChange(null);
  }, [committedBBox, committedPoints, keyframeDocument?.frame_index, onPreviewKeyframeChange, track?.track_id]);

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
        const currentPoints = draftPointsRef.current;
        if (!currentPoints || !currentPoints[activeDrag.index]) return;
        const nextPoints = currentPoints.map((entry, index) =>
          index === activeDrag.index ? movePoint(entry, point.x, point.y) : entry,
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
      setDragState(null);

      if (activeDrag.mode === "move-polygon-vertex" || activeDrag.mode === "move-polygon") {
        const nextPoints = draftPointsRef.current;
        if (!nextPoints || !committedPoints || pointsEqual(nextPoints, committedPoints)) {
          setDraftPoints(committedPoints);
          draftPointsRef.current = committedPoints;
          onPreviewKeyframeChange(null);
          return;
        }

        const nextSelectedVertex =
          activeDrag.mode === "move-polygon-vertex" ? activeDrag.index : selectedVertexIndex;
        const saved = await commitPolygonPoints(nextPoints, nextSelectedVertex);
        if (!saved) {
          setDraftPoints(committedPoints);
          draftPointsRef.current = committedPoints;
        }
        return;
      }

      const nextBBox = draftBBoxRef.current;
      if (!nextBBox || !committedBBox || bboxEquals(nextBBox, committedBBox)) {
        setDraftBBox(committedBBox);
        draftBBoxRef.current = committedBBox;
        onPreviewKeyframeChange(null);
        return;
      }

      onClearRemoteError();
      const saved = await onCommitKeyframePatch({ bbox: nextBBox });
      if (!saved) {
        setDraftBBox(committedBBox);
        draftBBoxRef.current = committedBBox;
        onPreviewKeyframeChange(null);
      }
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
    if (!activeBBox || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    onClearRemoteError();
    setDragState({
      mode: "move-ellipse",
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startBBox: activeBBox,
    });
  }

  function beginResize(handle: ResizeHandle, event: React.PointerEvent<HTMLButtonElement>) {
    if (!activeBBox || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    event.stopPropagation();
    onClearRemoteError();
    setDragState({
      mode: "resize-ellipse",
      handle,
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startBBox: activeBBox,
    });
  }

  function beginVertexDrag(index: number, event: React.PointerEvent<HTMLButtonElement>) {
    if (!activePoints || busy) return;
    event.preventDefault();
    event.stopPropagation();
    setLocalError("");
    setSelectedVertexIndex(index);
    setDragState({ mode: "move-polygon-vertex", index });
  }

  function beginPolygonMove(event: React.PointerEvent<SVGPolygonElement>) {
    if (!activePoints || busy) return;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;
    event.preventDefault();
    setLocalError("");
    setDragState({
      mode: "move-polygon",
      originX: (event.clientX - rect.left) / rect.width,
      originY: (event.clientY - rect.top) / rect.height,
      startPoints: activePoints,
    });
  }

  async function handleAddVertex(afterIndex: number) {
    if (!activePoints || busy) return;
    const left = activePoints[afterIndex];
    const right = activePoints[(afterIndex + 1) % activePoints.length];
    if (!left || !right) return;
    const nextPoints = insertPointAfter(activePoints, afterIndex, midpoint(left, right));
    await commitPolygonPoints(nextPoints, afterIndex + 1);
  }

  async function handleDeleteSelectedVertex() {
    if (!activePoints || busy || selectedVertexIndex === null) return;
    if (activePoints.length <= 3) {
      setLocalError("ポリゴンは最低 3 頂点が必要です。");
      return;
    }
    const nextPoints = removePointAt(activePoints, selectedVertexIndex);
    const nextSelected = nextPoints.length ? Math.min(selectedVertexIndex, nextPoints.length - 1) : null;
    await commitPolygonPoints(nextPoints, nextSelected);
  }

  if (!video) return null;

  return (
    <>
      <div
        ref={stageRef}
        className={`canvas-stage ${dragState ? "canvas-stage--dragging" : ""} ${busy ? "canvas-stage--saving" : ""}`}
        style={{ aspectRatio: `${video.width} / ${video.height}`, maxWidth: "100%", maxHeight: "100%" }}
      >
        <div className="canvas-stage__backdrop" />
        {activePoints?.length ? (
          <svg className="canvas-stage__svg" viewBox="0 0 1 1" preserveAspectRatio="none">
            <polygon
              className={`canvas-stage__polygon ${isEditablePolygon ? "canvas-stage__polygon--editable" : ""}`}
              points={activePoints.map(([x, y]) => `${x},${y}`).join(" ")}
              onPointerDown={isEditablePolygon ? beginPolygonMove : undefined}
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
            <div className="canvas-stage__ellipse" />
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
                  title={`頂点 ${index}`}
                  onClick={() => {
                    setLocalError("");
                    setSelectedVertexIndex(index);
                  }}
                  onPointerDown={(event) => beginVertexDrag(index, event)}
                />
              ))}
            </div>
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
