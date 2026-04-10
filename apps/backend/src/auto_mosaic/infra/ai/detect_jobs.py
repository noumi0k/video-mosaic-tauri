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

DEFAULT_RECENT_JOB_LIMIT = 8
TERMINAL_STATES = {"succeeded", "failed", "cancelled", "interrupted"}
ACTIVE_STATES = {"queued", "running"}


def _jobs_root() -> Path:
    runtime_dirs = ensure_runtime_dirs()
    root = Path(runtime_dirs.temp_dir) / "detect-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def generate_job_id() -> str:
    return f"detect-{uuid4().hex}"


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


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)


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


def _status_sort_key(status: dict[str, Any]) -> datetime:
    return _parse_timestamp(str(status.get("updated_at") or status.get("created_at") or ""))


def _iter_job_dirs() -> list[Path]:
    root = _jobs_root()
    return [path for path in root.iterdir() if path.is_dir()]


def build_status(
    *,
    job_id: str,
    state: str,
    stage: str,
    percent: float,
    message: str,
    current: int = 0,
    total: int = 0,
    error: dict | None = None,
    result_available: bool = False,
    worker_pid: int | None = None,
) -> dict:
    payload = {
        "job_id": job_id,
        "state": state,
        "stage": stage,
        "percent": round(max(0.0, min(percent, 100.0)), 2),
        "message": message,
        "current": current,
        "total": total,
        "error": error,
        "result_available": result_available,
        "updated_at": _timestamp(),
    }
    if worker_pid:
        payload["worker_pid"] = int(worker_pid)
    return payload


