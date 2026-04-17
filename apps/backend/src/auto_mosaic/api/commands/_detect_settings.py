"""Backend detect settings persistence.

Detect settings (detector backend, device, thresholds, batch size, etc.) are
stored as a single JSON object at `user-data/config/detect-settings.json` so
the frontend does not have to re-enter them every session.

The schema is intentionally permissive: this module validates shapes and
types, but does not enforce the set of allowed enum values. The frontend is
responsible for surfacing a known backend / device / contour mode; on load,
unknown values are simply returned as-is and the UI can fall back to a
default if an option is no longer valid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_mosaic.application.responses import failure, success
from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def _settings_path() -> Path:
    dirs = ensure_runtime_dirs()
    return Path(dirs.config_dir) / "detect-settings.json"


def _coerce_settings(raw: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    for key in ("backend", "device", "contour_mode"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            cleaned[key] = value

    for key in ("confidence_threshold",):
        value = raw.get(key)
        if isinstance(value, (int, float)):
            cleaned[key] = float(value)

    for key in ("sample_every", "max_samples", "inference_resolution", "batch_size"):
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            cleaned[key] = value
        elif isinstance(value, float) and value.is_integer():
            cleaned[key] = int(value)

    for key in ("precise_face_contour", "vram_saving_mode", "overwrite_manual_tracks"):
        value = raw.get(key)
        if isinstance(value, bool):
            cleaned[key] = value

    categories = raw.get("selected_categories")
    if isinstance(categories, list):
        cleaned["selected_categories"] = [str(item) for item in categories if isinstance(item, str) and item]

    return cleaned


def save_settings(payload: dict) -> dict:
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return failure(
            "save-detect-settings",
            "DETECT_SETTINGS_REQUIRED",
            "settings (object) is required.",
        )
    cleaned = _coerce_settings(settings)
    atomic_write_text(_settings_path(), json.dumps(cleaned, ensure_ascii=False, indent=2))
    return success("save-detect-settings", {"settings": cleaned})


def load_settings(_payload: dict) -> dict:
    path = _settings_path()
    if not path.exists():
        return success("load-detect-settings", {"settings": None, "broken": False})

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return success(
            "load-detect-settings",
            {"settings": None, "broken": True, "reason": str(exc)},
        )

    if not isinstance(raw, dict):
        return success(
            "load-detect-settings",
            {"settings": None, "broken": True, "reason": "Payload is not an object."},
        )

    return success("load-detect-settings", {"settings": _coerce_settings(raw), "broken": False})
