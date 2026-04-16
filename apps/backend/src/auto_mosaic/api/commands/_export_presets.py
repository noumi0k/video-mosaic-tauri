"""Backend export preset commands.

Presets are stored as individual JSON files under `user-data/presets/`
so listing and deletion are simple file operations. The preset name is
used as the filename after being validated against a strict regex.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from auto_mosaic.application.responses import failure, success
from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs

_SAFE_ID = re.compile(r"^[A-Za-z0-9._\- ]{1,128}$")


def _preset_dir() -> Path:
    dirs = ensure_runtime_dirs()
    return Path(dirs.preset_dir)


def _preset_path(name: str) -> Path:
    return _preset_dir() / f"{name}.json"


def save_preset(payload: dict) -> dict:
    name = payload.get("name")
    settings = payload.get("settings")
    if not isinstance(name, str) or not _SAFE_ID.match(name):
        return failure(
            "save-export-preset",
            "PRESET_NAME_INVALID",
            "name must be 1-128 chars of [A-Za-z0-9 ._-].",
            {"name": name},
        )
    if not isinstance(settings, dict):
        return failure(
            "save-export-preset",
            "PRESET_SETTINGS_REQUIRED",
            "settings (object) is required.",
        )
    record: dict[str, Any] = {"name": name, "settings": settings}
    atomic_write_text(_preset_path(name), json.dumps(record, ensure_ascii=False, indent=2))
    return success("save-export-preset", record)


def list_presets(_payload: dict) -> dict:
    root = _preset_dir()
    items: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    if root.exists():
        for entry in sorted(root.glob("*.json")):
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                broken.append({"path": str(entry), "reason": str(exc)})
                continue
            if not isinstance(data, dict):
                broken.append({"path": str(entry), "reason": "Preset payload is not an object."})
                continue
            items.append(
                {
                    "name": str(data.get("name") or entry.stem),
                    "settings": data.get("settings") or {},
                    "path": str(entry),
                }
            )
    return success("list-export-presets", {"items": items, "broken": broken})


def delete_preset(payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not _SAFE_ID.match(name):
        return failure(
            "delete-export-preset",
            "PRESET_NAME_INVALID",
            "name must be 1-128 chars of [A-Za-z0-9 ._-].",
            {"name": name},
        )
    target = _preset_path(name)
    if not target.exists():
        return success("delete-export-preset", {"name": name, "deleted": False})
    target.unlink()
    return success("delete-export-preset", {"name": name, "deleted": True})
