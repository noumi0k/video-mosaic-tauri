from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path

from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.gpu_diagnostics import _minimal_onnx_gpu_test, get_onnxruntime_summary
from auto_mosaic.infra.ai.model_catalog import ModelSpec, get_optional_model_names, get_required_model_names, get_model_spec_map
from auto_mosaic.infra.ai.model_converter import ultralytics_available
from auto_mosaic.runtime.bootstrap import bootstrap_backend_environment
from auto_mosaic.runtime.external_tools import resolve_external_tool
from auto_mosaic.runtime.paths import build_path_summary, ensure_runtime_dirs


_HTML_SIGNATURES = (b"<!DOCTYPE", b"<html", b"<!doctype")
_MIN_MODEL_BYTES = 1024  # any real model file is at least 1 KB

# Valid first bytes for an ONNX ModelProto (protobuf field tags for each known field).
# Each tag encodes (field_number << 3) | wire_type.
# HTML pages start with 0x3c ('<') which is excluded by the HTML guard above, but
# a raw protobuf field tag of 0x3c (field 7, wire 4 = end-group, invalid) would also
# be rejected here.
_ONNX_PROTO_FIRST_BYTES = frozenset({
    0x08,  # field 1 ir_version      (varint)
    0x12,  # field 2 producer_name   (len)
    0x1a,  # field 3 producer_version(len)
    0x22,  # field 4 domain          (len)
    0x28,  # field 5 model_version   (varint)
    0x32,  # field 6 doc_string      (len)
    0x3a,  # field 7 graph           (len)
    0x42,  # field 8 opset_import    (len)
    0x4a,  # field 9 metadata_props  (len)
    0x72,  # field 14 ir_version_prerelease (len)
})


def _check_model_file(path: Path, spec: ModelSpec | None = None) -> tuple[bool, bool]:
    """Return (exists, valid).

    Validity checks (applied in order, cheapest first):
    1. File must exist and be at least _MIN_MODEL_BYTES.
    2. If spec.expected_size is known, file size must match exactly.
    3. First bytes must not be HTML markup (catches auth-redirect saves).
    4. For .onnx files, first byte must be a valid protobuf field tag.
    5. If spec.expected_sha256 is known, SHA-256 must match.
    """
    if not path.exists():
        return False, False
    try:
        size = path.stat().st_size
        if size < _MIN_MODEL_BYTES:
            return True, False
        if spec is not None and spec.expected_size is not None and size != spec.expected_size:
            return True, False
        header = path.read_bytes()[:16]
        if any(header.startswith(sig) or header.lstrip().startswith(sig) for sig in _HTML_SIGNATURES):
            return True, False
        if path.suffix.lower() == ".onnx" and header[0] not in _ONNX_PROTO_FIRST_BYTES:
            return True, False
        if spec is not None and spec.expected_sha256:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != spec.expected_sha256:
                return True, False
    except OSError:
        return True, False
    return True, True


