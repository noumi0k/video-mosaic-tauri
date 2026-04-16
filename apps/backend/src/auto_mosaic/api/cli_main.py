from __future__ import annotations

import io
import json
import os
import sys
from contextlib import contextmanager, redirect_stdout
from importlib import import_module
from typing import Callable

from auto_mosaic.application.responses import failure
from auto_mosaic.runtime.bootstrap import bootstrap_backend_environment

COMMAND_MODULES: dict[str, str] = {
    "doctor": "doctor",
    "fetch-models": "fetch_models",
    "setup-environment": "setup_environment",
    "setup-erax": "setup_erax",
    "gpu-status": "gpu_status",
    "video-probe": "video_probe",
    "open-video": "open_video",
    "export-video": "export_video",
    "cancel-export": "cancel_export",
    "cancel-detect-job": "cancel_detect_job",
    "cancel-runtime-job": "cancel_runtime_job",
    "cleanup-detect-jobs": "cleanup_detect_jobs",
    "get-export-status": "get_export_status",
    "get-detect-status": "get_detect_status",
    "get-runtime-job-status": "get_runtime_job_status",
    "get-runtime-job-result": "get_runtime_job_result",
    "get-detect-result": "get_detect_result",
    "list-detect-jobs": "list_detect_jobs",
    "create-project": "create_project",
    "create-track": "create_track",
    "detect-video": "detect_video",
    "start-detect-job": "start_detect_job",
    "start-runtime-job": "start_runtime_job",
    "run-runtime-job": "run_runtime_job",
    "run-detect-job": "run_detect_job",
    "load-project": "load_project",
    "save-project": "save_project",
    "create-keyframe": "create_keyframe",
    "move-keyframe": "move_keyframe",
    "update-keyframe": "update_keyframe",
    "delete-keyframe": "delete_keyframe",
    "update-track": "update_track",
    "save-recovery-snapshot": "save_recovery_snapshot",
    "list-recovery-snapshots": "list_recovery_snapshots",
    "delete-recovery-snapshot": "delete_recovery_snapshot",
}
COMMAND_HANDLERS: dict[str, Callable[[dict], dict]] = {}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            continue


def _flush_captured_stdout(captured: io.StringIO) -> None:
    leaked = captured.getvalue()
    if leaked:
        sys.stderr.write(leaked)
        sys.stderr.flush()


@contextmanager
def _redirect_native_stdout_to_stderr():
    try:
        stdout_fd = sys.__stdout__.fileno()
        stderr_fd = sys.__stderr__.fileno()
    except (AttributeError, ValueError, OSError):
        yield
        return

    try:
        saved_stdout_fd = os.dup(stdout_fd)
    except OSError:
        yield
        return

    try:
        os.dup2(stderr_fd, stdout_fd)
        yield
    finally:
        try:
            os.dup2(saved_stdout_fd, stdout_fd)
        finally:
            os.close(saved_stdout_fd)


@contextmanager
def _json_stdout_guard():
    captured_stdout = io.StringIO()
    with _redirect_native_stdout_to_stderr():
        with redirect_stdout(captured_stdout):
            try:
                yield
            finally:
                _flush_captured_stdout(captured_stdout)


def _load_command_handler(command: str) -> Callable[[dict], dict] | None:
    module_name = COMMAND_MODULES.get(command)
    if module_name is None:
        return None
    if command in COMMAND_HANDLERS:
        return COMMAND_HANDLERS[command]

    with _json_stdout_guard():
        _configure_stdio()
        bootstrap_backend_environment()
        module = import_module(f"auto_mosaic.api.commands.{module_name}")
        handler = getattr(module, "run")
        COMMAND_HANDLERS[command] = handler
        return handler


def _read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def main() -> int:
    _configure_stdio()
    if len(sys.argv) < 2:
        sys.stdout.write(
            json.dumps(
                failure("unknown", "COMMAND_REQUIRED", "A command name is required."),
                ensure_ascii=False,
            )
        )
        return 2

    command = sys.argv[1]
    handler = _load_command_handler(command)
    if handler is None:
        sys.stdout.write(
            json.dumps(
                failure(command, "UNKNOWN_COMMAND", f"Unsupported command: {command}"),
                ensure_ascii=False,
            )
        )
        return 2

    try:
        payload = _read_payload()
        with _json_stdout_guard():
            response = handler(payload)
    except json.JSONDecodeError as exc:
        response = failure(
            command,
            "INVALID_JSON",
            "Failed to decode stdin JSON payload.",
            {"reason": str(exc)},
        )
    except Exception as exc:  # pragma: no cover
        response = failure(command, "UNHANDLED_EXCEPTION", str(exc))

    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())