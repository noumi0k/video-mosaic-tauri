from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import read_result, read_status


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("get-detect-result", "JOB_ID_REQUIRED", "job_id is required.")

    result = read_result(str(job_id))
    if result is None:
        status = read_status(str(job_id))
        if status is None:
            return failure(
                "get-detect-result",
                "DETECT_JOB_NOT_FOUND",
                "Detection job result was not found.",
                {"job_id": str(job_id)},
            )
        return failure(
            "get-detect-result",
            "DETECT_RESULT_NOT_READY",
            "Detection result is not available yet.",
            {"job_id": str(job_id), "state": status.get("state")},
        )

    return success("get-detect-result", {"job_id": str(job_id), "result": result})
