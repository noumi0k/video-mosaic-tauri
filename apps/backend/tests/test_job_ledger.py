"""Unit tests for the SQLite Job Ledger (Phase 1).

These tests cover only ledger mechanics: create / read / update / heartbeat /
finish / cancel / schema-version. They do not touch detect command wiring,
subprocess kill fixtures, or real runtime directories. Phase 6 will add
race-focused worker-death tests against the integrated pipeline.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from auto_mosaic.infra.jobs.job_ledger import (
    ACTIVE_STATES,
    DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    SCHEMA_VERSION,
    TERMINAL_STATES,
    JobAlreadyExistsError,
    JobLedger,
    JobNotFoundError,
    JobStateError,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "job-ledger.sqlite3"


@pytest.fixture()
def ledger(ledger_path: Path) -> JobLedger:
    return JobLedger(ledger_path)


def _make_job(ledger: JobLedger, job_id: str = "detect-abc123", **kwargs):
    return ledger.create_job(job_id, **kwargs)


# ---------------------------------------------------------------------------
# create / read
# ---------------------------------------------------------------------------


def test_create_job_initial_state_is_queued(ledger: JobLedger) -> None:
    row = _make_job(ledger, worker_pid=4321, total=120, stage="initializing")
    assert row.job_id == "detect-abc123"
    assert row.job_kind == "detect"
    assert row.state == "queued"
    assert row.stage == "initializing"
    assert row.progress_percent == 0.0
    assert row.current == 0
    assert row.total == 120
    assert row.error is None
    assert row.result is None
    assert row.worker_pid == 4321
    assert row.cancel_requested is False
    assert row.finished_at is None
    assert row.created_at == row.updated_at == row.heartbeat_at


def test_create_job_allows_null_worker_pid(ledger: JobLedger) -> None:
    row = _make_job(ledger, worker_pid=None)
    assert row.worker_pid is None


def test_create_job_duplicate_raises(ledger: JobLedger) -> None:
    _make_job(ledger)
    with pytest.raises(JobAlreadyExistsError):
        _make_job(ledger)


def test_get_job_returns_none_when_absent(ledger: JobLedger) -> None:
    assert ledger.get_job("missing") is None


def test_get_job_roundtrip_matches_create(ledger: JobLedger) -> None:
    created = _make_job(ledger, total=50)
    fetched = ledger.get_job("detect-abc123")
    assert fetched == created


# ---------------------------------------------------------------------------
# update_progress
# ---------------------------------------------------------------------------


def test_update_progress_advances_heartbeat(ledger: JobLedger) -> None:
    initial = _make_job(ledger)
    time.sleep(0.01)  # ensure timestamp delta
    updated = ledger.update_progress(
        initial.job_id,
        state="running",
        stage="detecting",
        progress_percent=25.0,
        current=30,
        total=120,
        message="frame 30 of 120",
    )
    assert updated.state == "running"
    assert updated.stage == "detecting"
    assert updated.progress_percent == 25.0
    assert updated.current == 30
    assert updated.total == 120
    assert updated.message == "frame 30 of 120"
    assert updated.heartbeat_at > initial.heartbeat_at
    assert updated.updated_at > initial.updated_at
    assert updated.created_at == initial.created_at  # created_at immutable


def test_update_progress_partial_leaves_other_fields(ledger: JobLedger) -> None:
    _make_job(ledger, total=100, stage="initial")
    updated = ledger.update_progress("detect-abc123", progress_percent=10.0)
    assert updated.stage == "initial"
    assert updated.total == 100
    assert updated.progress_percent == 10.0


def test_update_progress_rejects_terminal_state_value(ledger: JobLedger) -> None:
    _make_job(ledger)
    with pytest.raises(JobStateError):
        ledger.update_progress("detect-abc123", state="succeeded")
    with pytest.raises(JobStateError):
        ledger.update_progress("detect-abc123", state="failed")


def test_update_progress_rejects_on_terminal_job(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_succeeded("detect-abc123", {"tracks": []})
    with pytest.raises(JobStateError):
        ledger.update_progress("detect-abc123", progress_percent=50.0)


def test_update_progress_raises_for_missing_job(ledger: JobLedger) -> None:
    with pytest.raises(JobNotFoundError):
        ledger.update_progress("no-such-job", progress_percent=10.0)


def test_update_progress_can_transition_active_states(ledger: JobLedger) -> None:
    _make_job(ledger)
    r1 = ledger.update_progress("detect-abc123", state="running")
    assert r1.state == "running"
    r2 = ledger.update_progress("detect-abc123", state="cancelling")
    assert r2.state == "cancelling"


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


def test_touch_heartbeat_advances_timestamp(ledger: JobLedger) -> None:
    initial = _make_job(ledger)
    time.sleep(0.01)
    refreshed = ledger.touch_heartbeat("detect-abc123")
    assert refreshed.heartbeat_at > initial.heartbeat_at
    assert refreshed.state == initial.state
    assert refreshed.progress_percent == initial.progress_percent


def test_touch_heartbeat_rejects_terminal(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_cancelled("detect-abc123")
    with pytest.raises(JobStateError):
        ledger.touch_heartbeat("detect-abc123")


def test_touch_heartbeat_raises_for_missing(ledger: JobLedger) -> None:
    with pytest.raises(JobNotFoundError):
        ledger.touch_heartbeat("no-such-job")


# ---------------------------------------------------------------------------
# terminal transitions
# ---------------------------------------------------------------------------


def test_mark_succeeded_writes_state_and_result_together(ledger: JobLedger) -> None:
    _make_job(ledger)
    payload = {"tracks": [{"track_id": "t1", "keyframes": []}]}
    finished = ledger.mark_succeeded("detect-abc123", payload)
    assert finished.state == "succeeded"
    assert finished.result == payload
    assert finished.progress_percent == 100.0
    assert finished.finished_at is not None


def test_mark_succeeded_result_visible_to_get_result(ledger: JobLedger) -> None:
    _make_job(ledger)
    payload = {"tracks": [], "meta": {"frames": 42}}
    ledger.mark_succeeded("detect-abc123", payload)
    assert ledger.get_result("detect-abc123") == payload


def test_mark_succeeded_persists_across_reopen(
    ledger_path: Path, ledger: JobLedger
) -> None:
    _make_job(ledger)
    ledger.mark_succeeded("detect-abc123", {"tracks": []})

    reopened = JobLedger(ledger_path)
    assert reopened.get_job("detect-abc123").state == "succeeded"
    assert reopened.get_result("detect-abc123") == {"tracks": []}


def test_mark_succeeded_rejects_already_terminal(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_succeeded("detect-abc123", {"tracks": []})
    with pytest.raises(JobStateError):
        ledger.mark_succeeded("detect-abc123", {"tracks": []})


def test_mark_failed_persists_error(ledger: JobLedger) -> None:
    _make_job(ledger)
    error = {"code": "DETECT_FAILED", "message": "model crashed", "details": {}}
    finished = ledger.mark_failed("detect-abc123", error)
    assert finished.state == "failed"
    assert finished.error == error
    assert finished.result is None
    assert finished.finished_at is not None


def test_mark_cancelled_sets_terminal(ledger: JobLedger) -> None:
    _make_job(ledger)
    finished = ledger.mark_cancelled("detect-abc123")
    assert finished.state == "cancelled"
    assert finished.finished_at is not None
    assert finished.error is None


def test_mark_cancelled_preserves_error_details(ledger: JobLedger) -> None:
    _make_job(ledger)
    finished = ledger.mark_cancelled(
        "detect-abc123",
        error={"code": "DETECT_CANCELLED", "message": "cancel requested"},
    )
    assert finished.state == "cancelled"
    assert finished.error == {"code": "DETECT_CANCELLED", "message": "cancel requested"}


def test_mark_interrupted_with_error_details(ledger: JobLedger) -> None:
    _make_job(ledger)
    finished = ledger.mark_interrupted(
        "detect-abc123",
        error={"code": "WORKER_DEAD", "message": "heartbeat timeout"},
    )
    assert finished.state == "interrupted"
    assert finished.error == {
        "code": "WORKER_DEAD",
        "message": "heartbeat timeout",
    }


def test_mark_interrupted_without_error(ledger: JobLedger) -> None:
    _make_job(ledger)
    finished = ledger.mark_interrupted("detect-abc123")
    assert finished.state == "interrupted"
    assert finished.error is None


def test_mark_terminal_raises_for_missing(ledger: JobLedger) -> None:
    with pytest.raises(JobNotFoundError):
        ledger.mark_failed("no-such-job", {"code": "x", "message": "y"})


# ---------------------------------------------------------------------------
# cancel flag
# ---------------------------------------------------------------------------


def test_request_cancel_sets_flag(ledger: JobLedger) -> None:
    _make_job(ledger)
    assert ledger.request_cancel("detect-abc123") is True
    row = ledger.get_job("detect-abc123")
    assert row.cancel_requested is True
    assert row.state == "queued"  # does not move to cancelling on its own


def test_request_cancel_on_terminal_job_is_noop(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_succeeded("detect-abc123", {"tracks": []})
    assert ledger.request_cancel("detect-abc123") is False
    row = ledger.get_job("detect-abc123")
    assert row.cancel_requested is False  # unchanged
    assert row.state == "succeeded"


def test_request_cancel_raises_for_missing(ledger: JobLedger) -> None:
    with pytest.raises(JobNotFoundError):
        ledger.request_cancel("no-such-job")


# ---------------------------------------------------------------------------
# get_result invariants
# ---------------------------------------------------------------------------


def test_get_result_returns_none_for_active_job(ledger: JobLedger) -> None:
    _make_job(ledger)
    assert ledger.get_result("detect-abc123") is None


def test_get_result_returns_none_for_failed_job(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_failed("detect-abc123", {"code": "x", "message": "y"})
    assert ledger.get_result("detect-abc123") is None


def test_get_result_raises_for_missing(ledger: JobLedger) -> None:
    with pytest.raises(JobNotFoundError):
        ledger.get_result("no-such-job")


# ---------------------------------------------------------------------------
# list_active / find_stale
# ---------------------------------------------------------------------------


def test_list_active_excludes_terminal_jobs(ledger: JobLedger) -> None:
    ledger.create_job("detect-a")
    ledger.create_job("detect-b")
    ledger.create_job("detect-c")
    ledger.mark_succeeded("detect-b", {"tracks": []})

    active = {row.job_id for row in ledger.list_active()}
    assert active == {"detect-a", "detect-c"}


def test_list_active_includes_all_active_states(ledger: JobLedger) -> None:
    ledger.create_job("detect-q")
    ledger.create_job("detect-r")
    ledger.create_job("detect-c")
    ledger.update_progress("detect-r", state="running")
    ledger.update_progress("detect-c", state="cancelling")

    states = {row.state for row in ledger.list_active()}
    assert states == ACTIVE_STATES


def test_find_stale_detects_jobs_past_timeout(ledger: JobLedger) -> None:
    _make_job(ledger)
    future = datetime.now(UTC) + timedelta(
        seconds=DEFAULT_HEARTBEAT_TIMEOUT_SECONDS + 10
    )
    stale = ledger.find_stale(now=future)
    assert [row.job_id for row in stale] == ["detect-abc123"]


def test_find_stale_ignores_fresh_jobs(ledger: JobLedger) -> None:
    _make_job(ledger)
    now = datetime.now(UTC) + timedelta(seconds=5)
    assert ledger.find_stale(now=now) == []


def test_find_stale_ignores_terminal_jobs(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.mark_succeeded("detect-abc123", {"tracks": []})
    future = datetime.now(UTC) + timedelta(
        seconds=DEFAULT_HEARTBEAT_TIMEOUT_SECONDS + 10
    )
    assert ledger.find_stale(now=future) == []


def test_find_stale_honors_custom_timeout(ledger: JobLedger) -> None:
    _make_job(ledger)
    future = datetime.now(UTC) + timedelta(seconds=3)
    assert ledger.find_stale(now=future, timeout_seconds=2) != []
    assert ledger.find_stale(now=future, timeout_seconds=10) == []


# ---------------------------------------------------------------------------
# schema version / persistence
# ---------------------------------------------------------------------------


def test_schema_version_after_migration(ledger: JobLedger) -> None:
    assert ledger.get_schema_version() == SCHEMA_VERSION


def test_migration_is_idempotent(ledger_path: Path) -> None:
    JobLedger(ledger_path)
    JobLedger(ledger_path)  # second open must not re-run schema
    ledger = JobLedger(ledger_path)
    assert ledger.get_schema_version() == SCHEMA_VERSION


def test_reopen_preserves_jobs(ledger_path: Path) -> None:
    first = JobLedger(ledger_path)
    first.create_job("detect-abc123", total=42, worker_pid=999)
    first.update_progress("detect-abc123", state="running", progress_percent=20.0)

    second = JobLedger(ledger_path)
    row = second.get_job("detect-abc123")
    assert row is not None
    assert row.state == "running"
    assert row.progress_percent == 20.0
    assert row.total == 42
    assert row.worker_pid == 999


def test_pragmas_applied_per_connection(ledger: JobLedger, ledger_path: Path) -> None:
    # Open a fresh connection to confirm WAL journal mode was set by _migrate.
    conn = sqlite3.connect(str(ledger_path))
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_constants_are_disjoint() -> None:
    assert ACTIVE_STATES.isdisjoint(TERMINAL_STATES)


# ---------------------------------------------------------------------------
# list_jobs / delete_job / is_cancel_requested (Phase 2 additions)
# ---------------------------------------------------------------------------


def test_list_jobs_returns_all_ordered_by_updated_desc(ledger: JobLedger) -> None:
    ledger.create_job("detect-a")
    time.sleep(0.01)
    ledger.create_job("detect-b")
    time.sleep(0.01)
    ledger.create_job("detect-c")
    time.sleep(0.01)
    ledger.update_progress("detect-a", progress_percent=10.0)  # refresh updated_at

    ids = [row.job_id for row in ledger.list_jobs()]
    assert ids == ["detect-a", "detect-c", "detect-b"]


def test_list_jobs_filters_by_state_set(ledger: JobLedger) -> None:
    ledger.create_job("detect-a")
    ledger.create_job("detect-b")
    ledger.create_job("detect-c")
    ledger.mark_succeeded("detect-b", {"tracks": []})

    succeeded = ledger.list_jobs(states={"succeeded"})
    assert [row.job_id for row in succeeded] == ["detect-b"]


def test_list_jobs_empty_ledger_returns_empty_list(ledger: JobLedger) -> None:
    assert ledger.list_jobs() == []


def test_delete_job_removes_row(ledger: JobLedger) -> None:
    _make_job(ledger)
    assert ledger.delete_job("detect-abc123") is True
    assert ledger.get_job("detect-abc123") is None


def test_delete_job_missing_returns_false(ledger: JobLedger) -> None:
    assert ledger.delete_job("no-such-job") is False


def test_is_cancel_requested_defaults_to_false(ledger: JobLedger) -> None:
    _make_job(ledger)
    assert ledger.is_cancel_requested("detect-abc123") is False


def test_is_cancel_requested_reflects_flag(ledger: JobLedger) -> None:
    _make_job(ledger)
    ledger.request_cancel("detect-abc123")
    assert ledger.is_cancel_requested("detect-abc123") is True


def test_is_cancel_requested_missing_returns_false(ledger: JobLedger) -> None:
    # Worker-hot-path contract: a missing row must read as False rather than
    # raise, to tolerate read-your-own-write races with the writer.
    assert ledger.is_cancel_requested("no-such-job") is False
