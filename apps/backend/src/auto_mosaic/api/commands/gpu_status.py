from __future__ import annotations

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.gpu_diagnostics import run_gpu_status


def run(payload: dict) -> dict:
    result = run_gpu_status(payload)
    return success(command="gpu-status", data=result, warnings=result.get("warnings", []))
