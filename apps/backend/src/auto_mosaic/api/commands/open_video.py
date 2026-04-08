from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.video.probe import open_video_metadata


def run(payload: dict) -> dict:
    video_path = payload.get("video_path")
    if not video_path:
        return failure("open-video", "VIDEO_PATH_REQUIRED", "video_path is required.")

    result = open_video_metadata(
        video_path,
        progress_callback=payload.get("_progress_callback"),
        cancel_requested=payload.get("_cancel_requested"),
        ensure_not_cancelled=payload.get("_ensure_not_cancelled"),
    )
    if result["ok"]:
        return success("open-video", {"video": result["data"]}, result["warnings"])

    return failure(
        "open-video",
        result["error"]["code"],
        result["error"]["message"],
        result["error"].get("details"),
        result["warnings"],
    )
