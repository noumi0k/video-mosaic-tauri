from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_mosaic.api.commands import load_project
from auto_mosaic.domain.project import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    Keyframe,
    MaskTrack,
    ProjectDocument,
    ProjectMigrationError,
)


def _pyside6_project_payload(*, user_locked: bool = True, manual_keyframe: bool = True) -> dict:
    keyframes = [
        {
            "frame_index": 10,
            "shape_type": "ellipse",
            "points": [],
            "bbox": [0.1, 0.2, 0.2, 0.3],
            "confidence": 0.92,
            "source": "auto",
            "contour_points": [],
            "rotation": 0.0,
            "opacity": 1.0,
            "expand_px": None,
            "feather": None,
        }
    ]
    if manual_keyframe:
        keyframes.append(
            {
                "frame_index": 15,
                "shape_type": "ellipse",
                "points": [],
                "bbox": [0.12, 0.22, 0.2, 0.3],
                "confidence": 1.0,
                "source": "manual",
                "contour_points": [],
                "rotation": 0.0,
                "opacity": 1.0,
                "expand_px": None,
                "feather": None,
            }
        )

    return {
        "project_version": 1,
        "project_id": "pyside6-project-fixture-001",
        "source_video_path": "C:\\video\\sample.mp4",
        "video_meta": {
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": 300,
            "duration_sec": 10.0,
        },
        "mask_tracks": [
            {
                "track_id": "track-auto-001",
                "label": "female_genitalia",
                "start_frame": 10,
                "end_frame": 20,
                "visible": True,
                "style": {"mosaic_strength": 20, "expand_px": 12, "feather": 0},
                "keyframes": keyframes,
                "state": "active",
                "source": "auto",
                "last_detected_frame": 20,
                "last_tracked_frame": 20,
                "missing_frame_count": 0,
                "confidence": 0.91,
                "user_locked": user_locked,
                "motion_history": [],
                "association_history": [],
            }
        ],
        "export_preset": {
            "preset_name": "high_quality_1080p_mp4",
            "container": "mp4",
            "video_codec": "h264",
            "audio_mode": "copy_if_possible",
            "mosaic_strength": 20,
            "resolution": "1080p",
            "bitrate_mode": "auto",
            "video_bitrate_kbps": 16000,
            "fps_mode": "source",
            "fps_value": 0.0,
            "use_gpu": False,
        },
    }


def _detector_track(track_id: str) -> MaskTrack:
    return MaskTrack(
        track_id=track_id,
        label="AI",
        state="detected",
        source="detector",
        visible=True,
        keyframes=[
            Keyframe(
                frame_index=10,
                shape_type="ellipse",
                points=[],
                bbox=[0.4, 0.4, 0.2, 0.2],
                confidence=0.9,
                source="detector",
            )
        ],
    )


def test_pyside6_project_v1_payload_migrates_to_tauri_schema_v2() -> None:
    project = ProjectDocument.from_payload(_pyside6_project_payload())

    assert project.schema_version == CURRENT_PROJECT_SCHEMA_VERSION
    assert project.project_id == "pyside6-project-fixture-001"
    assert project.video is not None
    assert project.video.source_path == "C:\\video\\sample.mp4"
    assert project.video.width == 1920
    assert project.export_preset == {
        "mosaic_strength": 20,
        "audio_mode": "mux_if_possible",
        "last_output_dir": None,
    }

    track = project.tracks[0]
    assert track.track_id == "track-auto-001"
    assert track.source == "manual"
    assert track.user_locked is True
    assert track.user_edited is True
    assert track.segments[0].start_frame == 10
    assert track.segments[0].end_frame == 20
    assert track.style["_pyside6_lifetime"] == {
        "start_frame": 10,
        "end_frame": 20,
        "last_detected_frame": 20,
        "last_tracked_frame": 20,
        "missing_frame_count": 0,
    }

    auto_keyframe = track.keyframes[0]
    manual_keyframe = track.keyframes[1]
    assert auto_keyframe.source == "detector"
    assert auto_keyframe.source_detail == "detector_accepted"
    assert auto_keyframe.is_locked is False
    assert manual_keyframe.source == "manual"
    assert manual_keyframe.is_locked is True


