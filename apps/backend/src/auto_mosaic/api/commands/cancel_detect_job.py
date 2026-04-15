from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_ledger import get_detect_job_ledger
from auto_mosaic.infra.jobs.job_ledger import JobNotFoundError


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("cancel-detect-job", "JOB_ID_REQUIRED", "job_id is required.")

    ledger = get_detect_job_ledger(payload.get("paths"))
    try:
        cancel_accepted = ledger.request_cancel(str(job_id))
    except JobNotFoundError:
        return failure(
            "cancel-detect-job",
            "DETECT_JOB_NOT_FOUND",
            "Detection job was not found.",
            {"job_id": str(job_id)},
        )

    return success(
        "cancel-detect-job",
        {"job_id": str(job_id), "cancel_requested": cancel_accepted},
    )
