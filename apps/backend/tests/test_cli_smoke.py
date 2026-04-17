from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from auto_mosaic.api.commands import (
    cancel_detect_job,
    cleanup_detect_jobs,
    cancel_export,
    cancel_runtime_job,
    clear_terminal_export_queue,
    create_keyframe,
    create_project,
    create_track,
    delete_recovery_snapshot,
    detect_video,
    delete_keyframe,
    enqueue_export,
    export_video,
    fetch_models,
    get_detect_result,
    get_detect_status,
    get_export_status,
    get_runtime_job_result,
    get_runtime_job_status,
    list_detect_jobs,
    list_export_queue,
    list_recovery_snapshots,
    load_project,
    move_keyframe,
    open_video,
    remove_export_queue_item,
    save_project,
    save_recovery_snapshot,
    start_detect_job,
    start_runtime_job,
    update_export_queue_item,
    update_keyframe,
    update_track,
)
from auto_mosaic.api.commands import doctor
from auto_mosaic.api.commands import run_detect_job
from auto_mosaic.api.commands import run_runtime_job
from auto_mosaic.domain.project import CURRENT_PROJECT_SCHEMA_VERSION, ProjectDocument
from auto_mosaic.domain.project import Keyframe, MaskTrack
from auto_mosaic.infra.ai import detect_video as detect_video_infra
from auto_mosaic.infra.ai.detect_ledger import get_detect_job_ledger
from auto_mosaic.infra.video import export as export_infra
from auto_mosaic.infra.video.export import export_project_video
from auto_mosaic.infra.video import export_jobs
from auto_mosaic.runtime.external_tools import resolve_external_tool


TEST_ROOT = Path(tempfile.mkdtemp(prefix="taurimozaic-test-artifacts-"))
TEST_ROOT.mkdir(parents=True, exist_ok=True)


def _require_media_tool(tool_name: str) -> str:
    resolved = resolve_external_tool(tool_name)
    if not resolved["found"] or not resolved["path"]:
        pytest.skip(f"{tool_name} is not available in this environment.")
    return str(resolved["path"])


def _make_sample_video(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (160, 90))
    for frame_index in range(8):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        for y in range(90):
            for x in range(160):
                frame[y, x, 0] = (x * 3 + frame_index * 7) % 256
                frame[y, x, 1] = (y * 5 + frame_index * 11) % 256
                frame[y, x, 2] = ((x + y) * 2 + frame_index * 13) % 256
        writer.write(frame)
    writer.release()


def _make_sample_video_with_audio(path: Path) -> None:
    ffmpeg = _require_media_tool("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=160x90:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=660:sample_rate=44100",
        "-t",
        "0.5",
        "-c:v",
        "mpeg4",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not path.exists():
        raise AssertionError(f"Failed to create audio fixture: {completed.stderr}")


def _probe_stream_types(path: Path) -> list[str]:
    ffprobe = _require_media_tool("ffprobe")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise AssertionError(f"ffprobe failed: {completed.stderr}")
    payload = json.loads(completed.stdout)
    return [stream.get("codec_type", "") for stream in payload.get("streams", [])]


def _asset_localhost_path() -> str:
    return "http://asset.localhost/H%3A%5Cvideo.mp4"


def _project_payload_with_video(source_path: str) -> dict:
    return {
        "project_id": "project-invalid-path",
        "version": "0.1.0",
        "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "name": "InvalidPathProject",
        "project_path": None,
        "video": {
            "source_path": source_path,
            "width": 160,
            "height": 90,
            "fps": 24.0,
            "frame_count": 8,
            "duration_sec": 8 / 24.0,
            "readable": True,
            "warnings": [],
            "errors": [],
            "first_frame_shape": [90, 160, 3],
        },
        "tracks": [],
        "detector_config": {},
        "export_preset": {
            "mosaic_strength": 12,
            "audio_mode": "video_only",
            "last_output_dir": None,
        },
        "paths": {},
    }


def _run_cli_command(command: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "auto_mosaic.api.cli_main", command],
        input=json.dumps(payload),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_create_project_smoke():
    response = create_project.run({"name": "Smoke"})
    assert response["ok"] is True
    assert response["data"]["project"]["name"] == "Smoke"
    assert response["data"]["project"]["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    assert response["data"]["project"]["export_preset"] == {
        "mosaic_strength": 12,
        "audio_mode": "mux_if_possible",
        "last_output_dir": None,
    }


def test_resolve_external_tool_prefers_explicit_path():
    fake = TEST_ROOT / "ffmpeg.exe"
    fake.write_text("stub", encoding="utf-8")
    result = resolve_external_tool("ffmpeg", str(fake))
    assert result["found"] is True
    assert result["path"] == str(fake)


def test_doctor_finds_local_ffmpeg_tools():
    ffmpeg = TEST_ROOT / "ffmpeg.cmd"
    ffprobe = TEST_ROOT / "ffprobe.cmd"
    ffmpeg.write_text("@echo off\r\necho ffmpeg\r\n", encoding="utf-8")
    ffprobe.write_text("@echo off\r\necho ffprobe\r\n", encoding="utf-8")
    response = doctor.run({"ffmpeg_path": str(ffmpeg), "ffprobe_path": str(ffprobe)})
    assert response["ok"] is True
    assert response["data"]["ffmpeg"]["found"] is True
    assert response["data"]["ffprobe"]["found"] is True
    assert response["data"]["runtime"]["project_dir"]["writable"] is True
    assert response["data"]["runtime"]["export_job_dir"]["writable"] is True
    assert "ffmpeg was not found" not in " ".join(response["warnings"])


def test_fetch_models_downloads_missing_file(monkeypatch):
    model_root = TEST_ROOT / "fetched-models"
    payload_paths = {"model_dir": str(model_root)}

    def fake_download(url: str, target_path: Path, **_kwargs) -> int:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a minimal valid-looking ONNX file (starts with 0x08, size >= 1024).
        data = bytes([0x08]) + b"\x00" * 2047
        target_path.write_bytes(data)
        return len(data)

    monkeypatch.setattr("auto_mosaic.api.commands.fetch_models._download_to_path", fake_download)

    response = fetch_models.run({"model_names": ["320n.onnx"], "paths": payload_paths})
    assert response["ok"] is True
    assert response["data"]["downloaded"] == 1
    assert response["data"]["results"][0]["status"] == "downloaded"
    assert (model_root / "320n.onnx").exists() is True


def test_fetch_models_skips_existing_file():
    model_root = TEST_ROOT / "existing-models"
    model_root.mkdir(parents=True, exist_ok=True)
    # Use 640m.onnx which has no expected_size / expected_sha256 in its spec,
    # so a valid-magic 2 KB file passes the integrity check.
    existing = model_root / "640m.onnx"
    existing.write_bytes(bytes([0x08]) + b"\x00" * 2047)

    response = fetch_models.run({"model_names": ["640m.onnx"], "paths": {"model_dir": str(model_root)}})
    assert response["ok"] is True
    assert response["data"]["downloaded"] == 0
    assert response["data"]["skipped"] == 1
    assert response["data"]["results"][0]["status"] == "skipped"


def test_start_runtime_fetch_models_job_transitions_to_completed(monkeypatch):
    model_root = TEST_ROOT / "runtime-job-models"

    def fake_download(url: str, target_path: Path, **_kwargs) -> int:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes("繝｢繝・Ν".encode("utf-8"))
        return len("繝｢繝・Ν".encode("utf-8"))

    def fake_spawn(job_id: str, payload: dict) -> int:
        thread = threading.Thread(
            target=lambda: run_runtime_job.run({**payload, "job_id": job_id}),
            daemon=True,
        )
        thread.start()
        return thread.ident or 1

    monkeypatch.setattr("auto_mosaic.api.commands.fetch_models._download_to_path", fake_download)
    monkeypatch.setattr("auto_mosaic.api.commands.start_runtime_job._spawn_runtime_worker", fake_spawn)

    started = start_runtime_job.run(
        {"job_kind": "fetch_models", "model_names": ["320n.onnx"], "paths": {"model_dir": str(model_root)}}
    )
    assert started["ok"] is True
    job_id = started["data"]["job_id"]

    deadline = time.time() + 3.0
    while time.time() < deadline:
        status_response = get_runtime_job_status.run({"job_id": job_id})
        assert status_response["ok"] is True
        if status_response["data"]["status"]["state"] == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("runtime fetch job did not complete")

    result_response = get_runtime_job_result.run({"job_id": job_id})
    assert result_response["ok"] is True
    assert result_response["data"]["result"]["data"]["downloaded"] == 1


def test_runtime_fetch_models_job_can_be_cancelled(monkeypatch):
    model_root = TEST_ROOT / "runtime-job-cancel-models"

    def fake_download(url: str, target_path: Path, **kwargs) -> int:
        cancel_requested = kwargs.get("cancel_requested")
        for _ in range(20):
            if callable(cancel_requested) and cancel_requested():
                raise fetch_models.ModelFetchCancelled("cancelled")
            time.sleep(0.02)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"done")
        return 4

    def fake_spawn(job_id: str, payload: dict) -> int:
        thread = threading.Thread(
            target=lambda: run_runtime_job.run({**payload, "job_id": job_id}),
            daemon=True,
        )
        thread.start()
        return thread.ident or 1

    monkeypatch.setattr("auto_mosaic.api.commands.fetch_models._download_to_path", fake_download)
    monkeypatch.setattr("auto_mosaic.api.commands.start_runtime_job._spawn_runtime_worker", fake_spawn)

    started = start_runtime_job.run(
        {"job_kind": "fetch_models", "model_names": ["320n.onnx"], "paths": {"model_dir": str(model_root)}}
    )
    assert started["ok"] is True
    job_id = started["data"]["job_id"]
    cancel_runtime_job.run({"job_id": job_id})

    deadline = time.time() + 3.0
    while time.time() < deadline:
        status_response = get_runtime_job_status.run({"job_id": job_id})
        assert status_response["ok"] is True
        if status_response["data"]["status"]["state"] == "cancelled":
            assert status_response["data"]["status"]["message"]
            break
        time.sleep(0.02)
    else:
        raise AssertionError("runtime fetch cancel did not complete")


def test_runtime_open_video_job_round_trips_japanese_path(monkeypatch):
    video_path = TEST_ROOT / "譌･譛ｬ隱槭し繝ｳ繝励Ν.mp4"
    _make_sample_video(video_path)

    def fake_spawn(job_id: str, payload: dict) -> int:
        thread = threading.Thread(
            target=lambda: run_runtime_job.run({**payload, "job_id": job_id}),
            daemon=True,
        )
        thread.start()
        return thread.ident or 1

    monkeypatch.setattr("auto_mosaic.api.commands.start_runtime_job._spawn_runtime_worker", fake_spawn)
    started = start_runtime_job.run({"job_kind": "open_video", "video_path": str(video_path)})
    assert started["ok"] is True
    job_id = started["data"]["job_id"]

    deadline = time.time() + 3.0
    while time.time() < deadline:
        status_response = get_runtime_job_status.run({"job_id": job_id})
        assert status_response["ok"] is True
        if status_response["data"]["status"]["state"] == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("open video job did not complete")

    result_response = get_runtime_job_result.run({"job_id": job_id})
    assert result_response["ok"] is True
    assert result_response["data"]["result"]["data"]["video"]["source_path"] == str(video_path)


def test_start_runtime_accepts_erax_convert_job(monkeypatch):
    def fake_spawn(job_id: str, payload: dict) -> int:
        assert payload["job_kind"] == "setup_erax_convert"
        return 12345

    monkeypatch.setattr("auto_mosaic.api.commands.start_runtime_job._spawn_runtime_worker", fake_spawn)
    started = start_runtime_job.run({"job_kind": "setup_erax_convert"})

    assert started["ok"] is True
    assert started["data"]["status"]["job_kind"] == "setup_erax_convert"


def test_fetch_models_reports_non_downloadable_optional_model():
    model_root = TEST_ROOT / "non-downloadable-models"
    response = fetch_models.run(
        {
            "model_names": ["erax_nsfw_yolo11s.onnx"],
            "paths": {"model_dir": str(model_root)},
        }
    )
    assert response["ok"] is True
    assert response["data"]["results"][0]["status"] == "skipped"
    assert response["warnings"]


