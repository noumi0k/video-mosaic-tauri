"""Backend export queue commands.

Queue state is persisted as a single JSON file under
`user-data/export-queue/queue.json` so that a single atomic write replaces
the full list. Items stay lightweight (~1 KB each); the heavy project
snapshot is referenced by `project_path` and therefore not duplicated in
the queue file.

State transitions are not enforced at the backend level beyond the basic
restore step (`running → interrupted` on list). The frontend owns the
drive loop: dequeue a queued item, call `export-video`, update the item
as completion / cancellation events arrive.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from auto_mosaic.application.responses import failure, success
from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_VALID_STATES = {"queued", "running", "interrupted", "completed", "failed", "cancelled"}


def _queue_path() -> Path:
    dirs = ensure_runtime_dirs()
    return Path(dirs.export_queue_dir) / "queue.json"


def _read_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_queue(items: list[dict[str, Any]]) -> None:
    atomic_write_text(_queue_path(), json.dumps(items, ensure_ascii=False, indent=2))


def _normalize_state(raw: object) -> str:
    value = str(raw) if isinstance(raw, str) else "queued"
    return value if value in _VALID_STATES else "queued"


def _normalize_item(entry: dict[str, Any]) -> dict[str, Any]:
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    return {
        "queue_id": str(entry.get("queue_id") or uuid.uuid4().hex),
        "job_id": str(entry.get("job_id") or ""),
        "project_path": str(entry.get("project_path") or ""),
        "project_name": str(entry.get("project_name") or ""),
        "output_path": str(entry.get("output_path") or ""),
        "options": options,
        "state": _normalize_state(entry.get("state")),
        "progress": float(entry.get("progress") or 0.0),
        "status_text": str(entry.get("status_text") or ""),
        "warnings": [str(w) for w in (entry.get("warnings") or []) if isinstance(w, (str, int, float))],
        "audio_status": entry.get("audio_status") if isinstance(entry.get("audio_status"), str) else None,
    }


def list_queue(_payload: dict) -> dict:
    items = _read_queue()
    changed = False
    restored = 0
    for item in items:
        if item.get("state") == "running":
            item["state"] = "interrupted"
            if not item.get("status_text"):
                item["status_text"] = "アプリ再起動により中断されました。"
            restored += 1
            changed = True
    if changed:
        _write_queue(items)
    return success(
        "list-export-queue",
        {"items": [_normalize_item(item) for item in items], "recovered_interrupted": restored},
    )


def enqueue(payload: dict) -> dict:
    item = _normalize_item(payload.get("item") or payload)
    if not item["project_path"]:
        return failure("enqueue-export", "PROJECT_PATH_REQUIRED", "item.project_path is required.")
    if not item["output_path"]:
        return failure("enqueue-export", "OUTPUT_PATH_REQUIRED", "item.output_path is required.")
    if not _SAFE_ID.match(item["queue_id"]):
        return failure(
            "enqueue-export",
            "QUEUE_ID_INVALID",
            "queue_id must match [A-Za-z0-9._-]{1,128}.",
            {"queue_id": item["queue_id"]},
        )
    # Fresh items always start as "queued" regardless of what the caller sent.
    item["state"] = "queued"
    item["progress"] = 0.0
    items = _read_queue()
    items = [existing for existing in items if existing.get("queue_id") != item["queue_id"]]
    items.append(item)
    _write_queue(items)
    return success("enqueue-export", {"item": item, "items": [_normalize_item(i) for i in items]})


def update_item(payload: dict) -> dict:
    queue_id = payload.get("queue_id")
    patch = payload.get("patch")
    if not isinstance(queue_id, str) or not _SAFE_ID.match(queue_id):
        return failure("update-export-queue-item", "QUEUE_ID_INVALID", "queue_id invalid.", {"queue_id": queue_id})
    if not isinstance(patch, dict):
        return failure("update-export-queue-item", "PATCH_REQUIRED", "patch is required.")

    items = _read_queue()
    for item in items:
        if item.get("queue_id") == queue_id:
            if "state" in patch:
                item["state"] = _normalize_state(patch["state"])
            if "progress" in patch:
                try:
                    item["progress"] = float(patch["progress"])
                except (TypeError, ValueError):
                    pass
            if "status_text" in patch:
                item["status_text"] = str(patch["status_text"] or "")
            if "job_id" in patch:
                item["job_id"] = str(patch["job_id"] or "")
            if "warnings" in patch and isinstance(patch["warnings"], list):
                item["warnings"] = [str(w) for w in patch["warnings"]]
            if "audio_status" in patch:
                audio = patch["audio_status"]
                item["audio_status"] = str(audio) if isinstance(audio, str) else None
            _write_queue(items)
            return success("update-export-queue-item", {"item": _normalize_item(item)})
    return failure(
        "update-export-queue-item",
        "QUEUE_ITEM_NOT_FOUND",
        "Queue item not found.",
        {"queue_id": queue_id},
    )


def remove_item(payload: dict) -> dict:
    queue_id = payload.get("queue_id")
    if not isinstance(queue_id, str) or not _SAFE_ID.match(queue_id):
        return failure("remove-export-queue-item", "QUEUE_ID_INVALID", "queue_id invalid.", {"queue_id": queue_id})
    items = _read_queue()
    next_items = [item for item in items if item.get("queue_id") != queue_id]
    removed = len(next_items) < len(items)
    if removed:
        _write_queue(next_items)
    return success(
        "remove-export-queue-item",
        {"queue_id": queue_id, "removed": removed, "items": [_normalize_item(i) for i in next_items]},
    )


def clear_terminal(_payload: dict) -> dict:
    items = _read_queue()
    terminal = {"completed", "failed", "cancelled"}
    next_items = [item for item in items if item.get("state") not in terminal]
    removed = len(items) - len(next_items)
    if removed:
        _write_queue(next_items)
    return success(
        "clear-terminal-export-queue",
        {"removed": removed, "items": [_normalize_item(i) for i in next_items]},
    )
