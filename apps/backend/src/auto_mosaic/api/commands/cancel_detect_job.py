from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import request_cancel


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("cancel-detect-job", "JOB_ID_REQUIRED", "job_id is required.")

    return success("cancel-detect-job", request_cancel(str(job_id)))
