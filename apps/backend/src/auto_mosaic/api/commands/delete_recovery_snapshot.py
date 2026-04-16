from __future__ import annotations

import re
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.runtime.paths import ensure_runtime_dirs


_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def run(payload: dict) -> dict:
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SAFE_ID.match(snapshot_id):
        return failure(
            "delete-recovery-snapshot",
            "SNAPSHOT_ID_INVALID",
            "snapshot_id must be a short alphanumeric string (A-Z, a-z, 0-9, ., _, -, max 128 chars).",
            {"snapshot_id": snapshot_id},
        )

    dirs = ensure_runtime_dirs()
    target = Path(dirs.recovery_dir) / f"{snapshot_id}.json"
    if not target.exists():
        # Treat missing snapshot as a no-op so the caller can idempotently clear.
        return success(
            "delete-recovery-snapshot",
            {"snapshot_id": snapshot_id, "deleted": False},
        )
    try:
        target.unlink()
    except OSError as exc:
        return failure(
            "delete-recovery-snapshot",
            "SNAPSHOT_DELETE_FAILED",
            f"Failed to delete recovery snapshot: {exc}",
            {"path": str(target)},
        )

    return success(
        "delete-recovery-snapshot",
        {"snapshot_id": snapshot_id, "deleted": True},
    )
