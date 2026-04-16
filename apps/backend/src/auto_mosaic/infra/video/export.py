from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from auto_mosaic.domain.mask_continuity import resolve_for_render
from auto_mosaic.domain.project import Keyframe, ProjectDocument
from auto_mosaic.infra.video.export_jobs import clear_runtime_state, is_cancel_requested, write_status
from auto_mosaic.runtime.external_tools import resolve_external_tool


class ExportCancelledError(Exception):
    pass


class FfmpegEncodeError(RuntimeError):
    def __init__(self, encoder_used: str, message: str) -> None:
        super().__init__(message)
        self.encoder_used = encoder_used


# ---------------------------------------------------------------------------
# GPU encoder probe
# ---------------------------------------------------------------------------

_GPU_ENCODER_CANDIDATES = ["h264_nvenc", "h264_qsv", "h264_amf"]

# Module-level cache: { ffmpeg_path -> [available_encoder, ...] }
_encoder_cache: dict[str, list[str]] = {}


def _open_capture(source_path: Path) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        raise RuntimeError(f"Failed to open the source video for export: {source_path}")
    return capture


def _probe_available_gpu_encoders(ffmpeg_path: str) -> list[str]:
    """Return GPU h264 encoder names that ffmpeg reports as available."""
    if ffmpeg_path in _encoder_cache:
        return _encoder_cache[ffmpeg_path]

    available: list[str] = []
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        output = result.stdout + result.stderr
        for enc in _GPU_ENCODER_CANDIDATES:
            if enc in output:
                available.append(enc)
    except Exception:
        pass

    _encoder_cache[ffmpeg_path] = available
    return available


def _build_encoder_cmd_fragment(
    encoder_pref: str,
    ffmpeg_path: str,
    bitrate_kbps: int,
) -> tuple[list[str], str, str | None]:
    """Return (ffmpeg_args, encoder_name_used, warning_or_None).

    encoder_pref: "auto" | "gpu" | "cpu"
    """
    br = bitrate_kbps
    maxrate = int(br * 1.5)
    bufsize = br * 2

    if encoder_pref == "cpu":
        args = [
            "-c:v", "libx264", "-preset", "medium",
            "-b:v", f"{br}k", "-maxrate", f"{maxrate}k",
            "-bufsize", f"{bufsize}k",
            "-pix_fmt", "yuv420p",
        ]
        return args, "libx264", None

    # "gpu" or "auto" — probe and try GPU encoders
    gpu_encoders = _probe_available_gpu_encoders(ffmpeg_path)

    if gpu_encoders:
        enc = gpu_encoders[0]
        if enc == "h264_nvenc":
            args = [
                "-c:v", "h264_nvenc", "-preset", "p4",
                "-b:v", f"{br}k", "-maxrate", f"{maxrate}k",
                "-bufsize", f"{bufsize}k",
                "-pix_fmt", "yuv420p",
            ]
        elif enc == "h264_qsv":
            args = [
                "-c:v", "h264_qsv", "-preset", "medium",
                "-b:v", f"{br}k",
                "-pix_fmt", "nv12",
            ]
        else:  # h264_amf
            args = [
                "-c:v", "h264_amf", "-quality", "balanced",
                "-b:v", f"{br}k",
                "-pix_fmt", "yuv420p",
            ]
        return args, enc, None

    # No GPU encoder found
    if encoder_pref == "gpu":
        # Caller asked explicitly for GPU; we will try but warn
        warning = "No GPU encoder found (h264_nvenc/qsv/amf). Falling back to CPU (libx264)."
    else:
        warning = None  # "auto" silently falls back

    args = [
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", f"{br}k", "-maxrate", f"{maxrate}k",
        "-bufsize", f"{bufsize}k",
        "-pix_fmt", "yuv420p",
    ]
    return args, "libx264", warning


# ---------------------------------------------------------------------------
# Resolution / bitrate presets (aligned with PySide6 ExportPreset)
# ---------------------------------------------------------------------------

_RESOLUTION_PRESETS: dict[str, tuple[int, int] | None] = {
    "source": None,
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "4k": (3840, 2160),
}


