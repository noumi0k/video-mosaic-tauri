"""Filesystem helpers for detect workers.

Historically this module owned the status.json / result.json / cancel.flag
split-brain that the SQLite Job Ledger now replaces (see
`docs/engineering/job-ledger-migration-plan.md`). After Phase 2-5 it keeps
only the worker stderr location — canonical job state lives in the ledger,
and `infra/ai/detect_ledger` contains the ledger-aware helpers.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from auto_mosaic.infra.ai.detect_ledger import (  # re-exports for call-site stability
    DEFAULT_RECENT_JOB_LIMIT,
    generate_job_id,
)
from auto_mosaic.runtime.paths import ensure_runtime_dirs

__all__ = [
    "DEFAULT_RECENT_JOB_LIMIT",
    "generate_job_id",
    "job_directory",
    "stderr_log_path",
    "delete_job_directory",
]


def _jobs_root(paths: dict | None = None) -> Path:
    runtime_dirs = ensure_runtime_dirs(paths)
    root = Path(runtime_dirs.temp_dir) / "detect-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_directory(job_id: str, paths: dict | None = None) -> Path:
    path = _jobs_root(paths) / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def stderr_log_path(job_id: str, paths: dict | None = None) -> Path:
    return job_directory(job_id, paths) / "stderr.log"


def delete_job_directory(job_id: str, paths: dict | None = None) -> bool:
    path = _jobs_root(paths) / job_id
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True
