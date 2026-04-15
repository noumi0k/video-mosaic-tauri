from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.detect_jobs import (
    DEFAULT_RECENT_JOB_LIMIT,
    delete_job_directory,
    generate_job_id,
    stderr_log_path,
)
from auto_mosaic.infra.ai.detect_ledger import (
    cleanup_detect_jobs,
    get_detect_job_ledger,
    row_to_status,
)
from auto_mosaic.infra.ai.model_catalog import ONNX_MAGIC_BYTES, get_model_spec_map
from auto_mosaic.runtime.paths import ensure_runtime_dirs


_HTML_SIGS = (b"<!DOCTYPE", b"<html", b"<!doctype")


def _model_name_for_backend(backend: str) -> str:
    if backend == "nudenet_640m":
        return "640m.onnx"
    if backend == "erax_v1_1":
        return "erax_nsfw_yolo11s.onnx"
    return "320n.onnx"


def _detector_backends_for_payload(payload: dict) -> list[str]:
    backend = str(payload.get("backend") or "nudenet_320n")
    if backend != "composite":
        return [backend]

    raw_categories = payload.get("enabled_label_categories")
    categories = {str(item) for item in raw_categories} if isinstance(raw_categories, list) else set()
    if not categories:
        return ["nudenet_320n"]

    backends: list[str] = []
    if "female_face" in categories or "male_face" in categories:
        backends.append("nudenet_320n")
    if "intercourse" in categories:
        backends.append("erax_v1_1")
    if "male_genitalia" in categories or "female_genitalia" in categories:
        preferred = str(payload.get("genitalia_preferred_backend") or "nudenet_320n")
        if preferred not in {"nudenet_320n", "nudenet_640m", "erax_v1_1"}:
            preferred = "nudenet_320n"
        backends.append(preferred)

    deduped: list[str] = []
    for item in backends or ["nudenet_320n"]:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _model_names_for_detect_payload(payload: dict) -> list[str]:
    return [_model_name_for_backend(backend) for backend in _detector_backends_for_payload(payload)]


def _model_integrity_status(path: Path, spec) -> str:
    """Quick pre-flight check: returns 'missing' | 'broken' | 'installed'.

    Intentionally avoids importing doctor.py to keep this module free of
    the heavier onnxruntime / gpu_diagnostics imports that doctor brings in.
    SHA-256 is checked when the catalog has a known digest, so a stale or
    corrupted detector cannot be treated as runnable just because it exists.
    """
    if not path.exists():
        return "missing"
    try:
        size = path.stat().st_size
        if size < 1024:
            return "broken"
        if spec is not None and spec.expected_size is not None and size != spec.expected_size:
            return "broken"
        header = path.read_bytes()[:16]
        if any(header.startswith(s) or header.lstrip().startswith(s) for s in _HTML_SIGS):
            return "broken"
        if spec is not None:
            magic = spec.valid_magic_bytes
        else:
            magic = ONNX_MAGIC_BYTES if path.suffix.lower() == ".onnx" else None
        if magic is not None and header[0] not in magic:
            return "broken"
        if spec is not None and spec.expected_sha256:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != spec.expected_sha256:
                return "broken"
    except OSError:
        return "broken"
    return "installed"


def _backend_root() -> Path:
    configured = os.environ.get("AUTO_MOSAIC_BACKEND_ROOT")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4]


def _spawn_detect_worker(job_id: str, payload: dict) -> int:
    backend_root = _backend_root()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(backend_root / "src"))
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    stderr_path = stderr_log_path(job_id, payload.get("paths"))
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_handle = open(stderr_path, "a", encoding="utf-8")
    try:
        creationflags = 0
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(
            [sys.executable, "-m", "auto_mosaic.api.cli_main", "run-detect-job"],
            cwd=backend_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_handle,
            creationflags=creationflags,
            **popen_kwargs,
        )
        if process.stdin is None:
            raise OSError("Worker stdin pipe was not available.")
        process.stdin.write(json.dumps({**payload, "job_id": job_id}).encode("utf-8"))
        process.stdin.close()
        return int(process.pid)
    finally:
        stderr_handle.close()


def run(payload: dict) -> dict:
    # --- Pre-flight: verify required model integrity before spawning worker ---
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)
    spec_map = get_model_spec_map()
    bad_models: list[dict[str, str]] = []
    for required_model_name in _model_names_for_detect_payload(payload):
        required_model_path = model_dir / required_model_name
        required_model_status = _model_integrity_status(required_model_path, spec_map.get(required_model_name))
        if required_model_status != "installed":
            bad_models.append(
                {
                    "model_name": required_model_name,
                    "model_path": str(required_model_path),
                    "model_status": required_model_status,
                }
            )
    if bad_models:
        first = bad_models[0]
        code = "MODEL_MISSING" if any(item["model_status"] == "missing" for item in bad_models) else "MODEL_BROKEN"
        message = (
            f"Detector model is not available: {first['model_name']}"
            if first["model_status"] == "missing"
            else f"Detector model failed integrity check: {first['model_name']}"
        )
        return failure(
            "start-detect-job",
            code,
            message,
            {
                "model_name": first["model_name"],
                "model_path": first["model_path"],
                "model_status": first["model_status"],
                "required_models": bad_models,
            },
        )

    job_id = generate_job_id()
    ledger = get_detect_job_ledger(payload.get("paths"))
    queued_row = ledger.create_job(
        job_id,
        stage="preparing",
        message="Detection job queued",
    )

    try:
        worker_pid = _spawn_detect_worker(job_id, payload)
        progressed_row = ledger.update_progress(job_id, worker_pid=worker_pid)
        cleanup_detect_jobs(
            ledger,
            retain_limit=DEFAULT_RECENT_JOB_LIMIT,
            active_job_ids={job_id},
            on_row_deleted=lambda r: delete_job_directory(r.job_id, payload.get("paths")),
        )
    except Exception as exc:
        ledger.mark_failed(
            job_id,
            {
                "code": "DETECT_JOB_START_FAILED",
                "message": str(exc),
                "details": {"job_id": job_id},
            },
        )
        return failure(
            "start-detect-job",
            "DETECT_JOB_START_FAILED",
            "Failed to start background detection worker.",
            {"job_id": job_id, "reason": str(exc)},
        )

    return success(
        "start-detect-job",
        {
            "job_id": job_id,
            "status": row_to_status(progressed_row),
        },
    )
