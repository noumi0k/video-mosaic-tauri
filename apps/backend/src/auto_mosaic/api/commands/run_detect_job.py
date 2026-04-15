from __future__ import annotations

import traceback

from auto_mosaic.api.commands.detect_video import execute_detect
from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import DEFAULT_RECENT_JOB_LIMIT, delete_job_directory
from auto_mosaic.infra.ai.detect_ledger import cleanup_detect_jobs, get_detect_job_ledger
from auto_mosaic.infra.jobs.job_ledger import JobNotFoundError, JobStateError


def run(payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return failure("run-detect-job", "JOB_ID_REQUIRED", "job_id is required.")

    ledger = get_detect_job_ledger(payload.get("paths"))

    def progress_callback(
        *,
        stage: str,
        percent: float,
        message: str,
        current: int = 0,
        total: int = 0,
    ) -> None:
        try:
            ledger.update_progress(
                job_id,
                state="running",
                stage=stage,
                progress_percent=percent,
                message=message,
                current=current,
                total=total,
            )
        except (JobNotFoundError, JobStateError):
            # Progress after a terminal transition is a benign race (cancel
            # racing with a slow frame): drop the update rather than crash.
            return

    worker_payload = {
        **payload,
        "_progress_callback": progress_callback,
        "_cancel_requested": lambda: ledger.is_cancel_requested(job_id),
    }

    try:
        try:
            ledger.update_progress(
                job_id,
                state="running",
                stage="preparing",
                progress_percent=1.0,
                message="Detection job started",
            )
        except (JobNotFoundError, JobStateError):
            return failure(
                "run-detect-job",
                "DETECT_JOB_NOT_FOUND",
                "Detection job row was missing or already terminal.",
                {"job_id": job_id},
            )

        response = execute_detect(worker_payload)
        if response.get("ok"):
            ledger.mark_succeeded(job_id, response)
            return success("run-detect-job", {"job_id": job_id})

        error = response.get("error") or {}
        if error.get("code") == "DETECT_CANCELLED":
            ledger.mark_cancelled(
                job_id,
                error={
                    "code": "DETECT_CANCELLED",
                    "message": error.get("message", "Detection was cancelled."),
                    "details": error.get("details") or {},
                },
            )
            return failure(
                "run-detect-job",
                "DETECT_CANCELLED",
                error.get("message", "Detection was cancelled."),
            )

        ledger.mark_failed(
            job_id,
            {
                "code": error.get("code", "DETECT_JOB_FAILED"),
                "message": error.get("message", "Detection failed."),
                "details": error.get("details") or {},
            },
        )
        return failure(
            "run-detect-job",
            error.get("code", "DETECT_JOB_FAILED"),
            error.get("message", "Detection failed."),
            error.get("details"),
        )
    except Exception as exc:  # pragma: no cover
        try:
            ledger.mark_failed(
                job_id,
                {
                    "code": "DETECT_JOB_FAILED",
                    "message": str(exc),
                    "details": {"traceback": traceback.format_exc()},
                },
            )
        except (JobNotFoundError, JobStateError):
            pass
        return failure("run-detect-job", "DETECT_JOB_FAILED", str(exc))
    finally:
        try:
            cleanup_detect_jobs(
                ledger,
                retain_limit=DEFAULT_RECENT_JOB_LIMIT,
                active_job_ids={job_id},
                on_row_deleted=lambda r: delete_job_directory(
                    r.job_id, payload.get("paths")
                ),
            )
        except Exception:  # pragma: no cover
            pass
