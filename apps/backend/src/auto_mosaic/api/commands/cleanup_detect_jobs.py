from __future__ import annotations

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.detect_jobs import delete_job_directory
from auto_mosaic.infra.ai.detect_ledger import (
    DEFAULT_RECENT_JOB_LIMIT,
    cleanup_detect_jobs,
    get_detect_job_ledger,
)


def run(payload: dict) -> dict:
    retain_limit = payload.get("retain_limit")
    try:
        parsed_retain_limit = int(retain_limit) if retain_limit is not None else DEFAULT_RECENT_JOB_LIMIT
    except (TypeError, ValueError):
        parsed_retain_limit = DEFAULT_RECENT_JOB_LIMIT
    parsed_retain_limit = max(0, min(parsed_retain_limit, 50))

    ledger = get_detect_job_ledger(payload.get("paths"))
    paths = payload.get("paths")
    return success(
        "cleanup-detect-jobs",
        cleanup_detect_jobs(
            ledger,
            retain_limit=parsed_retain_limit,
            include_terminal=bool(payload.get("include_terminal", True)),
            include_interrupted=bool(payload.get("include_interrupted", True)),
            recover=True,
            on_row_deleted=lambda r: delete_job_directory(r.job_id, paths),
        ),
    )
