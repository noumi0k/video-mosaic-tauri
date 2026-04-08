from __future__ import annotations

import traceback

from auto_mosaic.api.commands.detect_video import execute_detect
from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import (
    DEFAULT_RECENT_JOB_LIMIT,
    build_status,
    cleanup_jobs,
    clear_runtime_state,
    is_cancel_requested,
    write_result,
    write_status,
)


def _update_status(job_id: str, *, state: str, stage: str, percent: float, message: str, current: int = 0, total: int = 0, error: dict | None = None, result_available: bool = False) -> None:
    write_status(
        job_id,
        build_status(
            job_id=job_id,
            state=state,
            stage=stage,
            percent=percent,
            message=message,
            current=current,
            total=total,
            error=error,
            result_available=result_available,
        ),
    )


def run(payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return failure("run-detect-job", "JOB_ID_REQUIRED", "job_id is required.")

    def progress_callback(*, stage: str, percent: float, message: str, current: int = 0, total: int = 0) -> None:
        _update_status(
            job_id,
            state="running",
            stage=stage,
            percent=percent,
            message=message,
            current=current,
            total=total,
        )

    worker_payload = {
        **payload,
        "_progress_callback": progress_callback,
        "_cancel_requested": lambda: is_cancel_requested(job_id),
    }

    try:
        _update_status(job_id, state="running", stage="preparing", percent=1.0, message="Detection job started")
        response = execute_detect(worker_payload)
        if response.get("ok"):
            write_result(job_id, response)
            _update_status(
                job_id,
                state="succeeded",
                stage="finalizing",
                percent=100.0,
                message="Detection completed",
                result_available=True,
            )
            return success("run-detect-job", {"job_id": job_id})

        error = response.get("error") or {}
        if error.get("code") == "DETECT_CANCELLED":
            _update_status(
                job_id,
                state="cancelled",
                stage="finalizing",
                percent=0.0,
                message=error.get("message", "Detection was cancelled."),
                error=error,
            )
            return failure("run-detect-job", "DETECT_CANCELLED", error.get("message", "Detection was cancelled."))

        _update_status(
            job_id,
            state="failed",
            stage="finalizing",
            percent=0.0,
            message=error.get("message", "Detection failed."),
            error=error,
        )
        return failure(
            "run-detect-job",
            error.get("code", "DETECT_JOB_FAILED"),
            error.get("message", "Detection failed."),
            error.get("details"),
        )
    except Exception as exc:  # pragma: no cover
        _update_status(
            job_id,
            state="failed",
            stage="finalizing",
            percent=0.0,
            message=str(exc),
            error={
                "code": "DETECT_JOB_FAILED",
                "message": str(exc),
                "details": {"traceback": traceback.format_exc()},
            },
        )
        return failure("run-detect-job", "DETECT_JOB_FAILED", str(exc))
    finally:
        clear_runtime_state(job_id)
        cleanup_jobs(retain_limit=DEFAULT_RECENT_JOB_LIMIT, active_job_ids={job_id})
