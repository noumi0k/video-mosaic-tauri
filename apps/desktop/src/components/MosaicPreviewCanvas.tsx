import { useEffect, useRef, type RefObject } from "react";
import type { Keyframe, MaskTrack, VideoMetadata } from "../types";
import { resolveForRender } from "../maskShapeResolver";

const MOSAIC_CELL_PX = 12;

function drawMosaicRegion(
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  keyframe: Keyframe,
  width: number,
  height: number,
  cellPx: number,
): void {
  let x0: number;
  let y0: number;
  let x1: number;
  let y1: number;

  if (keyframe.shape_type === "ellipse") {
    if (!keyframe.bbox || keyframe.bbox.length < 4) return;
    x0 = keyframe.bbox[0]! * width;
    y0 = keyframe.bbox[1]! * height;
    x1 = (keyframe.bbox[0]! + keyframe.bbox[2]!) * width;
    y1 = (keyframe.bbox[1]! + keyframe.bbox[3]!) * height;
  } else if (keyframe.shape_type === "polygon") {
    if (!keyframe.points || keyframe.points.length < 3) return;
    const xs = keyframe.points.map((point) => point[0]! * width);
    const ys = keyframe.points.map((point) => point[1]! * height);
    x0 = Math.min(...xs);
    y0 = Math.min(...ys);
    x1 = Math.max(...xs);
    y1 = Math.max(...ys);
  } else {
    return;
  }

  const regionX0 = Math.max(0, Math.floor(x0));
  const regionY0 = Math.max(0, Math.floor(y0));
  const regionX1 = Math.min(width, Math.ceil(x1));
  const regionY1 = Math.min(height, Math.ceil(y1));
  const regionWidth = regionX1 - regionX0;
  const regionHeight = regionY1 - regionY0;
  if (regionWidth <= 0 || regionHeight <= 0) return;

  const cellSize = Math.max(2, cellPx);
  const mosaicWidth = Math.max(1, Math.round(regionWidth / cellSize));
  const mosaicHeight = Math.max(1, Math.round(regionHeight / cellSize));

  const tinyCanvas = document.createElement("canvas");
  tinyCanvas.width = mosaicWidth;
  tinyCanvas.height = mosaicHeight;
  const tinyCtx = tinyCanvas.getContext("2d");
  if (!tinyCtx) return;

  tinyCtx.drawImage(video, regionX0, regionY0, regionWidth, regionHeight, 0, 0, mosaicWidth, mosaicHeight);

  ctx.save();
  ctx.beginPath();

  if (keyframe.shape_type === "ellipse") {
    const centerX = (keyframe.bbox[0]! + keyframe.bbox[2]! / 2) * width;
    const centerY = (keyframe.bbox[1]! + keyframe.bbox[3]! / 2) * height;
    const radiusX = (keyframe.bbox[2]! / 2) * width;
    const radiusY = (keyframe.bbox[3]! / 2) * height;
    const rotationRad = ((keyframe.rotation ?? 0) * Math.PI) / 180;
    ctx.ellipse(centerX, centerY, radiusX, radiusY, rotationRad, 0, Math.PI * 2);
  } else {
    const firstPoint = keyframe.points[0]!;
    ctx.moveTo(firstPoint[0]! * width, firstPoint[1]! * height);
    for (let index = 1; index < keyframe.points.length; index += 1) {
      const point = keyframe.points[index]!;
      ctx.lineTo(point[0]! * width, point[1]! * height);
    }
    ctx.closePath();
  }

  ctx.clip();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(tinyCanvas, 0, 0, mosaicWidth, mosaicHeight, regionX0, regionY0, regionWidth, regionHeight);
  ctx.imageSmoothingEnabled = true;
  ctx.restore();
}

