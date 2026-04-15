from __future__ import annotations

import json
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.domain.project import Keyframe, ProjectDocument, ProjectMigrationError
from auto_mosaic.runtime.file_io import atomic_write_text


def load_project_for_mutation(command: str, payload: dict) -> tuple[ProjectDocument | None, Path | None, dict | None]:
    project_path = payload.get("project_path")

    if project_path:
        # 保存済みプロジェクト: ファイルから読み込む
        path = Path(project_path)
        if not path.exists():
            return (
                None,
                None,
                failure(
                    command,
                    "PROJECT_NOT_FOUND",
                    "Project file does not exist.",
                    {"project_path": str(path)},
                ),
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return (
                None,
                None,
                failure(
                    command,
                    "PROJECT_JSON_INVALID",
                    "Project JSON is invalid.",
                    {"project_path": str(path), "reason": str(exc)},
                ),
            )

        try:
            project = ProjectDocument.from_payload({**raw, "project_path": str(path)})
        except ProjectMigrationError as exc:
            return (
                None,
                None,
                failure(
                    command,
                    exc.code,
                    exc.message,
                    {"project_path": str(path), **exc.details},
                ),
            )
        except (ValueError, KeyError) as exc:
            return (
                None,
                None,
                failure(
                    command,
                    "PROJECT_SCHEMA_INVALID",
                    "Project JSON is invalid.",
                    {"project_path": str(path), "reason": str(exc)},
                ),
            )

        issues = project.validate()
        if issues:
            return (
                None,
                None,
                failure(
                    command,
                    "PROJECT_SCHEMA_INVALID",
                    "Project JSON failed validation.",
                    {"project_path": str(path), "issues": issues},
                ),
            )

        return project, path, None

    # 未保存プロジェクト: frontend から渡されたインライン project を使う (path=None)
    inline = payload.get("project")
    if not inline:
        return None, None, failure(command, "PROJECT_PATH_REQUIRED", "project_path or project is required.")

    try:
        project = ProjectDocument.from_payload(inline)
    except ProjectMigrationError as exc:
        return None, None, failure(command, exc.code, exc.message, exc.details)
    except (ValueError, KeyError) as exc:
        return None, None, failure(command, "PROJECT_SCHEMA_INVALID", str(exc), {})

    issues = project.validate()
    if issues:
        return None, None, failure(command, "PROJECT_SCHEMA_INVALID", "Project JSON failed validation.", {"issues": issues})

    return project, None, None


def find_track(project: ProjectDocument, track_id: str):
    return next((track for track in project.tracks if track.track_id == track_id), None)


def find_keyframe(track, frame_index: int):
    return next((item for item in track.keyframes if item.frame_index == frame_index), None)


def persist_project(command: str, project: ProjectDocument, path: Path | None, selection: dict | None = None):
    project.apply_domain_rules()
    if path is not None:
        # 保存済みプロジェクト: ディスクに書き込む
        project.project_path = str(path)
        try:
            atomic_write_text(path, project.to_json(), encoding="utf-8")
        except OSError as exc:
            return failure(
                command,
                "PROJECT_SAVE_FAILED",
                "Could not save the project file.",
                {"project_path": str(path), "reason": str(exc)},
            )
    # path=None の場合はディスク書き込みをスキップ (未保存 in-memory 編集)
    return success(
        command,
        {
            "project_path": project.project_path,
            "project": project.to_dict(),
            "read_model": project.build_read_model(),
            "selection": selection
            if selection is not None
            else {"track_id": None, "frame_index": None},
        },
    )


def build_keyframe_from_payload(payload: dict) -> Keyframe:
    frame_index = int(payload["frame_index"])
    bbox = payload.get("bbox") or [0.25, 0.25, 0.2, 0.2]
    points = payload.get("points")
    if points is None:
        x, y, w, h = bbox
        points = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

    return Keyframe(
        frame_index=frame_index,
        shape_type=payload.get("shape_type", "polygon"),
        points=points,
        bbox=bbox,
        confidence=float(payload.get("confidence", 1.0)),
        source=payload.get("source", "manual"),
        rotation=float(payload.get("rotation", 0.0)),
        opacity=float(payload.get("opacity", 1.0)),
        expand_px=payload.get("expand_px"),
        feather=payload.get("feather"),
        is_locked=bool(payload.get("is_locked", False)),
    )


def validate_bbox(bbox: object) -> str | None:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return "bbox must be a list of four numbers."
    if not all(isinstance(item, (int, float)) for item in bbox):
        return "bbox must contain only numbers."
    if float(bbox[2]) <= 0 or float(bbox[3]) <= 0:
        return "bbox width and height must be greater than zero."
    return None


def validate_points(points: object) -> str | None:
    if not isinstance(points, list) or len(points) < 3:
        return "points must contain at least three points."
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            return "each point must be a two-number list."
        if not all(isinstance(item, (int, float)) for item in point):
            return "each point must contain only numbers."
    return None


def validate_shape_payload(shape_type: object, bbox: object, points: object) -> str | None:
    if shape_type not in {"polygon", "ellipse"}:
        return "shape_type must be polygon or ellipse."

    if shape_type == "ellipse":
        return validate_bbox(bbox)

    return validate_points(points)
