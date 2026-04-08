from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs

TERMINAL_STATES = {"cancelled", "completed", "failed"}
ACTIVE_STATES = {"queued", "starting", "running", "cancelling"}
JOB_TITLES = {
    "setup_environment": "初期環境をセットアップ中",
    "fetch_models": "モデルを取得中",
    "open_video": "動画を読み込み中",
}


def _jobs_root() -> Path:
    runtime_dirs = ensure_runtime_dirs()
    root = Path(runtime_dirs.temp_dir) / "runtime-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def generate_job_id(job_kind: str) -> str:
    return f"{job_kind}-{uuid4().hex}"


def job_directory(job_id: str) -> Path:
    path = _jobs_root() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def status_path(job_id: str) -> Path:
    return job_directory(job_id) / "status.json"


def result_path(job_id: str) -> Path:
    return job_directory(job_id) / "result.json"


def cancel_flag_path(job_id: str) -> Path:
    return job_directory(job_id) / "cancel.flag"


def stderr_log_path(job_id: str) -> Path:
    return job_directory(job_id) / "stderr.log"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_worker_alive(worker_pid: int | None) -> bool:
    if not worker_pid or worker_pid <= 0:
        return False
    if any(thread.ident == worker_pid for thread in threading.enumerate()):
        return True
    try:
        os.kill(worker_pid, 0)
    except OSError:
        return False
    return True


def read_status(job_id: str) -> dict[str, Any] | None:
    return _safe_read_json(status_path(job_id))


def read_result(job_id: str) -> dict[str, Any] | None:
    return _safe_read_json(result_path(job_id))


def write_status(job_id: str, status: dict[str, Any]) -> None:
    current = read_status(job_id) or {}
    payload = {**current, **status}
    if "created_at" not in payload:
        payload["created_at"] = _timestamp()
    payload["updated_at"] = _timestamp()
    if payload.get("state") in TERMINAL_STATES and not payload.get("finished_at"):
        payload["finished_at"] = payload["updated_at"]
    atomic_write_text(status_path(job_id), json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_result(job_id: str, result: dict[str, Any]) -> None:
    atomic_write_text(result_path(job_id), json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_status(job_id, {"result_available": True})


def request_cancel(job_id: str) -> dict[str, Any]:
    atomic_write_text(cancel_flag_path(job_id), "cancelled", encoding="utf-8")
    return {"job_id": job_id, "cancel_flag": str(cancel_flag_path(job_id))}


def is_cancel_requested(job_id: str) -> bool:
    return cancel_flag_path(job_id).exists()


def clear_runtime_state(job_id: str) -> None:
    cancel_flag_path(job_id).unlink(missing_ok=True)


def delete_job(job_id: str) -> bool:
    path = job_directory(job_id)
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def is_active_state(state: str) -> bool:
    return state in ACTIVE_STATES


def find_active_job(job_kind: str) -> dict[str, Any] | None:
    for directory in sorted(_jobs_root().iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not directory.is_dir():
            continue
        status = read_status(directory.name)
        if not status:
            continue
        if str(status.get("job_kind") or "") != job_kind:
            continue
        if is_active_state(str(status.get("state") or "")):
            worker_pid = int(status.get("worker_pid") or 0)
            if is_cancel_requested(directory.name) and not worker_pid:
                continue
            if worker_pid and not _is_worker_alive(worker_pid):
                continue
            return status
    return None


def build_status(
    *,
    job_id: str,
    job_kind: str,
    state: str,
    title: str | None = None,
    stage: str,
    message: str,
    progress_percent: float | None = None,
    is_indeterminate: bool = False,
    can_cancel: bool = True,
    current: int | None = None,
    total: int | None = None,
    artifact_path: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "job_kind": job_kind,
        "state": state,
        "title": title or JOB_TITLES.get(job_kind, job_kind),
        "stage": stage,
        "message": message,
        "progress_percent": None if progress_percent is None else round(max(0.0, min(progress_percent, 100.0)), 2),
        "is_indeterminate": bool(is_indeterminate),
        "can_cancel": bool(can_cancel),
        "result_available": False,
    }
    if current is not None:
        payload["current"] = int(current)
    if total is not None:
        payload["total"] = int(total)
    if artifact_path:
        payload["artifact_path"] = artifact_path
    if error_code:
        payload["error_code"] = error_code
    if error_message:
        payload["error_message"] = error_message
    if extra:
        payload.update(extra)
    return payload
