from __future__ import annotations

from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.domain.project import ProjectDocument, ProjectMigrationError
from auto_mosaic.runtime.file_io import atomic_write_text


def run(payload: dict) -> dict:
    project_path = payload.get("project_path")
    project_payload = payload.get("project")
    if not project_payload:
        return failure(
            "save-project",
            "PROJECT_PAYLOAD_REQUIRED",
            "project is required.",
        )

    try:
        project = ProjectDocument.from_payload(project_payload)
    except ProjectMigrationError as exc:
        return failure(
            "save-project",
            exc.code,
            exc.message,
            exc.details,
        )
    except (KeyError, ValueError) as exc:
        return failure(
            "save-project",
            "PROJECT_SCHEMA_INVALID",
            str(exc),
        )

    bytes_written: int | None = None
    persisted_path: str | None = None
    if project_path:
        # Saved project: write to disk.
        path = Path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        project.project_path = str(path)
        try:
            atomic_write_text(path, project.to_json(), encoding="utf-8")
        except OSError as exc:
            return failure(
                "save-project",
                "PROJECT_SAVE_FAILED",
                "Could not save the project file.",
                {"project_path": str(path), "reason": str(exc)},
            )
        persisted_path = str(path)
        try:
            bytes_written = path.stat().st_size
        except OSError:
            bytes_written = None
    # else: inline (unsaved) mode — no disk write; project_path stays None.

    return success(
        "save-project",
        {
            "project_path": persisted_path,
            "bytes_written": bytes_written,
            "project": project.to_dict(),
            "read_model": project.build_read_model(),
            # Conform to MutationCommandData so the frontend's applyMutationResult
            # can consume this response like other mutation results.
            "selection": {"track_id": None, "frame_index": None},
        },
    )
