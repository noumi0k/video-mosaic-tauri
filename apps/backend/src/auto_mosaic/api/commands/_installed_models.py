"""Installed model management (M-D03).

Lists model files present in the model_dir and allows a user to delete them.
Integrity status reuses the doctor._check_model_file logic so the UI can
surface broken files and prompt the user to re-download.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from auto_mosaic.api.commands.doctor import _check_model_file
from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.model_catalog import get_model_spec_map
from auto_mosaic.runtime.paths import ensure_runtime_dirs

# Accept the same filename shape as the catalog (alnum + dot/underscore/hyphen).
# Critically rejects path separators so this cannot be used to delete arbitrary files.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._\-]+$")

# Model file extensions we consider "installed models" for the UI.
_MODEL_SUFFIXES = {".onnx", ".pt"}


def list_installed(_payload: dict) -> dict:
    dirs = ensure_runtime_dirs()
    model_dir = Path(dirs.model_dir)
    spec_map = get_model_spec_map()

    items: list[dict[str, Any]] = []
    if model_dir.exists():
        for entry in sorted(model_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in _MODEL_SUFFIXES:
                continue
            spec = spec_map.get(entry.name)
            status = _check_model_file(entry, spec)
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            items.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "size_bytes": size,
                    "status": status,
                    "known": spec is not None,
                    "required": bool(spec and spec.required),
                    "description": spec.description if spec else None,
                    "source_label": spec.source_label if spec else None,
                    "model_id": spec.model_id if spec else None,
                }
            )

    return success(
        "list-installed-models",
        {
            "model_dir": str(model_dir),
            "items": items,
        },
    )


def delete_installed(payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not _SAFE_FILENAME.match(name):
        return failure(
            "delete-installed-model",
            "MODEL_NAME_INVALID",
            "name must be a plain filename (no path separators).",
            {"name": name},
        )
    if name.startswith(".") or ".." in name:
        return failure(
            "delete-installed-model",
            "MODEL_NAME_INVALID",
            "name must not contain traversal segments.",
            {"name": name},
        )

    dirs = ensure_runtime_dirs()
    model_dir = Path(dirs.model_dir)
    target = model_dir / name

    # Confirm target is still under model_dir after resolution (defence in depth
    # even though _SAFE_FILENAME should already block traversal).
    try:
        resolved = target.resolve()
        resolved.relative_to(model_dir.resolve())
    except (OSError, ValueError):
        return failure(
            "delete-installed-model",
            "MODEL_NAME_INVALID",
            "Resolved path is outside the model directory.",
            {"name": name},
        )

    if not target.exists():
        return success(
            "delete-installed-model",
            {"name": name, "deleted": False},
        )

    try:
        target.unlink()
    except OSError as exc:
        return failure(
            "delete-installed-model",
            "MODEL_DELETE_FAILED",
            f"Failed to delete model file: {exc}",
            {"name": name, "reason": str(exc)},
        )

    return success(
        "delete-installed-model",
        {"name": name, "deleted": True},
    )
