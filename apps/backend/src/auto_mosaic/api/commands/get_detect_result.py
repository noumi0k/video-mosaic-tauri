from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_ledger import get_detect_job_ledger
from auto_mosaic.infra.jobs.job_ledger import JobNotFoundError


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("get-detect-result", "JOB_ID_REQUIRED", "job_id is required.")

    ledger = get_detect_job_ledger(payload.get("paths"))
    try:
        result = ledger.get_result(str(job_id))
    except JobNotFoundError:
        return failure(
            "get-detect-result",
            "DETECT_JOB_NOT_FOUND",
            "Detection job result was not found.",
            {"job_id": str(job_id)},
        )

    if result is None:
        row = ledger.get_job(str(job_id))
        return failure(
            "get-detect-result",
            "DETECT_RESULT_NOT_READY",
            "Detection result is not available yet.",
            {"job_id": str(job_id), "state": row.state if row else None},
        )

    return success("get-detect-result", {"job_id": str(job_id), "result": result})