def test_open_video_ok():
    video_path = TEST_ROOT / "sample.mp4"
    _make_sample_video(video_path)
    response = open_video.run({"video_path": str(video_path)})
    assert response["ok"] is True
    assert response["data"]["video"]["readable"] is True
    assert response["data"]["video"]["width"] == 160


def test_detect_video_replaces_detector_tracks(monkeypatch):
    video_path = TEST_ROOT / "detect-sample.mp4"
    _make_sample_video(video_path)
    project_path = TEST_ROOT / "detect-project.json"

    created = create_project.run(
        {
            "name": "Detect",
            "project_path": str(project_path),
            "video": open_video.run({"video_path": str(video_path)})["data"]["video"],
            "tracks": [
                {
                    "track_id": "manual-track",
                    "label": "manual",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [{"start_frame": 0, "end_frame": 7, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                            "bbox": [0.1, 0.1, 0.2, 0.2],
                            "confidence": 1.0,
                            "source": "manual",
                        }
                    ],
                }
            ],
        }
    )
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})

    def fake_detect(*_args, **_kwargs):
        return __import__("auto_mosaic.infra.ai.detect_video", fromlist=["DetectionSummary"]).DetectionSummary(
            tracks=[
                MaskTrack(
                    track_id="detector-track-1",
                    label="AI讀懷・ 1",
                    state="detected",
                    source="detector",
                    visible=True,
                    keyframes=[
                        Keyframe(
                            frame_index=0,
                            shape_type="ellipse",
                            points=[[0.2, 0.2], [0.5, 0.2], [0.5, 0.5], [0.2, 0.5]],
                            bbox=[0.2, 0.2, 0.3, 0.3],
                            confidence=0.9,
                            source="detector",
                        )
                    ],
                )
            ],
            analyzed_frames=1,
            created_tracks=1,
            model_name="320n.onnx",
            device="gpu",
            sampled_frame_indexes=[0],
        )

    monkeypatch.setattr("auto_mosaic.api.commands.detect_video.detect_project_video", fake_detect)

    response = detect_video.run({"project_path": str(project_path)})
    assert response["ok"] is True
    assert response["data"]["detection"]["device"] == "gpu"
    assert response["data"]["project"]["tracks"][0]["track_id"] == "manual-track"
    assert response["data"]["project"]["tracks"][1]["track_id"] == "detector-track-1"


def test_detect_video_cli_stdout_contains_only_json():
    payload = {
        "project": {
            "project_id": "cli-detect-no-video",
            "version": "0.1.0",
            "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            "name": "CLI Detect No Video",
            "project_path": None,
            "video": None,
            "tracks": [],
            "detector_config": {},
            "export_preset": {
                "mosaic_strength": 12,
                "audio_mode": "mux_if_possible",
                "last_output_dir": None,
            },
            "paths": {},
        }
    }
    completed = _run_cli_command("detect-video", payload)

    assert completed.returncode == 1
    response = json.loads(completed.stdout)
    assert response["ok"] is False
    assert response["error"]["code"] == "SOURCE_VIDEO_MISSING"
    assert "[detect-video]" in completed.stderr


def test_cli_json_stdout_guard_redirects_native_stdout_to_stderr(capfd):
    from auto_mosaic.api import cli_main

    with cli_main._json_stdout_guard():
        print("python stdout noise")
        os.write(sys.__stdout__.fileno(), b"native stdout noise\n")

    captured = capfd.readouterr()
    assert captured.out == ""
    assert "python stdout noise" in captured.err
    assert "native stdout noise" in captured.err


def test_detect_video_returns_json_error_for_missing_model_path(monkeypatch):
    video_path = TEST_ROOT / "detect-missing-model.mp4"
    _make_sample_video(video_path)
    project = create_project.run(
        {
            "name": "MissingModelProject",
            "video": open_video.run({"video_path": str(video_path)})["data"]["video"],
            "tracks": [],
        }
    )["data"]["project"]

    response = detect_video.run(
        {
            "project": project,
            "paths": {"model_dir": str(TEST_ROOT / "missing-model-dir")},
        }
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "MODEL_NOT_FOUND"
    assert response["error"]["details"]["model_name"] == "320n.onnx"


def test_cli_commands_stdout_contains_only_json():
    video_path = TEST_ROOT / "cli-open-video.mp4"
    _make_sample_video(video_path)
    save_project_path = TEST_ROOT / "cli-save-project.json"
    save_payload = {
        "project_path": str(save_project_path),
        "project": create_project.run({"name": "CLI Save"})["data"]["project"],
    }

    cases = [
        ("create-project", {"name": "CLI Purity"}),
        ("open-video", {"video_path": str(video_path)}),
        ("save-project", save_payload),
    ]

    for command, payload in cases:
        completed = _run_cli_command(command, payload)
        parsed = json.loads(completed.stdout)
        assert parsed["command"] == command
        assert completed.stdout.strip().startswith("{")
        assert "\n{" not in completed.stdout.strip()


def test_detect_video_preserves_user_edited_detector_tracks(monkeypatch):
    video_path = TEST_ROOT / "detect-user-edited-source.mp4"
    _make_sample_video(video_path)
    project_path = TEST_ROOT / "detect-user-edited.json"

    created = create_project.run(
        {
            "name": "DetectUserEdited",
            "project_path": str(project_path),
            "video": open_video.run({"video_path": str(video_path)})["data"]["video"],
            "tracks": [
                {
                    "track_id": "detector-track-edited",
                    "label": "AI 1",
                    "state": "detected",
                    "source": "detector",
                    "visible": True,
                    "user_edited": False,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
                            "bbox": [0.1, 0.1, 0.2, 0.2],
                            "confidence": 0.8,
                            "source": "detector",
                        }
                    ],
                }
            ],
        }
    )
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})

    edit_response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "detector-track-edited",
            "frame_index": 0,
            "patch": {"bbox": [0.15, 0.12, 0.25, 0.22]},
        }
    )
    assert edit_response["ok"] is True
    edited_track = edit_response["data"]["project"]["tracks"][0]
    assert edited_track["source"] == "manual"
    assert edited_track["user_edited"] is True
    assert edited_track["keyframes"][0]["source"] == "manual"

    def fake_detect(*_args, **_kwargs):
        return __import__("auto_mosaic.infra.ai.detect_video", fromlist=["DetectionSummary"]).DetectionSummary(
            tracks=[
                MaskTrack(
                    track_id="detector-track-new",
                    label="AI 2",
                    state="detected",
                    source="detector",
                    visible=True,
                    keyframes=[
                        Keyframe(
                            frame_index=0,
                            shape_type="ellipse",
                            points=[[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]],
                            bbox=[0.4, 0.4, 0.2, 0.2],
                            confidence=0.9,
                            source="detector",
                        )
                    ],
                )
            ],
            analyzed_frames=1,
            created_tracks=1,
            model_name="320n.onnx",
            device="cpu",
            sampled_frame_indexes=[0],
        )

    monkeypatch.setattr("auto_mosaic.api.commands.detect_video.detect_project_video", fake_detect)

    response = detect_video.run({"project_path": str(project_path)})
    assert response["ok"] is True
    track_ids = [track["track_id"] for track in response["data"]["project"]["tracks"]]
    assert track_ids == ["detector-track-edited", "detector-track-new"]
    preserved = response["data"]["project"]["tracks"][0]
    assert preserved["user_edited"] is True
    assert preserved["keyframes"][0]["bbox"] == [0.15, 0.12, 0.25, 0.22]


def test_user_edited_detector_track_protection_survives_update_track_patch():
    project_path = TEST_ROOT / "edited-track-protection.json"
    created = create_project.run(
        {
            "name": "EditedTrackProtection",
            "tracks": [
                {
                    "track_id": "detector-track-edited",
                    "label": "AI 1",
                    "state": "detected",
                    "source": "detector",
                    "visible": True,
                    "user_edited": True,
                    "keyframes": [
                        {
                            "frame_index": 4,
                            "shape_type": "ellipse",
                            "points": [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4]],
                            "bbox": [0.2, 0.2, 0.2, 0.2],
                            "confidence": 0.9,
                            "source": "manual",
                        }
                    ],
                }
            ],
        }
    )
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})

    response = update_track.run(
        {
            "project_path": str(project_path),
            "track_id": "detector-track-edited",
            "patch": {
                "label": "edited",
                "source": "detector",
                "user_edited": False,
            },
        }
    )
    assert response["ok"] is True
    track = response["data"]["project"]["tracks"][0]
    assert track["label"] == "edited"
    assert track["user_edited"] is True
    assert track["source"] == "manual"


def test_detector_track_matching_preserves_identity_across_frames():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    detector_tracks: list[MaskTrack] = []
    track_cursors: list[object] = []
    model_dir = TEST_ROOT / "models-for-track-matching"
    model_dir.mkdir(parents=True, exist_ok=True)

    detect_video_infra._apply_frame_detections(
        [
            {"bbox_norm": [0.10, 0.10, 0.16, 0.16], "score": 0.95},
            {"bbox_norm": [0.62, 0.10, 0.16, 0.16], "score": 0.93},
        ],
        0,
        frame,
        "none",
        model_dir,
        detector_tracks,
        track_cursors,
    )
    detect_video_infra._apply_frame_detections(
        [
            {"bbox_norm": [0.60, 0.10, 0.16, 0.16], "score": 0.94},
            {"bbox_norm": [0.12, 0.10, 0.16, 0.16], "score": 0.92},
        ],
        2,
        frame,
        "none",
        model_dir,
        detector_tracks,
        track_cursors,
    )

    assert len(detector_tracks) == 2
    assert [keyframe.frame_index for keyframe in detector_tracks[0].keyframes] == [0, 2]
    assert [keyframe.frame_index for keyframe in detector_tracks[1].keyframes] == [0, 2]
    assert detector_tracks[0].keyframes[1].bbox[0] < 0.2
    assert detector_tracks[1].keyframes[1].bbox[0] > 0.5


def test_detector_track_matching_creates_new_track_for_far_detection():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    detector_tracks: list[MaskTrack] = []
    track_cursors: list[object] = []
    model_dir = TEST_ROOT / "models-for-track-split"
    model_dir.mkdir(parents=True, exist_ok=True)

    detect_video_infra._apply_frame_detections(
        [{"bbox_norm": [0.10, 0.10, 0.16, 0.16], "score": 0.95}],
        0,
        frame,
        "none",
        model_dir,
        detector_tracks,
        track_cursors,
    )
    detect_video_infra._apply_frame_detections(
        [{"bbox_norm": [0.72, 0.58, 0.16, 0.16], "score": 0.90}],
        1,
        frame,
        "none",
        model_dir,
        detector_tracks,
        track_cursors,
    )

    assert len(detector_tracks) == 2
    assert [keyframe.frame_index for keyframe in detector_tracks[0].keyframes] == [0]
    assert [keyframe.frame_index for keyframe in detector_tracks[1].keyframes] == [1]


