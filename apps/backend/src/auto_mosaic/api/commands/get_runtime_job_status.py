from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.runtime_jobs import read_status


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("get-runtime-job-status", "JOB_ID_REQUIRED", "job_id is required.")

    status = read_status(str(job_id))
    if status is None:
        return failure(
            "get-runtime-job-status",
            "RUNTIME_JOB_NOT_FOUND",
            "Runtime job status was not found.",
            {"job_id": str(job_id)},
        )

    return success("get-runtime-job-status", {"job_id": str(job_id), "status": status})

