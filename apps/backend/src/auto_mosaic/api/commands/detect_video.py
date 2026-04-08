from __future__ import annotations

import sys
import traceback

from auto_mosaic.api.commands._project_mutation import load_project_for_mutation, persist_project
from auto_mosaic.application.responses import failure, success
from auto_mosaic.domain.project import ProjectDocument
from auto_mosaic.infra.ai.detect_video import DetectCancelledError, DetectVideoError, detect_project_video


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def execute_detect(payload: dict) -> dict:
    project_path_str = payload.get("project_path", "")
    project_inline = payload.get("project")
    backend = payload.get("backend", "<not set>")
    device = payload.get("device", "<not set>")
    contour_mode = payload.get("contour_mode", "none")
    inference_res = payload.get("inference_resolution", "<not set>")
    batch_size = payload.get("batch_size", 1)
    vram_saving = payload.get("vram_saving_mode", False)
    categories = payload.get("enabled_label_categories", "<not set>")
    confidence = payload.get("confidence_threshold", 0.28)
    sample_every = payload.get("sample_every", 0)
    max_samples = payload.get("max_samples", 120)

    _log(
        f"[detect-video] received payload:"
        f"\n  project_path       = {project_path_str or '<unsaved>'}"
        f"\n  has_inline_project = {bool(project_inline)}"
        f"\n  backend            = {backend}"
        f"\n  device             = {device}"
        f"\n  contour_mode       = {contour_mode}"
        f"\n  inference_res      = {inference_res}"
        f"\n  batch_size         = {batch_size}"
        f"\n  vram_saving_mode   = {vram_saving}"
        f"\n  confidence         = {confidence}"
        f"\n  sample_every       = {sample_every}"
        f"\n  max_samples        = {max_samples}"
        f"\n  categories         = {categories}"
    )

    save_after = False
    path = None

    if project_path_str:
        # Saved project: load from disk, persist result after detection.
        project, path, error = load_project_for_mutation("detect-video", payload)
        if error:
            _log(f"[detect-video] project load failed: {error}")
            return error
        assert project is not None
        assert path is not None
        save_after = True
    elif project_inline:
        # Unsaved project: load from inline JSON, return in-memory result without saving.
        try:
            project = ProjectDocument.from_payload(project_inline)
        except (KeyError, ValueError, TypeError) as exc:
            _log(f"[detect-video] PROJECT_STATE_INVALID: {exc}")
            return failure(
                "detect-video",
                getattr(exc, "code", "PROJECT_STATE_INVALID"),
                getattr(exc, "message", f"Invalid project state: {exc}"),
                getattr(exc, "details", None),
            )
        save_after = False
    else:
        _log("[detect-video] PROJECT_STATE_INVALID: no project_path or inline project")
        return failure(
            "detect-video",
            "PROJECT_STATE_INVALID",
            "Either project_path (saved project) or project (unsaved project) must be provided.",
        )

    if not project.video:
        _log("[detect-video] SOURCE_VIDEO_MISSING: no source video on project")
        return failure(
            "detect-video",
            "SOURCE_VIDEO_MISSING",
            "Load a source video before starting AI detection.",
        )

    _log(
        f"[detect-video] project loaded:"
        f"\n  source_video     = {project.video.source_path}"
        f"\n  frame_count      = {project.video.frame_count}"
        f"\n  fps              = {project.video.fps}"
        f"\n  save_after       = {save_after}"
        f"\n  detector_config  = {project.detector_config}"
    )

    try:
        detection = detect_project_video(project, payload)
        _log(
            f"[detect-video] detection complete:"
            f"\n  analyzed_frames  = {detection.analyzed_frames}"
            f"\n  created_tracks   = {detection.created_tracks}"
            f"\n  model_name       = {detection.model_name}"
            f"\n  device           = {detection.device}"
        )
    except DetectVideoError as exc:
        _log(f"[detect-video] {exc.code}: {exc.message} / {exc.details}")
        return failure(
            "detect-video",
            exc.code,
            exc.message,
            {"project_path": str(path) if path else None, **exc.details},
        )
    except DetectCancelledError as exc:
        _log(f"[detect-video] {exc.code}: {exc.message}")
        return failure(
            "detect-video",
            exc.code,
            exc.message,
            {"project_path": str(path) if path else None},
        )
    except Exception as exc:
        tb = traceback.format_exc()
        _log(f"[detect-video] DETECT_RUNTIME_FAILED: {exc}\n{tb}")
        return failure(
            "detect-video",
            "DETECT_RUNTIME_FAILED",
            str(exc),
            {"project_path": str(path) if path else None, "traceback": tb},
        )

    if not detection.tracks:
        diagnostics = detection.diagnostics_dict()
        _log(
            "[detect-video] DETECTION_EMPTY: no tracks found"
            f" reason={diagnostics.get('empty_reason')}"
            f" frames_queued={diagnostics.get('frames_queued')}"
            f" frames_decoded={diagnostics.get('frames_decoded')}"
            f" frames_inferred={diagnostics.get('frames_inferred')}"
            f" raw={diagnostics.get('raw_detections_total')}"
            f" filtered={diagnostics.get('filtered_detections_total')}"
            f" track_candidates={diagnostics.get('track_candidates_total')}"
        )
        return failure(
            "detect-video",
            "DETECTION_EMPTY",
            "AI detection completed, but no candidate masks were found.",
            {
                "project_path": str(path) if path else None,
                **diagnostics,
            },
        )

    project.replace_detector_tracks(detection.tracks)

    selection = {
        "track_id": detection.tracks[0].track_id if detection.tracks else None,
        "frame_index": detection.tracks[0].keyframes[0].frame_index if detection.tracks and detection.tracks[0].keyframes else None,
    }
    detection_info = {
        "analyzed_frames": detection.analyzed_frames,
        "created_tracks": detection.created_tracks,
        "model_name": detection.model_name,
        "device": detection.device,
        "sampled_frame_indexes": detection.sampled_frame_indexes,
        "contour_mode_counts": detection.contour_mode_counts,
    }

    if save_after:
        response = persist_project("detect-video", project, path, selection=selection)
        if response.get("ok"):
            response["data"]["detection"] = detection_info
        return response
    else:
        # Unsaved project: return updated state without saving to disk.
        # Frontend receives the full project JSON and marks the session as dirty.
        return success("detect-video", {
            "project": project.to_dict(),
            "read_model": project.build_read_model(),
            "selection": selection,
            "detection": detection_info,
        })


def run(payload: dict) -> dict:
    return execute_detect(payload)