def test_detect_video_requires_video():
    project_path = TEST_ROOT / "detect-empty.json"
    created = create_project.run({"name": "No Video", "project_path": str(project_path)})
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    response = detect_video.run({"project_path": str(project_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "SOURCE_VIDEO_MISSING"


def test_detect_job_start_status_and_result(monkeypatch):
    video_path = TEST_ROOT / "detect-job-source.mp4"
    _make_sample_video(video_path)
    project_path = TEST_ROOT / "detect-job-project.json"
    created = create_project.run(
        {
            "name": "DetectJobProject",
            "project_path": str(project_path),
            "video": open_video.run({"video_path": str(video_path)})["data"]["video"],
            "tracks": [],
        }
    )
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})

    def fake_detect(*_args, **_kwargs):
        return detect_video_infra.DetectionSummary(
            tracks=[
                MaskTrack(
                    track_id="detector-track-1",
                    label="AI 1",
                    state="detected",
                    source="detector",
                    visible=True,
                    keyframes=[
                        Keyframe(
                            frame_index=0,
                            shape_type="ellipse",
                            points=[[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4]],
                            bbox=[0.2, 0.2, 0.2, 0.2],
                            confidence=0.9,
                            source="detector",
                        )
                    ],
                )
            ],
            analyzed_frames=2,
            created_tracks=1,
            model_name="320n.onnx",
            device="cpu",
            sampled_frame_indexes=[0, 7],
        )

    monkeypatch.setattr("auto_mosaic.api.commands.detect_video.detect_project_video", fake_detect)

    workers: list[threading.Thread] = []

    def fake_spawn(job_id: str, payload: dict) -> int:
        worker = threading.Thread(
            target=lambda: run_detect_job.run({**payload, "job_id": job_id}),
            daemon=True,
        )
        workers.append(worker)
        worker.start()
        return worker.ident or 1

    monkeypatch.setattr("auto_mosaic.api.commands.start_detect_job._spawn_detect_worker", fake_spawn)

    start_response = start_detect_job.run({"project_path": str(project_path)})
    assert start_response["ok"] is True
    job_id = start_response["data"]["job_id"]
    assert start_response["data"]["status"]["state"] == "queued"

    status_response = None
    for _ in range(30):
        status_response = get_detect_status.run({"job_id": job_id})
        if status_response["ok"] and status_response["data"]["status"]["state"] == "succeeded":
            break
        time.sleep(0.02)

    assert status_response is not None
    assert status_response["ok"] is True
    assert status_response["data"]["status"]["state"] == "succeeded"
    assert status_response["data"]["status"]["result_available"] is True

    result_response = get_detect_result.run({"job_id": job_id})
    assert result_response["ok"] is True
    assert result_response["data"]["result"]["ok"] is True
    assert result_response["data"]["result"]["data"]["detection"]["created_tracks"] == 1

    for worker in workers:
        worker.join(timeout=1.0)


def test_detect_job_cancelled_transition(monkeypatch):
    video_path = TEST_ROOT / "detect-job-cancel-source.mp4"
    _make_sample_video(video_path)
    project_path = TEST_ROOT / "detect-job-cancel-project.json"
    created = create_project.run(
        {
            "name": "DetectJobCancelProject",
            "project_path": str(project_path),
            "video": open_video.run({"video_path": str(video_path)})["data"]["video"],
            "tracks": [],
        }
    )
    save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})

    def fake_detect(_project, payload):
        progress_callback = payload["_progress_callback"]
        cancel_requested = payload["_cancel_requested"]
        for index in range(20):
            if cancel_requested():
                raise detect_video_infra.DetectCancelledError()
            progress_callback(stage="running_inference", percent=35.0 + index, message="Running detector inference", current=index, total=20)
            time.sleep(0.01)
        raise AssertionError("cancel was never requested")

    monkeypatch.setattr("auto_mosaic.api.commands.detect_video.detect_project_video", fake_detect)

    workers: list[threading.Thread] = []

    def fake_spawn(job_id: str, payload: dict) -> int:
        worker = threading.Thread(
            target=lambda: run_detect_job.run({**payload, "job_id": job_id}),
            daemon=True,
        )
        workers.append(worker)
        worker.start()
        return worker.ident or 1

    monkeypatch.setattr("auto_mosaic.api.commands.start_detect_job._spawn_detect_worker", fake_spawn)

    start_response = start_detect_job.run({"project_path": str(project_path)})
    assert start_response["ok"] is True
    job_id = start_response["data"]["job_id"]

    for _ in range(20):
        status_poll = get_detect_status.run({"job_id": job_id})
        if status_poll["ok"] and status_poll["data"]["status"]["state"] == "running":
            break
        time.sleep(0.01)

    cancel_response = cancel_detect_job.run({"job_id": job_id})
    assert cancel_response["ok"] is True
    assert cancel_response["data"]["cancel_requested"] is True

    final_status = None
    for _ in range(40):
        status_response = get_detect_status.run({"job_id": job_id})
        if status_response["ok"] and status_response["data"]["status"]["state"] == "cancelled":
            final_status = status_response["data"]["status"]
            break
        time.sleep(0.02)

    assert final_status is not None
    assert final_status["state"] == "cancelled"
    assert final_status["error"]["code"] == "DETECT_CANCELLED"

    for worker in workers:
        worker.join(timeout=1.0)


def _age_ledger_heartbeat(ledger_db_path: Path, job_id: str, seconds_in_past: int) -> None:
    """Rewrite a job's heartbeat_at to simulate a stale worker.

    Used by ledger-level reconciliation tests: the staleness cutoff is computed
    from `datetime.now(UTC) - timeout`, so we backdate heartbeat_at directly
    rather than sleep for the full timeout in tests.
    """
    import sqlite3 as _sqlite3
    from datetime import UTC as _UTC, datetime as _datetime, timedelta as _timedelta

    past = _datetime.now(_UTC) - _timedelta(seconds=seconds_in_past)
    past_iso = past.isoformat().replace("+00:00", "Z")
    conn = _sqlite3.connect(str(ledger_db_path))
    try:
        conn.execute(
            "UPDATE jobs SET heartbeat_at = ? WHERE job_id = ?",
            (past_iso, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_list_detect_jobs_marks_dead_running_job_interrupted(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    ledger = get_detect_job_ledger()
    job_id = "detect-dead-running"
    ledger.create_job(job_id, stage="running_inference", message="Running detector inference")
    ledger.update_progress(
        job_id,
        state="running",
        progress_percent=42.0,
        current=21,
        total=50,
        worker_pid=999999,
    )
    _age_ledger_heartbeat(ledger.db_path, job_id, seconds_in_past=120)

    response = list_detect_jobs.run({"limit": 5})
    assert response["ok"] is True
    job = response["data"]["jobs"][0]
    assert job["job_id"] == job_id
    assert job["state"] == "interrupted"
    assert job["error"]["code"] == "DETECT_JOB_INTERRUPTED"
    assert response["data"]["recovered_interrupted"] == 1


def test_list_detect_jobs_reports_succeeded_job(tmp_path, monkeypatch):
    # With the SQLite ledger, state=succeeded and result_json are written in the
    # same transaction; there is no longer a race where result exists but state
    # lags behind. This test confirms a succeeded row is surfaced correctly.
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    ledger = get_detect_job_ledger()
    job_id = "detect-succeeded"
    ledger.create_job(job_id, stage="running_inference", message="Running detector inference")
    ledger.update_progress(job_id, state="running", progress_percent=80.0, current=40, total=50)
    ledger.mark_succeeded(
        job_id,
        {
            "ok": True,
            "command": "detect-video",
            "data": {"read_model": {"track_count": 3}},
            "error": None,
            "warnings": [],
        },
    )

    response = list_detect_jobs.run({"limit": 5})
    assert response["ok"] is True
    job = response["data"]["jobs"][0]
    assert job["job_id"] == job_id
    assert job["state"] == "succeeded"
    assert job["percent"] == 100.0
    assert job["result_available"] is True
    assert job["has_result"] is True
    assert job["error"] is None
    assert response["data"]["recovered_interrupted"] == 0


def test_cleanup_detect_jobs_prunes_old_terminal_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    ledger = get_detect_job_ledger()

    for index in range(4):
        job_id = f"detect-old-{index}"
        ledger.create_job(job_id, message=f"done-{index}")
        ledger.mark_succeeded(
            job_id,
            {"ok": True, "command": "detect-video", "data": {}, "error": None, "warnings": []},
        )
        time.sleep(0.01)  # ensure updated_at is strictly ordered

    cleanup_response = cleanup_detect_jobs.run({"retain_limit": 2})
    assert cleanup_response["ok"] is True
    assert len(cleanup_response["data"]["deleted_job_ids"]) == 2

    remaining = list_detect_jobs.run({"limit": 10})
    assert remaining["ok"] is True
    assert [job["job_id"] for job in remaining["data"]["jobs"]] == ["detect-old-3", "detect-old-2"]


def test_list_detect_jobs_empty_ledger_returns_no_broken_ids(tmp_path, monkeypatch):
    # Canonical ledger rows replace on-disk status.json; there is no "broken
    # directory" concept anymore. broken_job_ids is always [].
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))

    response = list_detect_jobs.run({"limit": 5})
    assert response["ok"] is True
    assert response["data"]["jobs"] == []
    assert response["data"]["broken_job_ids"] == []


def test_export_job_state_uses_runtime_data_dir(monkeypatch):
    runtime_root = TEST_ROOT / "runtime-state"
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(runtime_root))
    payload = {"phase": "rendering_frames", "progress": 0.5}
    export_jobs.write_status("job-runtime-path", payload)
    status_file = runtime_root / "temp" / "export-jobs" / "job-runtime-path" / "status.json"
    assert status_file.exists() is True
    assert export_jobs.read_status("job-runtime-path") == payload


def test_open_video_missing():
    response = open_video.run({"video_path": str(TEST_ROOT / "missing.mp4")})
    assert response["ok"] is False
    assert response["error"]["code"] == "VIDEO_NOT_FOUND"


