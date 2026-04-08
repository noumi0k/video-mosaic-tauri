from __future__ import annotations

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import (
    find_track,
    load_project_for_mutation,
    persist_project,
)


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("delete-keyframe", payload)
    if error:
        return error

    track_id = payload.get("track_id")
    frame_index = payload.get("frame_index")
    if not track_id:
        return failure("delete-keyframe", "TRACK_ID_REQUIRED", "track_id is required.")
    if frame_index is None:
        return failure("delete-keyframe", "FRAME_INDEX_REQUIRED", "frame_index is required.")

    track = find_track(project, track_id)
    if track is None:
        return failure(
            "delete-keyframe",
            "TRACK_NOT_FOUND",
            "Requested track does not exist.",
            {"track_id": track_id},
        )

    frame_index_int = int(frame_index)
    before_count = len(track.keyframes)
    track.keyframes = [item for item in track.keyframes if item.frame_index != frame_index_int]
    if len(track.keyframes) == before_count:
        return failure(
            "delete-keyframe",
            "KEYFRAME_NOT_FOUND",
            "Requested keyframe does not exist.",
            {"track_id": track_id, "frame_index": frame_index_int},
        )

    track.mark_user_edited()
    return persist_project(
        "delete-keyframe",
        project,
        path,
        {"track_id": track.track_id, "frame_index": None},
    )
