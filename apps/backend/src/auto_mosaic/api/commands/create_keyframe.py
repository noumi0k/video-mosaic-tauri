from __future__ import annotations

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import (
    build_keyframe_from_payload,
    find_keyframe,
    find_track,
    load_project_for_mutation,
    persist_project,
    validate_shape_payload,
)


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("create-keyframe", payload)
    if error:
        return error

    track_id = payload.get("track_id")
    if not track_id:
        return failure("create-keyframe", "TRACK_ID_REQUIRED", "track_id is required.")

    frame_index = payload.get("frame_index")
    if frame_index is None:
        return failure("create-keyframe", "FRAME_INDEX_REQUIRED", "frame_index is required.")

    track = find_track(project, track_id)
    if track is None:
        return failure(
            "create-keyframe",
            "TRACK_NOT_FOUND",
            "Requested track does not exist.",
            {"track_id": track_id},
        )

    frame_index_int = int(frame_index)
    if find_keyframe(track, frame_index_int) is not None:
        return failure(
            "create-keyframe",
            "KEYFRAME_ALREADY_EXISTS",
            "A keyframe already exists at the requested frame.",
            {"track_id": track_id, "frame_index": frame_index_int},
        )

    keyframe = build_keyframe_from_payload(payload)
    shape_error = validate_shape_payload(keyframe.shape_type, keyframe.bbox, keyframe.points)
    if shape_error:
        return failure(
            "create-keyframe",
            "INVALID_KEYFRAME_PAYLOAD",
            shape_error,
            {"track_id": track_id, "frame_index": frame_index_int},
        )
    track.mark_user_edited(keyframe)
    track.keyframes.append(keyframe)
    track.keyframes.sort(key=lambda item: item.frame_index)
    return persist_project(
        "create-keyframe",
        project,
        path,
        {"track_id": track.track_id, "frame_index": keyframe.frame_index},
    )
