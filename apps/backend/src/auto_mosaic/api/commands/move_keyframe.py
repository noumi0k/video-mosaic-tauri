from __future__ import annotations

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import (
    find_keyframe,
    find_track,
    load_project_for_mutation,
    persist_project,
)


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("move-keyframe", payload)
    if error:
        return error

    track_id = payload.get("track_id")
    frame_index = payload.get("frame_index")
    target_frame_index = payload.get("target_frame_index")
    if not track_id:
        return failure("move-keyframe", "TRACK_ID_REQUIRED", "track_id is required.")
    if frame_index is None:
        return failure("move-keyframe", "FRAME_INDEX_REQUIRED", "frame_index is required.")
    if target_frame_index is None:
        return failure("move-keyframe", "TARGET_FRAME_REQUIRED", "target_frame_index is required.")

    track = find_track(project, track_id)
    if track is None:
        return failure(
            "move-keyframe",
            "TRACK_NOT_FOUND",
            "Requested track does not exist.",
            {"track_id": track_id},
        )

    source_frame_index = int(frame_index)
    next_frame_index = int(target_frame_index)
    if next_frame_index < 0:
        return failure(
            "move-keyframe",
            "INVALID_TARGET_FRAME",
            "target_frame_index must be a non-negative integer.",
            {"track_id": track_id, "target_frame_index": next_frame_index},
        )

    if project.video is not None and next_frame_index >= int(project.video.frame_count):
        return failure(
            "move-keyframe",
            "TARGET_FRAME_OUT_OF_RANGE",
            "target_frame_index exceeds the video frame range.",
            {
                "track_id": track_id,
                "target_frame_index": next_frame_index,
                "max_frame_index": max(int(project.video.frame_count) - 1, 0),
            },
        )

    keyframe = find_keyframe(track, source_frame_index)
    if keyframe is None:
        return failure(
            "move-keyframe",
            "KEYFRAME_NOT_FOUND",
            "Requested keyframe does not exist.",
            {"track_id": track_id, "frame_index": source_frame_index},
        )

    if source_frame_index != next_frame_index and find_keyframe(track, next_frame_index) is not None:
        return failure(
            "move-keyframe",
            "TARGET_FRAME_OCCUPIED",
            "Another keyframe already exists at the target frame.",
            {
                "track_id": track_id,
                "frame_index": source_frame_index,
                "target_frame_index": next_frame_index,
            },
        )

    keyframe.frame_index = next_frame_index
    track.mark_user_edited(keyframe)
    track.keyframes.sort(key=lambda item: item.frame_index)
    return persist_project(
        "move-keyframe",
        project,
        path,
        {"track_id": track.track_id, "frame_index": keyframe.frame_index},
    )