def write_status(job_id: str, status: dict) -> None:
    current = read_status(job_id) or {}
    payload = {**current, **status}
    if "created_at" not in payload:
        payload["created_at"] = _timestamp()
    if "updated_at" not in payload:
        payload["updated_at"] = _timestamp()
    if "result_size_bytes" not in payload and result_path(job_id).exists():
        payload["result_size_bytes"] = result_path(job_id).stat().st_size
    atomic_write_text(status_path(job_id), json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(job_id: str) -> dict | None:
    return _safe_read_json(status_path(job_id))


def write_result(job_id: str, result: dict) -> None:
    path = result_path(job_id)
    atomic_write_text(path, json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    status = read_status(job_id)
    if status is not None:
        status["result_size_bytes"] = path.stat().st_size
        status["result_available"] = True
        write_status(job_id, status)


def read_result(job_id: str) -> dict | None:
    return _safe_read_json(result_path(job_id))


def request_cancel(job_id: str) -> dict:
    atomic_write_text(cancel_flag_path(job_id), "cancelled", encoding="utf-8")
    return {"job_id": job_id, "cancel_flag": str(cancel_flag_path(job_id))}


def is_cancel_requested(job_id: str) -> bool:
    return cancel_flag_path(job_id).exists()


def delete_job(job_id: str) -> bool:
    path = _jobs_root() / job_id
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def clear_runtime_state(job_id: str) -> None:
    cancel_flag_path(job_id).unlink(missing_ok=True)


def _build_recent_job(status: dict[str, Any]) -> dict[str, Any]:
    job_id = str(status.get("job_id") or "")
    status_copy = dict(status)
    status_copy["job_id"] = job_id
    status_copy["has_result"] = result_path(job_id).exists()
    status_copy["has_cancel_flag"] = cancel_flag_path(job_id).exists()
    status_copy["result_size_bytes"] = int(status_copy.get("result_size_bytes") or 0)
    return status_copy


def reconcile_job_state(job_id: str) -> dict[str, Any] | None:
    status = read_status(job_id)
    if status is None:
        return None

    state = str(status.get("state") or "")
    if result_path(job_id).exists() and state != "succeeded":
        completed_status = build_status(
            job_id=job_id,
            state="succeeded",
            stage="finalizing",
            percent=100.0,
            message="Detection completed",
            current=int(status.get("current") or 0),
            total=int(status.get("total") or 0),
            error=None,
            result_available=True,
            worker_pid=int(status.get("worker_pid") or 0) or None,
        )
        write_status(job_id, completed_status)
        clear_runtime_state(job_id)
        return read_status(job_id)

    if state not in ACTIVE_STATES:
        return status

    worker_pid = int(status.get("worker_pid") or 0)
    if _is_worker_alive(worker_pid):
        return status

    # Worker is dead.  Re-check for result.json: on Windows with
    # DETACHED_PROCESS the file may not have been visible at the top-of-function
    # check but becomes visible after the process exits.
    if result_path(job_id).exists():
        completed_status = build_status(
            job_id=job_id,
            state="succeeded",
            stage="finalizing",
            percent=100.0,
            message="Detection completed",
            current=int(status.get("current") or 0),
            total=int(status.get("total") or 0),
            error=None,
            result_available=True,
            worker_pid=worker_pid or None,
        )
        write_status(job_id, completed_status)
        clear_runtime_state(job_id)
        return read_status(job_id)

    interrupted_message = (
        "Detection was interrupted after a cancel request."
        if cancel_flag_path(job_id).exists()
        else "Detection worker was no longer running and the job was marked interrupted."
    )
    interrupted_status = build_status(
        job_id=job_id,
        state="interrupted",
        stage=str(status.get("stage") or "finalizing"),
        percent=float(status.get("percent") or 0.0),
        message=interrupted_message,
        current=int(status.get("current") or 0),
        total=int(status.get("total") or 0),
        error={
            "code": "DETECT_JOB_INTERRUPTED",
            "message": interrupted_message,
            "details": {"job_id": job_id, "last_state": state},
        },
    )
    write_status(job_id, interrupted_status)
    clear_runtime_state(job_id)
    return read_status(job_id)


def recover_incomplete_jobs() -> dict[str, Any]:
    recovered: list[dict[str, Any]] = []
    broken_job_ids: list[str] = []
    for directory in _iter_job_dirs():
        job_id = directory.name
        status = read_status(job_id)
        if status is None:
            broken_job_ids.append(job_id)
            continue
        previous_state = str(status.get("state") or "")
        current = reconcile_job_state(job_id)
        if current and current.get("state") == "interrupted" and previous_state in ACTIVE_STATES:
            recovered.append(current)
    return {"recovered": recovered, "broken_job_ids": broken_job_ids}


def list_recent_jobs(limit: int = DEFAULT_RECENT_JOB_LIMIT, recover: bool = True) -> dict[str, Any]:
    recovery = recover_incomplete_jobs() if recover else {"recovered": [], "broken_job_ids": []}
    statuses: list[dict[str, Any]] = []
    broken_job_ids = list(recovery["broken_job_ids"])
    for directory in _iter_job_dirs():
        job_id = directory.name
        status = read_status(job_id)
        if status is None:
            if job_id not in broken_job_ids:
                broken_job_ids.append(job_id)
            continue
        statuses.append(_build_recent_job(status))

    statuses.sort(key=_status_sort_key, reverse=True)
    recent = statuses[: max(0, limit)]
    return {
        "jobs": recent,
        "retained_limit": limit,
        "recovered_interrupted": len(recovery["recovered"]),
        "broken_job_ids": broken_job_ids,
    }


def cleanup_jobs(
    *,
    retain_limit: int = DEFAULT_RECENT_JOB_LIMIT,
    include_terminal: bool = True,
    include_interrupted: bool = True,
    include_broken: bool = True,
    recover: bool = True,
    active_job_ids: set[str] | None = None,
) -> dict[str, Any]:
    active_job_ids = active_job_ids or set()
    listing = list_recent_jobs(limit=10_000, recover=recover)
    deleted_job_ids: list[str] = []
    skipped_job_ids: list[str] = []

    statuses = listing["jobs"]
    retained_ids = {str(item.get("job_id")) for item in statuses[: max(0, retain_limit)]}

    for item in statuses:
        job_id = str(item.get("job_id") or "")
        state = str(item.get("state") or "")
        if not job_id or job_id in active_job_ids:
            continue
        if state in ACTIVE_STATES:
            skipped_job_ids.append(job_id)
            continue
        if state == "interrupted" and not include_interrupted:
            skipped_job_ids.append(job_id)
            continue
        if state in TERMINAL_STATES and state != "interrupted" and not include_terminal:
            skipped_job_ids.append(job_id)
            continue
        if job_id in retained_ids:
            skipped_job_ids.append(job_id)
            continue
        if delete_job(job_id):
            deleted_job_ids.append(job_id)

    if include_broken:
        for job_id in listing["broken_job_ids"]:
            if job_id in active_job_ids:
                continue
            if delete_job(job_id):
                deleted_job_ids.append(job_id)

    return {
        "deleted_job_ids": deleted_job_ids,
        "skipped_job_ids": skipped_job_ids,
        "retained_limit": retain_limit,
        "broken_job_ids": listing["broken_job_ids"],
    }
