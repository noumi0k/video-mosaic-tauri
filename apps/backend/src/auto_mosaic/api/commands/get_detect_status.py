from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_ledger import (
    get_detect_job_ledger,
    reconcile_single_job,
    row_to_status,
)


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("get-detect-status", "JOB_ID_REQUIRED", "job_id is required.")

    ledger = get_detect_job_ledger(payload.get("paths"))
    row = reconcile_single_job(ledger, str(job_id))
    if row is None:
        return failure(
            "get-detect-status",
            "DETECT_JOB_NOT_FOUND",
            "Detection job status was not found.",
            {"job_id": str(job_id)},
        )

    return success("get-detect-status", {"job_id": str(job_id), "status": row_to_status(row)})
