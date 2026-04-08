from __future__ import annotations

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.detect_jobs import DEFAULT_RECENT_JOB_LIMIT, cleanup_jobs


def run(payload: dict) -> dict:
    retain_limit = payload.get("retain_limit")
    try:
        parsed_retain_limit = int(retain_limit) if retain_limit is not None else DEFAULT_RECENT_JOB_LIMIT
    except (TypeError, ValueError):
        parsed_retain_limit = DEFAULT_RECENT_JOB_LIMIT
    parsed_retain_limit = max(0, min(parsed_retain_limit, 50))
    return success(
        "cleanup-detect-jobs",
        cleanup_jobs(
            retain_limit=parsed_retain_limit,
            include_terminal=bool(payload.get("include_terminal", True)),
            include_interrupted=bool(payload.get("include_interrupted", True)),
            include_broken=bool(payload.get("include_broken", True)),
            recover=True,
        ),
    )
