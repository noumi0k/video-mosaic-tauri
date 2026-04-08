from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.runtime_jobs import read_status, request_cancel, write_status

TERMINAL_STATES = {"cancelled", "completed", "failed"}


def run(payload: dict) -> dict:
    job_id = payload.get("job_id")
    if not job_id:
        return failure("cancel-runtime-job", "JOB_ID_REQUIRED", "job_id is required.")

    job_id = str(job_id)
    status = read_status(job_id)
    if status is None:
        return failure("cancel-runtime-job", "RUNTIME_JOB_NOT_FOUND", "Runtime job was not found.", {"job_id": job_id})

    current_state = str(status.get("state") or "")
    if current_state in TERMINAL_STATES:
        return success("cancel-runtime-job", {"job_id": job_id, "already_terminal": True, "state": current_state})

    request = request_cancel(job_id)
    next_state = "cancelled" if current_state in {"queued", "starting"} else "cancelling"
    next_stage = "cancelled" if next_state == "cancelled" else "cancelling"
    next_message = "中断しました。" if next_state == "cancelled" else "中断要求を送信しました。"
    write_status(job_id, {"state": next_state, "stage": next_stage, "message": next_message, "can_cancel": False})
    return success("cancel-runtime-job", request)