def test_open_video_invalid_file():
    invalid_path = TEST_ROOT / "not-a-video.txt"
    invalid_path.write_text("plain text", encoding="utf-8")
    response = open_video.run({"video_path": str(invalid_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "VIDEO_OPEN_FAILED"


def test_save_and_load_project_roundtrip():
    project_path = TEST_ROOT / "roundtrip.json"
    created = create_project.run(
        {
            "name": "Roundtrip",
            "video": {
                "source_path": "C:/video.mp4",
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "frame_count": 90,
                "duration_sec": 3.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [1080, 1920, 3],
            },
            "export_preset": {
                "mosaic_strength": 20,
                "audio_mode": "video_only",
                "last_output_dir": "H:/exports",
            },
            "tracks": [
                {
                    "track_id": "track-001",
                    "label": "person",
                    "state": "active",
                    "source": "manual",
                    "keyframes": [
                        {
                            "frame_index": 12,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5]],
                            "bbox": [0.1, 0.1, 0.3, 0.4],
                            "confidence": 0.91,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        },
                        {
                            "frame_index": 48,
                            "shape_type": "ellipse",
                            "points": [[0.5, 0.4], [0.7, 0.6]],
                            "bbox": [0.5, 0.4, 0.2, 0.2],
                            "confidence": 0.88,
                            "source": "detector",
                            "rotation": 0.0,
                            "opacity": 0.9,
                            "expand_px": 4,
                            "feather": 2,
                            "is_locked": False,
                        },
                    ],
                }
            ],
        }
    )
    save_response = save_project.run(
        {
            "project_path": str(project_path),
            "project": created["data"]["project"],
        }
    )
    assert save_response["ok"] is True

    load_response = load_project.run({"project_path": str(project_path)})
    assert load_response["ok"] is True
    assert load_response["data"]["project"]["name"] == "Roundtrip"
    assert load_response["data"]["project"]["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    assert load_response["data"]["project"]["export_preset"] == {
        "mosaic_strength": 20,
        "audio_mode": "video_only",
        "last_output_dir": "H:/exports",
    }
    assert load_response["data"]["read_model"]["track_count"] == 1
    track_summary = load_response["data"]["read_model"]["track_summaries"][0]
    assert track_summary["index"] == 0
    assert track_summary["start_frame"] == 12
    assert track_summary["end_frame"] == 48
    assert track_summary["keyframe_count"] == 2
    assert track_summary["keyframes"] == [
        {"frame_index": 12, "source": "manual", "shape_type": "polygon"},
        {"frame_index": 48, "source": "detector", "shape_type": "ellipse"},
    ]
    assert not list(project_path.parent.glob(f".{project_path.name}.*.tmp"))


def test_save_project_returns_error_when_atomic_write_fails(monkeypatch):
    project_path = TEST_ROOT / "save-failure.json"
    created = create_project.run({"name": "SaveFailure"})

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("auto_mosaic.api.commands.save_project.atomic_write_text", explode)
    response = save_project.run(
        {
            "project_path": str(project_path),
            "project": created["data"]["project"],
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "PROJECT_SAVE_FAILED"


def test_load_project_migrates_legacy_schema_and_fills_defaults():
    project_path = TEST_ROOT / "legacy-project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_id": "legacy-project",
                "version": "0.0.1",
                "name": "Legacy",
                "tracks": [
                    {
                        "track_id": "legacy-track",
                        "label": "legacy",
                        "keyframes": [
                            {
                                "frame_index": 3,
                                "shape_type": "polygon",
                                "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                                "bbox": [0.1, 0.1, 0.1, 0.1],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    response = load_project.run({"project_path": str(project_path)})
    assert response["ok"] is True
    assert response["data"]["project"]["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    assert response["data"]["project"]["export_preset"] == {
        "mosaic_strength": 12,
        "audio_mode": "mux_if_possible",
        "last_output_dir": None,
    }
    assert response["data"]["project"]["tracks"][0]["visible"] is True
    assert response["data"]["project"]["tracks"][0]["state"] == "active"
    assert response["data"]["project"]["tracks"][0]["source"] == "manual"
    assert response["data"]["project"]["tracks"][0]["keyframes"][0]["confidence"] == 1.0
    assert response["warnings"]

    save_response = save_project.run(
        {
            "project_path": str(project_path),
            "project": response["data"]["project"],
        }
    )
    assert save_response["ok"] is True
    assert save_response["data"]["project"]["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION


def test_load_project_invalid_json():
    project_path = TEST_ROOT / "broken.json"
    project_path.write_text("{invalid", encoding="utf-8")
    response = load_project.run({"project_path": str(project_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "PROJECT_JSON_INVALID"


def test_load_project_missing_field():
    project_path = TEST_ROOT / "missing-field.json"
    project_path.write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    response = load_project.run({"project_path": str(project_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "PROJECT_SCHEMA_INVALID"


def test_load_project_rejects_invalid_schema_version():
    project_path = TEST_ROOT / "invalid-schema-version.json"
    project_path.write_text(
        json.dumps(
            {
                "project_id": "invalid-schema-version",
                "name": "Broken",
                "version": "0.1.0",
                "schema_version": "broken",
                "tracks": [],
            }
        ),
        encoding="utf-8",
    )
    response = load_project.run({"project_path": str(project_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "PROJECT_SCHEMA_VERSION_INVALID"


def test_load_project_rejects_unsupported_future_schema_version():
    project_path = TEST_ROOT / "unsupported-schema-version.json"
    project_path.write_text(
        json.dumps(
            {
                "project_id": "future-schema-version",
                "name": "Future",
                "version": "0.1.0",
                "schema_version": CURRENT_PROJECT_SCHEMA_VERSION + 1,
                "tracks": [],
            }
        ),
        encoding="utf-8",
    )
    response = load_project.run({"project_path": str(project_path)})
    assert response["ok"] is False
    assert response["error"]["code"] == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"


def test_read_model_includes_timeline_fields():
    created = create_project.run(
        {
            "name": "ReadModel",
            "tracks": [
                {
                    "track_id": "track-xyz",
                    "label": "sample",
                    "state": "active",
                    "source": "manual",
                    "keyframes": [
                        {
                            "frame_index": 3,
                            "shape_type": "polygon",
                            "points": [[0.2, 0.2], [0.5, 0.2], [0.5, 0.6]],
                            "bbox": [0.2, 0.2, 0.3, 0.4],
                            "confidence": 0.95,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    read_model = created["data"]["read_model"]
    assert "track_count" in read_model
    assert "track_summaries" in read_model
    track_summary = read_model["track_summaries"][0]
    assert track_summary["index"] == 0
    assert track_summary["visible"] is True
    assert track_summary["keyframes"] == [
        {"frame_index": 3, "source": "manual", "shape_type": "polygon"}
    ]


def test_read_model_keyframes_are_sorted_for_selection():
    created = create_project.run(
        {
            "name": "SelectionModel",
            "tracks": [
                {
                    "track_id": "track-selection",
                    "label": "selection",
                    "state": "active",
                    "source": "manual",
                    "keyframes": [
                        {
                            "frame_index": 25,
                            "shape_type": "ellipse",
                            "points": [[0.2, 0.2], [0.3, 0.3]],
                            "bbox": [0.2, 0.2, 0.1, 0.1],
                            "confidence": 0.8,
                            "source": "detector",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        },
                        {
                            "frame_index": 4,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.15, 0.1], [0.15, 0.2]],
                            "bbox": [0.1, 0.1, 0.05, 0.1],
                            "confidence": 0.95,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        },
                    ],
                }
            ],
        }
    )
    keyframes = created["data"]["read_model"]["track_summaries"][0]["keyframes"]
    assert keyframes == [
        {"frame_index": 4, "source": "manual", "shape_type": "polygon"},
        {"frame_index": 25, "source": "detector", "shape_type": "ellipse"},
    ]


def _write_mutation_project(project_path: Path) -> None:
    created = create_project.run(
        {
            "name": "MutationProject",
            "tracks": [
                {
                    "track_id": "track-main",
                    "label": "person",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 10,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True


def test_create_keyframe_roundtrip():
    project_path = TEST_ROOT / "create-keyframe.json"
    _write_mutation_project(project_path)
    response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 20,
            "source": "manual",
            "shape_type": "polygon",
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": "track-main", "frame_index": 20}
    loaded = load_project.run({"project_path": str(project_path)})
    keyframes = loaded["data"]["read_model"]["track_summaries"][0]["keyframes"]
    assert keyframes == [
        {"frame_index": 10, "source": "manual", "shape_type": "polygon"},
        {"frame_index": 20, "source": "manual", "shape_type": "polygon"},
    ]


def test_create_track_defaults_to_ellipse_shape():
    project_path = TEST_ROOT / "create-track-ellipse.json"
    created = create_project.run({"name": "CreateTrackEllipse"})
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = create_track.run(
        {
            "project_path": str(project_path),
            "frame_index": 18,
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"]["frame_index"] == 18

    loaded = load_project.run({"project_path": str(project_path)})
    created_track = loaded["data"]["project"]["tracks"][0]
    created_keyframe = created_track["keyframes"][0]
    assert created_track["source"] == "manual"
    assert created_keyframe["shape_type"] == "ellipse"
    assert created_keyframe["bbox"] == [0.3, 0.3, 0.2, 0.2]


def test_create_track_accepts_polygon_shape():
    project_path = TEST_ROOT / "create-track-polygon.json"
    created = create_project.run({"name": "CreateTrackPolygon"})
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = create_track.run(
        {
            "project_path": str(project_path),
            "frame_index": 6,
            "shape_type": "polygon",
            "bbox": [0.2, 0.25, 0.18, 0.12],
            "points": [[0.2, 0.25], [0.38, 0.25], [0.38, 0.37], [0.2, 0.37]],
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": response["data"]["selection"]["track_id"], "frame_index": 6}

    loaded = load_project.run({"project_path": str(project_path)})
    created_track = loaded["data"]["project"]["tracks"][0]
    created_keyframe = created_track["keyframes"][0]
    assert created_track["user_edited"] is True
    assert created_keyframe["shape_type"] == "polygon"
    assert created_keyframe["bbox"] == [0.2, 0.25, 0.18, 0.12]
    assert created_keyframe["points"] == [[0.2, 0.25], [0.38, 0.25], [0.38, 0.37], [0.2, 0.37]]


def test_create_track_accepts_inline_project_when_unsaved():
    created = create_project.run({"name": "InlineCreateTrack"})
    inline_project = created["data"]["project"]
    inline_project["project_path"] = None

    response = create_track.run(
        {
            "project": inline_project,
            "frame_index": 12,
            "shape_type": "polygon",
            "points": [[0.2, 0.2], [0.32, 0.2], [0.32, 0.34], [0.2, 0.34]],
            "bbox": [0.2, 0.2, 0.12, 0.14],
        }
    )
    assert response["ok"] is True
    assert response["data"]["project_path"] is None
    assert len(response["data"]["project"]["tracks"]) == 1
    assert len(response["data"]["read_model"]["track_summaries"]) == 1
    created_track = response["data"]["project"]["tracks"][0]
    assert created_track["keyframes"][0]["shape_type"] == "polygon"


def test_create_keyframe_accepts_valid_ellipse():
    project_path = TEST_ROOT / "create-ellipse.json"
    _write_mutation_project(project_path)
    response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 22,
            "source": "manual",
            "shape_type": "ellipse",
            "bbox": [0.2, 0.2, 0.15, 0.1],
        }
    )
    assert response["ok"] is True
    loaded = load_project.run({"project_path": str(project_path)})
    created = loaded["data"]["project"]["tracks"][0]["keyframes"][1]
    assert created["shape_type"] == "ellipse"
    assert created["bbox"] == [0.2, 0.2, 0.15, 0.1]


def test_create_keyframe_accepts_valid_polygon():
    project_path = TEST_ROOT / "create-polygon.json"
    _write_mutation_project(project_path)
    response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 24,
            "source": "manual",
            "shape_type": "polygon",
            "bbox": [0.2, 0.2, 0.15, 0.1],
            "points": [[0.2, 0.2], [0.35, 0.2], [0.35, 0.3]],
        }
    )
    assert response["ok"] is True
    loaded = load_project.run({"project_path": str(project_path)})
    created = loaded["data"]["project"]["tracks"][0]["keyframes"][1]
    assert created["shape_type"] == "polygon"
    assert created["points"] == [[0.2, 0.2], [0.35, 0.2], [0.35, 0.3]]


def test_update_keyframe_roundtrip():
    project_path = TEST_ROOT / "update-keyframe.json"
    _write_mutation_project(project_path)
    response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {
                "source": "detector",
                "shape_type": "polygon",
                "bbox": [0.2, 0.2, 0.15, 0.15],
                "points": [[0.2, 0.2], [0.35, 0.2], [0.35, 0.35]],
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": "track-main", "frame_index": 10}
    loaded = load_project.run({"project_path": str(project_path)})
    project_keyframe = loaded["data"]["project"]["tracks"][0]["keyframes"][0]
    assert loaded["data"]["project"]["tracks"][0]["user_edited"] is True
    assert loaded["data"]["project"]["tracks"][0]["source"] == "manual"
    assert project_keyframe["source"] == "manual"
    assert project_keyframe["shape_type"] == "polygon"
    assert project_keyframe["bbox"] == [0.2, 0.2, 0.15, 0.15]
    assert project_keyframe["points"] == [[0.2, 0.2], [0.35, 0.2], [0.35, 0.35]]
    assert loaded["data"]["read_model"]["track_summaries"][0]["keyframes"][0] == {
        "frame_index": 10,
        "source": "manual",
        "shape_type": "polygon",
    }


def test_update_keyframe_rotation_roundtrip_and_normalisation():
    project_path = TEST_ROOT / "update-keyframe-rotation.json"
    _write_mutation_project(project_path)
    response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {"rotation": 45.0},
        }
    )
    assert response["ok"] is True
    loaded = load_project.run({"project_path": str(project_path)})
    assert loaded["data"]["project"]["tracks"][0]["keyframes"][0]["rotation"] == 45.0

    # Values outside (-180, 180] are wrapped to the equivalent shortest-path angle.
    wrap_response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {"rotation": 270.0},
        }
    )
    assert wrap_response["ok"] is True
    wrapped = load_project.run({"project_path": str(project_path)})
    assert wrapped["data"]["project"]["tracks"][0]["keyframes"][0]["rotation"] == -90.0

    invalid = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {"rotation": "not-a-number"},
        }
    )
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "INVALID_KEYFRAME_PATCH"
    assert invalid["error"]["details"]["field"] == "rotation"


def test_move_keyframe_roundtrip():
    project_path = TEST_ROOT / "move-keyframe.json"
    _write_mutation_project(project_path)
    response = move_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "target_frame_index": 18,
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": "track-main", "frame_index": 18}
    loaded = load_project.run({"project_path": str(project_path)})
    assert loaded["data"]["project"]["tracks"][0]["keyframes"][0]["frame_index"] == 18
    assert loaded["data"]["read_model"]["track_summaries"][0]["keyframes"][0]["frame_index"] == 18


def test_move_keyframe_rejects_duplicate_or_invalid_target():
    project_path = TEST_ROOT / "move-keyframe-invalid.json"
    created = create_project.run(
        {
            "name": "MoveCollision",
            "video": {
                "source_path": "C:/video.mp4",
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "frame_count": 20,
                "duration_sec": 0.66,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [1080, 1920, 3],
            },
            "tracks": [
                {
                    "track_id": "track-main",
                    "label": "person",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 10,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        },
                        {
                            "frame_index": 12,
                            "shape_type": "polygon",
                            "points": [[0.3, 0.3], [0.4, 0.3], [0.4, 0.4]],
                            "bbox": [0.3, 0.3, 0.1, 0.1],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        },
                    ],
                }
            ],
        }
    )
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    duplicate_response = move_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "target_frame_index": 12,
        }
    )
    assert duplicate_response["ok"] is False
    assert duplicate_response["error"]["code"] == "TARGET_FRAME_OCCUPIED"

    out_of_range_response = move_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "target_frame_index": 20,
        }
    )
    assert out_of_range_response["ok"] is False
    assert out_of_range_response["error"]["code"] == "TARGET_FRAME_OUT_OF_RANGE"


def test_export_video_writes_output_and_applies_shapes():
    source_path = TEST_ROOT / "export-source.mp4"
    output_path = TEST_ROOT / "export-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "ellipse-track",
                    "label": "ellipse",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [{"start_frame": 0, "end_frame": 7, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                },
                {
                    "track_id": "polygon-track",
                    "label": "polygon",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.25, 0.1], [0.25, 0.25]],
                            "bbox": [0.1, 0.1, 0.15, 0.15],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                },
            ],
        }
    )
    project_path = TEST_ROOT / "export-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "mosaic_strength": 10,
                "audio_mode": "video_only",
            },
        }
    )
    assert response["ok"] is True
    assert output_path.exists()
    assert response["data"]["frame_count"] == 8

    source_capture = cv2.VideoCapture(str(source_path))
    source_ok, source_frame = source_capture.read()
    source_capture.release()
    assert source_ok is True

    output_capture = cv2.VideoCapture(str(output_path))
    output_ok, output_frame = output_capture.read()
    output_capture.release()
    assert output_ok is True

    ellipse_source = source_frame[27:63, 64:96]
    ellipse_output = output_frame[27:63, 64:96]
    polygon_source = source_frame[9:25, 16:40]
    polygon_output = output_frame[9:25, 16:40]
    untouched_source = source_frame[70:82, 120:140]
    untouched_output = output_frame[70:82, 120:140]

    ellipse_difference = float(np.mean(np.abs(ellipse_output.astype(np.int16) - ellipse_source.astype(np.int16))))
    polygon_difference = float(np.mean(np.abs(polygon_output.astype(np.int16) - polygon_source.astype(np.int16))))
    untouched_difference = float(np.mean(np.abs(untouched_output.astype(np.int16) - untouched_source.astype(np.int16))))

    assert response["data"]["effect"] == "mosaic"
    assert response["data"]["mosaic_strength"] == 10
    assert response["data"]["audio_mode"] == "video_only"
    assert response["data"]["audio"] == "video-only"
    assert ellipse_difference > 5.0
    assert polygon_difference > 5.0
    assert untouched_difference < 8.0


def test_export_video_mosaic_persists_across_all_frames():
    """Phase C M-E03: every written frame inside the track span must be mosaicked."""
    source_path = TEST_ROOT / "export-multi-frame-source.mp4"
    output_path = TEST_ROOT / "export-multi-frame-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "MultiFrameExport",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "ellipse-track",
                    "label": "ellipse",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [{"start_frame": 0, "end_frame": 7, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    project_path = TEST_ROOT / "export-multi-frame-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True
    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {"mosaic_strength": 10, "audio_mode": "video_only"},
        }
    )
    assert response["ok"] is True

    source_cap = cv2.VideoCapture(str(source_path))
    output_cap = cv2.VideoCapture(str(output_path))
    try:
        frame_count = 0
        while True:
            src_ok, src_frame = source_cap.read()
            out_ok, out_frame = output_cap.read()
            if not src_ok or not out_ok:
                break
            frame_count += 1
            # ellipse ROI ~ (y:27..63, x:64..96); difference must be > 5 every frame.
            src_roi = src_frame[27:63, 64:96].astype(np.int16)
            out_roi = out_frame[27:63, 64:96].astype(np.int16)
            diff = float(np.mean(np.abs(out_roi - src_roi)))
            assert diff > 4.0, f"frame {frame_count - 1}: mosaic not applied (diff={diff:.2f})"
        assert frame_count == 8
    finally:
        source_cap.release()
        output_cap.release()


def test_recovery_workflow_simulates_restart(tmp_path, monkeypatch):
    """Phase C M-E02 (partial): save → list after process restart (new ensure_runtime_dirs) → restore."""
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    project_payload = {
        "project_id": "after-restart",
        "version": "0.1.0",
        "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "name": "restart demo",
        "project_path": None,
        "video": None,
        "tracks": [],
        "detector_config": {},
        "export_preset": {},
        "paths": {},
    }
    saved = save_recovery_snapshot.run(
        {
            "snapshot_id": "restart-demo",
            "project": project_payload,
            "read_model": None,
            "timestamp": "2026-04-17T12:34:56.000Z",
            "confirmed_danger_frames": ["track-1-10", "track-1-20"],
        }
    )
    assert saved["ok"] is True

    # Simulating a restart: the next process starts fresh and calls list.
    listed = list_recovery_snapshots.run({})
    assert listed["ok"] is True
    snapshots = listed["data"]["snapshots"]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["id"] == "restart-demo"
    assert snapshot["project"]["project_id"] == "after-restart"
    assert snapshot["confirmed_danger_frames"] == ["track-1-10", "track-1-20"]

    deleted = delete_recovery_snapshot.run({"snapshot_id": "restart-demo"})
    assert deleted["ok"] is True
    assert deleted["data"]["deleted"] is True
    assert list_recovery_snapshots.run({})["data"]["snapshots"] == []


def test_export_video_skips_tracks_with_export_enabled_false():
    source_path = TEST_ROOT / "export-disabled-source.mp4"
    output_path = TEST_ROOT / "export-disabled-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportDisabledProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "ellipse-track",
                    "label": "ellipse",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "export_enabled": False,
                    "segments": [{"start_frame": 0, "end_frame": 7, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                },
                {
                    "track_id": "polygon-track",
                    "label": "polygon",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "export_enabled": True,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.25, 0.1], [0.25, 0.25]],
                            "bbox": [0.1, 0.1, 0.15, 0.15],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                },
            ],
        }
    )
    project_path = TEST_ROOT / "export-disabled-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "mosaic_strength": 10,
                "audio_mode": "video_only",
            },
        }
    )
    assert response["ok"] is True
    assert output_path.exists()

    source_capture = cv2.VideoCapture(str(source_path))
    source_ok, source_frame = source_capture.read()
    source_capture.release()
    assert source_ok is True

    output_capture = cv2.VideoCapture(str(output_path))
    output_ok, output_frame = output_capture.read()
    output_capture.release()
    assert output_ok is True

    # ellipse-track has export_enabled=False, so its ROI must match the source.
    ellipse_source = source_frame[27:63, 64:96]
    ellipse_output = output_frame[27:63, 64:96]
    # polygon-track stays enabled — its ROI must still be mosaicked.
    polygon_source = source_frame[9:25, 16:40]
    polygon_output = output_frame[9:25, 16:40]

    ellipse_difference = float(np.mean(np.abs(ellipse_output.astype(np.int16) - ellipse_source.astype(np.int16))))
    polygon_difference = float(np.mean(np.abs(polygon_output.astype(np.int16) - polygon_source.astype(np.int16))))

    assert ellipse_difference < 8.0, "export_enabled=False track must not be mosaicked"
    assert polygon_difference > 5.0, "other tracks must still be mosaicked"


