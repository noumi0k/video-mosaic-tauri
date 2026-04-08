from __future__ import annotations

from typing import Callable

from auto_mosaic.api.commands import fetch_models, open_video, setup_environment, setup_erax
from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.runtime_jobs import (
    build_status,
    clear_runtime_state,
    is_cancel_requested,
    write_result,
    write_status,
)


class RuntimeJobCancelled(Exception):
    def __init__(self, message: str = "Job was cancelled.") -> None:
        super().__init__(message)


RUNNERS: dict[str, Callable[[dict], dict]] = {
    "setup_environment": setup_environment.run,
    "fetch_models": fetch_models.run,
    "open_video": open_video.run,
    "setup_erax_convert": lambda payload: setup_erax.run({**payload, "action": "convert"}),
}


def _update_status(job_id: str, job_kind: str, **kwargs: object) -> None:
    write_status(job_id, build_status(job_id=job_id, job_kind=job_kind, **kwargs))


def run(payload: dict) -> dict:
    job_id = str(payload.get("job_id") or "")
    job_kind = str(payload.get("job_kind") or "")
    runner = RUNNERS.get(job_kind)
    if not job_id:
        return failure("run-runtime-job", "JOB_ID_REQUIRED", "job_id is required.")
    if runner is None:
        return failure("run-runtime-job", "UNSUPPORTED_JOB_KIND", "Unsupported runtime job kind.", {"job_kind": job_kind})

    def progress_callback(
        *,
        state: str = "running",
        stage: str,
        message: str,
        progress_percent: float | None = None,
        is_indeterminate: bool = False,
        can_cancel: bool = True,
        current: int | None = None,
        total: int | None = None,
        artifact_path: str | None = None,
        extra: dict | None = None,
    ) -> None:
        _update_status(
            job_id,
            job_kind,
            state=state,
            stage=stage,
            message=message,
            progress_percent=progress_percent,
            is_indeterminate=is_indeterminate,
            can_cancel=can_cancel,
            current=current,
            total=total,
            artifact_path=artifact_path,
            extra=extra,
        )

    def ensure_not_cancelled(message: str = "Job was cancelled.") -> None:
        if is_cancel_requested(job_id):
            raise RuntimeJobCancelled(message)

    try:
        _update_status(
            job_id,
            job_kind,
            state="starting",
            stage="starting",
            message="Job starting.",
            progress_percent=0.0,
            is_indeterminate=True,
        )
        response = runner(
            {
                **payload,
                "_progress_callback": progress_callback,
                "_cancel_requested": lambda: is_cancel_requested(job_id),
                "_ensure_not_cancelled": ensure_not_cancelled,
            }
        )
        ensure_not_cancelled()
        if response.get("ok"):
            write_result(job_id, response)
            artifact_path = None
            data = response.get("data") or {}
            if isinstance(data, dict):
                artifact_path = data.get("project_path") or data.get("model_dir") or data.get("video", {}).get("source_path")
            _update_status(
                job_id,
                job_kind,
                state="completed",
                stage="completed",
                message="Job completed.",
                progress_percent=100.0,
                is_indeterminate=False,
                can_cancel=False,
                artifact_path=artifact_path if isinstance(artifact_path, str) else None,
                extra={"result_available": True},
            )
            return success("run-runtime-job", {"job_id": job_id})

        error = response.get("error") or {}
        _update_status(
            job_id,
            job_kind,
            state="failed",
            stage="failed",
            message=str(error.get("message") or "Job failed."),
            progress_percent=0.0,
            is_indeterminate=False,
            can_cancel=False,
            error_code=str(error.get("code") or "RUNTIME_JOB_FAILED"),
            error_message=str(error.get("message") or "Job failed."),
        )
        return failure(
            "run-runtime-job",
            str(error.get("code") or "RUNTIME_JOB_FAILED"),
            str(error.get("message") or "Job failed."),
            error.get("details"),
            response.get("warnings"),
        )
    except RuntimeJobCancelled as exc:
        _update_status(
            job_id,
            job_kind,
            state="cancelled",
            stage="cancelled",
            message=str(exc),
            progress_percent=0.0,
            is_indeterminate=False,
            can_cancel=False,
            error_code="RUNTIME_JOB_CANCELLED",
            error_message=str(exc),
        )
        return failure("run-runtime-job", "RUNTIME_JOB_CANCELLED", str(exc), {"job_id": job_id, "job_kind": job_kind})
    except fetch_models.ModelFetchCancelled as exc:
        message = "モデル取得を中断しました。"
        _update_status(
            job_id,
            job_kind,
            state="cancelled",
            stage="cancelled",
            message=message,
            progress_percent=0.0,
            is_indeterminate=False,
            can_cancel=False,
            error_code="RUNTIME_JOB_CANCELLED",
            error_message=message,
        )
        return failure("run-runtime-job", "RUNTIME_JOB_CANCELLED", message, {"job_id": job_id, "job_kind": job_kind})
    except Exception as exc:  # pragma: no cover
        _update_status(
            job_id,
            job_kind,
            state="failed",
            stage="failed",
            message=str(exc),
            progress_percent=0.0,
            is_indeterminate=False,
            can_cancel=False,
            error_code="RUNTIME_JOB_FAILED",
            error_message=str(exc),
        )
        return failure("run-runtime-job", "RUNTIME_JOB_FAILED", str(exc), {"job_id": job_id, "job_kind": job_kind})
    finally:
        clear_runtime_state(job_id)
