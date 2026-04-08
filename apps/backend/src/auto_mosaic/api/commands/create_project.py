from __future__ import annotations

import uuid

from auto_mosaic.application.responses import success
from auto_mosaic.domain.project import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    CURRENT_PROJECT_VERSION,
    ProjectDocument,
    ProjectPaths,
    VideoMetadata,
    normalize_export_preset,
)


def run(payload: dict) -> dict:
    tracks = []
    for item in payload.get("tracks", []):
        track_document = ProjectDocument.from_payload(
            {
                "project_id": payload.get("project_id", "project-preview"),
                "version": CURRENT_PROJECT_VERSION,
                "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
                "name": payload.get("name", "Untitled Project"),
                "project_path": payload.get("project_path"),
                "video": payload.get("video"),
                "tracks": [item],
                "detector_config": payload.get("detector_config", {}),
                "export_preset": normalize_export_preset(payload.get("export_preset")),
                "paths": payload.get("paths", {}),
            }
        )
        tracks.extend(track_document.tracks)

    project = ProjectDocument(
        project_id=payload.get("project_id", f"project-{uuid.uuid4()}"),
        version=CURRENT_PROJECT_VERSION,
        schema_version=CURRENT_PROJECT_SCHEMA_VERSION,
        name=payload.get("name", "Untitled Project"),
        project_path=payload.get("project_path"),
        video=VideoMetadata.from_payload(payload.get("video")),
        tracks=tracks,
        detector_config=payload.get("detector_config", {}),
        export_preset=normalize_export_preset(payload.get("export_preset")),
        paths=ProjectPaths.from_payload(payload.get("paths", {})),
    )
    return success(
        "create-project",
        {
            "project": project.to_dict(),
            "read_model": project.build_read_model(),
        },
    )