def test_update_track_roundtrip_toggles_export_enabled():
    project_path = TEST_ROOT / "update-track-export-enabled.json"
    _write_mutation_project(project_path)
    response = update_track.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "patch": {"export_enabled": False},
        }
    )
    assert response["ok"] is True
    loaded = load_project.run({"project_path": str(project_path)})
    track = loaded["data"]["project"]["tracks"][0]
    summary = loaded["data"]["read_model"]["track_summaries"][0]
    assert track["export_enabled"] is False
    assert summary["export_enabled"] is False

    # Re-enable to confirm the patch is idempotent in both directions.
    re_enable = update_track.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "patch": {"export_enabled": True},
        }
    )
    assert re_enable["ok"] is True
    reloaded = load_project.run({"project_path": str(project_path)})
    assert reloaded["data"]["project"]["tracks"][0]["export_enabled"] is True


def test_export_video_does_not_hold_single_keyframe_until_video_end():
    source_path = TEST_ROOT / "export-single-keyframe-source.mp4"
    output_path = TEST_ROOT / "export-single-keyframe-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportSingleKeyframeProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "single-kf",
                    "label": "single",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                        }
                    ],
                }
            ],
        }
    )

    response = export_project_video(
        ProjectDocument.from_payload(created["data"]["project"]),
        str(output_path),
        mosaic_strength=10,
        audio_mode="video_only",
    )
    assert response["ok"] is True

    source_capture = cv2.VideoCapture(str(source_path))
    output_capture = cv2.VideoCapture(str(output_path))
    frames: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(6):
        source_ok, source_frame = source_capture.read()
        output_ok, output_frame = output_capture.read()
        assert source_ok is True and output_ok is True
        frames.append((source_frame, output_frame))
    source_capture.release()
    output_capture.release()

    frame0_source, frame0_output = frames[0]
    frame5_source, frame5_output = frames[5]
    roi_y0, roi_y1 = 27, 63
    roi_x0, roi_x1 = 64, 96
    frame0_diff = float(
        np.mean(
            np.abs(
                frame0_output[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                - frame0_source[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
            )
        )
    )
    frame5_diff = float(
        np.mean(
            np.abs(
                frame5_output[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                - frame5_source[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
            )
        )
    )

    assert frame0_diff > 5.0
    assert frame5_diff < 8.0


def test_export_video_uses_segment_spans_to_limit_rendering():
    source_path = TEST_ROOT / "export-segment-span-source.mp4"
    output_path = TEST_ROOT / "export-segment-span-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportSegmentSpanProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "segment-track",
                    "label": "segment",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [{"start_frame": 2, "end_frame": 3, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 2,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                        }
                    ],
                }
            ],
        }
    )

    response = export_project_video(
        ProjectDocument.from_payload(created["data"]["project"]),
        str(output_path),
        mosaic_strength=10,
        audio_mode="video_only",
    )
    assert response["ok"] is True

    source_capture = cv2.VideoCapture(str(source_path))
    output_capture = cv2.VideoCapture(str(output_path))
    frames: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(5):
        source_ok, source_frame = source_capture.read()
        output_ok, output_frame = output_capture.read()
        assert source_ok is True and output_ok is True
        frames.append((source_frame, output_frame))
    source_capture.release()
    output_capture.release()

    roi_y0, roi_y1 = 27, 63
    roi_x0, roi_x1 = 64, 96

    def roi_diff(index: int) -> float:
        source_frame, output_frame = frames[index]
        return float(
            np.mean(
                np.abs(
                    output_frame[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                    - source_frame[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                )
            )
        )

    assert roi_diff(1) < 8.0
    assert roi_diff(2) > 5.0
    assert roi_diff(3) > 5.0
    assert roi_diff(4) < 8.0


def test_export_video_does_not_render_inside_segment_gap():
    source_path = TEST_ROOT / "export-gap-source.mp4"
    output_path = TEST_ROOT / "export-gap-output.avi"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportGapProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "gap-track",
                    "label": "gap",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [
                        {"start_frame": 0, "end_frame": 1, "state": "confirmed"},
                        {"start_frame": 4, "end_frame": 5, "state": "confirmed"},
                    ],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                        },
                        {
                            "frame_index": 4,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                        },
                    ],
                }
            ],
        }
    )

    response = export_project_video(
        ProjectDocument.from_payload(created["data"]["project"]),
        str(output_path),
        mosaic_strength=10,
        audio_mode="video_only",
    )
    assert response["ok"] is True

    source_capture = cv2.VideoCapture(str(source_path))
    output_capture = cv2.VideoCapture(str(output_path))
    frames: list[tuple[np.ndarray, np.ndarray]] = []
    for _ in range(6):
        source_ok, source_frame = source_capture.read()
        output_ok, output_frame = output_capture.read()
        assert source_ok is True and output_ok is True
        frames.append((source_frame, output_frame))
    source_capture.release()
    output_capture.release()

    roi_y0, roi_y1 = 27, 63
    roi_x0, roi_x1 = 64, 96

    def roi_diff(index: int) -> float:
        source_frame, output_frame = frames[index]
        return float(
            np.mean(
                np.abs(
                    output_frame[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                    - source_frame[roi_y0:roi_y1, roi_x0:roi_x1].astype(np.int16)
                )
            )
        )

    assert roi_diff(0) > 5.0
    assert roi_diff(1) > 5.0
    assert roi_diff(2) < 8.0
    assert roi_diff(3) < 8.0
    assert roi_diff(4) > 5.0


def test_export_video_falls_back_to_video_only_when_ffmpeg_is_unavailable(monkeypatch):
    source_path = TEST_ROOT / "export-fallback-source.mp4"
    output_path = TEST_ROOT / "export-fallback-output.mp4"
    _make_sample_video_with_audio(source_path)
    created = create_project.run(
        {
            "name": "ExportFallbackProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )
    monkeypatch.setattr(
        "auto_mosaic.infra.video.export.resolve_external_tool",
        lambda tool_name: {"found": False, "path": None, "source": "not-found"},
    )

    response = export_project_video(
        ProjectDocument.from_payload(created["data"]["project"]),
        str(output_path),
        audio_mode="mux_if_possible",
    )
    assert response["ok"] is True
    assert output_path.exists()
    assert response["data"]["audio"] == "video-only"
    assert any("without audio" in warning for warning in response["warnings"])
    assert "audio" not in _probe_stream_types(output_path)


def test_export_video_auto_encoder_retries_with_cpu_after_gpu_runtime_failure(monkeypatch):
    local_test_root = Path.cwd() / ".pytest-tmp-export-auto-retry"
    local_test_root.mkdir(parents=True, exist_ok=True)
    source_path = local_test_root / "export-auto-encoder-retry-source.avi"
    output_path = local_test_root / "export-auto-encoder-retry-output.avi"
    source_path.write_bytes(b"placeholder")
    created = create_project.run(
        {
            "name": "ExportAutoEncoderRetryProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )

    attempts: list[str] = []
    capture_open_count = 0

    class DummyCapture:
        def get(self, _prop):
            return 0

        def release(self):
            return None

    def fake_open_capture(_path):
        nonlocal capture_open_count
        capture_open_count += 1
        return DummyCapture()

    def fake_pipe_export(**kwargs):
        attempts.append(kwargs["encoder_pref"])
        if len(attempts) == 1:
            raise export_infra.FfmpegEncodeError("h264_nvenc", "gpu runtime failure")
        return 8, "video-only", "libx264", []

    monkeypatch.setattr(
        "auto_mosaic.infra.video.export.resolve_external_tool",
        lambda tool_name: {"found": tool_name == "ffmpeg", "path": "ffmpeg", "source": "test"},
    )
    monkeypatch.setattr("auto_mosaic.infra.video.export._open_capture", fake_open_capture)
    monkeypatch.setattr("auto_mosaic.infra.video.export._ffmpeg_pipe_export", fake_pipe_export)

    response = export_project_video(
        ProjectDocument.from_payload(created["data"]["project"]),
        str(output_path),
        audio_mode="video_only",
        encoder="auto",
    )

    assert response["ok"] is True
    assert attempts == ["auto", "cpu"]
    assert capture_open_count == 2
    assert response["data"]["encoder"] == "libx264"
    assert any("Retrying export with CPU encoder" in warning for warning in response["warnings"])


def test_export_video_mux_if_possible_preserves_audio_stream():
    source_path = TEST_ROOT / "export-audio-source.mp4"
    output_path = TEST_ROOT / "export-audio-output.mp4"
    _make_sample_video_with_audio(source_path)
    created = create_project.run(
        {
            "name": "ExportAudioProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 12,
                "duration_sec": 0.5,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )
    project_path = TEST_ROOT / "export-audio-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "audio_mode": "mux_if_possible",
                "mosaic_strength": 12,
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["audio"] == "muxed"
    stream_types = _probe_stream_types(output_path)
    assert "video" in stream_types
    assert "audio" in stream_types


def test_export_video_mux_if_possible_reports_video_only_when_source_has_no_audio():
    source_path = TEST_ROOT / "export-no-audio-source.mp4"
    output_path = TEST_ROOT / "export-no-audio-output.mp4"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportNoAudioProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )
    project_path = TEST_ROOT / "export-no-audio-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "audio_mode": "mux_if_possible",
                "mosaic_strength": 12,
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["audio"] == "video-only"
    assert "audio" not in _probe_stream_types(output_path)


def test_export_video_video_only_omits_audio_stream():
    source_path = TEST_ROOT / "export-video-only-source.mp4"
    output_path = TEST_ROOT / "export-video-only-output.mp4"
    _make_sample_video_with_audio(source_path)
    created = create_project.run(
        {
            "name": "ExportVideoOnlyProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 12,
                "duration_sec": 0.5,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )
    project_path = TEST_ROOT / "export-video-only-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "audio_mode": "video_only",
                "mosaic_strength": 12,
            },
        }
    )
    assert response["ok"] is True
    assert response["data"]["audio"] == "video-only"
    stream_types = _probe_stream_types(output_path)
    assert "video" in stream_types
    assert "audio" not in stream_types


def test_export_video_rejects_invalid_options():
    project_path = TEST_ROOT / "export-invalid-options.json"
    _write_mutation_project(project_path)

    invalid_strength = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-invalid-strength.mp4"),
            "options": {"mosaic_strength": 0},
        }
    )
    assert invalid_strength["ok"] is False
    assert invalid_strength["error"]["code"] == "INVALID_EXPORT_OPTIONS"

    invalid_audio = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-invalid-audio.mp4"),
            "options": {"audio_mode": "unsupported"},
        }
    )
    assert invalid_audio["ok"] is False
    assert invalid_audio["error"]["code"] == "INVALID_EXPORT_OPTIONS"


