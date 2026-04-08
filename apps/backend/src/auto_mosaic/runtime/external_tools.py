from __future__ import annotations

import os
import shutil
from pathlib import Path


WINDOWS_TOOL_EXTENSIONS = (".exe", ".cmd", ".bat")


def _candidate_paths(tool_name: str, explicit_path: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))

    env_name = f"AUTO_MOSAIC_{tool_name.upper()}_PATH"
    env_value = os.environ.get(env_name)
    if env_value:
        candidates.append(Path(env_value))

    workspace_root = Path(__file__).resolve().parents[5]
    tool_root = workspace_root / "tools" / "ffmpeg" / "bin"
    for extension in WINDOWS_TOOL_EXTENSIONS:
        candidates.append(tool_root / f"{tool_name}{extension}")

    return candidates


def resolve_external_tool(tool_name: str, explicit_path: str | None = None) -> dict:
    for candidate in _candidate_paths(tool_name, explicit_path):
        try:
            if candidate.exists():
                return {
                    "found": True,
                    "path": str(candidate),
                    "source": "explicit" if explicit_path and candidate == Path(explicit_path) else "configured",
                }
        except OSError:
            continue

    try:
        discovered = shutil.which(tool_name)
    except OSError:
        discovered = None
    if discovered:
        return {"found": True, "path": discovered, "source": "path"}

    return {
        "found": False,
        "path": None,
        "source": "not-found",
        "expected_locations": [str(path) for path in _candidate_paths(tool_name, explicit_path)],
    }
