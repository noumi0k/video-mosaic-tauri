"""SQLite Job Ledger for detect jobs (Phase 1 of the migration plan).

See docs/engineering/job-ledger-migration-plan.md for the PM decisions behind
this module. The intent of Phase 1 is to land the ledger foundation without
wiring it into CLI commands yet; Phase 2-5 connect detect commands to this
ledger in a single slice to avoid contract mixing.

Key invariants enforced by this module:

- state=succeeded and result_json are written in the same SQLite transaction.
  No consumer may infer success from anything other than the canonical row.
- heartbeat_at is updated on every state-changing write. The ledger does not
  run its own timer; writers update heartbeat_at as part of their normal path.
- worker_pid is stored as a diagnostic hint; staleness is determined from
  heartbeat_at only.
- Terminal states (succeeded / failed / cancelled / interrupted) never flip
  back to active states. request_cancel on a terminal job is a no-op.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1
DEFAULT_BUSY_TIMEOUT_MS = 5000
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 60

ACTIVE_STATES: frozenset[str] = frozenset({"queued", "running", "cancelling"})
TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_kind TEXT NOT NULL,
    state TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT '',
    progress_percent REAL NOT NULL DEFAULT 0.0,
    message TEXT NOT NULL DEFAULT '',
    current INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    error_json TEXT,
    result_json TEXT,
    worker_pid INTEGER,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state_heartbeat
    ON jobs (state, heartbeat_at);
"""


class JobLedgerError(Exception):
    """Base class for job ledger errors."""