def test_export_video_rejects_custom_fps_without_value():
    project_path = TEST_ROOT / "export-fps-no-value.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-fps-no-value.mp4"),
            "options": {"fps_mode": "custom"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "fps_custom"


def test_export_video_rejects_fps_custom_out_of_range():
    project_path = TEST_ROOT / "export-fps-oor.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-fps-oor.mp4"),
            "options": {"fps_mode": "custom", "fps_custom": 500.0},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "fps_custom"


def test_export_video_rejects_target_size_without_value():
    project_path = TEST_ROOT / "export-target-no-value.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-target-no-value.mp4"),
            "options": {"bitrate_mode": "target_size"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "target_size_mb"


def test_export_video_rejects_manual_bitrate_without_value():
    project_path = TEST_ROOT / "export-manual-no-value.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-manual-no-value.mp4"),
            "options": {"bitrate_mode": "manual"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "bitrate_kbps"


def test_export_video_accepts_spec_audio_aliases():
    project_path = TEST_ROOT / "export-audio-alias.json"
    _write_mutation_project(project_path)

    # "none" should be accepted and normalized internally.
    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-audio-alias.mp4"),
            "options": {"audio_mode": "none"},
        }
    )
    # May succeed or fail depending on ffmpeg availability; what matters is
    # that it is NOT rejected as INVALID_EXPORT_OPTIONS.
    if not response["ok"]:
        assert response["error"]["code"] != "INVALID_EXPORT_OPTIONS"


