from __future__ import annotations

import json
import re
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def run(payload: dict) -> dict:
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SAFE_ID.match(snapshot_id):
        return failure(
            "save-recovery-snapshot",
            "SNAPSHOT_ID_INVALID",
            "snapshot_id must be a short alphanumeric string (A-Z, a-z, 0-9, ., _, -, max 128 chars).",
            {"snapshot_id": snapshot_id},
        )

    project = payload.get("project")
    if not isinstance(project, dict):
        return failure(
            "save-recovery-snapshot",
            "PROJECT_REQUIRED",
            "project (ProjectDocument dict) is required.",
        )

    timestamp = payload.get("timestamp")
    read_model = payload.get("read_model")
    confirmed_danger_frames = payload.get("confirmed_danger_frames")
    if isinstance(confirmed_danger_frames, list):
        confirmed_danger_frames = [str(item) for item in confirmed_danger_frames]
    else:
        confirmed_danger_frames = []

    record = {
        "id": snapshot_id,
        "project": project,
        "read_model": read_model if isinstance(read_model, (dict, list)) else None,
        "timestamp": str(timestamp) if timestamp is not None else "",
        "confirmed_danger_frames": confirmed_danger_frames,
    }

    dirs = ensure_runtime_dirs()
    target = Path(dirs.recovery_dir) / f"{snapshot_id}.json"
    try:
        atomic_write_text(target, json.dumps(record, ensure_ascii=False, indent=2))
    except OSError as exc:
        return failure(
            "save-recovery-snapshot",
            "SNAPSHOT_WRITE_FAILED",
            f"Failed to write recovery snapshot: {exc}",
            {"path": str(target)},
        )

    return success("save-recovery-snapshot", {"snapshot_id": snapshot_id, "path": str(target)})
