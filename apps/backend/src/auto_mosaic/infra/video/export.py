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
        cv2.ellipse(mask, center, axes, 0.0, 0.0, 360.0, 255, thickness=-1)
        return mask

    points = np.array([_normalized_point(point, width, height) for point in keyframe.points], dtype=np.int32)
    if len(points) >= 3:
        cv2.fillPoly(mask, [points], 255)
    return mask


def _apply_mosaic_mask(frame: np.ndarray, keyframe: Keyframe, mosaic_cell_px: int = 12) -> np.ndarray:
    mask = _build_shape_mask(frame.shape, keyframe)
    if not np.any(mask):
        return frame

    output = frame.copy()
    ys, xs = np.where(mask > 0)
    x0 = int(xs.min())
    x1 = int(xs.max()) + 1
    y0 = int(ys.min())
    y1 = int(ys.max()) + 1
    roi = output[y0:y1, x0:x1]
    roi_mask = mask[y0:y1, x0:x1]
    roi_height, roi_width = roi.shape[:2]

    block = max(int(mosaic_cell_px), 2)
    downsampled_width = max(1, roi_width // block)
    downsampled_height = max(1, roi_height // block)
    reduced = cv2.resize(roi, (downsampled_width, downsampled_height), interpolation=cv2.INTER_LINEAR)
    mosaic = cv2.resize(reduced, (roi_width, roi_height), interpolation=cv2.INTER_NEAREST)
    roi[roi_mask > 0] = mosaic[roi_mask > 0]
    output[y0:y1, x0:x1] = roi
    return output


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

    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
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
    written_frames = 0
    audio_status = "video-only"
    _set_job_status(
        job_id,
        phase="preparing",
        progress=0.02,
        message="Preparing export",
        total_frames=total_frames,
        audio_mode=audio_mode,
        output_path=str(output),
    )

    try:
        with tempfile.TemporaryDirectory(prefix="taurimozaic-export-") as temp_dir:
            temp_output = Path(temp_dir) / f"{output.stem}.video-only{output.suffix}"
            writer = cv2.VideoWriter(str(temp_output), _choose_fourcc(temp_output), fps, (width, height))
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
                        _resolved = resolve_for_render(track, frame_index)
                        if _resolved is None:
                            continue
                        active_keyframe = _resolved[0]
                        rendered = _apply_mosaic_mask(rendered, active_keyframe, mosaic_strength)

                    writer.write(rendered)
                    frame_index += 1
                    written_frames += 1
                    if job_id and (written_frames == 1 or written_frames % 5 == 0 or written_frames == total_frames):
                        render_ratio = (written_frames / total_frames) if total_frames > 0 else 0.0
                        _set_job_status(
                            job_id,
                            phase="rendering_frames",
                            progress=min(0.9, 0.08 + (render_ratio * 0.8)),
                            message="Rendering mosaic frames",
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
            "width": width,
            "height": height,
            "effect": "mosaic",
            "audio": audio_status,
            "audio_mode": audio_mode,
            "mosaic_strength": mosaic_strength,
        },
        "warnings": warnings,
    }