def _resolve_output_size(
    source_w: int, source_h: int, preset: str,
) -> tuple[int, int]:
    """Return (width, height) for the output, both even numbers."""
    target = _RESOLUTION_PRESETS.get(preset)
    if target is None:
        w, h = source_w, source_h
    else:
        tw, th = target
        scale = min(tw / max(source_w, 1), th / max(source_h, 1))
        w = int(round(source_w * scale))
        h = int(round(source_h * scale))
    # Ensure even dimensions (required by most codecs).
    w += w % 2
    h += h % 2
    return w, h


def _auto_bitrate_kbps(width: int, height: int) -> int:
    """PySide6-aligned auto bitrate selection."""
    pixels = width * height
    if pixels >= 3840 * 2160:
        return 40000
    if pixels >= 1920 * 1080:
        return 16000
    if pixels >= 1280 * 720:
        return 8000
    return 4000


def _set_job_status(
    job_id: str | None,
    *,
    phase: str,
    progress: float,
    message: str,
    frames_written: int = 0,
    total_frames: int | None = None,
    audio_mode: str | None = None,
    audio_status: str | None = None,
    output_path: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    write_status(
        job_id,
        {
            "phase": phase,
            "progress": round(max(0.0, min(progress, 1.0)), 4),
            "message": message,
            "frames_written": frames_written,
            "total_frames": total_frames,
            "audio_mode": audio_mode,
            "audio_status": audio_status,
            "output_path": output_path,
            "warnings": warnings or [],
        },
    )


def _choose_fourcc(path: Path) -> int:
    suffix = path.suffix.lower()
    if suffix == ".avi":
        return cv2.VideoWriter_fourcc(*"MJPG")
    return cv2.VideoWriter_fourcc(*"mp4v")


def _normalized_point(point: list[float], width: int, height: int) -> tuple[int, int]:
    x = int(round(float(point[0]) * max(width - 1, 1)))
    y = int(round(float(point[1]) * max(height - 1, 1)))
    return x, y


def _normalized_bbox(bbox: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x = int(round(float(bbox[0]) * width))
    y = int(round(float(bbox[1]) * height))
    w = max(int(round(float(bbox[2]) * width)), 1)
    h = max(int(round(float(bbox[3]) * height)), 1)
    x = max(min(x, max(width - 1, 0)), 0)
    y = max(min(y, max(height - 1, 0)), 0)
    w = min(w, max(width - x, 1))
    h = min(h, max(height - y, 1))
    return x, y, w, h


def _build_shape_mask(frame_shape: tuple[int, ...], keyframe: Keyframe) -> np.ndarray:
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    if keyframe.shape_type == "ellipse":
        x, y, w, h = _normalized_bbox(keyframe.bbox, width, height)
        center = (x + (w // 2), y + (h // 2))
        axes = (max(w // 2, 1), max(h // 2, 1))
        cv2.ellipse(mask, center, axes, float(keyframe.rotation), 0.0, 360.0, 255, thickness=-1)
    else:
        points = np.array([_normalized_point(point, width, height) for point in keyframe.points], dtype=np.int32)
        if len(points) >= 3:
            cv2.fillPoly(mask, [points], 255)

    # expand_px: マスク境界をピクセル単位で外側に拡張する
    # ユーザーが設定したモザイク領域がマスクを超える場合に使用
    if keyframe.expand_px is not None and keyframe.expand_px > 0:
        px = int(keyframe.expand_px)
        kernel_size = px * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        mask = cv2.dilate(mask, kernel)

    return mask


def _apply_mosaic_mask(frame: np.ndarray, keyframe: Keyframe, mosaic_cell_px: int = 12) -> np.ndarray:
    """Apply pixelated mosaic to the region defined by keyframe's mask.

    Respects expand_px (mask dilation, handled in _build_shape_mask) and
    feather (soft edge blending via Gaussian blur of the binary mask).

    feather=0 or None  → hard binary mask (original behaviour)
    feather>0          → GaussianBlur softens the mask edge; pixels near the
                         boundary are partially blended (alpha compositing).
    """
    mask = _build_shape_mask(frame.shape, keyframe)
    if not np.any(mask):
        return frame

    height, width = frame.shape[:2]
    block = max(int(mosaic_cell_px), 2)
    feather_px = int(keyframe.feather) if (keyframe.feather is not None and keyframe.feather > 0) else 0

    # Binary-mask bounding box
    ys, xs = np.where(mask > 0)
    bx0 = int(xs.min())
    bx1 = int(xs.max()) + 1
    by0 = int(ys.min())
    by1 = int(ys.max()) + 1

    if feather_px > 0:
        # Extend ROI outward so the blurred fringe beyond the binary edge is captured
        x0 = max(0, bx0 - feather_px)
        x1 = min(width, bx1 + feather_px)
        y0 = max(0, by0 - feather_px)
        y1 = min(height, by1 + feather_px)

        ksize = feather_px * 2 + 1
        soft_mask = cv2.GaussianBlur(
            mask.astype(np.float32), (ksize, ksize), sigmaX=feather_px / 2.0,
        )
        alpha = soft_mask[y0:y1, x0:x1] / 255.0          # (h, w) in [0.0, 1.0]
        alpha_3c = alpha[:, :, np.newaxis]                  # broadcast over BGR channels

        roi_orig = frame[y0:y1, x0:x1].astype(np.float32)
        roi_h, roi_w = roi_orig.shape[:2]
        reduced = cv2.resize(
            roi_orig, (max(1, roi_w // block), max(1, roi_h // block)),
            interpolation=cv2.INTER_LINEAR,
        )
        mosaic = cv2.resize(reduced, (roi_w, roi_h), interpolation=cv2.INTER_NEAREST)

        blended = (roi_orig * (1.0 - alpha_3c) + mosaic * alpha_3c).astype(np.uint8)
        output = frame.copy()
        output[y0:y1, x0:x1] = blended
    else:
        # Hard binary mask — same as original behaviour
        x0, x1, y0, y1 = bx0, bx1, by0, by1
        output = frame.copy()
        roi = output[y0:y1, x0:x1]
        roi_mask = mask[y0:y1, x0:x1]
        roi_h, roi_w = roi.shape[:2]
        reduced = cv2.resize(
            roi, (max(1, roi_w // block), max(1, roi_h // block)),
            interpolation=cv2.INTER_LINEAR,
        )
        mosaic = cv2.resize(reduced, (roi_w, roi_h), interpolation=cv2.INTER_NEAREST)
        roi[roi_mask > 0] = mosaic[roi_mask > 0]
        output[y0:y1, x0:x1] = roi

    return output


def _ffmpeg_pipe_export(
    *,
    capture: cv2.VideoCapture,
    project: "ProjectDocument",
    output: Path,
    source_path: Path,
    width: int,
    height: int,
    out_w: int,
    out_h: int,
    fps: float,
    total_frames: int,
    mosaic_strength: int,
    audio_mode: str,
    bitrate_kbps: int,
    job_id: str | None,
    ffmpeg_path: str,
    encoder_pref: str = "auto",
) -> tuple[int, str, str, list[str]]:
    """Render frames through an ffmpeg rawvideo pipe.

    Returns (written_frames, audio_status, encoder_used, warnings).
    Raises ExportCancelledError on cancel.
    """
    needs_resize = (out_w != width or out_h != height)
    warnings: list[str] = []
    audio_status = "video-only"

    encoder_args, encoder_used, encoder_warning = _build_encoder_cmd_fragment(
        encoder_pref, ffmpeg_path, bitrate_kbps
    )
    if encoder_warning:
        warnings.append(encoder_warning)

    cmd: list[str] = [
        ffmpeg_path, "-y",
        # rawvideo input from stdin
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}", "-r", str(fps),
        "-i", "pipe:0",
    ]
    if audio_mode == "mux_if_possible":
        cmd += ["-i", str(source_path), "-map", "0:v:0", "-map", "1:a:0?"]
    cmd += encoder_args
    if audio_mode == "mux_if_possible":
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(str(output))

    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdin is not None

    written_frames = 0
    try:
        frame_index = 0
        while True:
            if is_cancel_requested(job_id):
                process.stdin.close()
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise ExportCancelledError("Export was cancelled.")

            ok, frame = capture.read()
            if not ok:
                break

            rendered = frame
            for track in project.tracks:
                if not track.visible:
                    continue
                if not track.export_enabled:
                    continue
                _resolved = resolve_for_render(track, frame_index)
                if _resolved is None:
                    continue
                rendered = _apply_mosaic_mask(rendered, _resolved[0], mosaic_strength)

            if needs_resize:
                interp = cv2.INTER_AREA if (out_w < width) else cv2.INTER_LINEAR
                rendered = cv2.resize(rendered, (out_w, out_h), interpolation=interp)

            process.stdin.write(rendered.tobytes())
            frame_index += 1
            written_frames += 1
            if job_id and (written_frames == 1 or written_frames % 5 == 0 or written_frames == total_frames):
                render_ratio = (written_frames / total_frames) if total_frames > 0 else 0.0
                _set_job_status(
                    job_id,
                    phase="rendering_frames",
                    progress=min(0.9, 0.08 + (render_ratio * 0.8)),
                    message=f"Rendering mosaic frames (ffmpeg {encoder_used})",
                    frames_written=written_frames,
                    total_frames=total_frames,
                    audio_mode=audio_mode,
                    output_path=str(output),
                )
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass

    _, stderr_bytes = process.communicate(timeout=60)
    if process.returncode != 0:
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise FfmpegEncodeError(
            encoder_used,
            f"ffmpeg encoding failed (exit {process.returncode}): {stderr_text[-300:]}",
        )

    if audio_mode == "mux_if_possible":
        audio_status = "muxed"

    return written_frames, audio_status, encoder_used, warnings


def _mux_original_audio(
    video_only_path: Path,
    source_path: Path,
    output_path: Path,
    job_id: str | None,
) -> tuple[bool, list[str]]:
    _set_job_status(
        job_id,
        phase="muxing_audio",
        progress=0.92,
        message="Muxing original audio",
    )
    ffmpeg = resolve_external_tool("ffmpeg")
    if not ffmpeg["found"] or not ffmpeg["path"]:
        return False, ["ffmpeg was not available, so the export was saved without audio."]
    ffprobe = resolve_external_tool("ffprobe")
    if not ffprobe["found"] or not ffprobe["path"]:
        return False, ["ffprobe was not available, so the export was saved without audio verification."]

    muxed_output = output_path.with_name(f"{output_path.stem}.muxed{output_path.suffix}")
    command = [
        ffmpeg["path"],
        "-y",
        "-i",
        str(video_only_path),
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(muxed_output),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return False, [f"ffmpeg audio mux failed to start: {exc}"]

    while process.poll() is None:
        if is_cancel_requested(job_id):
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
            raise ExportCancelledError("Export was cancelled during audio mux.")
        time.sleep(0.05)

    stdout, stderr = process.communicate()

    class CompletedProcessLike:
        def __init__(self, returncode: int, stdout_value: str, stderr_value: str) -> None:
            self.returncode = returncode
            self.stdout = stdout_value
            self.stderr = stderr_value

    completed = CompletedProcessLike(process.returncode, stdout, stderr)

    if completed.returncode != 0 or not muxed_output.exists():
        stderr = completed.stderr.strip()
        message = "ffmpeg audio mux failed, so the export was saved without audio."
        if stderr:
            message = f"{message} {stderr.splitlines()[-1]}"
        return False, [message]

    muxed_stream_types = _probe_stream_types(muxed_output, ffprobe["path"], job_id)
    if "audio" not in muxed_stream_types:
        muxed_output.unlink(missing_ok=True)
        return False, ["The source export did not contain a usable audio stream, so the export was saved without audio."]

    shutil.move(str(muxed_output), str(output_path))
    return True, []


def _probe_stream_types(path: Path, ffprobe_path: str, job_id: str | None = None) -> list[str]:
    if is_cancel_requested(job_id):
        raise ExportCancelledError("Export was cancelled during media probe.")

    completed = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return []

    payload = {}
    try:
        import json

        payload = json.loads(completed.stdout)
    except Exception:
        return []
    return [stream.get("codec_type", "") for stream in payload.get("streams", [])]


def export_project_video(
    project: ProjectDocument,
    output_path: str,
    mosaic_strength: int = 12,
    audio_mode: str = "mux_if_possible",
    job_id: str | None = None,
    resolution: str = "source",
    bitrate_kbps: int | None = None,
    encoder: str = "auto",
) -> dict:
    if project.video is None:
        return {
            "ok": False,
            "error": {
                "code": "VIDEO_REQUIRED",
                "message": "Project does not have a source video.",
                "details": {},
            },
            "warnings": [],
        }

    source_path = Path(project.video.source_path)
    if not source_path.exists():
        return {
            "ok": False,
            "error": {
                "code": "SOURCE_VIDEO_NOT_FOUND",
                "message": "Source video file does not exist.",
                "details": {"source_path": str(source_path)},
            },
            "warnings": [],
        }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    try:
        capture = _open_capture(source_path)
    except RuntimeError:
        return {
            "ok": False,
            "error": {
                "code": "SOURCE_VIDEO_OPEN_FAILED",
                "message": "Failed to open the source video for export.",
                "details": {"source_path": str(source_path)},
            },
            "warnings": [],
        }

    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or project.video.width)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or project.video.height)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or project.video.fps or 24.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or project.video.frame_count or 0)
    out_w, out_h = _resolve_output_size(width, height, resolution)
    if bitrate_kbps is None or bitrate_kbps <= 0:
        bitrate_kbps = _auto_bitrate_kbps(out_w, out_h)
    written_frames = 0
    audio_status = "video-only"
    encoder_used = "opencv"
    _set_job_status(
        job_id,
        phase="preparing",
        progress=0.02,
        message="Preparing export",
        total_frames=total_frames,
        audio_mode=audio_mode,
        output_path=str(output),
    )

    ffmpeg_info = resolve_external_tool("ffmpeg")
    use_ffmpeg = bool(ffmpeg_info.get("found") and ffmpeg_info.get("path"))

    try:
        if use_ffmpeg:
            # ── FFmpeg pipe export: h264 encoding + audio mux in one pass ──
            try:
                try:
                    written_frames, audio_status, encoder_used, ffmpeg_warnings = _ffmpeg_pipe_export(
                        capture=capture,
                        project=project,
                        output=output,
                        source_path=source_path,
                        width=width,
                        height=height,
                        out_w=out_w,
                        out_h=out_h,
                        fps=fps,
                        total_frames=total_frames,
                        mosaic_strength=mosaic_strength,
                        audio_mode=audio_mode,
                        bitrate_kbps=bitrate_kbps,
                        job_id=job_id,
                        ffmpeg_path=ffmpeg_info["path"],
                        encoder_pref=encoder,
                    )
                    warnings.extend(ffmpeg_warnings)
                except FfmpegEncodeError as exc:
                    if encoder != "auto" or exc.encoder_used not in _GPU_ENCODER_CANDIDATES:
                        raise
                    warnings.append(
                        f"{exc.encoder_used} failed at runtime in auto mode. Retrying export with CPU encoder (libx264)."
                    )
                    output.unlink(missing_ok=True)
                    capture.release()
                    capture = _open_capture(source_path)
                    _set_job_status(
                        job_id,
                        phase="preparing",
                        progress=0.03,
                        message="Retrying export with CPU encoder",
                        total_frames=total_frames,
                        audio_mode=audio_mode,
                        output_path=str(output),
                        warnings=warnings,
                    )
                    written_frames, audio_status, encoder_used, ffmpeg_warnings = _ffmpeg_pipe_export(
                        capture=capture,
                        project=project,
                        output=output,
                        source_path=source_path,
                        width=width,
                        height=height,
                        out_w=out_w,
                        out_h=out_h,
                        fps=fps,
                        total_frames=total_frames,
                        mosaic_strength=mosaic_strength,
                        audio_mode=audio_mode,
                        bitrate_kbps=bitrate_kbps,
                        job_id=job_id,
                        ffmpeg_path=ffmpeg_info["path"],
                        encoder_pref="cpu",
                    )
                    warnings.extend(ffmpeg_warnings)
            finally:
                capture.release()
        else:
            # ── OpenCV fallback: mp4v/MJPG encoding, then optional audio mux ──
            warnings.append("ffmpeg not found — using OpenCV encoder (lower quality, no bitrate control).")
            with tempfile.TemporaryDirectory(prefix="taurimozaic-export-") as temp_dir:
                temp_output = Path(temp_dir) / f"{output.stem}.video-only{output.suffix}"
                writer = cv2.VideoWriter(str(temp_output), _choose_fourcc(temp_output), fps, (out_w, out_h))
                if not writer.isOpened():
                    capture.release()
                    return {
                        "ok": False,
                        "error": {
                            "code": "OUTPUT_OPEN_FAILED",
                            "message": "Failed to open the export output path.",
                            "details": {"output_path": str(output)},
                        },
                        "warnings": [],
                    }

                needs_resize = (out_w != width or out_h != height)
                frame_index = 0
                try:
                    while True:
                        if is_cancel_requested(job_id):
                            raise ExportCancelledError("Export was cancelled before completion.")

                        ok, frame = capture.read()
                        if not ok:
                            break

                        rendered = frame
                        for track in project.tracks:
                            if not track.visible:
                                continue
                            if not track.export_enabled:
                                continue
                            _resolved = resolve_for_render(track, frame_index)
                            if _resolved is None:
                                continue
                            rendered = _apply_mosaic_mask(rendered, _resolved[0], mosaic_strength)

                        if needs_resize:
                            interp = cv2.INTER_AREA if (out_w < width) else cv2.INTER_LINEAR
                            rendered = cv2.resize(rendered, (out_w, out_h), interpolation=interp)

                        writer.write(rendered)
                        frame_index += 1
                        written_frames += 1
                        if job_id and (written_frames == 1 or written_frames % 5 == 0 or written_frames == total_frames):
                            render_ratio = (written_frames / total_frames) if total_frames > 0 else 0.0
                            _set_job_status(
                                job_id,
                                phase="rendering_frames",
                                progress=min(0.9, 0.08 + (render_ratio * 0.8)),
                                message="Rendering mosaic frames (OpenCV fallback)",
                                frames_written=written_frames,
                                total_frames=total_frames,
                                audio_mode=audio_mode,
                                output_path=str(output),
                            )
                finally:
                    capture.release()
                    writer.release()

                if output.exists():
                    output.unlink()

                if is_cancel_requested(job_id):
                    raise ExportCancelledError("Export was cancelled after rendering.")

                if audio_mode == "mux_if_possible":
                    audio_muxed, audio_warnings = _mux_original_audio(temp_output, source_path, output, job_id)
                    warnings.extend(audio_warnings)
                    if audio_muxed:
                        audio_status = "muxed"
                    else:
                        shutil.move(str(temp_output), str(output))
                else:
                    shutil.move(str(temp_output), str(output))
    except ExportCancelledError as exc:
        if output.exists():
            output.unlink(missing_ok=True)
        _set_job_status(
            job_id,
            phase="cancelled",
            progress=0.0,
            message=str(exc),
            frames_written=written_frames,
            total_frames=total_frames,
            audio_mode=audio_mode,
            audio_status=audio_status,
            output_path=str(output),
            warnings=warnings,
        )
        return {
            "ok": False,
            "error": {
                "code": "EXPORT_CANCELLED",
                "message": str(exc),
                "details": {"job_id": job_id},
            },
            "warnings": warnings,
        }
    except Exception as exc:
        _set_job_status(
            job_id,
            phase="failed",
            progress=0.0,
            message=str(exc),
            frames_written=written_frames,
            total_frames=total_frames,
            audio_mode=audio_mode,
            audio_status=audio_status,
            output_path=str(output),
            warnings=warnings,
        )
        raise
    finally:
        clear_runtime_state(job_id)

    _set_job_status(
        job_id,
        phase="completed",
        progress=1.0,
        message="Export completed",
        frames_written=written_frames,
        total_frames=total_frames,
        audio_mode=audio_mode,
        audio_status=audio_status,
        output_path=str(output),
        warnings=warnings,
    )

    return {
        "ok": True,
        "data": {
            "output_path": str(output),
            "source_path": str(source_path),
            "frame_count": written_frames,
            "fps": fps,
            "width": out_w,
            "height": out_h,
            "source_width": width,
            "source_height": height,
            "resolution": resolution,
            "bitrate_kbps": bitrate_kbps,
            "encoder": encoder_used,
            "effect": "mosaic",
            "audio": audio_status,
            "audio_mode": audio_mode,
            "mosaic_strength": mosaic_strength,
        },
        "warnings": warnings,
    }
