from __future__ import annotations

import json
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.domain.project import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    ProjectDocument,
    ProjectMigrationError,
    migrate_project_payload,
)


def run(payload: dict) -> dict:
    project_path = payload.get("project_path")
    if not project_path:
        return failure("load-project", "PROJECT_PATH_REQUIRED", "project_path is required.")

    path = Path(project_path)
    if not path.exists():
        return failure(
            "load-project",
            "PROJECT_NOT_FOUND",
            "Project file does not exist.",
            {"project_path": str(path)},
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return failure(
            "load-project",
            "PROJECT_JSON_INVALID",
            "Project JSON is invalid.",
            {"project_path": str(path), "reason": str(exc)},
        )

    try:
        migrated_raw, original_schema_version = migrate_project_payload({**raw, "project_path": str(path)})
    except ProjectMigrationError as exc:
        return failure(
            "load-project",
            exc.code,
            exc.message,
            {"project_path": str(path), **exc.details},
        )
    try:
        project = ProjectDocument.from_payload(migrated_raw)
    except ProjectMigrationError as exc:
        return failure(
            "load-project",
            exc.code,
            exc.message,
            {"project_path": str(path), **exc.details},
        )
    except ValueError as exc:
        return failure(
            "load-project",
            "PROJECT_SCHEMA_INVALID",
            "Project JSON contains invalid values.",
            {"project_path": str(path), "reason": str(exc)},
        )
    except KeyError as exc:
        return failure(
            "load-project",
            "PROJECT_SCHEMA_INVALID",
            "Project JSON is missing required fields.",
            {"project_path": str(path), "missing_field": str(exc)},
        )

    issues = project.validate()
    if issues:
        return failure(
            "load-project",
            "PROJECT_SCHEMA_INVALID",
            "Project JSON failed validation.",
            {"project_path": str(path), "issues": issues},
        )

    warnings: list[str] = []
    if original_schema_version != CURRENT_PROJECT_SCHEMA_VERSION:
        warnings.append(
            f"Project schema was migrated from {original_schema_version} to {CURRENT_PROJECT_SCHEMA_VERSION} during load."
        )

    return success(
        "load-project",
        {
            "project": project.to_dict(),
            "read_model": project.build_read_model(),
        },
        warnings,
    )
