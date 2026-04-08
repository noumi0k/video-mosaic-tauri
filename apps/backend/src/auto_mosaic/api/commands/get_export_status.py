from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.video.export_jobs import read_status


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("get-export-status", "JOB_ID_REQUIRED", "job_id is required.")

    status = read_status(str(job_id))
    if status is None:
        return failure(
            "get-export-status",
            "EXPORT_JOB_NOT_FOUND",
            "Export job status was not found.",
            {"job_id": str(job_id)},
        )

    return success("get-export-status", {"job_id": str(job_id), "status": status})
