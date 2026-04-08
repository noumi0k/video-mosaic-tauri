from __future__ import annotations

import io
import importlib.metadata
import shutil
import subprocess
import sys
from contextlib import redirect_stderr
from pathlib import Path

from auto_mosaic.runtime.bootstrap import bootstrap_backend_environment


def _run_command(args: list[str]) -> dict:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}


def get_onnxruntime_summary() -> dict:
    try:
        import onnxruntime as ort  # type: ignore

        return {
            "installed": True,
            "version": ort.__version__,
            "providers": ort.get_available_providers(),
        }
    except Exception as exc:
        return {
            "installed": False,
            "version": None,
            "providers": [],
            "error": str(exc),
        }


def _package_summary() -> dict:
    packages = {}
    for name in ("onnxruntime", "onnxruntime-gpu", "torch"):
        try:
            packages[name] = {
                "installed": True,
                "version": importlib.metadata.version(name),
            }
        except importlib.metadata.PackageNotFoundError:
            packages[name] = {
                "installed": False,
                "version": None,
            }
    return packages


def _torch_summary() -> dict:
    try:
        import torch  # type: ignore

        return {
            "installed": True,
            "version": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        }
    except Exception as exc:
        return {
            "installed": False,
            "version": None,
            "cuda_available": False,
            "device_count": 0,
            "error": str(exc),
        }


def _minimal_onnx_gpu_test() -> dict:
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        return {"ok": False, "reason": "onnxruntime import failed", "details": str(exc)}

    preload = {
        "available": hasattr(ort, "preload_dlls"),
        "called": False,
        "ok": False,
        "error": None,
    }
    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls(directory="")
            preload["called"] = True
            preload["ok"] = True
        except Exception as exc:
            preload["called"] = True
            preload["error"] = str(exc)

    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" not in providers:
        return {
            "ok": False,
            "reason": "CUDAExecutionProvider unavailable",
            "details": providers,
            "preload": preload,
        }

    model_path = Path(ort.__file__).resolve().parent / "datasets" / "mul_1.onnx"
    captured = io.StringIO()
    session_providers: list[str] = []
    try:
        with redirect_stderr(captured):
            session = ort.InferenceSession(
                str(model_path),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
        session_providers = session.get_providers()
    except Exception as exc:
        return {
            "ok": False,
            "reason": "Session creation failed",
            "details": {
                "model_path": str(model_path),
                "exception": str(exc),
                "stderr": captured.getvalue(),
            },
            "preload": preload,
        }

    if "CUDAExecutionProvider" not in session_providers:
        stderr = captured.getvalue()
        reason = "CUDA session fell back to CPU"
        missing_dll = None
        if ".dll" in stderr:
            marker = '"'
            parts = stderr.split(marker)
            dlls = [part for part in parts if part.lower().endswith(".dll")]
            if dlls:
                missing_dll = dlls[-1]
                reason = "CUDA DLL dependency missing"
        return {
            "ok": False,
            "reason": reason,
            "details": {
                "model_path": str(model_path),
                "requested_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "session_providers": session_providers,
                "stderr": stderr,
                "missing_dll": missing_dll,
            },
            "preload": preload,
        }

    return {
        "ok": True,
        "reason": "CUDA session created successfully",
        "details": {
            "model_path": str(model_path),
            "session_providers": session_providers,
            "stderr": captured.getvalue(),
        },
        "preload": preload,
    }


def _classify_status(nvidia: dict, packages: dict, provider_test: dict) -> str:
    if not nvidia["ok"]:
        return "nvidia-smi-unavailable"
    if not packages["onnxruntime-gpu"]["installed"] and packages["onnxruntime"]["installed"]:
        return "cpu-ort-only"
    if not packages["onnxruntime-gpu"]["installed"]:
        return "onnxruntime-gpu-missing"
    if not provider_test["ok"]:
        details = provider_test.get("details", {})
        if isinstance(details, dict) and details.get("missing_dll"):
            return "cuda-dll-missing"
        return "provider-unavailable"
    return "ready"


def run_gpu_status(payload: dict) -> dict:
    bootstrap = bootstrap_backend_environment()
    warnings: list[str] = []
    nvidia_smi = shutil.which("nvidia-smi")
    nvidia = _run_command([nvidia_smi, "--query-gpu=name,driver_version", "--format=csv,noheader"]) if nvidia_smi else {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "nvidia-smi not found",
    }

    packages = _package_summary()
    ort_summary = get_onnxruntime_summary()
    torch_summary = _torch_summary()
    provider_test = _minimal_onnx_gpu_test()

    classified = _classify_status(nvidia, packages, provider_test)
    if classified == "nvidia-smi-unavailable":
        warnings.append("nvidia-smi is unavailable.")
    elif classified == "cpu-ort-only":
        warnings.append("Only CPU onnxruntime is installed in the active environment.")
    elif not ort_summary.get("installed"):
        classified = "onnxruntime-missing"
        warnings.append("onnxruntime is not installed.")
    elif not provider_test["ok"]:
        classified = "provider-unavailable"
        warnings.append(str(provider_test["reason"]))
        details = provider_test.get("details", {})
        if isinstance(details, dict) and details.get("missing_dll"):
            classified = "cuda-dll-missing"

    return {
        "status": classified,
        "python_executable": sys.executable,
        "environment": bootstrap,
        "packages": packages,
        "nvidia_smi": {"path": nvidia_smi, "result": nvidia},
        "onnxruntime": ort_summary,
        "torch": torch_summary,
        "provider_test": provider_test,
        "warnings": warnings,
    }
