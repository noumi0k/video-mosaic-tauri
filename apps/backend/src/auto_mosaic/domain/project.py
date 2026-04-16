from __future__ import annotations

import json
from pathlib import PureWindowsPath
from dataclasses import asdict, dataclass, field
from typing import Any

CURRENT_PROJECT_VERSION = "0.1.0"
CURRENT_PROJECT_SCHEMA_VERSION = 2
RENDERABLE_SEGMENT_STATES = {
    "confirmed",
    "held",
    "predicted",
    "interpolated",
    "uncertain",
    "active",
    "detected",
}

DEFAULT_EXPORT_PRESET = {
    "mosaic_strength": 12,
    "audio_mode": "mux_if_possible",
    "last_output_dir": None,
}


class ProjectMigrationError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def normalize_export_preset(payload: dict | None) -> dict:
    merged = {**DEFAULT_EXPORT_PRESET, **(payload or {})}
    try:
        merged["mosaic_strength"] = int(merged.get("mosaic_strength", DEFAULT_EXPORT_PRESET["mosaic_strength"]))
    except (TypeError, ValueError):
        merged["mosaic_strength"] = DEFAULT_EXPORT_PRESET["mosaic_strength"]
    if merged["mosaic_strength"] < 2 or merged["mosaic_strength"] > 64:
        merged["mosaic_strength"] = DEFAULT_EXPORT_PRESET["mosaic_strength"]

    audio_mode = str(merged.get("audio_mode", DEFAULT_EXPORT_PRESET["audio_mode"]))
    if audio_mode not in {"mux_if_possible", "video_only"}:
        audio_mode = DEFAULT_EXPORT_PRESET["audio_mode"]
    merged["audio_mode"] = audio_mode

    last_output_dir = merged.get("last_output_dir")
    merged["last_output_dir"] = str(last_output_dir) if last_output_dir else None
    return merged


def _normalize_keyframe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    points = payload.get("points")
    if points is None:
        points = []

    bbox = payload.get("bbox")
    if bbox is None:
        bbox = [0.0, 0.0, 0.1, 0.1]

    _sd = payload.get("source_detail")
    return {
        "frame_index": int(payload["frame_index"]),
        "shape_type": str(payload.get("shape_type", "polygon")),
        "points": points,
        "bbox": bbox,
        "confidence": float(payload.get("confidence", 1.0)),
        "source": str(payload.get("source", "manual")),
        "rotation": float(payload.get("rotation", 0.0)),
        "opacity": float(payload.get("opacity", 1.0)),
        "expand_px": payload.get("expand_px"),
        "feather": payload.get("feather"),
        "is_locked": bool(payload.get("is_locked", False)),
        "contour_points": list(payload.get("contour_points") or []),
        # source_detail is optional — absent in legacy projects normalizes to None.
        "source_detail": str(_sd) if isinstance(_sd, str) and _sd else None,
    }


def _normalize_track_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_id": str(payload["track_id"]),
        "label": str(payload.get("label", payload["track_id"])),
        "state": str(payload.get("state", "active")),
        "source": str(payload.get("source", "manual")),
        "visible": bool(payload.get("visible", True)),
        "export_enabled": bool(payload.get("export_enabled", True)),
        "keyframes": [_normalize_keyframe_payload(frame) for frame in payload.get("keyframes", [])],
        "label_group": str(payload.get("label_group", "")),
        "user_locked": bool(payload.get("user_locked", False)),
        "user_edited": bool(payload.get("user_edited", False)),
        "confidence": float(payload.get("confidence", 0.0)),
        "style": dict(payload.get("style") or {}),
        "segments": list(payload.get("segments") or []),
    }


def _looks_like_url(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("asset://")
        or lowered.startswith("file://")
    )


