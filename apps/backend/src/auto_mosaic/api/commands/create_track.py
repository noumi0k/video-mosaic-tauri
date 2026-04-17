from __future__ import annotations

import uuid

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import (
    build_keyframe_from_payload,
    load_project_for_mutation,
    persist_project,
)
from auto_mosaic.domain.project import MaskTrack


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("create-track", payload)
    if error:
        return error
    assert project is not None
    # path may be None for unsaved (inline) projects; persist_project handles that.

    shape_type = str(payload.get("shape_type", "ellipse"))
    if shape_type not in {"ellipse", "polygon"}:
        return failure(
            "create-track",
            "INVALID_SHAPE_TYPE",
            "shape_type must be ellipse or polygon.",
        )

    label = str(payload.get("label", f"Track {len(project.tracks) + 1}"))
    track_id = payload.get("track_id") or f"track-{uuid.uuid4()}"

    track = MaskTrack(
        track_id=track_id,
        label=label,
        state="active",
        source="manual",
        visible=True,
        keyframes=[],
        label_group=str(payload.get("label_group", "")),
        user_locked=False,
        user_edited=True,
        confidence=1.0,
    )

    # Optionally create an initial keyframe at specified frame
    frame_index = payload.get("frame_index")
    if frame_index is not None:
        kf_payload = {
            "frame_index": int(frame_index),
            "shape_type": shape_type,
            "source": "manual",
            "bbox": payload.get("bbox") or [0.3, 0.3, 0.2, 0.2],
            "points": payload.get("points"),
        }
        keyframe = build_keyframe_from_payload(kf_payload)
        track.keyframes.append(keyframe)

    project.tracks.append(track)

    return persist_project(
        "create-track",
        project,
        path,
        {"track_id": track.track_id, "frame_index": frame_index},
    )
