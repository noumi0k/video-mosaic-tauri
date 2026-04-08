from __future__ import annotations

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.detect_jobs import DEFAULT_RECENT_JOB_LIMIT, list_recent_jobs


def run(payload: dict) -> dict:
    limit = payload.get("limit")
    try:
        parsed_limit = int(limit) if limit is not None else DEFAULT_RECENT_JOB_LIMIT
    except (TypeError, ValueError):
        parsed_limit = DEFAULT_RECENT_JOB_LIMIT
    parsed_limit = max(1, min(parsed_limit, 50))
    return success("list-detect-jobs", list_recent_jobs(limit=parsed_limit, recover=True))
