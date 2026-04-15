from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.runtime_jobs import (
    build_status,
    find_active_job,
    generate_job_id,
    stderr_log_path,
    write_status,
)

SUPPORTED_JOB_KINDS = {"setup_environment", "fetch_models", "open_video", "setup_erax_convert"}


def _backend_root() -> Path:
    configured = os.environ.get("AUTO_MOSAIC_BACKEND_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4]


def _spawn_runtime_worker(job_id: str, payload: dict) -> int:
    backend_root = _backend_root()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(backend_root / "src"))
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    stderr_path = stderr_log_path(job_id)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    try:
        creationflags = 0
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(
            [sys.executable, "-m", "auto_mosaic.api.cli_main", "run-runtime-job"],
            cwd=backend_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_handle,
            creationflags=creationflags,
            **popen_kwargs,
        )
        if process.stdin is None:
            raise OSError("Worker stdin pipe was not available.")
        process.stdin.write(json.dumps({**payload, "job_id": job_id}, ensure_ascii=False).encode("utf-8"))
        process.stdin.close()
        return int(process.pid)
    finally:
        stderr_handle.close()


def run(payload: dict) -> dict:
    job_kind = str(payload.get("job_kind") or "")
    if job_kind not in SUPPORTED_JOB_KINDS:
        return failure(
            "start-runtime-job",
            "UNSUPPORTED_JOB_KIND",
            "job_kind must be setup_environment, fetch_models, open_video, or setup_erax_convert.",
            {"job_kind": job_kind},
        )

    active = find_active_job(job_kind)
    if active is not None:
        return failure(
            "start-runtime-job",
            "JOB_ALREADY_RUNNING",
            "A job of the same kind is already running.",
            {"job_kind": job_kind, "active_job_id": active.get("job_id")},
        )

    job_id = generate_job_id(job_kind)
    queued_status = build_status(
        job_id=job_id,
        job_kind=job_kind,
        state="queued",
        stage="queued",
        message="Job queued.",
        progress_percent=0.0,
        is_indeterminate=True,
    )
    write_status(job_id, queued_status)

    try:
        worker_pid = _spawn_runtime_worker(job_id, payload)
        write_status(job_id, {"worker_pid": worker_pid})
    except Exception as exc:
        failed_status = build_status(
            job_id=job_id,
            job_kind=job_kind,
            state="failed",
            stage="starting",
            message="Failed to start background job.",
            progress_percent=0.0,
            is_indeterminate=True,
            can_cancel=False,
            error_code="RUNTIME_JOB_START_FAILED",
            error_message=str(exc),
        )
        write_status(job_id, failed_status)
        return failure(
            "start-runtime-job",
            "RUNTIME_JOB_START_FAILED",
            "Failed to start background job.",
            {"job_id": job_id, "job_kind": job_kind, "reason": str(exc)},
        )

    return success("start-runtime-job", {"job_id": job_id, "status": queued_status})
