from __future__ import annotations

from auto_mosaic.application.responses import failure, success
from auto_mosaic.api.commands._project_mutation import load_project_for_mutation
from auto_mosaic.infra.video.export import export_project_video


DEFAULT_MOSAIC_STRENGTH = 12
VALID_AUDIO_MODES = {"mux_if_possible", "video_only"}


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
            "audio_mode must be mux_if_possible or video_only.",
            {"field": "audio_mode"},
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