function drawOutlineOnly(
  ctx: CanvasRenderingContext2D,
  keyframe: Keyframe,
  width: number,
  height: number,
): void {
  ctx.save();
  ctx.strokeStyle = "rgba(220, 38, 38, 0.9)";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();

  if (keyframe.shape_type === "ellipse") {
    if (!keyframe.bbox || keyframe.bbox.length < 4) {
      ctx.restore();
      return;
    }
    const centerX = (keyframe.bbox[0]! + keyframe.bbox[2]! / 2) * width;
    const centerY = (keyframe.bbox[1]! + keyframe.bbox[3]! / 2) * height;
    const radiusX = (keyframe.bbox[2]! / 2) * width;
    const radiusY = (keyframe.bbox[3]! / 2) * height;
    const rotationRad = ((keyframe.rotation ?? 0) * Math.PI) / 180;
    ctx.ellipse(centerX, centerY, radiusX, radiusY, rotationRad, 0, Math.PI * 2);
  } else if (keyframe.shape_type === "polygon") {
    if (!keyframe.points || keyframe.points.length < 3) {
      ctx.restore();
      return;
    }
    const firstPoint = keyframe.points[0]!;
    ctx.moveTo(firstPoint[0]! * width, firstPoint[1]! * height);
    for (let index = 1; index < keyframe.points.length; index += 1) {
      const point = keyframe.points[index]!;
      ctx.lineTo(point[0]! * width, point[1]! * height);
    }
    ctx.closePath();
  } else {
    ctx.restore();
    return;
  }

  ctx.stroke();
  ctx.restore();
}

type Props = {
  videoRef: RefObject<HTMLVideoElement | null>;
  tracks: MaskTrack[];
  currentFrame: number;
  videoMeta: VideoMetadata;
  enabled: boolean;
  cellPx?: number;
};

export function MosaicPreviewCanvas({
  videoRef,
  tracks,
  currentFrame,
  videoMeta,
  enabled,
  cellPx = MOSAIC_CELL_PX,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const tracksRef = useRef<MaskTrack[]>(tracks);
  const frameRef = useRef<number>(currentFrame);
  const cellRef = useRef<number>(cellPx);

  useEffect(() => {
    tracksRef.current = tracks;
  }, [tracks]);

  useEffect(() => {
    frameRef.current = currentFrame;
  }, [currentFrame]);

  useEffect(() => {
    cellRef.current = cellPx;
  }, [cellPx]);

  function drawFrame(
    ctx: CanvasRenderingContext2D,
    video: HTMLVideoElement,
    drawTracks: readonly MaskTrack[],
    frameIndex: number,
    cellSize: number,
  ) {
    const width = videoMeta.width;
    const height = videoMeta.height;

    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(video, 0, 0, width, height);

    for (const track of drawTracks) {
      if (!track.visible) continue;
      const resolved = resolveForRender(track, frameIndex);
      if (!resolved) continue;
      if (!track.export_enabled) {
        drawOutlineOnly(ctx, resolved.keyframe, width, height);
        continue;
      }
      drawMosaicRegion(ctx, video, resolved.keyframe, width, height, cellSize);
    }
  }

  useEffect(() => {
    if (!enabled) return;

    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const renderCtx = ctx;
    const renderVideo = video;

    const width = videoMeta.width;
    const height = videoMeta.height;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    function draw() {
      if (renderVideo.readyState < 2) return;
      drawFrame(renderCtx, renderVideo, tracksRef.current, frameRef.current, cellRef.current);
    }

    function rafLoop() {
      draw();
      rafRef.current = requestAnimationFrame(rafLoop);
    }

    function handlePlay() {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(rafLoop);
    }

    function handlePause() {
      cancelAnimationFrame(rafRef.current);
      draw();
    }

    function handleSeeked() {
      draw();
    }

    draw();
    if (!video.paused) {
      rafRef.current = requestAnimationFrame(rafLoop);
    }

    video.addEventListener("play", handlePlay);
    video.addEventListener("pause", handlePause);
    video.addEventListener("seeked", handleSeeked);

    return () => {
      cancelAnimationFrame(rafRef.current);
      video.removeEventListener("play", handlePlay);
      video.removeEventListener("pause", handlePause);
      video.removeEventListener("seeked", handleSeeked);
    };
  }, [enabled, videoMeta.height, videoMeta.width, videoRef]);

  useEffect(() => {
    if (!enabled) return;

    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video || video.readyState < 2) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    drawFrame(ctx, video, tracks, currentFrame, cellPx);
  }, [cellPx, currentFrame, enabled, tracks, videoMeta.height, videoMeta.width, videoRef]);

  return (
    <canvas
      ref={canvasRef}
      className="nle-preview-stage__mosaic-canvas"
      style={{ display: enabled ? "block" : "none" }}
    />
  );
}