def run(payload: dict) -> dict:
    bootstrap = bootstrap_backend_environment()
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)

    ffmpeg = resolve_external_tool("ffmpeg", payload.get("ffmpeg_path"))
    ffprobe = resolve_external_tool("ffprobe", payload.get("ffprobe_path"))

    spec_map = get_model_spec_map()

    required_models = []
    for name in get_required_model_names():
        path = model_dir / name
        spec = spec_map[name]
        exists, valid = _check_model_file(path, spec)
        required_models.append(
            {
                "name": name,
                "exists": exists and valid,
                "path": str(path),
                "downloadable": bool(spec.url),
                "source": spec.source_label,
                "note": spec.note,
                "valid": valid,
                "auto_fetch": spec.auto_fetch,
            }
        )

    optional_models = []
    for name in get_optional_model_names():
        path = model_dir / name
        spec = spec_map[name]
        exists, valid = _check_model_file(path, spec)
        optional_models.append(
            {
                "name": name,
                "exists": exists and valid,
                "path": str(path),
                "downloadable": bool(spec.url),
                "source": spec.source_label,
                "note": spec.note,
                "valid": valid,
                "auto_fetch": spec.auto_fetch,
            }
        )

    # EraX-specific state: distinguish missing / downloaded_pt / ready so the
    # frontend can show "needs conversion" separately from "fully ready".
    _erax_pt_name = "erax_nsfw_yolo11s.pt"
    _erax_onnx_name = "erax_nsfw_yolo11s.onnx"
    _erax_pt_path = model_dir / _erax_pt_name
    _erax_onnx_path = model_dir / _erax_onnx_name
    _erax_pt_ok = bool(
        next((m for m in optional_models if m["name"] == _erax_pt_name and m["exists"]), None)
    )
    _erax_onnx_ok = bool(
        next((m for m in optional_models if m["name"] == _erax_onnx_name and m["exists"]), None)
    )
    if _erax_onnx_ok:
        _erax_state = "ready"
    elif _erax_pt_ok:
        _erax_state = "downloaded_pt"
    else:
        _erax_state = "missing"

    erax_summary = {
        "actual_model_name": "erax_nsfw_yolo11s",
        "source_repo": "erax-ai/EraX-NSFW-V1.0",
        "local_pt_path": str(_erax_pt_path),
        "local_onnx_path": str(_erax_onnx_path),
        "pt_exists": _erax_pt_ok,
        "onnx_exists": _erax_onnx_ok,
        "state": _erax_state,
        "convertible": ultralytics_available(),
        "ready_for_backend": _erax_onnx_ok,
    }

    # CUDA session test: only run when CUDAExecutionProvider is listed.
    # _minimal_onnx_gpu_test() creates an actual InferenceSession, which is
    # the only reliable way to distinguish "provider listed" from "provider
    # actually works". Skipped on CPU-only systems to avoid wasted latency.
    ort_summary = get_onnxruntime_summary()
    cuda_listed = "CUDAExecutionProvider" in (ort_summary.get("providers") or [])
    cuda_session_test: dict | None = _minimal_onnx_gpu_test() if cuda_listed else None
    cuda_session_ok: bool = cuda_session_test["ok"] if cuda_session_test is not None else False

    runtime_summary = build_path_summary(runtime_dirs)
    unwritable_runtime_paths = [
        key
        for key, entry in runtime_summary.items()
        if entry.get("writable") is False
    ]

    warnings = []
    if not ffmpeg["found"]:
        warnings.append("ffmpeg was not found in configured locations or PATH.")
    if not ffprobe["found"]:
        warnings.append("ffprobe was not found in configured locations or PATH.")
    if not all(item["exists"] for item in required_models):
        warnings.append("One or more required models are missing.")
    if unwritable_runtime_paths:
        warnings.append(
            "One or more runtime folders are not writable: " + ", ".join(unwritable_runtime_paths) + "."
        )

    ready = (
        ffmpeg["found"]
        and ffprobe["found"]
        and all(item["exists"] for item in required_models)
        and not unwritable_runtime_paths
    )

    return success(
        command="doctor",
        data={
            "ready": ready,
            "environment": bootstrap,
            "python": {
                "version": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
            },
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
            "ffmpeg_policy": {
                "development": "Allow explicit path, AUTO_MOSAIC_* env vars, bundled tools/ffmpeg/bin, or PATH.",
                "release": "Bundle ffmpeg and ffprobe under the app runtime and prefer bundled binaries.",
            },
            "models": {"required": required_models, "optional": optional_models},
            "erax": erax_summary,
            "runtime": runtime_summary,
            "onnxruntime": {
                **ort_summary,
                # cuda_session_ok: True only when an actual ONNX InferenceSession
                # with CUDAExecutionProvider was created successfully. This is
                # more reliable than checking ort.get_available_providers() alone,
                # which can list CUDA even when DLLs are missing or incompatible.
                "cuda_session_ok": cuda_session_ok,
                "cuda_session_test": cuda_session_test,
            },
        },
        warnings=warnings,
    )
