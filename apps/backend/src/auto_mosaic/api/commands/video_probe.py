from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.video.probe import probe_video


def run(payload: dict) -> dict:
    video_path = payload.get("video_path")
    if not video_path:
        return failure("video-probe", "VIDEO_PATH_REQUIRED", "video_path is required.")

    result = probe_video(video_path)
    if result["ok"]:
        return success("video-probe", result["data"], result["warnings"])

    return failure(
        "video-probe",
        result["error"]["code"],
        result["error"]["message"],
        result["error"].get("details"),
        result["warnings"],
    )
