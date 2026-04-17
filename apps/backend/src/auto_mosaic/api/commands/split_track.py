"""Split a track at a frame boundary into two independent tracks.

- Keyframes with frame_index < split_frame stay on the original track.
- Keyframes with frame_index >= split_frame move to a new track with a
  fresh track_id and a " (split)" label suffix.
- Segments are filtered to those that remain valid for each side.
- Both tracks are marked user_edited=True since splitting is a manual
  editing action.
"""

from __future__ import annotations

import copy
import uuid

from auto_mosaic.application.responses import failure
from auto_mosaic.api.commands._project_mutation import load_project_for_mutation, persist_project
from auto_mosaic.domain.project import MaskTrack


def run(payload: dict) -> dict:
    project, path, error = load_project_for_mutation("split-track", payload)
    if error:
        return error
    assert project is not None
    # path may be None for unsaved (inline) projects; persist_project handles that.

    track_id = payload.get("track_id")
    if not isinstance(track_id, str) or not track_id:
        return failure(
            "split-track",
            "TRACK_ID_REQUIRED",
            "track_id is required.",
        )

    split_raw = payload.get("split_frame")
    try:
        split_frame = int(split_raw)
    except (TypeError, ValueError):
        return failure(
            "split-track",
            "SPLIT_FRAME_REQUIRED",
            "split_frame (integer) is required.",
            {"split_frame": split_raw},
        )
    if split_frame < 0:
        return failure(
            "split-track",
            "SPLIT_FRAME_INVALID",
            "split_frame must be >= 0.",
            {"split_frame": split_frame},
        )

    source_track = next((t for t in project.tracks if t.track_id == track_id), None)
    if source_track is None:
        return failure(
            "split-track",
            "TRACK_NOT_FOUND",
            f"No track with id {track_id!r} exists.",
            {"track_id": track_id},
        )

    left_keyframes = [kf for kf in source_track.keyframes if kf.frame_index < split_frame]
    right_keyframes = [kf for kf in source_track.keyframes if kf.frame_index >= split_frame]

    if not left_keyframes or not right_keyframes:
        return failure(
            "split-track",
            "SPLIT_EMPTY_SIDE",
            "Split would produce an empty track — both sides must contain at least one keyframe.",
            {
                "split_frame": split_frame,
                "left_keyframes": len(left_keyframes),
                "right_keyframes": len(right_keyframes),
            },
        )

    # Segments: keep only those whose [start, end] interval stays on one side
    # of the split. Segments that straddle the split boundary are trimmed.
    left_segments = []
    right_segments = []
    for seg in source_track.segments:
        if seg.end_frame < split_frame:
            left_segments.append(copy.deepcopy(seg))
        elif seg.start_frame >= split_frame:
            right_segments.append(copy.deepcopy(seg))
        else:
            # Straddles split — trim
            left_trim = copy.deepcopy(seg)
            left_trim.end_frame = split_frame - 1
            if left_trim.end_frame >= left_trim.start_frame:
                left_segments.append(left_trim)
            right_trim = copy.deepcopy(seg)
            right_trim.start_frame = split_frame
            if right_trim.end_frame >= right_trim.start_frame:
                right_segments.append(right_trim)

    # Update the original track in-place (left side).
    source_track.keyframes = left_keyframes
    source_track.segments = left_segments
    source_track.mark_user_edited()

    # Create the new right-side track.
    new_track_id = f"track-{uuid.uuid4()}"
    right_track = MaskTrack(
        track_id=new_track_id,
        label=f"{source_track.label} (split)",
        state=source_track.state,
        source="manual",
        visible=source_track.visible,
        export_enabled=source_track.export_enabled,
        keyframes=[copy.deepcopy(kf) for kf in right_keyframes],
        label_group=source_track.label_group,
        user_locked=False,
        user_edited=True,
        confidence=source_track.confidence,
        style=copy.deepcopy(source_track.style),
        segments=right_segments,
    )

    project.tracks.append(right_track)

    return persist_project(
        "split-track",
        project,
        path,
        {"track_id": new_track_id, "frame_index": split_frame},
    )
