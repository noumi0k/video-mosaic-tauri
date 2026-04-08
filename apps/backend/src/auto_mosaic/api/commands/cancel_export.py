from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.video.export_jobs import request_cancel


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("cancel-export", "JOB_ID_REQUIRED", "job_id is required.")

    data = request_cancel(str(job_id))
    return success("cancel-export", data)
