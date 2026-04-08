"""setup-erax CLI command — status / convert / test for the EraX detector."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.model_converter import (
    convert_erax_pt_to_onnx,
    ultralytics_available,
)
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


_ERAX_PT_NAME = "erax_nsfw_yolo11s.pt"
_ERAX_ONNX_NAME = "erax_nsfw_yolo11s.onnx"
_ERAX_LABELS_NAME = "erax_nsfw_yolo11s.labels.json"
_ERAX_SOURCE_REPO = "erax-ai/EraX-NSFW-V1.0"


def _status(model_dir: Path) -> dict:
    pt_path = model_dir / _ERAX_PT_NAME
    onnx_path = model_dir / _ERAX_ONNX_NAME
    labels_sidecar = model_dir / _ERAX_LABELS_NAME
    pt_exists = pt_path.exists()
    onnx_exists = onnx_path.exists()
    if onnx_exists:
        state = "ready"
    elif pt_exists:
        state = "downloaded_pt"
    else:
        state = "missing"
    return {
        "model_dir": str(model_dir),
        "actual_model_name": _ERAX_PT_NAME.replace(".pt", ""),
        "source_repo": _ERAX_SOURCE_REPO,
        "pt": {"exists": pt_exists, "path": str(pt_path)},
        "onnx": {"exists": onnx_exists, "path": str(onnx_path)},
        "labels_sidecar": {"exists": labels_sidecar.exists(), "path": str(labels_sidecar)},
        "state": state,
        "convertible": ultralytics_available(),
        "ready_for_backend": onnx_exists,
    }


def _run_convert(model_dir: Path, progress_callback=None) -> dict:
    pt_path = model_dir / _ERAX_PT_NAME
    onnx_path = model_dir / _ERAX_ONNX_NAME

    def report(**kwargs):
        if callable(progress_callback):
            progress_callback(**kwargs)

    report(
        stage="checking",
        message="EraX PT ファイルを確認中",
        progress_percent=0.0,
        is_indeterminate=False,
    )

    if not pt_path.exists():
        return {
            "ok": False,
            "reason": (
                "EraX .pt checkpoint is not present. Use 'fetch-models' with "
                f"model_names=['{_ERAX_PT_NAME}'] before attempting conversion."
            ),
            "onnx_path": None,
            "pt_path": str(pt_path),
        }

    if not ultralytics_available():
        return {
            "ok": False,
            "reason": (
                "ultralytics パッケージが未インストールです。"
                " pip install ultralytics を実行してから再試行してください。"
            ),
            "onnx_path": None,
            "pt_path": str(pt_path),
            "install_hint": "pip install ultralytics",
        }

    report(
        stage="converting",
        message="EraX PT → ONNX 変換中 (ultralytics) — 数分かかることがあります",
        progress_percent=None,
        is_indeterminate=True,
    )

    result = convert_erax_pt_to_onnx(pt_path, onnx_path)
    result.setdefault("pt_path", str(pt_path))

    if result.get("ok"):
        report(
            stage="done",
            message="EraX ONNX 変換完了",
            progress_percent=100.0,
            is_indeterminate=False,
        )

    return result


def _run_test(model_dir: Path) -> dict:
    """Smoke-test the EraX ONNX session with a zero-filled dummy frame."""
    onnx_path = model_dir / _ERAX_ONNX_NAME
    if not onnx_path.exists():
        return {
            "ok": False,
            "reason": (
                f"EraX ONNX model missing at {onnx_path}. "
                f"Download {_ERAX_PT_NAME} first, then run setup-erax action='convert'."
            ),
            "onnx_path": str(onnx_path),
        }
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "reason": "onnxruntime is not available in this Python environment.",
            "detail": str(exc),
            "onnx_path": str(onnx_path),
        }
    try:
        session = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"Failed to load EraX ONNX session: {exc}",
            "onnx_path": str(onnx_path),
        }

    try:
        input_meta = session.get_inputs()[0]
        # YOLO11 expects NCHW float32 in the range [0, 1]. Use a deterministic
        # zero tensor so we only verify that the graph actually runs.
        shape = [int(d) if isinstance(d, int) else 1 for d in input_meta.shape]
        if len(shape) != 4:
            shape = [1, 3, 640, 640]
        dummy = np.zeros(shape, dtype=np.float32)
        outputs = session.run(None, {input_meta.name: dummy})
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"EraX ONNX inference smoke-test failed: {exc}",
            "onnx_path": str(onnx_path),
        }

    return {
        "ok": True,
        "reason": "EraX ONNX session loaded and ran a dummy frame successfully.",
        "onnx_path": str(onnx_path),
        "output_count": len(outputs),
        "output_shapes": [list(getattr(o, "shape", [])) for o in outputs],
    }


def run(payload: dict) -> dict:
    action = str(payload.get("action") or "status").lower()
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)
    progress_callback = payload.get("_progress_callback")

    if action == "status":
        return success("setup-erax", data={"action": "status", **_status(model_dir)})

    if action == "convert":
        result = _run_convert(model_dir, progress_callback=progress_callback)
        if not result.get("ok"):
            return failure(
                "setup-erax",
                "ERAX_CONVERT_FAILED",
                str(result.get("reason") or "conversion failed"),
                {"action": "convert", **result, **_status(model_dir)},
            )
        return success("setup-erax", data={"action": "convert", **result, **_status(model_dir)})

    if action == "test":
        result = _run_test(model_dir)
        if not result.get("ok"):
            return failure(
                "setup-erax",
                "ERAX_TEST_FAILED",
                str(result.get("reason") or "smoke test failed"),
                {"action": "test", **result, **_status(model_dir)},
            )
        return success("setup-erax", data={"action": "test", **result, **_status(model_dir)})

    return failure(
        "setup-erax",
        "UNKNOWN_ACTION",
        f"Unknown action '{action}'. Supported: status / convert / test.",
    )