def test_export_video_rejects_invalid_video_codec():
    project_path = TEST_ROOT / "export-invalid-codec.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-invalid-codec.mp4"),
            "options": {"video_codec": "h265"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "video_codec"


def test_export_video_rejects_invalid_container():
    project_path = TEST_ROOT / "export-invalid-container.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-invalid-container.avi"),
            "options": {"container": "avi"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_EXPORT_OPTIONS"
    assert response["error"]["details"]["field"] == "container"


def test_export_video_rejects_incompatible_codec_container():
    project_path = TEST_ROOT / "export-incompat.json"
    _write_mutation_project(project_path)

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(TEST_ROOT / "export-incompat.mp4"),
            "options": {"video_codec": "vp9", "container": "mp4"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "EXPORT_CODEC_CONTAINER_INVALID"


def test_export_video_target_size_computes_bitrate_from_duration(tmp_path, monkeypatch):
    source_path = tmp_path / "target-size-source.mp4"
    output_path = tmp_path / "target-size-output.mp4"
    _make_sample_video(source_path)

    captured: dict[str, object] = {}

    real_export = export_infra.export_project_video

    def _capture(*args, **kwargs):
        captured.update(kwargs)
        return real_export(*args, **kwargs)

    monkeypatch.setattr(export_infra, "export_project_video", _capture)
    monkeypatch.setattr(
        "auto_mosaic.api.commands.export_video.export_project_video",
        _capture,
    )

    project_path = tmp_path / "target-size-project.json"
    project_path.write_text(
        json.dumps(
            {
                "project_id": "target-size",
                "version": "0.1.0",
                "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
                "name": "target size",
                "project_path": str(project_path),
                "video": {
                    "source_path": str(source_path),
                    "width": 160,
                    "height": 90,
                    "fps": 24.0,
                    "frame_count": 8,
                    "duration_sec": 8 / 24.0,
                    "readable": True,
                    "warnings": [],
                    "errors": [],
                    "first_frame_shape": [90, 160, 3],
                },
                "tracks": [],
                "detector_config": {},
                "export_preset": {},
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "options": {
                "audio_mode": "video_only",
                "bitrate_mode": "target_size",
                "target_size_mb": 5.0,
            },
        }
    )
    # Regardless of ffmpeg availability, kwargs should reach export_project_video.
    assert captured.get("bitrate_mode") == "target_size"
    assert captured.get("target_size_mb") == 5.0
    # If export succeeded, result should reflect the computed bitrate.
    if response["ok"]:
        data = response["data"]
        assert data["bitrate_mode"] == "target_size"
        # 5 MB over 8 frames / 24 fps = 1/3 sec → ~122.88 Mbps (huge), but
        # we just assert it's > auto default (8000 kbps for 160x90).
        assert data["bitrate_kbps"] > 8000


def test_export_video_can_be_cancelled_and_cleans_output(monkeypatch):
    source_path = TEST_ROOT / "export-cancel-source.mp4"
    output_path = TEST_ROOT / "export-cancel-output.mp4"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportCancelProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [
                {
                    "track_id": "ellipse-track",
                    "label": "ellipse",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    project_path = TEST_ROOT / "export-cancel-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    original_apply = export_video.export_project_video.__globals__["_apply_mosaic_mask"]

    def slow_apply(frame, keyframe, mosaic_strength):
        time.sleep(0.03)
        return original_apply(frame, keyframe, mosaic_strength)

    monkeypatch.setitem(export_video.export_project_video.__globals__, "_apply_mosaic_mask", slow_apply)

    job_id = "cancel-job-smoke"

    def request_cancel_later():
        time.sleep(0.06)
        cancel_export.run({"job_id": job_id})

    canceller = threading.Thread(target=request_cancel_later, daemon=True)
    canceller.start()
    response = export_video.run(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "job_id": job_id,
            "options": {
                "audio_mode": "video_only",
                "mosaic_strength": 12,
            },
        }
    )
    canceller.join(timeout=1.0)

    assert response["ok"] is False
    assert response["error"]["code"] == "EXPORT_CANCELLED"
    assert output_path.exists() is False
    status_response = get_export_status.run({"job_id": job_id})
    assert status_response["ok"] is True
    assert status_response["data"]["status"]["phase"] == "cancelled"


def test_export_status_is_available_while_rendering(monkeypatch):
    source_path = TEST_ROOT / "export-status-source.mp4"
    output_path = TEST_ROOT / "export-status-output.mp4"
    _make_sample_video(source_path)
    created = create_project.run(
        {
            "name": "ExportStatusProject",
            "video": {
                "source_path": str(source_path),
                "width": 160,
                "height": 90,
                "fps": 24.0,
                "frame_count": 8,
                "duration_sec": 8 / 24.0,
                "readable": True,
                "warnings": [],
                "errors": [],
                "first_frame_shape": [90, 160, 3],
            },
            "tracks": [],
        }
    )
    project_path = TEST_ROOT / "export-status-project.json"
    save_response = save_project.run({"project_path": str(project_path), "project": created["data"]["project"]})
    assert save_response["ok"] is True

    original_apply = export_video.export_project_video.__globals__["_apply_mosaic_mask"]

    def slow_apply(frame, keyframe, mosaic_strength):
        time.sleep(0.03)
        return original_apply(frame, keyframe, mosaic_strength)

    created_with_track = create_project.run(
        {
            "name": "ExportStatusProject",
            "video": created["data"]["project"]["video"],
            "tracks": [
                {
                    "track_id": "track-status",
                    "label": "status",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "segments": [{"start_frame": 0, "end_frame": 7, "state": "confirmed"}],
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "ellipse",
                            "points": [[0.4, 0.3], [0.6, 0.7]],
                            "bbox": [0.4, 0.3, 0.2, 0.4],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    save_response = save_project.run({"project_path": str(project_path), "project": created_with_track["data"]["project"]})
    assert save_response["ok"] is True
    monkeypatch.setitem(export_video.export_project_video.__globals__, "_apply_mosaic_mask", slow_apply)

    job_id = "status-job-smoke"
    result_holder: dict[str, dict] = {}

    def run_export():
        result_holder["response"] = export_video.run(
            {
                "project_path": str(project_path),
                "output_path": str(output_path),
                "job_id": job_id,
                "options": {
                    "audio_mode": "video_only",
                    "mosaic_strength": 12,
                },
            }
        )

    worker = threading.Thread(target=run_export, daemon=True)
    worker.start()
    time.sleep(0.08)
    status_response = get_export_status.run({"job_id": job_id})
    worker.join(timeout=2.0)

    assert status_response["ok"] is True
    assert status_response["data"]["status"]["phase"] in {"preparing", "rendering_frames"}
    assert status_response["data"]["status"]["progress"] >= 0.0
    assert result_holder["response"]["ok"] is True


def test_backend_rejects_asset_localhost_video_paths():
    invalid_project_payload = _project_payload_with_video(_asset_localhost_path())

    save_response = save_project.run(
        {
            "project_path": str(TEST_ROOT / "invalid-asset-save.json"),
            "project": invalid_project_payload,
        }
    )
    assert save_response["ok"] is False
    assert save_response["error"]["code"] == "SOURCE_VIDEO_PATH_INVALID"

    invalid_project_path = TEST_ROOT / "invalid-asset-project.json"
    invalid_project_path.write_text(json.dumps(invalid_project_payload), encoding="utf-8")

    load_response = load_project.run({"project_path": str(invalid_project_path)})
    assert load_response["ok"] is False
    assert load_response["error"]["code"] == "SOURCE_VIDEO_PATH_INVALID"

    export_response = export_video.run(
        {
            "project_path": str(invalid_project_path),
            "output_path": str(TEST_ROOT / "invalid-asset-export.mp4"),
            "options": {"audio_mode": "video_only", "mosaic_strength": 12},
        }
    )
    assert export_response["ok"] is False
    assert export_response["error"]["code"] == "SOURCE_VIDEO_PATH_INVALID"

    detect_response = detect_video.run({"project_path": str(invalid_project_path)})
    assert detect_response["ok"] is False
    assert detect_response["error"]["code"] == "SOURCE_VIDEO_PATH_INVALID"


def test_delete_keyframe_roundtrip():
    project_path = TEST_ROOT / "delete-keyframe.json"
    _write_mutation_project(project_path)
    response = delete_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": "track-main", "frame_index": None}
    loaded = load_project.run({"project_path": str(project_path)})
    track_summary = loaded["data"]["read_model"]["track_summaries"][0]
    assert track_summary["keyframe_count"] == 0
    assert track_summary["keyframes"] == []


def test_recovery_snapshot_save_list_delete_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    project_payload = {
        "project_id": "demo",
        "version": "0.1.0",
        "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "name": "recovery demo",
        "project_path": None,
        "video": None,
        "tracks": [],
        "detector_config": {},
        "export_preset": {},
        "paths": {},
    }
    save_response = save_recovery_snapshot.run(
        {
            "snapshot_id": "demo-1",
            "project": project_payload,
            "read_model": {"track_summaries": [], "track_count": 0},
            "timestamp": "2026-04-17T10:00:00.000Z",
            "current_frame": 42,
            "selected_track_id": "track-1",
            "selected_keyframe_frame": 40,
        }
    )
    assert save_response["ok"] is True

    list_response = list_recovery_snapshots.run({})
    assert list_response["ok"] is True
    snapshot = next(snap for snap in list_response["data"]["snapshots"] if snap["id"] == "demo-1")
    assert snapshot["current_frame"] == 42
    assert snapshot["selected_track_id"] == "track-1"
    assert snapshot["selected_keyframe_frame"] == 40

    delete_response = delete_recovery_snapshot.run({"snapshot_id": "demo-1"})
    assert delete_response["ok"] is True
    assert delete_response["data"]["deleted"] is True

    after = list_recovery_snapshots.run({})
    assert after["ok"] is True
    assert [snap["id"] for snap in after["data"]["snapshots"]] == []


def test_recovery_snapshot_rejects_invalid_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    response = save_recovery_snapshot.run(
        {"snapshot_id": "../escape", "project": {"project_id": "x"}}
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "SNAPSHOT_ID_INVALID"


def test_export_queue_enqueue_update_remove_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    enq = enqueue_export.run(
        {
            "queue_id": "q-1",
            "job_id": "",
            "project_path": "C:/fake/demo.autoproj",
            "project_name": "demo",
            "output_path": "C:/fake/demo-export.mp4",
            "options": {"mosaic_strength": 12, "audio_mode": "mux_if_possible"},
        }
    )
    assert enq["ok"] is True
    assert enq["data"]["item"]["state"] == "queued"

    listed = list_export_queue.run({})
    assert listed["ok"] is True
    assert [item["queue_id"] for item in listed["data"]["items"]] == ["q-1"]

    update = update_export_queue_item.run(
        {"queue_id": "q-1", "patch": {"state": "running", "progress": 42.5, "job_id": "export-xyz"}}
    )
    assert update["ok"] is True
    assert update["data"]["item"]["state"] == "running"
    assert update["data"]["item"]["progress"] == 42.5
    assert update["data"]["item"]["job_id"] == "export-xyz"

    removed = remove_export_queue_item.run({"queue_id": "q-1"})
    assert removed["ok"] is True
    assert removed["data"]["removed"] is True
    assert removed["data"]["items"] == []


def test_export_queue_running_items_restored_as_interrupted(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    enqueue_export.run(
        {
            "queue_id": "q-restore",
            "project_path": "C:/fake/demo.autoproj",
            "project_name": "demo",
            "output_path": "C:/fake/demo-export.mp4",
            "options": {"mosaic_strength": 12, "audio_mode": "mux_if_possible"},
        }
    )
    update_export_queue_item.run({"queue_id": "q-restore", "patch": {"state": "running", "progress": 10.0}})

    listed = list_export_queue.run({})
    assert listed["ok"] is True
    items = listed["data"]["items"]
    assert len(items) == 1
    assert items[0]["state"] == "interrupted"
    assert listed["data"]["recovered_interrupted"] == 1


def test_clear_terminal_export_queue_removes_only_terminal_items(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    for idx, state in enumerate(["queued", "completed", "failed", "cancelled"]):
        enqueue_export.run(
            {
                "queue_id": f"q-{idx}",
                "project_path": "C:/fake.autoproj",
                "output_path": f"C:/fake-{idx}.mp4",
                "options": {"mosaic_strength": 12, "audio_mode": "mux_if_possible"},
            }
        )
        if state != "queued":
            update_export_queue_item.run({"queue_id": f"q-{idx}", "patch": {"state": state}})

    cleared = clear_terminal_export_queue.run({})
    assert cleared["ok"] is True
    assert cleared["data"]["removed"] == 3
    remaining_ids = [item["queue_id"] for item in cleared["data"]["items"]]
    assert remaining_ids == ["q-0"]


def test_list_recovery_snapshots_reports_broken_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    recovery_dir = Path(tmp_path) / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    (recovery_dir / "broken.json").write_text("not json", encoding="utf-8")

    response = list_recovery_snapshots.run({})
    assert response["ok"] is True
    assert response["data"]["snapshots"] == []
    assert len(response["data"]["broken"]) == 1
    assert Path(response["data"]["broken"][0]["path"]).name == "broken.json"


def test_detect_settings_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    from auto_mosaic.api.commands import load_detect_settings, save_detect_settings

    empty = load_detect_settings.run({})
    assert empty["ok"] is True
    assert empty["data"]["settings"] is None
    assert empty["data"]["broken"] is False

    saved = save_detect_settings.run(
        {
            "settings": {
                "backend": "nudenet_320n",
                "device": "auto",
                "confidence_threshold": 0.42,
                "sample_every": 4,
                "max_samples": 200,
                "inference_resolution": 640,
                "batch_size": 2,
                "contour_mode": "balanced",
                "precise_face_contour": True,
                "vram_saving_mode": False,
                "selected_categories": ["genital_m", "breast"],
            }
        }
    )
    assert saved["ok"] is True
    assert saved["data"]["settings"]["backend"] == "nudenet_320n"
    assert saved["data"]["settings"]["confidence_threshold"] == 0.42
    assert saved["data"]["settings"]["selected_categories"] == ["genital_m", "breast"]

    loaded = load_detect_settings.run({})
    assert loaded["ok"] is True
    assert loaded["data"]["broken"] is False
    assert loaded["data"]["settings"]["backend"] == "nudenet_320n"
    assert loaded["data"]["settings"]["sample_every"] == 4
    assert loaded["data"]["settings"]["precise_face_contour"] is True


def test_detect_settings_save_rejects_non_object_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    from auto_mosaic.api.commands import save_detect_settings

    response = save_detect_settings.run({"settings": "not-an-object"})
    assert response["ok"] is False
    assert response["error"]["code"] == "DETECT_SETTINGS_REQUIRED"


def test_detect_settings_load_reports_broken_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    from auto_mosaic.api.commands import load_detect_settings

    config_dir = Path(tmp_path) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "detect-settings.json").write_text("not json", encoding="utf-8")

    response = load_detect_settings.run({})
    assert response["ok"] is True
    assert response["data"]["settings"] is None
    assert response["data"]["broken"] is True


def test_list_installed_models_reports_onnx_files(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    model_dir = tmp_path / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUTO_MOSAIC_MODEL_DIR", str(model_dir))
    # Write a large-enough plausible ONNX file (>= _MIN_MODEL_BYTES)
    from auto_mosaic.infra.ai.model_catalog import ONNX_MAGIC_BYTES
    magic_byte = next(iter(ONNX_MAGIC_BYTES))
    fake = bytes([magic_byte]) + b"\x00" * 2048
    (model_dir / "custom_probe.onnx").write_bytes(fake)

    from auto_mosaic.api.commands import list_installed_models

    response = list_installed_models.run({})
    assert response["ok"] is True
    names = [item["name"] for item in response["data"]["items"]]
    assert "custom_probe.onnx" in names
    item = next(item for item in response["data"]["items"] if item["name"] == "custom_probe.onnx")
    assert item["status"] in {"installed", "broken"}
    assert item["known"] is False


def test_delete_installed_model_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    model_dir = tmp_path / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUTO_MOSAIC_MODEL_DIR", str(model_dir))

    from auto_mosaic.api.commands import delete_installed_model

    traversal = delete_installed_model.run({"name": "../escape.onnx"})
    assert traversal["ok"] is False
    assert traversal["error"]["code"] == "MODEL_NAME_INVALID"

    with_slash = delete_installed_model.run({"name": "sub/path.onnx"})
    assert with_slash["ok"] is False
    assert with_slash["error"]["code"] == "MODEL_NAME_INVALID"


def test_duplicate_track_copies_keyframes_with_new_id():
    from auto_mosaic.api.commands import duplicate_track

    project_path = TEST_ROOT / "duplicate-track.json"
    _write_mutation_project(project_path)

    response = duplicate_track.run(
        {"project_path": str(project_path), "track_id": "track-main"}
    )
    assert response["ok"] is True
    new_id = response["data"]["selection"]["track_id"]
    assert new_id != "track-main"

    loaded = load_project.run({"project_path": str(project_path)})
    tracks = loaded["data"]["project"]["tracks"]
    assert len(tracks) == 2
    original = next(t for t in tracks if t["track_id"] == "track-main")
    duplicated = next(t for t in tracks if t["track_id"] == new_id)
    assert duplicated["label"] == f"{original['label']} (copy)"
    assert len(duplicated["keyframes"]) == len(original["keyframes"])
    assert duplicated["user_edited"] is True
    assert duplicated["user_locked"] is False


def test_duplicate_track_returns_track_not_found_for_missing_id():
    from auto_mosaic.api.commands import duplicate_track

    project_path = TEST_ROOT / "duplicate-track-missing.json"
    _write_mutation_project(project_path)

    response = duplicate_track.run(
        {"project_path": str(project_path), "track_id": "does-not-exist"}
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "TRACK_NOT_FOUND"


def test_split_track_partitions_keyframes_at_frame():
    from auto_mosaic.api.commands import split_track

    project_path = TEST_ROOT / "split-track.json"
    _write_mutation_project(project_path)

    # Seed additional keyframes to make a split meaningful.
    create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 30,
            "source": "manual",
            "shape_type": "polygon",
        }
    )
    create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 50,
            "source": "manual",
            "shape_type": "polygon",
        }
    )

    response = split_track.run(
        {"project_path": str(project_path), "track_id": "track-main", "split_frame": 30}
    )
    assert response["ok"] is True
    new_id = response["data"]["selection"]["track_id"]

    loaded = load_project.run({"project_path": str(project_path)})
    tracks = loaded["data"]["project"]["tracks"]
    left = next(t for t in tracks if t["track_id"] == "track-main")
    right = next(t for t in tracks if t["track_id"] == new_id)

    assert [kf["frame_index"] for kf in left["keyframes"]] == [10]
    assert sorted(kf["frame_index"] for kf in right["keyframes"]) == [30, 50]
    assert right["label"].endswith("(split)")
    assert right["user_edited"] is True


def test_duplicate_track_accepts_inline_project_when_unsaved():
    from auto_mosaic.api.commands import duplicate_track

    created = create_project.run(
        {
            "name": "InlineDuplicateProject",
            "tracks": [
                {
                    "track_id": "inline-track",
                    "label": "inline",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 0,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "confidence": 1.0,
                            "source": "manual",
                        }
                    ],
                }
            ],
        }
    )
    # Clear project_path to simulate unsaved state.
    inline_project = created["data"]["project"]
    inline_project["project_path"] = None

    response = duplicate_track.run(
        {"project": inline_project, "track_id": "inline-track"}
    )
    assert response["ok"] is True
    assert response["data"]["project_path"] is None
    assert len(response["data"]["project"]["tracks"]) == 2


def test_split_track_accepts_inline_project_when_unsaved():
    from auto_mosaic.api.commands import split_track

    created = create_project.run(
        {
            "name": "InlineSplitProject",
            "tracks": [
                {
                    "track_id": "inline-split",
                    "label": "inline",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 5,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "source": "manual",
                        },
                        {
                            "frame_index": 25,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "source": "manual",
                        },
                    ],
                }
            ],
        }
    )
    inline_project = created["data"]["project"]
    inline_project["project_path"] = None

    response = split_track.run(
        {"project": inline_project, "track_id": "inline-split", "split_frame": 15}
    )
    assert response["ok"] is True
    assert response["data"]["project_path"] is None
    assert len(response["data"]["project"]["tracks"]) == 2


def test_save_project_accepts_inline_project_without_path():
    created = create_project.run(
        {"name": "InlineSaveProject", "tracks": []}
    )
    inline_project = created["data"]["project"]
    inline_project["project_path"] = None

    response = save_project.run({"project": inline_project})
    assert response["ok"] is True
    assert response["data"]["project_path"] is None
    assert response["data"]["bytes_written"] is None
    assert response["data"]["selection"] == {"track_id": None, "frame_index": None}


def test_split_track_rejects_empty_side():
    from auto_mosaic.api.commands import split_track

    project_path = TEST_ROOT / "split-track-empty.json"
    _write_mutation_project(project_path)

    # Original project has only one keyframe at frame 10; splitting at 5
    # would leave the left side empty.
    response = split_track.run(
        {"project_path": str(project_path), "track_id": "track-main", "split_frame": 5}
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "SPLIT_EMPTY_SIDE"


def test_delete_installed_model_removes_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    model_dir = tmp_path / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AUTO_MOSAIC_MODEL_DIR", str(model_dir))
    target = model_dir / "removable.onnx"
    target.write_bytes(b"\x08" + b"\x00" * 2048)

    from auto_mosaic.api.commands import delete_installed_model

    first = delete_installed_model.run({"name": "removable.onnx"})
    assert first["ok"] is True
    assert first["data"]["deleted"] is True
    assert not target.exists()

    # Idempotent: deleting again reports deleted=False but still ok=True.
    again = delete_installed_model.run({"name": "removable.onnx"})
    assert again["ok"] is True
    assert again["data"]["deleted"] is False


def test_detect_settings_coerces_unexpected_field_shapes(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MOSAIC_DATA_DIR", str(tmp_path))
    from auto_mosaic.api.commands import load_detect_settings, save_detect_settings

    saved = save_detect_settings.run(
        {
            "settings": {
                "backend": "nudenet_320n",
                "confidence_threshold": "not-a-number",
                "sample_every": 3.0,
                "batch_size": True,
                "selected_categories": ["ok", 42, None, "breast"],
                "unknown_field": "ignored",
            }
        }
    )
    assert saved["ok"] is True
    cleaned = saved["data"]["settings"]
    assert "confidence_threshold" not in cleaned
    assert cleaned["sample_every"] == 3
    assert "batch_size" not in cleaned
    assert cleaned["selected_categories"] == ["ok", "breast"]
    assert "unknown_field" not in cleaned

    loaded = load_detect_settings.run({})
    assert loaded["ok"] is True
    assert loaded["data"]["settings"] == cleaned


def test_update_track_roundtrip():
    project_path = TEST_ROOT / "update-track.json"
    _write_mutation_project(project_path)
    response = update_track.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "patch": {"visible": False, "label": "person-hidden"},
        }
    )
    assert response["ok"] is True
    assert response["data"]["selection"] == {"track_id": "track-main", "frame_index": None}
    loaded = load_project.run({"project_path": str(project_path)})
    track = loaded["data"]["project"]["tracks"][0]
    summary = loaded["data"]["read_model"]["track_summaries"][0]
    assert track["visible"] is False
    assert track["label"] == "person-hidden"
    assert summary["visible"] is False
    assert summary["label"] == "person-hidden"


def test_mutation_commands_fail_for_missing_targets():
    project_path = TEST_ROOT / "missing-targets.json"
    _write_mutation_project(project_path)
    create_response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "missing-track",
            "frame_index": 30,
            "source": "manual",
            "shape_type": "polygon",
        }
    )
    assert create_response["ok"] is False
    assert create_response["error"]["code"] == "TRACK_NOT_FOUND"

    update_response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 999,
            "patch": {"source": "detector"},
        }
    )
    assert update_response["ok"] is False
    assert update_response["error"]["code"] == "KEYFRAME_NOT_FOUND"

    delete_response = delete_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 999,
        }
    )
    assert delete_response["ok"] is False
    assert delete_response["error"]["code"] == "KEYFRAME_NOT_FOUND"

    track_response = update_track.run(
        {
            "project_path": str(project_path),
            "track_id": "missing-track",
            "patch": {"visible": False},
        }
    )
    assert track_response["ok"] is False
    assert track_response["error"]["code"] == "TRACK_NOT_FOUND"


