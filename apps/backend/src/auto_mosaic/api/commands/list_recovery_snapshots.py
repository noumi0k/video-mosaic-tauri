from __future__ import annotations

import json
from pathlib import Path

from auto_mosaic.application.responses import success
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def run(_payload: dict) -> dict:
    dirs = ensure_runtime_dirs()
    recovery_root = Path(dirs.recovery_dir)
    snapshots: list[dict] = []
    broken: list[dict] = []

    if recovery_root.exists():
        for entry in sorted(recovery_root.glob("*.json")):
            try:
                raw = entry.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError) as exc:
                broken.append({"path": str(entry), "reason": str(exc)})
                continue
            if not isinstance(data, dict):
                broken.append({"path": str(entry), "reason": "Snapshot payload is not an object."})
                continue
            confirmed = data.get("confirmed_danger_frames")
            if isinstance(confirmed, list):
                confirmed_list = [str(item) for item in confirmed]
            else:
                confirmed_list = []
            snapshots.append(
                {
                    "id": data.get("id") or entry.stem,
                    "project": data.get("project"),
                    "read_model": data.get("read_model"),
                    "timestamp": data.get("timestamp") or "",
                    "confirmed_danger_frames": confirmed_list,
                    "path": str(entry),
                }
            )

    return success(
        "list-recovery-snapshots",
        {"snapshots": snapshots, "broken": broken, "recovery_dir": str(recovery_root)},
    )