def validate_raw_video_source_path(source_path: object) -> str:
    if not isinstance(source_path, str):
        raise ProjectMigrationError(
            "SOURCE_VIDEO_PATH_INVALID",
            "video.source_path must be a string.",
            {"source_path": source_path},
        )

    normalized = source_path.strip()
    if not normalized:
        raise ProjectMigrationError(
            "SOURCE_VIDEO_PATH_INVALID",
            "video.source_path must not be empty.",
            {"source_path": source_path},
        )

    lowered = normalized.lower()
    if (
        "asset.localhost" in lowered
        or lowered.startswith("asset://localhost")
        or _looks_like_url(normalized)
    ):
        raise ProjectMigrationError(
            "SOURCE_VIDEO_PATH_INVALID",
            "video.source_path must be a raw local file path, not a display URL.",
            {"source_path": source_path},
        )

    windows_path = PureWindowsPath(normalized)
    if windows_path.drive or windows_path.anchor.startswith("\\\\"):
        return normalized

    raise ProjectMigrationError(
        "SOURCE_VIDEO_PATH_INVALID",
        "video.source_path must be an absolute local Windows path.",
        {"source_path": source_path},
    )


def _is_pyside6_project_v1_payload(payload: dict[str, Any]) -> bool:
    return (
        "project_version" in payload
        and "mask_tracks" in payload
        and "source_video_path" in payload
        and "video_meta" in payload
    )


