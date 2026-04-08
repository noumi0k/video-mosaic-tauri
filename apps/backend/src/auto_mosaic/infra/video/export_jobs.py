from __future__ import annotations

import json
from pathlib import Path

from auto_mosaic.runtime.file_io import atomic_write_text
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def _jobs_root() -> Path:
    root = Path(ensure_runtime_dirs().export_job_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_directory(job_id: str) -> Path:
    path = _jobs_root() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def cancel_flag_path(job_id: str) -> Path:
    return job_directory(job_id) / "cancel.flag"


def status_path(job_id: str) -> Path:
    return job_directory(job_id) / "status.json"


def request_cancel(job_id: str) -> dict:
    flag = cancel_flag_path(job_id)
    atomic_write_text(flag, "cancelled", encoding="utf-8")
    return {"job_id": job_id, "cancel_flag": str(flag)}


def write_status(job_id: str | None, status: dict) -> None:
    if not job_id:
        return
    path = status_path(job_id)
    atomic_write_text(path, json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(job_id: str | None) -> dict | None:
    if not job_id:
        return None
    path = status_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_cancel_requested(job_id: str | None) -> bool:
    if not job_id:
        return False
    return cancel_flag_path(job_id).exists()


def clear_job(job_id: str | None) -> None:
    if not job_id:
        return
    path = job_directory(job_id)
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
    path.rmdir()


def clear_runtime_state(job_id: str | None) -> None:
    if not job_id:
        return
    cancel_flag_path(job_id).unlink(missing_ok=True)
