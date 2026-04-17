"""Duplicate an existing track into a new track with a fresh track_id.

The new track copies label (with a " (copy)" suffix), style, visible /
export_enabled flags, and all keyframes. `user_locked` and the original
`track_id` are not copied; `user_edited` is set to True so the duplicate
is treated as manual intent from the start.
"""

from __future__ import annotations

import copy
import uuid

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import load_project_for_mutation, persist_project
from auto_mosaic.domain.project import MaskTrack


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("duplicate-track", payload)
    if error:
        return error
    assert project is not None
    # path may be None for unsaved (inline) projects; persist_project handles that.

    track_id = payload.get("track_id")
    if not isinstance(track_id, str) or not track_id:
        return failure(
            "duplicate-track",
            "TRACK_ID_REQUIRED",
            "track_id is required.",
        )

    source_track = next((t for t in project.tracks if t.track_id == track_id), None)
    if source_track is None:
        return failure(
            "duplicate-track",
            "TRACK_NOT_FOUND",
            f"No track with id {track_id!r} exists.",
            {"track_id": track_id},
        )

    new_track_id = f"track-{uuid.uuid4()}"
    new_label = f"{source_track.label} (copy)"

    duplicated = MaskTrack(
        track_id=new_track_id,
        label=new_label,
        state=source_track.state,
        source="manual",
        visible=source_track.visible,
        export_enabled=source_track.export_enabled,
        keyframes=[copy.deepcopy(kf) for kf in source_track.keyframes],
        label_group=source_track.label_group,
        user_locked=False,
        user_edited=True,
        confidence=source_track.confidence,
        style=copy.deepcopy(source_track.style),
        segments=[copy.deepcopy(seg) for seg in source_track.segments],
    )

    project.tracks.append(duplicated)

    return persist_project(
        "duplicate-track",
        project,
        path,
        {"track_id": new_track_id, "frame_index": None},
    )
