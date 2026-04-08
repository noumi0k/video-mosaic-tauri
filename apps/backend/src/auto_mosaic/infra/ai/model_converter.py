"""Model conversion helpers (EraX .pt -> .onnx, lazy-imported ultralytics)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _log(message: str) -> None:
    import sys
    print(message, file=sys.stderr, flush=True)


def convert_erax_pt_to_onnx(pt_path: Path, onnx_path: Path, imgsz: int = 640) -> dict[str, Any]:
    """Convert an EraX YOLO11 .pt checkpoint to ONNX via ultralytics.

    Returns a structured result dict:
      {"ok": bool, "reason": str, "onnx_path": str | None}

    The ultralytics dependency is lazy-imported so that environments without
    it still boot (the caller can surface "ultralytics missing" to the user
    and instruct them to install it, or drop a pre-converted .onnx in place).
    """
    if not pt_path.exists():
        return {
            "ok": False,
            "reason": f"Source checkpoint not found: {pt_path}",
            "onnx_path": None,
        }

    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "reason": (
                "ultralytics package is not installed in the active Python "
                "environment. Install it (`pip install ultralytics`) or drop "
                f"a pre-converted {onnx_path.name} next to {pt_path}."
            ),
            "onnx_path": None,
            "install_hint": "pip install ultralytics",
            "detail": str(exc),
        }

    try:
        model = YOLO(str(pt_path))
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"Failed to load YOLO checkpoint: {exc}",
            "onnx_path": None,
        }

    try:
        # ultralytics writes the ONNX next to the .pt by default
        exported = model.export(format="onnx", imgsz=imgsz)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"ultralytics ONNX export failed: {exc}",
            "onnx_path": None,
        }

    # `exported` is usually a path string / Path object pointing at the .onnx
    exported_path = Path(str(exported)) if exported else pt_path.with_suffix(".onnx")
    if not exported_path.exists():
        return {
            "ok": False,
            "reason": f"Export reported success but output file is missing: {exported_path}",
            "onnx_path": None,
        }

    # Move the exported file to the requested destination if they differ.
    if exported_path.resolve() != onnx_path.resolve():
        try:
            onnx_path.parent.mkdir(parents=True, exist_ok=True)
            if onnx_path.exists():
                onnx_path.unlink()
            exported_path.replace(onnx_path)
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"Failed to move exported ONNX into place: {exc}",
                "onnx_path": str(exported_path),
            }

    return {
        "ok": True,
        "reason": "conversion successful",
        "onnx_path": str(onnx_path),
    }


def ultralytics_available() -> bool:
    """Return True if the ultralytics package can be imported."""
    try:
        import ultralytics  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False