def _coerce_pyside6_int(value: object, *, field: str, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ProjectMigrationError(
            "PYSIDE6_PROJECT_SCHEMA_INVALID",
            "PySide6 project contains an invalid integer value.",
            {"field": field, "value": value, "reason": str(exc)},
        ) from exc


def _coerce_pyside6_float(value: object, *, field: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ProjectMigrationError(
            "PYSIDE6_PROJECT_SCHEMA_INVALID",
            "PySide6 project contains an invalid numeric value.",
            {"field": field, "value": value, "reason": str(exc)},
        ) from exc


def _map_pyside6_keyframe_source(source: object) -> tuple[str, str | None, bool]:
    normalized = str(source or "auto")
    if normalized == "manual":
        return "manual", None, True
    if normalized == "anchor_fallback":
        return "detector", "detector_anchored", False
    if normalized in {"auto", "re-detected"}:
        return "detector", "detector_accepted", False
    if normalized in {"interpolated", "predicted"}:
        return normalized, None, False
    return normalized, None, False


def _map_pyside6_track_source(source: object, *, user_edited: bool) -> str:
    normalized = str(source or "auto")
    if user_edited:
        return "manual"
    if normalized in {"auto", "re-detected"}:
        return "detector"
    if normalized == "user-adjusted":
        return "manual"
    return normalized


def _migrate_pyside6_video_payload(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("video_meta")
    if not isinstance(meta, dict):
        raise ProjectMigrationError(
            "PYSIDE6_PROJECT_SCHEMA_INVALID",
            "PySide6 project video_meta must be an object.",
            {"video_meta": meta},
        )
    return {
        "source_path": validate_raw_video_source_path(payload.get("source_video_path")),
        "width": _coerce_pyside6_int(meta.get("width"), field="video_meta.width"),
        "height": _coerce_pyside6_int(meta.get("height"), field="video_meta.height"),
        "fps": _coerce_pyside6_float(meta.get("fps"), field="video_meta.fps"),
        "frame_count": _coerce_pyside6_int(meta.get("frame_count"), field="video_meta.frame_count"),
        "duration_sec": _coerce_pyside6_float(meta.get("duration_sec"), field="video_meta.duration_sec"),
        "readable": True,
        "warnings": [],
        "errors": [],
        "first_frame_shape": None,
    }


def _migrate_pyside6_keyframe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source, source_detail, is_locked = _map_pyside6_keyframe_source(payload.get("source"))
    return {
        "frame_index": _coerce_pyside6_int(payload.get("frame_index"), field="keyframes.frame_index"),
        "shape_type": str(payload.get("shape_type", "ellipse")),
        "points": list(payload.get("points") or []),
        "bbox": list(payload.get("bbox") or [0.0, 0.0, 0.1, 0.1]),
        "confidence": _coerce_pyside6_float(payload.get("confidence", 1.0), field="keyframes.confidence"),
        "source": source,
        "rotation": _coerce_pyside6_float(payload.get("rotation", 0.0), field="keyframes.rotation", default=0.0),
        "opacity": _coerce_pyside6_float(payload.get("opacity", 1.0), field="keyframes.opacity", default=1.0),
        "expand_px": payload.get("expand_px"),
        "feather": payload.get("feather"),
        "is_locked": is_locked,
        "contour_points": list(payload.get("contour_points") or []),
        "source_detail": source_detail,
    }


def _migrate_pyside6_segments(
    *,
    start_frame: int,
    end_frame: int,
    last_tracked_frame: int,
    user_edited: bool,
    has_keyframes: bool,
) -> list[dict[str, Any]]:
    if not has_keyframes or end_frame < start_frame:
        return []

    detected_state = "confirmed" if user_edited else "detected"
    segments: list[dict[str, Any]] = [
        {"start_frame": start_frame, "end_frame": end_frame, "state": detected_state}
    ]
    if last_tracked_frame > end_frame:
        segments.append(
            {"start_frame": end_frame + 1, "end_frame": last_tracked_frame, "state": "predicted"}
        )
    return segments


def _migrate_pyside6_track_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keyframes = [
        _migrate_pyside6_keyframe_payload(item)
        for item in payload.get("keyframes", [])
        if isinstance(item, dict)
    ]
    user_locked = bool(payload.get("user_locked", False))
    has_manual_keyframe = any(keyframe["source"] == "manual" for keyframe in keyframes)
    source = str(payload.get("source", "auto"))
    user_edited = user_locked or has_manual_keyframe or source == "user-adjusted"
    start_frame = _coerce_pyside6_int(payload.get("start_frame"), field="tracks.start_frame", default=0)
    end_frame = _coerce_pyside6_int(payload.get("end_frame"), field="tracks.end_frame", default=start_frame)
    last_tracked_frame = _coerce_pyside6_int(
        payload.get("last_tracked_frame"),
        field="tracks.last_tracked_frame",
        default=-1,
    )
    style = dict(payload.get("style") or {})
    style["_pyside6_lifetime"] = {
        "start_frame": start_frame,
        "end_frame": end_frame,
        "last_detected_frame": _coerce_pyside6_int(
            payload.get("last_detected_frame"),
            field="tracks.last_detected_frame",
            default=-1,
        ),
        "last_tracked_frame": last_tracked_frame,
        "missing_frame_count": _coerce_pyside6_int(
            payload.get("missing_frame_count"),
            field="tracks.missing_frame_count",
            default=0,
        ),
    }
    segments = _migrate_pyside6_segments(
        start_frame=start_frame,
        end_frame=end_frame,
        last_tracked_frame=last_tracked_frame,
        user_edited=user_edited,
        has_keyframes=bool(keyframes),
    )
    return {
        "track_id": str(payload["track_id"]),
        "label": str(payload.get("label", payload["track_id"])),
        "state": str(payload.get("state", "active")),
        "source": _map_pyside6_track_source(source, user_edited=user_edited),
        "visible": bool(payload.get("visible", True)),
        "export_enabled": bool(payload.get("export_enabled", True)),
        "keyframes": keyframes,
        "label_group": str(payload.get("label_group", "")),
        "user_locked": user_locked,
        "user_edited": user_edited,
        "confidence": _coerce_pyside6_float(payload.get("confidence", 0.0), field="tracks.confidence", default=0.0),
        "style": style,
        "segments": segments,
    }


def _migrate_pyside6_export_preset(payload: object) -> dict[str, Any]:
    preset = dict(payload) if isinstance(payload, dict) else {}
    audio_mode = str(preset.get("audio_mode", "copy_if_possible"))
    return normalize_export_preset(
        {
            "mosaic_strength": preset.get("mosaic_strength", DEFAULT_EXPORT_PRESET["mosaic_strength"]),
            "audio_mode": "video_only" if audio_mode in {"video_only", "none"} else "mux_if_possible",
            "last_output_dir": preset.get("last_output_dir"),
        }
    )


def _migrate_pyside6_project_v1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    version = _coerce_pyside6_int(payload.get("project_version"), field="project_version")
    if version != 1:
        raise ProjectMigrationError(
            "PYSIDE6_PROJECT_VERSION_UNSUPPORTED",
            "Only PySide6 project_version 1 can be migrated.",
            {"project_version": version},
        )
    return {
        "project_id": str(payload["project_id"]),
        "version": str(payload.get("version", CURRENT_PROJECT_VERSION)),
        "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "name": str(payload.get("name") or payload.get("project_id") or "PySide6 Project"),
        "project_path": payload.get("project_path"),
        "video": _migrate_pyside6_video_payload(payload),
        "tracks": [
            _migrate_pyside6_track_payload(track)
            for track in payload.get("mask_tracks", [])
            if isinstance(track, dict)
        ],
        "detector_config": dict(payload.get("detector_config") or {}),
        "export_preset": _migrate_pyside6_export_preset(payload.get("export_preset")),
        "paths": dict(payload.get("paths") or {}),
    }


def _parse_schema_version(payload: dict[str, Any]) -> int:
    raw_value = payload.get("schema_version", 1)
    if isinstance(raw_value, bool):
        raise ProjectMigrationError(
            "PROJECT_SCHEMA_VERSION_INVALID",
            "schema_version must be an integer.",
            {"schema_version": raw_value},
        )
    try:
        schema_version = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ProjectMigrationError(
            "PROJECT_SCHEMA_VERSION_INVALID",
            "schema_version must be an integer.",
            {"schema_version": raw_value, "reason": str(exc)},
        ) from exc

    if schema_version < 1:
        raise ProjectMigrationError(
            "PROJECT_SCHEMA_VERSION_INVALID",
            "schema_version must be greater than or equal to 1.",
            {"schema_version": schema_version},
        )

    if schema_version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise ProjectMigrationError(
            "PROJECT_SCHEMA_VERSION_UNSUPPORTED",
            "schema_version is newer than this build can load.",
            {
                "schema_version": schema_version,
                "supported_schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            },
        )

    return schema_version


def migrate_project_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    migrated = dict(payload)
    if _is_pyside6_project_v1_payload(migrated):
        return _migrate_pyside6_project_v1_payload(migrated), 1

    schema_version = _parse_schema_version(migrated)
    original_schema_version = schema_version

    if schema_version < 2:
        migrated["version"] = str(migrated.get("version", CURRENT_PROJECT_VERSION))
        migrated["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION
        migrated["detector_config"] = migrated.get("detector_config", {})
        migrated["export_preset"] = normalize_export_preset(migrated.get("export_preset"))
        migrated["paths"] = migrated.get("paths", {})
        migrated["tracks"] = [_normalize_track_payload(track) for track in migrated.get("tracks", [])]
        schema_version = CURRENT_PROJECT_SCHEMA_VERSION
    else:
        migrated["version"] = str(migrated.get("version", CURRENT_PROJECT_VERSION))
        migrated["schema_version"] = int(migrated.get("schema_version", CURRENT_PROJECT_SCHEMA_VERSION))
        migrated["export_preset"] = normalize_export_preset(migrated.get("export_preset"))
        migrated["tracks"] = [_normalize_track_payload(track) for track in migrated.get("tracks", [])]
        migrated["detector_config"] = migrated.get("detector_config", {})
        migrated["paths"] = migrated.get("paths", {})

    return migrated, original_schema_version


@dataclass
class VideoMetadata:
    source_path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float
    readable: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    first_frame_shape: list[int] | None = None

    @classmethod
    def from_payload(cls, payload: dict | None) -> "VideoMetadata | None":
        if payload is None:
            return None
        return cls(
            source_path=validate_raw_video_source_path(payload["source_path"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
            fps=float(payload["fps"]),
            frame_count=int(payload["frame_count"]),
            duration_sec=float(payload["duration_sec"]),
            readable=bool(payload["readable"]),
            warnings=list(payload.get("warnings", [])),
            errors=list(payload.get("errors", [])),
            first_frame_shape=payload.get("first_frame_shape"),
        )


@dataclass
class Keyframe:
    frame_index: int
    shape_type: str
    points: list[list[float]]
    bbox: list[float]
    confidence: float
    source: str
    rotation: float = 0.0
    opacity: float = 1.0
    expand_px: int | None = None
    feather: int | None = None
    is_locked: bool = False
    contour_points: list[list[float]] = field(default_factory=list)
    source_detail: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Keyframe":
        return cls(**_normalize_keyframe_payload(payload))


@dataclass
class MaskSegment:
    start_frame: int
    end_frame: int
    state: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MaskSegment | None":
        try:
            start_frame = int(payload["start_frame"])
            end_frame = int(payload["end_frame"])
        except (KeyError, TypeError, ValueError):
            return None
        if end_frame < start_frame:
            return None
        return cls(
            start_frame=start_frame,
            end_frame=end_frame,
            state=str(payload.get("state", "confirmed")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def contains(self, frame_index: int) -> bool:
        return self.start_frame <= frame_index <= self.end_frame

    def is_renderable(self) -> bool:
        return self.state in RENDERABLE_SEGMENT_STATES


@dataclass
class MaskTrack:
    track_id: str
    label: str
    state: str
    source: str
    visible: bool = True
    export_enabled: bool = True
    keyframes: list[Keyframe] = field(default_factory=list)
    label_group: str = ""
    user_locked: bool = False
    user_edited: bool = False
    confidence: float = 0.0
    style: dict = field(default_factory=dict)
    segments: list[MaskSegment] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.apply_domain_rules()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "MaskTrack":
        normalized = _normalize_track_payload(payload)
        return cls(
            track_id=normalized["track_id"],
            label=normalized["label"],
            state=normalized["state"],
            source=normalized["source"],
            visible=normalized["visible"],
            export_enabled=normalized["export_enabled"],
            keyframes=[Keyframe.from_payload(frame) for frame in normalized["keyframes"]],
            label_group=normalized["label_group"],
            user_locked=normalized["user_locked"],
            user_edited=normalized["user_edited"],
            confidence=normalized["confidence"],
            style=normalized["style"],
            segments=[
                segment
                for segment in (
                    MaskSegment.from_payload(item) for item in normalized["segments"]
                )
                if segment is not None
            ],
        )

    def apply_domain_rules(self) -> None:
        self.keyframes.sort(key=lambda item: item.frame_index)
        self.segments.sort(key=lambda item: (item.start_frame, item.end_frame))
        if self.user_edited or any(keyframe.source == "manual" for keyframe in self.keyframes):
            self.user_edited = True
            if self.source == "detector":
                self.source = "manual"

    def mark_user_edited(self, keyframe: Keyframe | None = None) -> None:
        self.user_edited = True
        if self.source == "detector":
            self.source = "manual"
        if keyframe is not None and keyframe.source == "detector":
            keyframe.source = "manual"
        self.apply_domain_rules()

    def set_source(self, source: str) -> None:
        self.source = source
        self.apply_domain_rules()

    def set_user_edited(self, value: bool) -> None:
        self.user_edited = self.user_edited or bool(value)
        self.apply_domain_rules()

    def is_detection_replaceable(self) -> bool:
        return self.source == "detector" and not self.user_edited and not self.user_locked

    def render_segments(self) -> list[MaskSegment]:
        explicit_segments = [segment for segment in self.segments if segment.is_renderable()]
        if explicit_segments:
            if self.keyframes and any(segment.state in {"held", "uncertain"} for segment in explicit_segments):
                first_frame = self.keyframes[0].frame_index
                last_frame = self.keyframes[-1].frame_index
                keyframe_span_is_covered = any(
                    segment.start_frame <= first_frame and segment.end_frame >= last_frame
                    for segment in explicit_segments
                )
                if not keyframe_span_is_covered:
                    # held/uncertain segments are detection-continuity metadata. They
                    # must not become the only renderable range and hide accepted
                    # keyframes during export.
                    state = "confirmed" if any(kf.source == "manual" for kf in self.keyframes) else "detected"
                    return sorted(
                        [
                            *explicit_segments,
                            MaskSegment(start_frame=first_frame, end_frame=last_frame, state=state),
                        ],
                        key=lambda item: (item.start_frame, item.end_frame),
                    )
            return explicit_segments
        if not self.keyframes:
            return []
        # Synthesise a single span covering all keyframes.
        # Frames between keyframes are renderable (hold-then-interpolate semantics).
        # Frames beyond the last keyframe are NOT included here; the export pipeline
        # therefore stops applying mosaic after the last keyframe unless explicit
        # segments extend further.
        first_frame = self.keyframes[0].frame_index
        last_frame = self.keyframes[-1].frame_index
        state = "confirmed" if any(kf.source == "manual" for kf in self.keyframes) else "detected"
        return [MaskSegment(start_frame=first_frame, end_frame=last_frame, state=state)]

    def frame_is_renderable(self, frame_index: int) -> bool:
        return any(segment.contains(frame_index) for segment in self.render_segments())

    def resolve_active_keyframe(self, frame_index: int) -> Keyframe | None:
        """Return the active keyframe within the track's renderable span.

        Used by the export pipeline: returns None for frames outside the
        renderable span so that mosaic is not applied beyond the track boundary.
        For editing beyond the last detected frame, use resolve_shape_for_editing.
        """
        if not self.frame_is_renderable(frame_index):
            return None

        active: Keyframe | None = None
        for keyframe in self.keyframes:
            if keyframe.frame_index > frame_index:
                break
            active = keyframe
        return active

    def resolve_shape_for_editing(self, frame_index: int) -> Keyframe | None:
        """Return the shape to display or edit at frame_index.

        Unlike resolve_active_keyframe this is not gated by frame_is_renderable,
        so it works beyond the last detected frame (held editing).

        Returns None only when the track has no keyframes, or when frame_index
        is before the track's first keyframe (track has not started yet).
        Otherwise returns the most recent keyframe at or before frame_index.
        """
        if not self.keyframes:
            return None
        if frame_index < self.keyframes[0].frame_index:
            return None
        active: Keyframe | None = None
        for keyframe in self.keyframes:
            if keyframe.frame_index > frame_index:
                break
            active = keyframe
        return active


@dataclass
class ProjectPaths:
    project_dir: str | None = None
    export_dir: str | None = None
    training_dir: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> "ProjectPaths":
        return cls(
            project_dir=payload.get("project_dir"),
            export_dir=payload.get("export_dir"),
            training_dir=payload.get("training_dir"),
        )


def _bbox_iou(a: list[float], b: list[float]) -> float:
    """Simple IoU for [x, y, w, h] bboxes."""
    if len(a) < 4 or len(b) < 4:
        return 0.0
    ax1, ay1, aw, ah = a[0], a[1], a[2], a[3]
    bx1, by1, bw, bh = b[0], b[1], b[2], b[3]
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax1 + aw, bx1 + bw)
    iy2 = min(ay1 + ah, by1 + bh)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(aw, 0) * max(ah, 0)
    area_b = max(bw, 0) * max(bh, 0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class ProjectDocument:
    project_id: str
    version: str
    schema_version: int
    name: str
    project_path: str | None
    video: VideoMetadata | None
    tracks: list[MaskTrack]
    detector_config: dict
    export_preset: dict
    paths: ProjectPaths

    def to_dict(self) -> dict:
        self.apply_domain_rules()
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def build_read_model(self) -> dict:
        self.apply_domain_rules()
        track_summaries = []
        for index, track in enumerate(self.tracks):
            frame_indexes = sorted(frame.frame_index for frame in track.keyframes)
            track_summaries.append(
                {
                    "index": index,
                    "track_id": track.track_id,
                    "label": track.label,
                    "visible": track.visible,
                    "export_enabled": track.export_enabled,
                    "state": track.state,
                    "source": track.source,
                    "start_frame": frame_indexes[0] if frame_indexes else None,
                    "end_frame": frame_indexes[-1] if frame_indexes else None,
                    "keyframe_count": len(track.keyframes),
                    "label_group": track.label_group,
                    "user_locked": track.user_locked,
                    "user_edited": track.user_edited,
                    "confidence": track.confidence,
                    "keyframes": [
                        {
                            "frame_index": frame.frame_index,
                            "source": frame.source,
                            "shape_type": frame.shape_type,
                        }
                        for frame in sorted(track.keyframes, key=lambda item: item.frame_index)
                    ],
                }
            )

        return {
            "project_id": self.project_id,
            "project_name": self.name,
            "project_path": self.project_path,
            "video": asdict(self.video) if self.video else None,
            "track_summaries": track_summaries,
            "track_count": len(track_summaries),
        }

    def validate(self) -> list[str]:
        issues: list[str] = []
        self.apply_domain_rules()
        if not self.project_id:
            issues.append("project_id is required.")
        if not self.version:
            issues.append("version is required.")
        if self.schema_version != CURRENT_PROJECT_SCHEMA_VERSION:
            issues.append(f"schema_version must be {CURRENT_PROJECT_SCHEMA_VERSION}.")
        if not self.name:
            issues.append("name is required.")
        return issues

    def apply_domain_rules(self) -> None:
        for track in self.tracks:
            track.apply_domain_rules()

    def replace_detector_tracks(self, detection_tracks: list[MaskTrack]) -> None:
        self.apply_domain_rules()
        self.tracks = [
            track for track in self.tracks if not track.is_detection_replaceable()
        ] + detection_tracks

    def merge_range_detection_tracks(
        self,
        detection_tracks: list[MaskTrack],
        start_frame: int,
        end_frame: int,
        iou_threshold: float = 0.1,
    ) -> None:
        """Merge range-detection results into existing tracks using IoU matching.

        For each new detection track, find the best matching existing track by
        label + IoU.  If matched, replace only keyframes within [start_frame,
        end_frame] while preserving manual keyframes.  Unmatched detection
        tracks are added as new tracks.
        """
        self.apply_domain_rules()
        used_existing: set[str] = set()

        for det_track in detection_tracks:
            best_match: MaskTrack | None = None
            best_iou = iou_threshold
            det_bbox = det_track.keyframes[0].bbox if det_track.keyframes else []

            for existing in self.tracks:
                if existing.track_id in used_existing:
                    continue
                # Find an existing keyframe near the detection range for IoU
                ref_kf = None
                for kf in existing.keyframes:
                    if start_frame <= kf.frame_index <= end_frame:
                        ref_kf = kf
                        break
                if ref_kf is None:
                    continue
                if not det_bbox or not ref_kf.bbox:
                    continue
                iou = _bbox_iou(det_bbox, ref_kf.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_match = existing

            if best_match is not None:
                used_existing.add(best_match.track_id)
                # Keep keyframes outside the range and manual keyframes inside.
                kept = [
                    kf for kf in best_match.keyframes
                    if kf.frame_index < start_frame
                    or kf.frame_index > end_frame
                    or kf.source == "manual"
                ]
                # Add new detection keyframes within the range.
                new_kfs = [
                    kf for kf in det_track.keyframes
                    if start_frame <= kf.frame_index <= end_frame
                    # Don't overwrite manual keyframes.
                    and not any(
                        k.frame_index == kf.frame_index and k.source == "manual"
                        for k in kept
                    )
                ]
                best_match.keyframes = kept + new_kfs
                best_match.keyframes.sort(key=lambda k: k.frame_index)
                best_match.apply_domain_rules()
            else:
                self.tracks.append(det_track)

        self.apply_domain_rules()

    @classmethod
    def from_payload(cls, payload: dict) -> "ProjectDocument":
        migrated, _ = migrate_project_payload(payload)
        tracks = [MaskTrack.from_payload(item) for item in migrated.get("tracks", [])]
        project = cls(
            project_id=migrated["project_id"],
            version=migrated["version"],
            schema_version=migrated["schema_version"],
            name=migrated["name"],
            project_path=migrated.get("project_path"),
            video=VideoMetadata.from_payload(migrated.get("video")),
            tracks=tracks,
            detector_config=migrated.get("detector_config", {}),
            export_preset=normalize_export_preset(migrated.get("export_preset")),
            paths=ProjectPaths.from_payload(migrated.get("paths", {})),
        )
        project.apply_domain_rules()
        return project
