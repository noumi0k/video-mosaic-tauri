from __future__ import annotations

from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.api.commands._project_mutation import load_project_for_mutation
from auto_mosaic.infra.video.export import _resolve_codec_container, export_project_video


DEFAULT_MOSAIC_STRENGTH = 12
# Legacy audio modes: {mux_if_possible, video_only}. M-B03 adds the
# spec-aligned variants {copy_if_possible, encode, none}. All five are
# accepted here; `none` maps to `video_only` internally.
VALID_AUDIO_MODES = {
    "mux_if_possible",
    "video_only",
    "copy_if_possible",
    "encode",
    "none",
}
VALID_ENCODERS = {"auto", "gpu", "cpu"}
VALID_FPS_MODES = {"source", "custom"}
VALID_BITRATE_MODES = {"auto", "manual", "target_size"}
VALID_VIDEO_CODECS = {"h264", "vp9"}
VALID_CONTAINERS = {"auto", "mp4", "mov", "webm"}


def run(payload: dict) -> dict:
    project, _, error = load_project_for_mutation("export-video", payload)
    if error:
        return error

    output_path = payload.get("output_path")
    if not output_path:
        return failure("export-video", "OUTPUT_PATH_REQUIRED", "output_path is required.")

    options = payload.get("options", {})
    mosaic_strength = options.get("mosaic_strength", DEFAULT_MOSAIC_STRENGTH)
    try:
        mosaic_strength = int(mosaic_strength)
    except (TypeError, ValueError):
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "mosaic_strength must be an integer.",
            {"field": "mosaic_strength"},
        )
    if mosaic_strength < 2 or mosaic_strength > 64:
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "mosaic_strength must be between 2 and 64.",
            {"field": "mosaic_strength"},
        )

    audio_mode = str(options.get("audio_mode", "mux_if_possible"))
    if audio_mode not in VALID_AUDIO_MODES:
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "audio_mode must be one of mux_if_possible / copy_if_possible / encode / video_only / none.",
            {"field": "audio_mode"},
        )
    # Spec-aligned alias: "none" → internal "video_only".
    if audio_mode == "none":
        audio_mode = "video_only"

    resolution = str(options.get("resolution", "source"))
    if resolution not in {"source", "720p", "1080p", "4k"}:
        resolution = "source"

    bitrate_kbps = options.get("bitrate_kbps")
    if bitrate_kbps is not None:
        try:
            bitrate_kbps = int(bitrate_kbps)
        except (TypeError, ValueError):
            bitrate_kbps = None

    encoder = str(options.get("encoder", "auto"))
    if encoder not in VALID_ENCODERS:
        encoder = "auto"

    # M-B03: fps override
    fps_mode = str(options.get("fps_mode", "source"))
    if fps_mode not in VALID_FPS_MODES:
        fps_mode = "source"
    fps_custom_raw = options.get("fps_custom")
    fps_custom: float | None = None
    if fps_custom_raw is not None:
        try:
            fps_custom = float(fps_custom_raw)
        except (TypeError, ValueError):
            fps_custom = None
        else:
            if fps_custom <= 0.0 or fps_custom > 240.0:
                return failure(
                    "export-video",
                    "INVALID_EXPORT_OPTIONS",
                    "fps_custom must be between 0 and 240.",
                    {"field": "fps_custom"},
                )
    if fps_mode == "custom" and (fps_custom is None or fps_custom <= 0.0):
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "fps_custom is required when fps_mode is custom.",
            {"field": "fps_custom"},
        )

    # M-B03: bitrate mode
    bitrate_mode = str(options.get("bitrate_mode", "auto"))
    if bitrate_mode not in VALID_BITRATE_MODES:
        bitrate_mode = "auto"
    target_size_raw = options.get("target_size_mb")
    target_size_mb: float | None = None
    if target_size_raw is not None:
        try:
            target_size_mb = float(target_size_raw)
        except (TypeError, ValueError):
            target_size_mb = None
        else:
            if target_size_mb <= 0.0:
                target_size_mb = None
    if bitrate_mode == "target_size" and target_size_mb is None:
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "target_size_mb (> 0) is required when bitrate_mode is target_size.",
            {"field": "target_size_mb"},
        )
    if bitrate_mode == "manual" and (bitrate_kbps is None or bitrate_kbps <= 0):
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "bitrate_kbps (> 0) is required when bitrate_mode is manual.",
            {"field": "bitrate_kbps"},
        )

    # M-B03: video codec / container
    video_codec = str(options.get("video_codec", "h264"))
    if video_codec not in VALID_VIDEO_CODECS:
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "video_codec must be h264 or vp9.",
            {"field": "video_codec"},
        )
    container = str(options.get("container", "auto"))
    if container not in VALID_CONTAINERS:
        return failure(
            "export-video",
            "INVALID_EXPORT_OPTIONS",
            "container must be auto / mp4 / mov / webm.",
            {"field": "container"},
        )

    # Preemptively validate codec/container compatibility so callers get a
    # deterministic error code regardless of whether the project has a video.
    try:
        _resolve_codec_container(video_codec, container, Path(str(output_path)).suffix)
    except ValueError as exc:
        return failure(
            "export-video",
            "EXPORT_CODEC_CONTAINER_INVALID",
            str(exc),
            {
                "video_codec": video_codec,
                "container": container,
                "output_suffix": Path(str(output_path)).suffix,
            },
        )

    job_id = payload.get("job_id")
    if job_id is not None:
        job_id = str(job_id)

    result = export_project_video(
        project,
        str(output_path),
        mosaic_strength=mosaic_strength,
        audio_mode=audio_mode,
        job_id=job_id,
        resolution=resolution,
        bitrate_kbps=bitrate_kbps,
        encoder=encoder,
        fps_mode=fps_mode,
        fps_custom=fps_custom,
        bitrate_mode=bitrate_mode,
        target_size_mb=target_size_mb,
        video_codec=video_codec,
        container=container,
    )
    if result["ok"]:
        return success("export-video", result["data"], result["warnings"])

    return failure(
        "export-video",
        result["error"]["code"],
        result["error"]["message"],
        result["error"].get("details"),
        result["warnings"],
    )
