from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RuntimeDirs:
    root_dir: str
    data_dir: str
    config_dir: str
    log_dir: str
    temp_dir: str
    export_job_dir: str
    export_dir: str
    training_dir: str
    project_dir: str
    model_dir: str


def ensure_runtime_dirs(overrides: dict | None = None) -> RuntimeDirs:
    overrides = overrides or {}
    workspace_root = Path(__file__).resolve().parents[5]
    data_dir = Path(overrides.get("data_dir") or os.environ.get("AUTO_MOSAIC_DATA_DIR") or workspace_root / "user-data")

    runtime = RuntimeDirs(
        root_dir=str(workspace_root),
        data_dir=str(data_dir),
        config_dir=str(data_dir / "config"),
        log_dir=str(data_dir / "logs"),
        temp_dir=str(data_dir / "temp"),
        export_job_dir=str(data_dir / "temp" / "export-jobs"),
        export_dir=str(data_dir / "exports"),
        training_dir=str(data_dir / "training"),
        project_dir=str(data_dir / "projects"),
        model_dir=str(overrides.get("model_dir") or os.environ.get("AUTO_MOSAIC_MODEL_DIR") or workspace_root / "models"),
    )

    for path in asdict(runtime).values():
        Path(path).mkdir(parents=True, exist_ok=True)

    return runtime


def _probe_writable(path: Path) -> tuple[bool | None, str | None]:
    if not path.exists():
        return False, "Path does not exist."
    try:
        probe = path / ".auto-mosaic-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, None
    except OSError as exc:
        return False, str(exc)


def build_path_summary(runtime_dirs: RuntimeDirs) -> dict:
    summary: dict[str, dict] = {}
    for key, value in asdict(runtime_dirs).items():
        path = Path(value)
        writable: bool | None = None
        probe_error: str | None = None
        if key not in {"root_dir", "model_dir"}:
            writable, probe_error = _probe_writable(path)
        summary[key] = {
            "path": value,
            "exists": path.exists(),
            "writable": writable,
            "probe_error": probe_error,
        }
    return summary