class JobNotFoundError(JobLedgerError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job not found: {job_id}")
        self.job_id = job_id


class JobAlreadyExistsError(JobLedgerError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job already exists: {job_id}")
        self.job_id = job_id


class JobStateError(JobLedgerError):
    """Raised when a state transition violates ledger rules."""


@dataclass(frozen=True)
class JobRow:
    job_id: str
    job_kind: str
    state: str
    stage: str
    progress_percent: float
    message: str
    current: int
    total: int
    error: dict | None
    result: dict | None
    worker_pid: int | None
    cancel_requested: bool
    heartbeat_at: str
    created_at: str
    updated_at: str
    finished_at: str | None


def _now() -> datetime:
    return datetime.now(UTC)


def _format_ts(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _timestamp() -> str:
    return _format_ts(_now())


def _loads(raw: str | None) -> dict | None:
    if raw is None:
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _row_to_jobrow(row: sqlite3.Row) -> JobRow:
    return JobRow(
        job_id=row["job_id"],
        job_kind=row["job_kind"],
        state=row["state"],
        stage=row["stage"],
        progress_percent=float(row["progress_percent"]),
        message=row["message"],
        current=int(row["current"]),
        total=int(row["total"]),
        error=_loads(row["error_json"]),
        result=_loads(row["result_json"]),
        worker_pid=int(row["worker_pid"]) if row["worker_pid"] is not None else None,
        cancel_requested=bool(row["cancel_requested"]),
        heartbeat_at=row["heartbeat_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )


class JobLedger:
    """SQLite-backed canonical store for job state.

    One instance maps to one SQLite database file. Connections are opened and
    closed per public call so that Windows file locks and parent/child process
    writes do not stall each other; WAL and busy_timeout are applied on every
    connection.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000.0,
        )
        try:
            conn.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._connect() as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current < 1:
                conn.executescript(_SCHEMA_V1)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                conn.commit()
            # Forward-only future migrations:
            #   if current < 2: apply v2 schema; execute PRAGMA user_version = 2; ...

    # ---------------------------------------------------------------- lifecycle

    def create_job(
        self,
        job_id: str,
        *,
        job_kind: str = "detect",
        worker_pid: int | None = None,
        stage: str = "",
        message: str = "",
        total: int = 0,
    ) -> JobRow:
        now = _timestamp()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id, job_kind, state, stage, progress_percent, message,
                        current, total, error_json, result_json, worker_pid,
                        cancel_requested, heartbeat_at, created_at, updated_at,
                        finished_at
                    ) VALUES (
                        ?, ?, 'queued', ?, 0.0, ?, 0, ?, NULL, NULL, ?, 0, ?, ?, ?, NULL
                    )
                    """,
                    (
                        job_id,
                        job_kind,
                        stage,
                        message,
                        total,
                        worker_pid,
                        now,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise JobAlreadyExistsError(job_id) from exc
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row)

    def get_job(self, job_id: str) -> JobRow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row) if row else None

    # ---------------------------------------------------------------- progress

    def update_progress(
        self,
        job_id: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        progress_percent: float | None = None,
        message: str | None = None,
        current: int | None = None,
        total: int | None = None,
        worker_pid: int | None = None,
    ) -> JobRow:
        if state is not None and state not in ACTIVE_STATES:
            raise JobStateError(
                "update_progress only accepts active states; "
                f"use mark_* for terminal transitions (got {state!r})"
            )
        now = _timestamp()
        set_clauses: list[str] = ["heartbeat_at = ?", "updated_at = ?"]
        params: list = [now, now]
        if state is not None:
            set_clauses.append("state = ?")
            params.append(state)
        if stage is not None:
            set_clauses.append("stage = ?")
            params.append(stage)
        if progress_percent is not None:
            set_clauses.append("progress_percent = ?")
            params.append(float(progress_percent))
        if message is not None:
            set_clauses.append("message = ?")
            params.append(message)
        if current is not None:
            set_clauses.append("current = ?")
            params.append(int(current))
        if total is not None:
            set_clauses.append("total = ?")
            params.append(int(total))
        if worker_pid is not None:
            set_clauses.append("worker_pid = ?")
            params.append(int(worker_pid))
        params.append(job_id)

        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if current_row is None:
                raise JobNotFoundError(job_id)
            if current_row["state"] in TERMINAL_STATES:
                raise JobStateError(
                    f"Cannot update terminal job {job_id} "
                    f"(state={current_row['state']!r})"
                )
            conn.execute(
                f"UPDATE jobs SET {', '.join(set_clauses)} WHERE job_id = ?",
                params,
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row)

    def touch_heartbeat(self, job_id: str) -> JobRow:
        """Refresh heartbeat_at without any progress change.

        Normal flow updates heartbeat via update_progress; this exists for edge
        cases (e.g., a long native call that produces no incremental progress)
        and for tests. The ledger never runs an independent timer.
        """
        now = _timestamp()
        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if current_row is None:
                raise JobNotFoundError(job_id)
            if current_row["state"] in TERMINAL_STATES:
                raise JobStateError(
                    f"Cannot heartbeat terminal job {job_id} "
                    f"(state={current_row['state']!r})"
                )
            conn.execute(
                "UPDATE jobs SET heartbeat_at = ?, updated_at = ? WHERE job_id = ?",
                (now, now, job_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row)

    # ---------------------------------------------------------------- terminal

    def mark_succeeded(self, job_id: str, result: dict) -> JobRow:
        """Atomically write state=succeeded and result_json in one transaction.

        This is the only sanctioned success path. A consumer must never read
        result file existence to infer success; reading the canonical row is
        the only contract.
        """
        now = _timestamp()
        payload = json.dumps(result, ensure_ascii=False)
        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if current_row is None:
                raise JobNotFoundError(job_id)
            if current_row["state"] in TERMINAL_STATES:
                raise JobStateError(
                    f"Cannot succeed terminal job {job_id} "
                    f"(state={current_row['state']!r})"
                )
            conn.execute(
                """
                UPDATE jobs SET
                    state = 'succeeded',
                    result_json = ?,
                    progress_percent = 100.0,
                    heartbeat_at = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE job_id = ?
                """,
                (payload, now, now, now, job_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row)

    def mark_failed(self, job_id: str, error: dict) -> JobRow:
        return self._mark_terminal(
            job_id,
            "failed",
            error_json=json.dumps(error, ensure_ascii=False),
        )

    def mark_cancelled(self, job_id: str, error: dict | None = None) -> JobRow:
        payload = json.dumps(error, ensure_ascii=False) if error else None
        return self._mark_terminal(job_id, "cancelled", error_json=payload)

    def mark_interrupted(
        self,
        job_id: str,
        error: dict | None = None,
    ) -> JobRow:
        payload = json.dumps(error, ensure_ascii=False) if error else None
        return self._mark_terminal(job_id, "interrupted", error_json=payload)

    def _mark_terminal(
        self,
        job_id: str,
        new_state: str,
        *,
        error_json: str | None = None,
    ) -> JobRow:
        assert new_state in TERMINAL_STATES
        now = _timestamp()
        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if current_row is None:
                raise JobNotFoundError(job_id)
            if current_row["state"] in TERMINAL_STATES:
                raise JobStateError(
                    f"Job {job_id} is already terminal "
                    f"(state={current_row['state']!r})"
                )
            conn.execute(
                """
                UPDATE jobs SET
                    state = ?,
                    error_json = COALESCE(?, error_json),
                    heartbeat_at = ?,
                    updated_at = ?,
                    finished_at = ?
                WHERE job_id = ?
                """,
                (new_state, error_json, now, now, now, job_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_jobrow(row)

    # ---------------------------------------------------------------- cancel

    def request_cancel(self, job_id: str) -> bool:
        """Set cancel_requested=1 on an active job.

        Returns True when the flag is set. Returns False when the job is
        already terminal (terminal jobs must not be pulled back to an active
        state). Raises JobNotFoundError when the job does not exist.
        """
        now = _timestamp()
        with self._connect() as conn:
            current_row = conn.execute(
                "SELECT state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if current_row is None:
                raise JobNotFoundError(job_id)
            if current_row["state"] in TERMINAL_STATES:
                return False
            conn.execute(
                "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )
            conn.commit()
        return True

    # ---------------------------------------------------------------- reads

    def get_result(self, job_id: str) -> dict | None:
        """Return the job result only when canonical state is succeeded.

        Consumers must not read a result file as a success signal; this is
        the only sanctioned path to fetch a detect job result.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state, result_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFoundError(job_id)
        if row["state"] != "succeeded":
            return None
        return _loads(row["result_json"])

    def list_active(self) -> list[JobRow]:
        states = tuple(sorted(ACTIVE_STATES))
        placeholders = ", ".join("?" for _ in states)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE state IN ({placeholders}) "
                "ORDER BY created_at",
                states,
            ).fetchall()
        return [_row_to_jobrow(r) for r in rows]

    def list_jobs(
        self,
        *,
        states: set[str] | frozenset[str] | None = None,
        order_by_updated_desc: bool = True,
    ) -> list[JobRow]:
        """List jobs, optionally filtered by state set.

        Results are ordered by updated_at descending by default (most recent
        first), matching the recent-jobs view expected by list-detect-jobs.
        """
        order = "updated_at DESC" if order_by_updated_desc else "created_at"
        with self._connect() as conn:
            if states:
                placeholders = ", ".join("?" for _ in states)
                rows = conn.execute(
                    f"SELECT * FROM jobs WHERE state IN ({placeholders}) "
                    f"ORDER BY {order}",
                    tuple(sorted(states)),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM jobs ORDER BY {order}"
                ).fetchall()
        return [_row_to_jobrow(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Remove a job row. Returns True when a row was deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM jobs WHERE job_id = ?", (job_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def is_cancel_requested(self, job_id: str) -> bool:
        """Return the cancel_requested flag for a job.

        Missing jobs read as False rather than raising, because this helper is
        called from the worker's hot path (frame-by-frame poll); a transient
        read-your-own-write race with the writer must not crash the worker.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return False
        return bool(row["cancel_requested"])

    def find_stale(
        self,
        *,
        timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
        now: datetime | None = None,
    ) -> list[JobRow]:
        current = now if now is not None else _now()
        cutoff = current - timedelta(seconds=timeout_seconds)
        cutoff_iso = _format_ts(cutoff)
        states = tuple(sorted(ACTIVE_STATES))
        placeholders = ", ".join("?" for _ in states)
        params = states + (cutoff_iso,)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM jobs
                WHERE state IN ({placeholders})
                  AND heartbeat_at < ?
                ORDER BY heartbeat_at
                """,
                params,
            ).fetchall()
        return [_row_to_jobrow(r) for r in rows]

    def get_schema_version(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])
