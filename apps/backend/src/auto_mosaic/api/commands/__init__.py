from __future__ import annotations

from importlib import import_module
from types import ModuleType

__all__ = [
    "cancel_export",
    "cancel_detect_job",
    "cancel_runtime_job",
    "cleanup_detect_jobs",
    "create_keyframe",
    "create_project",
    "create_track",
    "delete_keyframe",
    "detect_video",
    "doctor",
    "export_video",
    "fetch_models",
    "get_detect_result",
    "get_detect_status",
    "get_export_status",
    "get_runtime_job_result",
    "get_runtime_job_status",
    "gpu_status",
    "list_detect_jobs",
    "load_project",
    "move_keyframe",
    "open_video",
    "run_runtime_job",
    "run_detect_job",
    "save_project",
    "start_detect_job",
    "start_runtime_job",
    "setup_environment",
    "setup_erax",
    "update_keyframe",
    "update_track",
    "video_probe",
]


def __getattr__(name: str) -> ModuleType:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{name}", __name__)
    globals()[name] = module
    return module