def test_load_project_command_migrates_pyside6_project_v1() -> None:
    artifact_dir = Path(__file__).resolve().parents[1] / ".pytest_cache" / "pyside6-migration"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    project_path = artifact_dir / "pyside6-project.json"
    project_path.write_text(json.dumps(_pyside6_project_payload()), encoding="utf-8")

    try:
        response = load_project.run({"project_path": str(project_path)})
    finally:
        project_path.unlink(missing_ok=True)

    assert response["ok"] is True
    assert response["data"]["project"]["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    assert response["data"]["project"]["tracks"][0]["track_id"] == "track-auto-001"
    assert response["warnings"]


def test_pyside6_asset_localhost_video_path_is_rejected() -> None:
    payload = _pyside6_project_payload()
    payload["source_video_path"] = "http://asset.localhost/H%3A%5Cvideo.mp4"

    with pytest.raises(ProjectMigrationError) as error:
        ProjectDocument.from_payload(payload)

    assert error.value.code == "SOURCE_VIDEO_PATH_INVALID"


def test_pyside6_user_locked_track_survives_detector_replacement() -> None:
    project = ProjectDocument.from_payload(_pyside6_project_payload(user_locked=True, manual_keyframe=False))

    project.replace_detector_tracks([_detector_track("new-detector-track")])

    assert [track.track_id for track in project.tracks] == ["track-auto-001", "new-detector-track"]
    assert project.tracks[0].user_edited is True
    assert project.tracks[0].source == "manual"


def test_pyside6_unedited_detector_track_remains_replaceable() -> None:
    project = ProjectDocument.from_payload(_pyside6_project_payload(user_locked=False, manual_keyframe=False))

    project.replace_detector_tracks([_detector_track("new-detector-track")])

    assert [track.track_id for track in project.tracks] == ["new-detector-track"]


def test_pyside6_predicted_tail_becomes_predicted_segment() -> None:
    payload = _pyside6_project_payload(user_locked=False, manual_keyframe=False)
    payload["mask_tracks"][0]["end_frame"] = 20
    payload["mask_tracks"][0]["last_tracked_frame"] = 24

    project = ProjectDocument.from_payload(payload)

    track = project.tracks[0]
    assert track.source == "detector"
    assert track.user_edited is False
    assert [segment.to_dict() for segment in track.segments] == [
        {"start_frame": 10, "end_frame": 20, "state": "detected"},
        {"start_frame": 21, "end_frame": 24, "state": "predicted"},
    ]

def test_user_locked_detector_track_is_not_detection_replaceable_without_user_edited() -> None:
    project = ProjectDocument.from_payload(
        {
            "project_id": "locked-detector-project",
            "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            "version": "0.1.0",
            "name": "Locked Detector",
            "project_path": None,
            "video": None,
            "tracks": [
                {
                    "track_id": "locked-detector-track",
                    "label": "AI locked",
                    "state": "detected",
                    "source": "detector",
                    "visible": True,
                    "user_locked": True,
                    "user_edited": False,
                    "keyframes": [
                        {
                            "frame_index": 10,
                            "shape_type": "ellipse",
                            "points": [],
                            "bbox": [0.2, 0.2, 0.2, 0.2],
                            "confidence": 0.8,
                            "source": "detector",
                        }
                    ],
                }
            ],
            "detector_config": {},
            "export_preset": {},
            "paths": {},
        }
    )

    project.replace_detector_tracks([_detector_track("new-detector-track")])

    assert [track.track_id for track in project.tracks] == ["locked-detector-track", "new-detector-track"]
    assert project.tracks[0].user_locked is True
    assert project.tracks[0].user_edited is False

def test_pyside6_detector_variant_sources_map_to_source_detail() -> None:
    payload = _pyside6_project_payload(user_locked=False, manual_keyframe=False)
    payload["mask_tracks"][0]["keyframes"] = [
        {
            "frame_index": 10,
            "shape_type": "ellipse",
            "points": [],
            "bbox": [0.1, 0.2, 0.2, 0.3],
            "confidence": 0.9,
            "source": "re-detected",
        },
        {
            "frame_index": 12,
            "shape_type": "ellipse",
            "points": [],
            "bbox": [0.12, 0.22, 0.2, 0.3],
            "confidence": 0.7,
            "source": "anchor_fallback",
        },
        {
            "frame_index": 14,
            "shape_type": "ellipse",
            "points": [],
            "bbox": [0.14, 0.24, 0.2, 0.3],
            "confidence": 0.6,
            "source": "predicted",
        },
    ]

    project = ProjectDocument.from_payload(payload)
    keyframes = project.tracks[0].keyframes

    assert [(keyframe.source, keyframe.source_detail) for keyframe in keyframes] == [
        ("detector", "detector_accepted"),
        ("detector", "detector_anchored"),
        ("predicted", None),
    ]