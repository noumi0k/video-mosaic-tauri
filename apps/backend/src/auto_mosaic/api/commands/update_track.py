from __future__ import annotations

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import find_track, load_project_for_mutation, persist_project


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("update-track", payload)
    if error:
        return error

    track_id = payload.get("track_id")
    patch = payload.get("patch")
    if not track_id:
        return failure("update-track", "TRACK_ID_REQUIRED", "track_id is required.")
    if not isinstance(patch, dict) or not patch:
        return failure("update-track", "PATCH_REQUIRED", "patch is required.")

    track = find_track(project, track_id)
    if track is None:
        return failure(
            "update-track",
            "TRACK_NOT_FOUND",
            "Requested track does not exist.",
            {"track_id": track_id},
        )

    if "label" in patch:
        track.label = str(patch["label"])
    if "visible" in patch:
        track.visible = bool(patch["visible"])
    if "export_enabled" in patch:
        track.export_enabled = bool(patch["export_enabled"])
    if "state" in patch:
        track.state = str(patch["state"])
    if "source" in patch:
        track.set_source(str(patch["source"]))
    if "label_group" in patch:
        track.label_group = str(patch["label_group"])
    if "user_locked" in patch:
        track.user_locked = bool(patch["user_locked"])
    if "user_edited" in patch:
        track.set_user_edited(bool(patch["user_edited"]))

    return persist_project(
        "update-track",
        project,
        path,
        {"track_id": track.track_id, "frame_index": None},
    )
