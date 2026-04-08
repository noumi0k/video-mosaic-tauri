from __future__ import annotations

import io
import json
import os
import sys
from contextlib import contextmanager, redirect_stdout

from auto_mosaic.runtime.bootstrap import bootstrap_backend_environment
from auto_mosaic.application.responses import failure

COMMANDS: dict[str, object] | None = None


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


def _load_commands() -> dict[str, object]:
    global COMMANDS
    if COMMANDS is not None:
        return COMMANDS

    with _json_stdout_guard():
        _configure_stdio()
        bootstrap_backend_environment()
        from auto_mosaic.api.commands import (
            cancel_export,
            cancel_detect_job,
            cancel_runtime_job,
            cleanup_detect_jobs,
            create_keyframe,
            create_project,
            create_track,
            detect_video,
            delete_keyframe,
            doctor,
            export_video,
            fetch_models,
            get_detect_result,
            get_detect_status,
            get_export_status,
            get_runtime_job_result,
            get_runtime_job_status,
            gpu_status,
            list_detect_jobs,
            load_project,
            move_keyframe,
            open_video,
            run_runtime_job,
            run_detect_job,
            save_project,
            start_detect_job,
            start_runtime_job,
            setup_environment,
            setup_erax,
            update_keyframe,
            update_track,
            video_probe,
        )

        COMMANDS = {
            "doctor": doctor.run,
            "fetch-models": fetch_models.run,
            "setup-environment": setup_environment.run,
            "setup-erax": setup_erax.run,
            "gpu-status": gpu_status.run,
            "video-probe": video_probe.run,
            "open-video": open_video.run,
            "export-video": export_video.run,
            "cancel-export": cancel_export.run,
            "cancel-detect-job": cancel_detect_job.run,
            "cancel-runtime-job": cancel_runtime_job.run,
            "cleanup-detect-jobs": cleanup_detect_jobs.run,
            "get-export-status": get_export_status.run,
            "get-detect-status": get_detect_status.run,
            "get-runtime-job-status": get_runtime_job_status.run,
            "get-runtime-job-result": get_runtime_job_result.run,
            "get-detect-result": get_detect_result.run,
            "list-detect-jobs": list_detect_jobs.run,
            "create-project": create_project.run,
            "create-track": create_track.run,
            "detect-video": detect_video.run,
            "start-detect-job": start_detect_job.run,
            "start-runtime-job": start_runtime_job.run,
            "run-runtime-job": run_runtime_job.run,
            "run-detect-job": run_detect_job.run,
            "load-project": load_project.run,
            "save-project": save_project.run,
            "create-keyframe": create_keyframe.run,
            "move-keyframe": move_keyframe.run,
            "update-keyframe": update_keyframe.run,
            "delete-keyframe": delete_keyframe.run,
            "update-track": update_track.run,
        }
    return COMMANDS


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
    commands = _load_commands()
    handler = commands.get(command)
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
