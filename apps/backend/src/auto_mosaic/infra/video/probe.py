from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2

from auto_mosaic.runtime.external_tools import resolve_external_tool


def _ffprobe(video_path: str, *, progress_callback=None, cancel_requested=None, ensure_not_cancelled=None) -> dict:
    ffprobe = resolve_external_tool("ffprobe")
    if not ffprobe["found"]:
        return {"ok": False, "error": "ffprobe not found"}

    if callable(progress_callback):
        progress_callback(
            stage="metadata_probe",
            message="動画メタ情報を取得中",
            progress_percent=18.0,
            is_indeterminate=True,
            can_cancel=False,
        )
    if callable(ensure_not_cancelled):
        ensure_not_cancelled("動画読み込みを中断しました。")
    elif callable(cancel_requested) and cancel_requested():
        raise RuntimeError("動画読み込みを中断しました。")

    command = [
        ffprobe["path"],
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=20)
    if completed.returncode != 0:
        return {"ok": False, "error": completed.stderr.strip() or "ffprobe failed"}

    return {"ok": True, "data": json.loads(completed.stdout)}


def probe_video(video_path: str, *, progress_callback=None, cancel_requested=None, ensure_not_cancelled=None) -> dict:
    path = Path(video_path)
    if not path.exists():
        return {
            "ok": False,
            "data": None,
            "warnings": [],
            "error": {
                "code": "VIDEO_NOT_FOUND",
                "message": "Video file does not exist.",
                "details": {"video_path": str(path)},
            },
        }

    ffprobe_result = _ffprobe(
        str(path),
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
        ensure_not_cancelled=ensure_not_cancelled,
    )

    if callable(progress_callback):
        progress_callback(
            stage="preview_probe",
            message="先頭フレームを準備中",
            progress_percent=56.0,
            is_indeterminate=True,
            can_cancel=False,
        )
    if callable(ensure_not_cancelled):
        ensure_not_cancelled("動画読み込みを中断しました。")
    elif callable(cancel_requested) and cancel_requested():
        raise RuntimeError("動画読み込みを中断しました。")

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {
            "ok": False,
            "data": None,
            "warnings": [],
            "error": {
                "code": "VIDEO_OPEN_FAILED",
                "message": "OpenCV could not open the video.",
                "details": {"video_path": str(path)},
            },
        }

    ret, frame = capture.read()
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()

    warnings = []
    if not ffprobe_result["ok"]:
        warnings.append(ffprobe_result["error"])

    duration_sec = 0.0
    if fps > 0 and frame_count > 0:
        duration_sec = frame_count / fps

    if ffprobe_result.get("data"):
        format_info = ffprobe_result["data"].get("format", {})
        try:
            duration_sec = float(format_info.get("duration", duration_sec))
        except (TypeError, ValueError):
            pass

    if callable(progress_callback):
        progress_callback(
            stage="preview_init",
            message="プレビューを初期化中",
            progress_percent=88.0,
            is_indeterminate=False,
            can_cancel=True,
        )

    return {
        "ok": True,
        "warnings": warnings,
        "data": {
            "source_path": str(path),
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count,
            "duration_sec": duration_sec,
            "readable": bool(ret),
            "warnings": warnings,
            "errors": [],
            "first_frame_shape": list(frame.shape) if ret and frame is not None else None,
            "opencv": {
                "can_read_first_frame": bool(ret),
                "first_frame_shape": list(frame.shape) if ret and frame is not None else None,
                "width": width,
                "height": height,
                "fps": fps,
                "frame_count": frame_count,
            },
            "ffprobe": ffprobe_result.get("data"),
        },
    }


def open_video_metadata(video_path: str, *, progress_callback=None, cancel_requested=None, ensure_not_cancelled=None) -> dict:
    result = probe_video(
        video_path,
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
        ensure_not_cancelled=ensure_not_cancelled,
    )
    if not result["ok"]:
        return result

    return {
        "ok": True,
        "warnings": result["warnings"],
        "data": {
            "source_path": result["data"]["source_path"],
            "width": result["data"]["width"],
            "height": result["data"]["height"],
            "fps": result["data"]["fps"],
            "frame_count": result["data"]["frame_count"],
            "duration_sec": result["data"]["duration_sec"],
            "readable": result["data"]["readable"],
            "warnings": result["data"]["warnings"],
            "errors": result["data"]["errors"],
            "first_frame_shape": result["data"]["first_frame_shape"],
        },
    }
