from __future__ import annotations

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import (
    find_keyframe,
    find_track,
    load_project_for_mutation,
    persist_project,
    validate_bbox,
    validate_points,
    validate_shape_payload,
)


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("update-keyframe", payload)
    if error:
        return error

    track_id = payload.get("track_id")
    frame_index = payload.get("frame_index")
    patch = payload.get("patch")
    if not track_id:
        return failure("update-keyframe", "TRACK_ID_REQUIRED", "track_id is required.")
    if frame_index is None:
        return failure("update-keyframe", "FRAME_INDEX_REQUIRED", "frame_index is required.")
    if not isinstance(patch, dict) or not patch:
        return failure("update-keyframe", "PATCH_REQUIRED", "patch is required.")

    track = find_track(project, track_id)
    if track is None:
        return failure(
            "update-keyframe",
            "TRACK_NOT_FOUND",
            "Requested track does not exist.",
            {"track_id": track_id},
        )

    frame_index_int = int(frame_index)
    keyframe = find_keyframe(track, frame_index_int)
    if keyframe is None:
        return failure(
            "update-keyframe",
            "KEYFRAME_NOT_FOUND",
            "Requested keyframe does not exist.",
            {"track_id": track_id, "frame_index": frame_index_int},
        )

    if "source" in patch:
        keyframe.source = str(patch["source"])
    if "shape_type" in patch:
        shape_type = str(patch["shape_type"])
        keyframe.shape_type = shape_type
    if "bbox" in patch:
        bbox_error = validate_bbox(patch["bbox"])
        if bbox_error:
            return failure(
                "update-keyframe",
                "INVALID_KEYFRAME_PATCH",
                bbox_error,
                {"track_id": track_id, "frame_index": frame_index_int, "field": "bbox"},
            )
        keyframe.bbox = [float(item) for item in patch["bbox"]]
    if "points" in patch:
        points_error = validate_points(patch["points"])
        if points_error:
            return failure(
                "update-keyframe",
                "INVALID_KEYFRAME_PATCH",
                points_error,
                {"track_id": track_id, "frame_index": frame_index_int, "field": "points"},
            )
        keyframe.points = [[float(item) for item in point] for point in patch["points"]]
    if "rotation" in patch:
        try:
            rotation_value = float(patch["rotation"])
        except (TypeError, ValueError):
            return failure(
                "update-keyframe",
                "INVALID_KEYFRAME_PATCH",
                "rotation must be a number in degrees.",
                {"track_id": track_id, "frame_index": frame_index_int, "field": "rotation"},
            )
        # Normalise to (-180, 180] so interpolation stays on the shortest arc.
        rotation_value = ((rotation_value + 180.0) % 360.0) - 180.0
        keyframe.rotation = rotation_value

    shape_error = validate_shape_payload(keyframe.shape_type, keyframe.bbox, keyframe.points)
    if shape_error:
        return failure(
            "update-keyframe",
            "INVALID_KEYFRAME_PATCH",
            shape_error,
            {"track_id": track_id, "frame_index": frame_index_int, "field": "shape"},
        )

    if any(field in patch for field in ("shape_type", "bbox", "points", "rotation")):
        track.mark_user_edited(keyframe)

    track.keyframes.sort(key=lambda item: item.frame_index)
    return persist_project(
        "update-keyframe",
        project,
        path,
        {"track_id": track.track_id, "frame_index": keyframe.frame_index},
    )