def test_update_keyframe_rejects_invalid_bbox():
    project_path = TEST_ROOT / "invalid-bbox.json"
    _write_mutation_project(project_path)
    response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {
                "bbox": [0.1, 0.1, -0.2, 0.3],
            },
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_KEYFRAME_PATCH"
    assert response["error"]["details"]["field"] == "bbox"


def test_create_keyframe_rejects_invalid_bbox():
    project_path = TEST_ROOT / "create-invalid-bbox.json"
    _write_mutation_project(project_path)
    response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 30,
            "source": "manual",
            "shape_type": "ellipse",
            "bbox": [0.1, 0.1, 0.0, 0.3],
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_KEYFRAME_PAYLOAD"


def test_update_keyframe_rejects_invalid_polygon_points():
    project_path = TEST_ROOT / "invalid-points.json"
    _write_mutation_project(project_path)
    response = update_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 10,
            "patch": {
                "shape_type": "polygon",
                "points": [[0.1, 0.1], [0.2, 0.2]],
            },
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_KEYFRAME_PATCH"
    assert response["error"]["details"]["field"] == "points"


def test_create_keyframe_rejects_invalid_polygon_points():
    project_path = TEST_ROOT / "create-invalid-points.json"
    _write_mutation_project(project_path)
    response = create_keyframe.run(
        {
            "project_path": str(project_path),
            "track_id": "track-main",
            "frame_index": 32,
            "source": "manual",
            "shape_type": "polygon",
            "points": [[0.1, 0.1], [0.2, 0.2]],
        }
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_KEYFRAME_PAYLOAD"


def test_update_keyframe_inline_project_no_disk_write():
    """未保存プロジェクト (project_path なし) でも update-keyframe が動作し、ディスクに書かない。"""
    created = create_project.run(
        {
            "name": "InlineEditTest",
            "tracks": [
                {
                    "track_id": "track-a",
                    "label": "person",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 5,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3]],
                            "bbox": [0.1, 0.1, 0.2, 0.2],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    assert created["ok"] is True
    inline_project = created["data"]["project"]
    # project_path なし → inline project を渡す
    response = update_keyframe.run(
        {
            "project": inline_project,
            "track_id": "track-a",
            "frame_index": 5,
            "patch": {
                "points": [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4]],
            },
        }
    )
    assert response["ok"] is True, response
    assert response["data"]["selection"] == {"track_id": "track-a", "frame_index": 5}
    # project_path はインライン時も None のまま返る
    assert response["data"]["project_path"] is None
    updated_kf = response["data"]["project"]["tracks"][0]["keyframes"][0]
    assert updated_kf["points"] == [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4]]
    assert updated_kf["source"] == "manual"


def test_create_keyframe_inline_project_no_disk_write():
    """未保存プロジェクト (project_path なし) でも create-keyframe が動作し、ディスクに書かない。"""
    created = create_project.run(
        {
            "name": "InlineCreateTest",
            "tracks": [
                {
                    "track_id": "track-b",
                    "label": "face",
                    "state": "active",
                    "source": "manual",
                    "visible": True,
                    "keyframes": [
                        {
                            "frame_index": 1,
                            "shape_type": "polygon",
                            "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                            "bbox": [0.1, 0.1, 0.1, 0.1],
                            "confidence": 1.0,
                            "source": "manual",
                            "rotation": 0.0,
                            "opacity": 1.0,
                            "expand_px": None,
                            "feather": None,
                            "is_locked": False,
                        }
                    ],
                }
            ],
        }
    )
    assert created["ok"] is True
    inline_project = created["data"]["project"]
    response = create_keyframe.run(
        {
            "project": inline_project,
            "track_id": "track-b",
            "frame_index": 10,
            "shape_type": "polygon",
            "points": [[0.5, 0.5], [0.6, 0.5], [0.6, 0.6]],
            "source": "manual",
        }
    )
    assert response["ok"] is True, response
    assert response["data"]["selection"] == {"track_id": "track-b", "frame_index": 10}
    assert response["data"]["project_path"] is None
    kfs = response["data"]["project"]["tracks"][0]["keyframes"]
    assert len(kfs) == 2
    assert kfs[1]["frame_index"] == 10

