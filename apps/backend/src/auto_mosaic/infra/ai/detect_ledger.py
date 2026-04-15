"""Detect-job bindings for the SQLite Job Ledger.

This module is the glue layer between the detect CLI commands and the
canonical `JobLedger`. It owns:

- the ledger file location (`<data_dir>/jobs/job-ledger.sqlite3`),
- the JobRow -> legacy-status dict adapter used by get-detect-status /
  list-detect-jobs,
- the heartbeat-based staleness sweep that marks active-but-dead jobs as
  interrupted,
- the ledger-backed list / cleanup helpers consumed by the respective CLI
  commands.

No module-level ledger singleton is kept. Each CLI command constructs a new
`JobLedger` instance via `get_detect_job_ledger(paths)`. The ledger itself
opens and closes SQLite connections per operation.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from auto_mosaic.infra.jobs.job_ledger import (
    ACTIVE_STATES,
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    TERMINAL_STATES,
    JobLedger,
    JobRow,
)
from auto_mosaic.runtime.paths import ensure_runtime_dirs

DEFAULT_RECENT_JOB_LIMIT = 8

DETECT_INTERRUPTED_CODE = "DETECT_JOB_INTERRUPTED"
DETECT_INTERRUPTED_MESSAGE_DEAD = (
    "Detection worker was no longer running and the job was marked interrupted."
)
DETECT_INTERRUPTED_MESSAGE_CANCELLED = (
    "Detection was interrupted after a cancel request."
)


def get_detect_job_ledger(paths: dict | None = None) -> JobLedger:
    """Return a fresh JobLedger bound to the canonical ledger path.

    The ledger file lives under `ensure_runtime_dirs(paths).data_dir / "jobs"
    / "job-ledger.sqlite3"`. Callers create one ledger per command invocation;
    connections are managed inside the ledger.
    """
    runtime_dirs = ensure_runtime_dirs(paths)
    db_path = Path(runtime_dirs.data_dir) / "jobs" / "job-ledger.sqlite3"
    return JobLedger(db_path)


def generate_job_id() -> str:
    return f"detect-{uuid4().hex}"


def row_to_status(row: JobRow) -> dict[str, Any]:
    """Map a canonical JobRow to the legacy status dict shape consumed by
    the frontend (unchanged during Phase 2-5). Phase 7 removes the
    `result_available` / `has_result` fields from the frontend path; backend
    keeps emitting them meanwhile so App.tsx does not break.
    """
    status: dict[str, Any] = {
        "job_id": row.job_id,
        "state": row.state,
        "stage": row.stage,
        "percent": round(max(0.0, min(row.progress_percent, 100.0)), 2),
        "message": row.message,
        "current": row.current,
        "total": row.total,
        "error": row.error,
        "result_available": row.state == "succeeded",
        "has_result": row.state == "succeeded",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if row.worker_pid is not None:
        status["worker_pid"] = row.worker_pid
    if row.finished_at is not None:
        status["finished_at"] = row.finished_at
    return status


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)


def reconcile_stale_jobs(
    ledger: JobLedger,
    *,
    timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> list[JobRow]:
    """Mark active-but-dead jobs as interrupted.

    Staleness is decided by `heartbeat_at` alone; `worker_pid` is not
    consulted here. Returns the rows that were freshly moved to interrupted
    (so callers can count `recovered_interrupted`).
    """
    stale_rows = ledger.find_stale(timeout_seconds=timeout_seconds, now=now)
    recovered: list[JobRow] = []
    for row in stale_rows:
        message = (
            DETECT_INTERRUPTED_MESSAGE_CANCELLED
            if row.cancel_requested
            else DETECT_INTERRUPTED_MESSAGE_DEAD
        )
        error = {
            "code": DETECT_INTERRUPTED_CODE,
            "message": message,
            "details": {"job_id": row.job_id, "last_state": row.state},
        }
        recovered.append(ledger.mark_interrupted(row.job_id, error=error))
    return recovered


def reconcile_single_job(
    ledger: JobLedger,
    job_id: str,
    *,
    timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> JobRow | None:
    """Check one specific job and mark it interrupted if stale. Used by
    get-detect-status so every poll self-heals without scanning the table.
    """
    row = ledger.get_job(job_id)
    if row is None or row.state not in ACTIVE_STATES:
        return row
    current = now if now is not None else datetime.now(UTC)
    cutoff = current - timedelta(seconds=timeout_seconds)
    if _parse_timestamp(row.heartbeat_at) >= cutoff:
        return row
    message = (
        DETECT_INTERRUPTED_MESSAGE_CANCELLED
        if row.cancel_requested
        else DETECT_INTERRUPTED_MESSAGE_DEAD
    )
    error = {
        "code": DETECT_INTERRUPTED_CODE,
        "message": message,
        "details": {"job_id": job_id, "last_state": row.state},
    }
    return ledger.mark_interrupted(job_id, error=error)


def list_recent_jobs(
    ledger: JobLedger,
    *,
    limit: int = DEFAULT_RECENT_JOB_LIMIT,
    recover: bool = True,
) -> dict[str, Any]:
    """Return the most recent detect jobs as legacy status dicts."""
    recovered = reconcile_stale_jobs(ledger) if recover else []
    rows = ledger.list_jobs()
    clipped = rows[: max(0, limit)]
    return {
        "jobs": [row_to_status(row) for row in clipped],
        "retained_limit": limit,
        "recovered_interrupted": len(recovered),
        "broken_job_ids": [],
    }


def cleanup_detect_jobs(
    ledger: JobLedger,
    *,
    retain_limit: int = DEFAULT_RECENT_JOB_LIMIT,
    include_terminal: bool = True,
    include_interrupted: bool = True,
    recover: bool = True,
    active_job_ids: set[str] | None = None,
    on_row_deleted: "callable[[JobRow], None] | None" = None,
) -> dict[str, Any]:
    """Prune old terminal rows, respecting retain_limit and active jobs.

    `on_row_deleted` lets the caller perform side-effect cleanup for each
    deleted row (e.g., removing the worker stderr log directory).
    """
    active_job_ids = active_job_ids or set()
    if recover:
        reconcile_stale_jobs(ledger)
    rows = ledger.list_jobs()
    retained_ids = {row.job_id for row in rows[: max(0, retain_limit)]}
    deleted_job_ids: list[str] = []
    skipped_job_ids: list[str] = []

    for row in rows:
        if row.job_id in active_job_ids:
            continue
        if row.state in ACTIVE_STATES:
            skipped_job_ids.append(row.job_id)
            continue
        if row.state == "interrupted" and not include_interrupted:
            skipped_job_ids.append(row.job_id)
            continue
        if row.state in TERMINAL_STATES and row.state != "interrupted" and not include_terminal:
            skipped_job_ids.append(row.job_id)
            continue
        if row.job_id in retained_ids:
            skipped_job_ids.append(row.job_id)
            continue
        if ledger.delete_job(row.job_id):
            deleted_job_ids.append(row.job_id)
            if on_row_deleted is not None:
                try:
                    on_row_deleted(row)
                except Exception:  # pragma: no cover
                    pass

    return {
        "deleted_job_ids": deleted_job_ids,
        "skipped_job_ids": skipped_job_ids,
        "retained_limit": retain_limit,
        "broken_job_ids": [],
    }
