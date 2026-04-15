from __future__ import annotations

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.detect_ledger import (
    DEFAULT_RECENT_JOB_LIMIT,
    get_detect_job_ledger,
    list_recent_jobs,
)


def run(payload: dict) -> dict:
    limit = payload.get("limit")
    try:
        parsed_limit = int(limit) if limit is not None else DEFAULT_RECENT_JOB_LIMIT
    except (TypeError, ValueError):
        parsed_limit = DEFAULT_RECENT_JOB_LIMIT
    parsed_limit = max(1, min(parsed_limit, 50))

    ledger = get_detect_job_ledger(payload.get("paths"))
    return success("list-detect-jobs", list_recent_jobs(ledger, limit=parsed_limit))
