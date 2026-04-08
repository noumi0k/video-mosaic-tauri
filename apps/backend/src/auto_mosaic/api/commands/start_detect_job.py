from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import (
    DEFAULT_RECENT_JOB_LIMIT,
    build_status,
    cleanup_jobs,
    generate_job_id,
    stderr_log_path,
    write_status,
)


def _backend_root() -> Path:
    configured = os.environ.get("AUTO_MOSAIC_BACKEND_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4]


def _spawn_detect_worker(job_id: str, payload: dict) -> int:
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
            [sys.executable, "-m", "auto_mosaic.api.cli_main", "run-detect-job"],
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
        process.stdin.write(__import__("json").dumps({**payload, "job_id": job_id}).encode("utf-8"))
        process.stdin.close()
        return int(process.pid)
    finally:
        stderr_handle.close()


def run(payload: dict) -> dict:
    job_id = generate_job_id()
    queued_status = build_status(
        job_id=job_id,
        state="queued",
        stage="preparing",
        percent=0.0,
        message="Detection job queued",
        current=0,
        total=0,
    )
    write_status(job_id, queued_status)

    try:
        worker_pid = _spawn_detect_worker(job_id, payload)
        write_status(job_id, {"worker_pid": worker_pid})
        cleanup_jobs(retain_limit=DEFAULT_RECENT_JOB_LIMIT, active_job_ids={job_id})
    except Exception as exc:
        failed_status = build_status(
            job_id=job_id,
            state="failed",
            stage="preparing",
            percent=0.0,
            message="Failed to start detection worker",
            error={"code": "DETECT_JOB_START_FAILED", "message": str(exc), "details": {"job_id": job_id}},
        )
        write_status(job_id, failed_status)
        return failure(
            "start-detect-job",
            "DETECT_JOB_START_FAILED",
            "Failed to start background detection worker.",
            {"job_id": job_id, "reason": str(exc)},
        )

    return success(
        "start-detect-job",
        {
            "job_id": job_id,
            "status": queued_status,
        },
    )
