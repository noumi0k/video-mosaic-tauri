from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np

from auto_mosaic.domain.mask_continuity import (
    CandidateBBox,
    WriteAction,
    WriteDecision,
    apply_write_action,
    decide_write,
    evaluate_continuity,
    merge_held_segments,
)
from auto_mosaic.domain.project import Keyframe, MaskTrack, ProjectDocument
from auto_mosaic.domain.track_quality import (
    MATCH_MAX_FRAME_GAP,
    filter_ephemeral_tracks,
    stitch_tracks,
)
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


class DetectVideoError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DetectCancelledError(RuntimeError):
    def __init__(self, message: str = "Detection was cancelled.") -> None:
        super().__init__(message)
        self.code = "DETECT_CANCELLED"
        self.message = message


# ---------------------------------------------------------------------------
# NudeNet v3 class label order (matches 320n.onnx / 640m.onnx output columns)
# ---------------------------------------------------------------------------
# NudeNet v3.4 class labels — read from 320n.onnx model metadata `names`.
# WARNING: class indexes changed between NudeNet versions. These MUST match
# the model file. Verified against 320n.onnx metadata 2024-06-29 (v8.2.46).
_NUDENET_LABELS: list[str] = [
    "FEMALE_GENITALIA_COVERED",   # 0
    "FACE_FEMALE",                # 1
    "BUTTOCKS_EXPOSED",           # 2
    "FEMALE_BREAST_EXPOSED",      # 3
    "FEMALE_GENITALIA_EXPOSED",   # 4
    "MALE_BREAST_EXPOSED",        # 5
    "ANUS_EXPOSED",               # 6
    "FEET_EXPOSED",               # 7
    "BELLY_COVERED",              # 8
    "FEET_COVERED",               # 9
    "ARMPITS_COVERED",            # 10
    "ARMPITS_EXPOSED",            # 11
    "FACE_MALE",                  # 12
    "BELLY_EXPOSED",              # 13
    "MALE_GENITALIA_EXPOSED",     # 14
    "ANUS_COVERED",               # 15
    "FEMALE_BREAST_COVERED",      # 16
    "BUTTOCKS_COVERED",           # 17
]

# P1-1: The product-facing category set is the 5 items below. These are the
# only categories the UI should expose. Each detector backend advertises
# which of these it can actually handle (see _BACKEND_CATEGORY_SUPPORT) and
# anything not supported is silently ignored.
#
# NudeNet v3.4 coverage (verified against 320n.onnx model metadata):
#   - male_genitalia    -> class 14: MALE_GENITALIA_EXPOSED
#   - female_genitalia  -> class 4:  FEMALE_GENITALIA_EXPOSED
#   - female_face       -> class 1:  FACE_FEMALE
#   - male_face         -> class 12: FACE_MALE (added in v3.4)
#   - intercourse       -> not in NudeNet
#
# EraX coverage:
#   - male_genitalia / female_genitalia / intercourse
#   - faces are NOT covered by EraX
_NUDENET_CATEGORY_CLASS_INDEXES: dict[str, list[int]] = {
    "male_genitalia":    [14],   # MALE_GENITALIA_EXPOSED (v3.4 index)
    "female_genitalia":  [4],    # FEMALE_GENITALIA_EXPOSED
    "intercourse":       [],     # not in NudeNet
    "male_face":         [12],   # FACE_MALE (new in v3.4)
    "female_face":       [1],    # FACE_FEMALE
}

# Which product categories each backend can actually produce. The detection
# pipeline uses this to filter the payload so a user cannot ask NudeNet to
# find "intercourse" and then wonder why the run came back empty.
_BACKEND_CATEGORY_SUPPORT: dict[str, set[str]] = {
    "nudenet_320n": {"male_genitalia", "female_genitalia", "female_face", "male_face"},
    "nudenet_640m": {"male_genitalia", "female_genitalia", "female_face", "male_face"},
    "erax_v1_1":    {"male_genitalia", "female_genitalia", "intercourse"},
    # "composite" is the union of what the constituent backends can produce.
    # The orchestration layer selects only the detectors actually needed for
    # the currently-selected categories.
    "composite":    {"male_genitalia", "female_genitalia", "intercourse", "female_face"},
}

# ---------------------------------------------------------------------------
# EraX (erax-anti-nsfw-yolo11s v1.1) labels
# ---------------------------------------------------------------------------
# IMPORTANT: The actual class order of the shipped EraX ONNX export is NOT
# documented in this repo. The list below is an *educated guess* based on
# typical YOLO-NSFW label orderings. Users who know the true order can drop
# a sidecar file `{model_dir}/erax_nsfw_yolo11s.labels.json` containing:
#     {"labels": ["LABEL_A", "LABEL_B", ...]}
# and _load_erax_labels() below will pick it up at runtime. If the guess is
# wrong, detection will still run but will likely report
# empty_reason="filtered_all" via the P0-1 diagnostics (the raw detections
# count will be >0 while the filtered count is 0), giving a clear signal
# that the label mapping needs correcting.
_ERAX_DEFAULT_LABELS: list[str] = [
    "MALE_GENITALIA",          # 0
    "FEMALE_GENITALIA",        # 1
    "INTERCOURSE",             # 2
    "ANUS",                    # 3
    "BREAST",                  # 4
    "BUTTOCKS",                # 5
]

# Map of product-facing category -> substring patterns that should match the
# EraX label string (case-insensitive). This is used by _enabled_class_indexes
# at runtime to compute the index set without hard-coding positions — that way
# a sidecar override that rearranges labels just works.
_ERAX_CATEGORY_LABEL_PATTERNS: dict[str, tuple[str, ...]] = {
    "male_genitalia":   ("male_genitalia", "male genital", "penis"),
    "female_genitalia": ("female_genitalia", "female genital", "vagina", "vulva"),
    # The shipping EraX v1.1 weight uses "make_love" for the intercourse class
    # (verified 2026-04-11 against erax_nsfw_yolo11s.pt model.names). The other
    # patterns are kept so a future re-export with different label naming still
    # resolves cleanly.
    "intercourse":      ("intercourse", "sex", "penetration", "coitus", "make_love"),
}


def _load_erax_labels(model_dir: Path) -> list[str]:
    """Load EraX class labels, preferring a sidecar JSON when present."""
    sidecar = model_dir / "erax_nsfw_yolo11s.labels.json"
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            labels = data.get("labels") if isinstance(data, dict) else None
            if isinstance(labels, list) and all(isinstance(item, str) for item in labels):
                return labels
            _log(f"[erax] invalid labels sidecar at {sidecar}: missing 'labels' array")
        except Exception as exc:
            _log(f"[erax] failed to read labels sidecar {sidecar}: {exc}")
    return list(_ERAX_DEFAULT_LABELS)


def _erax_category_class_indexes(
    labels: list[str],
    enabled_categories: list[str],
) -> set[int]:
    """Resolve product categories to EraX class indexes via label-name matching."""
    indexes: set[int] = set()
    lowered = [label.lower() for label in labels]
    for cat in enabled_categories:
        patterns = _ERAX_CATEGORY_LABEL_PATTERNS.get(cat, ())
        if not patterns:
            continue
        for idx, label in enumerate(lowered):
            if any(pat in label for pat in patterns):
                indexes.add(idx)
    return indexes


def _enabled_class_indexes(
    enabled_categories: list[str] | None,
    backend_name: str = "nudenet_320n",
    labels: list[str] | None = None,
) -> set[int] | None:
    """Return set of allowed class indexes, or None = accept all.

    Categories that are not supported by the requested backend are dropped
    silently here; the UI is responsible for greying them out so the user
    knows why they weren't included. For EraX, `labels` must be supplied so
    we can resolve class indexes via label-name matching.
    """
    if not enabled_categories:
        return None
    supported = _BACKEND_CATEGORY_SUPPORT.get(backend_name, set())
    filtered = [cat for cat in enabled_categories if cat in supported]
    if not filtered:
        return None

    if backend_name == "erax_v1_1":
        erax_labels = labels if labels is not None else list(_ERAX_DEFAULT_LABELS)
        indexes = _erax_category_class_indexes(erax_labels, filtered)
        return indexes if indexes else None

    # NudeNet (320n / 640m) — direct index map
    indexes: set[int] = set()
    for cat in filtered:
        indexes.update(_NUDENET_CATEGORY_CLASS_INDEXES.get(cat, []))
    return indexes if indexes else None


@dataclass
class DetectionSummary:
    tracks: list[MaskTrack]
    analyzed_frames: int
    created_tracks: int
    model_name: str
    device: str
    sampled_frame_indexes: list[int]
    # P0-1 diagnostics: surface what actually happened during detection so that
    # DETECTION_EMPTY failures are distinguishable (env broken vs. model loaded
    # but produced zero detections vs. all filtered out vs. track assembly lost).
    detector_backend: str = ""
    model_path: str = ""
    requested_device: str = ""
    resolved_device: str = ""
    frames_queued: int = 0
    frames_decoded: int = 0
    frames_inferred: int = 0
    raw_detections_total: int = 0
    filtered_detections_total: int = 0
    track_candidates_total: int = 0
    empty_reason: str | None = None
    # Tracks how many detection-keyframes were produced by each contour algorithm.
    # Keys: "contour_quality_frames", "contour_balanced_frames", "contour_fast_frames",
    #        "contour_ellipse_frames", "contour_none_frames".
    contour_mode_counts: dict[str, int] = field(default_factory=dict)

    def diagnostics_dict(self) -> dict[str, Any]:
        """Return all diagnostic fields as a plain dict for JSON responses."""
        return {
            "detector_backend": self.detector_backend,
            "model_name": self.model_name,
            "model_path": self.model_path,
            "requested_device": self.requested_device,
            "resolved_device": self.resolved_device,
            "device": self.device,
            "frames_queued": self.frames_queued,
            "frames_decoded": self.frames_decoded,
            "frames_inferred": self.frames_inferred,
            "analyzed_frames": self.analyzed_frames,
            "raw_detections_total": self.raw_detections_total,
            "filtered_detections_total": self.filtered_detections_total,
            "track_candidates_total": self.track_candidates_total,
            "created_tracks": self.created_tracks,
            "empty_reason": self.empty_reason,
            "contour_mode_counts": self.contour_mode_counts,
        }


@dataclass
class _TrackCursor:
    track: MaskTrack
    last_frame_index: int
    last_bbox: list[float]


@dataclass
class _DetectorContext:
    """Resolved execution context for a single detector inside a composite run."""
    backend_name: str
    model_name: str
    model_path: Path
    session: Any
    device: str
    provider_label: str
    input_size: int
    labels: list[str]
    enabled_class_indexes: set[int] | None
    detector_tracks: list[MaskTrack] = field(default_factory=list)
    track_cursors: list[_TrackCursor] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=lambda: {
        "frames_inferred": 0,
        "raw_detections_total": 0,
        "filtered_detections_total": 0,
        "track_candidates_total": 0,
    })


def _select_backends_for_categories(
    enabled_categories: list[str] | None,
    genitalia_preferred: str = "nudenet_320n",
) -> list[str]:
    """Return the minimal ordered list of backends needed for the categories.

    Rules (P1-3):
      faces       -> NudeNet
      intercourse -> EraX
      genitalia   -> preferred backend (default NudeNet 320n)
    Empty selection defaults to NudeNet 320n so composite at least runs
    something deterministic rather than returning DETECTION_EMPTY with no
    diagnostics.
    """
    if not enabled_categories:
        return ["nudenet_320n"]
    needed: list[str] = []
    cats = set(enabled_categories)
    if "female_face" in cats or "male_face" in cats:
        if "nudenet_320n" not in needed:
            needed.append("nudenet_320n")
    if "intercourse" in cats:
        if "erax_v1_1" not in needed:
            needed.append("erax_v1_1")
    if "male_genitalia" in cats or "female_genitalia" in cats:
        pref = genitalia_preferred if genitalia_preferred in ("nudenet_320n", "nudenet_640m", "erax_v1_1") else "nudenet_320n"
        if pref not in needed:
            needed.append(pref)
    if not needed:
        needed.append("nudenet_320n")
    return needed


def _build_detector_context(
    backend_name: str,
    model_dir: Path,
    payload: dict,
    device_pref: str,
    vram_saving: bool,
    enabled_categories: list[str] | None,
    required_by: list[str] | None = None,
) -> _DetectorContext:
    """Build a fully-resolved detector context or raise DetectVideoError."""
    model_name = _model_name_for_backend(backend_name)
    model_path = model_dir / model_name
    if not model_path.exists():
        raise DetectVideoError(
            "MODEL_NOT_FOUND",
            f"Required detector model is missing: {model_name}",
            {
                "backend": backend_name,
                "model_name": model_name,
                "model_path": str(model_path),
                "required_by": required_by or [],
            },
        )
    session, device = _build_session(model_path, device_pref, vram_saving=vram_saving)
    provider_label = _session_device_label(session.get_providers())

    if backend_name == "erax_v1_1":
        labels = _load_erax_labels(model_dir)
        default_input_size = 640
    else:
        labels = list(_NUDENET_LABELS)
        default_input_size = 640 if "640" in model_name else 320

    raw_res = payload.get("inference_resolution")
    input_size = int(raw_res) if raw_res and int(raw_res) > 0 else default_input_size

    enabled_class_indexes = _enabled_class_indexes(
        enabled_categories if isinstance(enabled_categories, list) else None,
        backend_name=backend_name,
        labels=labels,
    )

    return _DetectorContext(
        backend_name=backend_name,
        model_name=model_name,
        model_path=model_path,
        session=session,
        device=device,
        provider_label=provider_label,
        input_size=input_size,
        labels=labels,
        enabled_class_indexes=enabled_class_indexes,
    )


def _run_frame_on_context(
    ctx: _DetectorContext,
    frame_idx: int,
    frame: np.ndarray,
    confidence_threshold: float,
    contour_mode: str,
    model_dir: Path,
) -> None:
    """Execute one frame of inference on a single detector context."""
    tensor = _preprocess(frame, ctx.input_size)
    try:
        raw_output = ctx.session.run(None, {ctx.session.get_inputs()[0].name: tensor})[0]
    except Exception as exc:
        _log(f"[composite] {ctx.backend_name} inference failed on frame {frame_idx}: {exc}")
        return
    ctx.counters["frames_inferred"] = ctx.counters.get("frames_inferred", 0) + 1
    detections, raw_count = _postprocess(
        raw_output, frame.shape[1], frame.shape[0], ctx.input_size,
        confidence_threshold=confidence_threshold,
        enabled_class_indexes=ctx.enabled_class_indexes,
        labels=ctx.labels,
    )
    ctx.counters["raw_detections_total"] = ctx.counters.get("raw_detections_total", 0) + raw_count
    ctx.counters["filtered_detections_total"] = ctx.counters.get("filtered_detections_total", 0) + len(detections)
    _apply_frame_detections(
        detections, frame_idx, frame, contour_mode, model_dir,
        ctx.detector_tracks, ctx.track_cursors, ctx.counters,
    )


def _run_frame_on_contexts(
    contexts: list[_DetectorContext],
    frame_idx: int,
    frame: np.ndarray,
    confidence_threshold: float,
    contour_mode: str,
    model_dir: Path,
    allow_parallel: bool,
) -> bool:
    """Run all contexts on a single decoded frame.

    Returns the updated `allow_parallel` flag. If parallel execution raises
    (OOM, CUDA error, etc.), it gets permanently downgraded to serial for the
    remainder of the run so we don't re-pay the failure cost per frame.
    """
    if len(contexts) <= 1:
        if contexts:
            _run_frame_on_context(contexts[0], frame_idx, frame, confidence_threshold, contour_mode, model_dir)
        return allow_parallel

    if allow_parallel and all(ctx.device != "cpu" for ctx in contexts):
        try:
            with ThreadPoolExecutor(max_workers=len(contexts)) as ex:
                futures = [
                    ex.submit(
                        _run_frame_on_context, ctx, frame_idx, frame,
                        confidence_threshold, contour_mode, model_dir,
                    )
                    for ctx in contexts
                ]
                for fut in futures:
                    fut.result()
            return True
        except Exception as exc:
            _log(f"[composite] parallel inference failed, falling back to serial: {exc}")
            allow_parallel = False

    for ctx in contexts:
        _run_frame_on_context(ctx, frame_idx, frame, confidence_threshold, contour_mode, model_dir)
    return allow_parallel


def _model_name_for_backend(backend_name: str) -> str:
    """Map a backend key to its on-disk ONNX filename."""
    if backend_name == "nudenet_640m":
        return "640m.onnx"
    if backend_name == "erax_v1_1":
        return "erax_nsfw_yolo11s.onnx"
    return "320n.onnx"


def _resolve_model_path(project: ProjectDocument, payload: dict) -> tuple[Path, str]:
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    # payload "backend" overrides project config (allows modal selection)
    backend_name = str(
        payload.get("backend") or project.detector_config.get("backend", "nudenet_320n")
    )
    model_name = _model_name_for_backend(backend_name)
    model_path = Path(runtime_dirs.model_dir) / model_name
    return model_path, model_name


def _preferred_providers() -> tuple[list[str], str]:
    import onnxruntime as ort  # type: ignore

    providers = ort.get_available_providers()
    if "CUDAExecutionProvider" in providers:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"], "gpu"
    # DirectML: Windows GPU acceleration without a full CUDA installation.
    # Available in onnxruntime >= 1.16 on Windows when the DML runtime is present.
    if "DmlExecutionProvider" in providers:
        return ["DmlExecutionProvider", "CPUExecutionProvider"], "gpu"
    return ["CPUExecutionProvider"], "cpu"


def _session_device(session_providers: list[str]) -> str:
    if "CUDAExecutionProvider" in session_providers:
        return "gpu"
    if "DmlExecutionProvider" in session_providers:
        return "gpu"
    return "cpu"


def _session_device_label(session_providers: list[str]) -> str:
    if "CUDAExecutionProvider" in session_providers:
        return "GPU/CUDA"
    if "DmlExecutionProvider" in session_providers:
        return "GPU/DirectML"
    return "CPU"


def _preload_onnxruntime_cuda_dlls(ort: Any) -> dict[str, Any]:
    preload = {
        "available": hasattr(ort, "preload_dlls"),
        "called": False,
        "ok": False,
        "error": None,
    }
    if not preload["available"]:
        return preload

    try:
        # Match gpu-status diagnostics. onnxruntime-gpu wheels can depend on
        # NVIDIA site-package DLLs that are not on the normal Windows DLL path.
        ort.preload_dlls(directory="")
        preload["called"] = True
        preload["ok"] = True
    except Exception as exc:
        preload["called"] = True
        preload["error"] = str(exc)
        _log(f"[device] onnxruntime CUDA DLL preload failed: {exc}")
    return preload


def _build_session(
    model_path: Path,
    device_pref: str = "auto",
    vram_saving: bool = False,
) -> tuple[Any, str]:
    try:
        import onnxruntime as ort  # type: ignore
    except Exception as exc:
        raise DetectVideoError(
            "MODEL_RUNTIME_MISSING",
            "onnxruntime is unavailable in the active backend environment.",
            {"reason": str(exc)},
        ) from exc

    cuda_preload = _preload_onnxruntime_cuda_dlls(ort)
    preferred, device = _preferred_providers()
    if device_pref == "cpu":
        preferred = ["CPUExecutionProvider"]
        device = "cpu"
    elif device_pref == "cuda":
        if "CUDAExecutionProvider" not in preferred:
            raise DetectVideoError(
                "CUDA_PROVIDER_UNAVAILABLE",
                "CUDAExecutionProvider is unavailable. Retry with CPU or auto mode.",
                {
                    "requested_device": device_pref,
                    "available_providers": ort.get_available_providers(),
                    "cuda_preload": cuda_preload,
                },
            )
        preferred = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        device = "gpu"

    sess_opts = ort.SessionOptions()
    if vram_saving:
        # Reduce memory pressure: disable arena and limit threads
        sess_opts.enable_mem_pattern = False
        sess_opts.enable_cpu_mem_arena = False
        sess_opts.intra_op_num_threads = 1
        sess_opts.inter_op_num_threads = 1

    try:
        session = ort.InferenceSession(str(model_path), sess_options=sess_opts, providers=preferred)
    except Exception as exc:
        code = "MODEL_LOAD_FAILED"
        if device_pref == "cuda":
            code = "CUDA_PROVIDER_UNAVAILABLE"
        raise DetectVideoError(
            code,
            f"Failed to load detector model: {model_path.name}",
            {
                # Structured fields for frontend diagnostics
                "user_requested_device": device_pref,
                "actual_device_used": None,
                "cuda_preflight_ok": "CUDAExecutionProvider" in preferred,
                "fallback_allowed": device_pref != "cuda",
                "provider_list": ort.get_available_providers(),
                "cuda_preload": cuda_preload,
                "failure_reason": str(exc),
                # Legacy fields kept for backward compat
                "requested_device": device_pref,
                "requested_providers": preferred,
                "model_path": str(model_path),
            },
        ) from exc

    session_providers = session.get_providers()
    if device_pref == "cuda" and "CUDAExecutionProvider" not in session_providers:
        raise DetectVideoError(
            "CUDA_PROVIDER_UNAVAILABLE",
            "The detector session fell back to CPU while CUDA was explicitly requested.",
            {
                # Structured fields for frontend diagnostics
                "user_requested_device": device_pref,
                "actual_device_used": "cpu",
                "cuda_preflight_ok": "CUDAExecutionProvider" in preferred,
                "fallback_allowed": False,
                "provider_list": session_providers,
                "cuda_preload": cuda_preload,
                "failure_reason": (
                    "Session was created but CUDAExecutionProvider was not used. "
                    "This typically indicates a missing or incompatible CUDA DLL."
                ),
                # Legacy fields kept for backward compat
                "requested_device": device_pref,
                "requested_providers": preferred,
                "session_providers": session_providers,
                "model_path": str(model_path),
            },
        )
    device = _session_device(session_providers)
    if device == "cpu" and device_pref == "auto" and preferred != ["CPUExecutionProvider"]:
        _log(
            f"[device] auto mode: preferred providers {preferred} but session "
            f"used {session_providers}; proceeding with CPU (degraded success)"
        )
    return session, device


def _preprocess(frame: np.ndarray, input_size: int) -> np.ndarray:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_LINEAR)
    tensor = resized.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))
    return np.expand_dims(tensor, axis=0)


def _postprocess(
    raw_output: np.ndarray,
    frame_width: int,
    frame_height: int,
    input_size: int,
    confidence_threshold: float = 0.28,
    iou_threshold: float = 0.45,
    enabled_class_indexes: set[int] | None = None,
    labels: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (filtered detections after NMS, raw candidate count before NMS).

    The raw count is the number of rows that passed the confidence+category
    filters but have not yet been deduplicated by NMS. Callers use this to
    distinguish "model saw nothing" from "NMS/filter collapsed everything".

    `labels` selects the class-name list used for label strings on each
    detection. Defaults to NudeNet for backward compatibility.
    """
    label_table = labels if labels is not None else _NUDENET_LABELS
    predictions = np.squeeze(raw_output, axis=0)
    if predictions.ndim != 2:
        return [], 0

    if predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.transpose(1, 0)

    boxes: list[list[int]] = []
    scores: list[float] = []
    detections: list[dict[str, Any]] = []

    scale_x = frame_width / float(input_size)
    scale_y = frame_height / float(input_size)

    for row in predictions:
        if row.shape[0] < 5:
            continue
        class_scores = row[4:]
        class_index = int(np.argmax(class_scores))
        score = float(class_scores[class_index])
        if score < confidence_threshold:
            continue

        # Filter by enabled categories
        if enabled_class_indexes is not None and class_index not in enabled_class_indexes:
            continue

        center_x, center_y, width, height = map(float, row[:4])
        x = (center_x - (width / 2.0)) * scale_x
        y = (center_y - (height / 2.0)) * scale_y
        w = width * scale_x
        h = height * scale_y

        x = max(0.0, min(x, frame_width - 1.0))
        y = max(0.0, min(y, frame_height - 1.0))
        w = max(1.0, min(w, frame_width - x))
        h = max(1.0, min(h, frame_height - y))

        boxes.append([int(round(x)), int(round(y)), int(round(w)), int(round(h))])
        scores.append(score)
        label = (
            label_table[class_index]
            if class_index < len(label_table)
            else f"class_{class_index}"
        )
        detections.append(
            {
                "bbox_norm": [
                    x / frame_width,
                    y / frame_height,
                    w / frame_width,
                    h / frame_height,
                ],
                "score": score,
                "class_index": class_index,
                "label": label,
            }
        )

    raw_candidate_count = len(boxes)

    if not boxes:
        return [], raw_candidate_count

    kept = cv2.dnn.NMSBoxes(boxes, scores, confidence_threshold, iou_threshold)
    if kept is None or len(kept) == 0:
        return [], raw_candidate_count

    kept_indexes = []
    for item in kept:
        if isinstance(item, (list, tuple, np.ndarray)):
            kept_indexes.append(int(item[0]))
        else:
            kept_indexes.append(int(item))

    filtered = [detections[index] for index in kept_indexes]
    filtered.sort(key=lambda item: item["bbox_norm"][0])
    return filtered, raw_candidate_count


# ---------------------------------------------------------------------------
# Contour processing helpers
# ---------------------------------------------------------------------------

def _build_polygon_from_bbox(bbox_norm: list[float]) -> list[list[float]]:
    x, y, w, h = bbox_norm
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _apply_contour_fast(
    frame: np.ndarray,
    bbox_px: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> list[list[float]] | None:
    """Fast contour via HSV skin-color segmentation inside the bbox ROI."""
    x, y, w, h = bbox_px
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(frame_width, x + w)
    y2 = min(frame_height, y + h)
    if x2 <= x1 or y2 <= y1:
        return None

    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 20, 70], dtype=np.uint8)
    upper = np.array([20, 170, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    epsilon = 0.02 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    if len(approx) < 3:
        return None

    return [
        [
            round((x1 + float(pt[0][0])) / frame_width, 6),
            round((y1 + float(pt[0][1])) / frame_height, 6),
        ]
        for pt in approx
    ]


def _apply_contour_balanced(
    frame: np.ndarray,
    bbox_px: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> list[list[float]] | None:
    """Balanced contour via GrabCut segmentation inside the bbox ROI."""
    x, y, w, h = bbox_px
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(frame_width, x + w)
    y2 = min(frame_height, y + h)

    # GrabCut needs a minimum ROI and at least 1px border from frame edges.
    if x2 - x1 < 16 or y2 - y1 < 16:
        return None

    # Ensure rect does not touch frame borders (GrabCut treats outside-rect as background).
    rx1 = max(1, x1)
    ry1 = max(1, y1)
    rx2 = min(frame_width - 1, x2)
    ry2 = min(frame_height - 1, y2)
    if rx2 - rx1 < 16 or ry2 - ry1 < 16:
        return None

    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    rect = (rx1, ry1, rx2 - rx1, ry2 - ry1)
    mask_gc = np.zeros(frame.shape[:2], np.uint8)
    try:
        cv2.grabCut(frame, mask_gc, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error as exc:
        _log(f"[contour/balanced] GrabCut failed: {exc}")
        return None

    mask2 = np.where(
        (mask_gc == cv2.GC_FGD) | (mask_gc == cv2.GC_PR_FGD), 255, 0
    ).astype(np.uint8)
    roi_mask = mask2[y1:y2, x1:x2]

    if roi_mask.size == 0 or roi_mask.max() == 0:
        return None

    contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 4:
        return None

    epsilon = 0.015 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    if len(approx) < 3:
        return None

    return [
        [
            round((x1 + float(pt[0][0])) / frame_width, 6),
            round((y1 + float(pt[0][1])) / frame_height, 6),
        ]
        for pt in approx
    ]


# ---------------------------------------------------------------------------
# SAM2 ONNX session cache (keyed by path string pairs so sessions are
# created at most once per model path across all frames in a job).
# ---------------------------------------------------------------------------
_sam2_session_cache: dict[tuple[str, str], tuple[object, object]] = {}


def _get_sam2_sessions(
    encoder_path: Path, decoder_path: Path
) -> tuple[object, object]:
    """Return (encoder_session, decoder_session), loading once and caching."""
    import onnxruntime as ort  # optional dependency

    key = (str(encoder_path), str(decoder_path))
    if key not in _sam2_session_cache:
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        enc = ort.InferenceSession(str(encoder_path), sess_options=opts)
        dec = ort.InferenceSession(str(decoder_path), sess_options=opts)
        _sam2_session_cache[key] = (enc, dec)
    return _sam2_session_cache[key]


_SAM2_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_SAM2_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _apply_contour_quality(
    frame: np.ndarray,
    bbox_px: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
    encoder_path: Path,
    decoder_path: Path,
) -> list[list[float]] | None:
    """
    SAM2 ONNX quality contour: encoder extracts image features, decoder
    segments using the bounding box as a prompt.
    Returns polygon points normalised to [0, 1] frame coordinates,
    or None on any failure (caller falls back to balanced).
    """
    x, y, w, h = bbox_px
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(frame_width, x + w)
    y2 = min(frame_height, y + h)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None

    # --- load sessions (cached) -------------------------------------------
    try:
        enc_sess, dec_sess = _get_sam2_sessions(encoder_path, decoder_path)
    except Exception as exc:
        _log(f"[contour/quality] SAM2 session load failed: {exc}")
        return None

    # --- preprocess image → (1, 3, 1024, 1024) float32 --------------------
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR)
    img = resized.astype(np.float32) / 255.0
    img = (img - _SAM2_MEAN) / _SAM2_STD
    image_tensor = img.transpose(2, 0, 1)[np.newaxis].astype(np.float32)

    # --- encoder -------------------------------------------------------------
    try:
        enc_out = enc_sess.run(None, {"image": image_tensor})
    except Exception as exc:
        _log(f"[contour/quality] SAM2 encoder failed: {exc}")
        return None
    # Look up outputs by name so the result is robust to export-order changes.
    enc_out_names = [o.name for o in enc_sess.get_outputs()]
    enc_out_map = dict(zip(enc_out_names, enc_out))
    try:
        image_embed = enc_out_map["image_embed"]    # (1, 256, 64, 64)
        high_res_0 = enc_out_map["high_res_feats_0"]  # (1, 32, 256, 256)
        high_res_1 = enc_out_map["high_res_feats_1"]  # (1, 64, 128, 128)
    except KeyError as exc:
        _log(f"[contour/quality] SAM2 encoder output missing: {exc}. Available: {enc_out_names}")
        return None

    # --- bounding box prompt (scaled to 1024×1024 encoder space) -----------
    sx = 1024.0 / frame_width
    sy = 1024.0 / frame_height
    point_coords = np.array(
        [[[x1 * sx, y1 * sy], [x2 * sx, y2 * sy]]], dtype=np.float32
    )  # (1, 2, 2)
    point_labels = np.array([[2, 3]], dtype=np.float32)  # (1, 2)
    mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
    has_mask_input = np.array([0], dtype=np.float32)

    # --- decoder -------------------------------------------------------------
    try:
        dec_out = dec_sess.run(
            None,
            {
                "image_embed": image_embed,
                "high_res_feats_0": high_res_0,
                "high_res_feats_1": high_res_1,
                "point_coords": point_coords,
                "point_labels": point_labels,
                "mask_input": mask_input,
                "has_mask_input": has_mask_input,
            },
        )
    except Exception as exc:
        _log(f"[contour/quality] SAM2 decoder failed: {exc}")
        return None

    raw_masks = dec_out[0]      # (1, 3, 256, 256) logits
    iou_scores = dec_out[1]     # (1, 3)

    # --- postprocess mask ----------------------------------------------------
    best_idx = int(np.argmax(iou_scores[0]))
    logit_mask = raw_masks[0, best_idx].astype(np.float32)  # (256, 256)
    prob_mask = 1.0 / (1.0 + np.exp(-logit_mask))           # sigmoid
    binary_mask = (prob_mask > 0.5).astype(np.uint8) * 255

    # Resize from SAM2 output (256×256) to original frame resolution
    full_mask = cv2.resize(
        binary_mask, (frame_width, frame_height), interpolation=cv2.INTER_LINEAR
    )

    # Crop to bbox ROI
    roi_mask = full_mask[y1:y2, x1:x2]
    if roi_mask.size == 0 or roi_mask.max() == 0:
        _log("[contour/quality] SAM2 produced empty mask; falling back")
        return None

    # --- contour → polygon ---------------------------------------------------
    contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 4:
        return None

    epsilon = 0.015 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    if len(approx) < 3:
        return None

    return [
        [
            round((x1 + float(pt[0][0])) / frame_width, 6),
            round((y1 + float(pt[0][1])) / frame_height, 6),
        ]
        for pt in approx
    ]


def _apply_contour(
    frame: np.ndarray,
    bbox_norm: list[float],
    contour_mode: str,
    frame_width: int,
    frame_height: int,
    model_dir: Path,
) -> tuple[str, list[list[float]], str]:
    """
    Apply contour processing to a bbox detection.
    Returns (shape_type, points, actual_mode).

    actual_mode reflects which algorithm produced the result:
      "none"     -> no contour requested
      "fast"     -> HSV segmentation succeeded
      "balanced" -> GrabCut succeeded (or quality fell back to it)
      "quality"  -> SAM2 succeeded
      "ellipse"  -> all contour attempts failed; bbox ellipse returned

    Modes:
      none     -> bbox ellipse
      fast     -> HSV skin segmentation -> polygon, fallback to bbox ellipse
      balanced -> GrabCut segmentation  -> polygon, fallback to bbox ellipse
      quality  -> SAM2 if available, fallback to balanced, fallback to ellipse
    """
    fallback_points = _build_polygon_from_bbox(bbox_norm)

    if contour_mode == "none":
        return "ellipse", fallback_points, "none"

    x_n, y_n, w_n, h_n = bbox_norm
    bbox_px = (
        int(round(x_n * frame_width)),
        int(round(y_n * frame_height)),
        int(round(w_n * frame_width)),
        int(round(h_n * frame_height)),
    )

    if contour_mode == "fast":
        try:
            points = _apply_contour_fast(frame, bbox_px, frame_width, frame_height)
            if points and len(points) >= 3:
                return "polygon", points, "fast"
        except Exception as exc:
            _log(f"[contour/fast] failed, falling back to ellipse: {exc}")
        return "ellipse", fallback_points, "ellipse"

    if contour_mode in ("balanced", "quality"):
        sam2_encoder = model_dir / "sam2_tiny_encoder.onnx"
        sam2_decoder = model_dir / "sam2_tiny_decoder.onnx"
        if contour_mode == "quality" and sam2_encoder.exists() and sam2_decoder.exists():
            try:
                points = _apply_contour_quality(
                    frame, bbox_px, frame_width, frame_height,
                    sam2_encoder, sam2_decoder,
                )
                if points and len(points) >= 3:
                    return "polygon", points, "quality"
                _log("[contour/quality] SAM2 returned no usable polygon; falling back to balanced")
            except Exception as exc:
                _log(f"[contour/quality] unexpected error, falling back to balanced: {exc}")

        try:
            points = _apply_contour_balanced(frame, bbox_px, frame_width, frame_height)
            if points and len(points) >= 3:
                return "polygon", points, "balanced"
        except Exception as exc:
            _log(f"[contour/balanced] failed, falling back to ellipse: {exc}")
        return "ellipse", fallback_points, "ellipse"

    # Unknown mode -> bbox fallback
    return "ellipse", fallback_points, "ellipse"


def _sampled_frame_indexes(
    frame_count: int,
    fps: float,
    sample_every: int = 0,
    max_samples: int = 120,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> list[int]:
    if frame_count <= 0:
        return [0]
    range_start = max(start_frame or 0, 0)
    range_end = min(end_frame or (frame_count - 1), frame_count - 1)
    if range_start > range_end:
        range_start, range_end = 0, frame_count - 1
    if sample_every and sample_every > 0:
        stride = sample_every
    else:
        stride = max(int(round(fps / 2.0)), 1) if fps > 0 else 12
    cap = max(max_samples, 1)
    indexes = list(range(range_start, range_end + 1, stride))
    if indexes[-1] != range_end:
        indexes.append(range_end)
    return indexes[:cap]


_MATCH_MIN_IOU: float = 0.05
"""Minimum IoU for a detection to be considered a candidate match."""

_MATCH_MAX_NORM_DISTANCE: float = 1.75
"""Maximum normalized center distance (distance / max_bbox_dimension)."""


def _build_detector_track(index: int) -> MaskTrack:
    return MaskTrack(
        track_id=f"detector-track-{index + 1}",
        label=f"AI検出 {index + 1}",
        state="detected",
        source="detector",
        visible=True,
        keyframes=[],
    )


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2 = ax1 + aw
    ay2 = ay1 + ah
    bx2 = bx1 + bw
    by2 = by1 + bh

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h
    if intersection <= 0:
        return 0.0

    area_a = max(aw, 0.0) * max(ah, 0.0)
    area_b = max(bw, 0.0) * max(bh, 0.0)
    union = area_a + area_b - intersection
    if union <= 0:
        return 0.0
    return intersection / union


def _bbox_center_distance(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx = ax + (aw / 2.0)
    acy = ay + (ah / 2.0)
    bcx = bx + (bw / 2.0)
    bcy = by + (bh / 2.0)
    return float(np.hypot(acx - bcx, acy - bcy))


def _match_detection_to_track(
    bbox: list[float],
    frame_idx: int,
    cursors: list[_TrackCursor],
    used_track_ids: set[str],
) -> _TrackCursor | None:
    best_cursor: _TrackCursor | None = None
    best_score = float("-inf")

    for cursor in cursors:
        if cursor.track.track_id in used_track_ids:
            continue

        frame_gap = max(frame_idx - cursor.last_frame_index, 0)
        if frame_gap > MATCH_MAX_FRAME_GAP:
            continue

        iou = _bbox_iou(cursor.last_bbox, bbox)
        distance = _bbox_center_distance(cursor.last_bbox, bbox)
        area_scale = max(cursor.last_bbox[2], bbox[2], cursor.last_bbox[3], bbox[3], 1e-6)
        normalized_distance = distance / area_scale

        if iou < _MATCH_MIN_IOU and normalized_distance > _MATCH_MAX_NORM_DISTANCE:
            continue

        score = (iou * 3.0) - normalized_distance - (frame_gap * 0.04)
        if score > best_score:
            best_score = score
            best_cursor = cursor

    return best_cursor


def _apply_frame_detections(
    detections: list[dict[str, Any]],
    frame_idx: int,
    frame: np.ndarray,
    contour_mode: str,
    model_dir: Path,
    detector_tracks: list[MaskTrack],
    track_cursors: list[_TrackCursor],
    counters: dict[str, int] | None = None,
) -> None:
    """Append detections while preserving detector track continuity across frames."""
    used_track_ids: set[str] = set()
    candidates = detections[:8]
    if counters is not None:
        counters["track_candidates_total"] = counters.get("track_candidates_total", 0) + len(candidates)
    for detection in candidates:
        bbox = [round(v, 6) for v in detection["bbox_norm"]]
        shape_type, points, actual_mode = _apply_contour(
            frame, bbox, contour_mode,
            frame.shape[1], frame.shape[0], model_dir,
        )
        if counters is not None:
            counters[f"contour_{actual_mode}_frames"] = (
                counters.get(f"contour_{actual_mode}_frames", 0) + 1
            )
        matched_cursor = _match_detection_to_track(bbox, frame_idx, track_cursors, used_track_ids)
        if matched_cursor is None:
            track = _build_detector_track(len(detector_tracks))
            detector_tracks.append(track)
            matched_cursor = _TrackCursor(
                track=track,
                last_frame_index=int(frame_idx),
                last_bbox=bbox,
            )
            track_cursors.append(matched_cursor)

        # W1-W4: evaluate continuity against the prior keyframe and apply the
        # write decision.  The first detection on a fresh track bypasses
        # continuity (no history) and is always written.
        candidate = CandidateBBox(
            bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
            confidence=float(detection["score"]),
            shape_type=shape_type,
        )
        prior_kf = matched_cursor.track.keyframes[-1] if matched_cursor.track.keyframes else None
        if prior_kf is None:
            # Brand-new track: write the first keyframe unconditionally.
            decision = WriteDecision(action=WriteAction.WRITE_DETECTED)
        else:
            frame_gap = frame_idx - prior_kf.frame_index
            verdict = evaluate_continuity(prior_kf, candidate, frame_gap)
            decision = decide_write(matched_cursor.track, frame_idx, candidate, verdict)

        if decision.action == WriteAction.WRITE_DETECTED:
            # Preserve contour-derived points (richer than W4's bbox-corner
            # fallback).  All other decision paths use apply_write_action.
            matched_cursor.track.keyframes.append(Keyframe(
                frame_index=int(frame_idx),
                shape_type=shape_type,
                bbox=bbox,
                points=points,
                confidence=float(detection["score"]),
                source="detector",
                source_detail="detector_accepted",
            ))
        elif decision.action != WriteAction.SKIP:
            apply_write_action(matched_cursor.track, frame_idx, candidate, decision)

        # Advance cursor so future frames can match this track.
        if decision.action in (WriteAction.WRITE_DETECTED, WriteAction.WRITE_ANCHORED):
            matched_cursor.last_frame_index = int(frame_idx)
            matched_cursor.last_bbox = bbox
        elif decision.action in (WriteAction.EXTEND_HELD, WriteAction.EXTEND_UNCERTAIN):
            # Keep last_bbox as the last known-good position for matching.
            matched_cursor.last_frame_index = int(frame_idx)
        # SKIP: leave cursor unchanged.
        used_track_ids.add(matched_cursor.track.track_id)


def _run_batch(
    session: Any,
    batch: list[tuple[int, np.ndarray]],
    input_size: int,
    confidence_threshold: float,
    enabled_class_indexes: set[int] | None,
    contour_mode: str,
    model_dir: Path,
    detector_tracks: list[MaskTrack],
    track_cursors: list[_TrackCursor],
    counters: dict[str, int] | None = None,
) -> int:
    """
    Run inference on a batch of (frame_index, frame) pairs.
    Returns number of frames successfully analyzed.

    When batch_size=1, runs single-frame inference (current behavior).
    When batch_size>1, attempts true batch inference; falls back to
    per-frame processing if the model does not support dynamic batch dims.
    """
    if not batch:
        return 0

    if len(batch) == 1:
        frame_idx, frame = batch[0]
        tensor = _preprocess(frame, input_size)
        try:
            raw_output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        except Exception:
            return 0
        if counters is not None:
            counters["frames_inferred"] = counters.get("frames_inferred", 0) + 1
        detections, raw_count = _postprocess(
            raw_output, frame.shape[1], frame.shape[0], input_size,
            confidence_threshold=confidence_threshold,
            enabled_class_indexes=enabled_class_indexes,
        )
        if counters is not None:
            counters["raw_detections_total"] = counters.get("raw_detections_total", 0) + raw_count
            counters["filtered_detections_total"] = counters.get("filtered_detections_total", 0) + len(detections)
        _apply_frame_detections(
            detections, frame_idx, frame, contour_mode, model_dir, detector_tracks, track_cursors, counters
        )
        return 1

    # True batch attempt
    tensors = [_preprocess(f, input_size) for _, f in batch]
    batch_tensor = np.concatenate(tensors, axis=0)
    try:
        raw_outputs = session.run(None, {session.get_inputs()[0].name: batch_tensor})
        batch_output = raw_outputs[0]  # expected shape: (N, P, C)
        if counters is not None:
            counters["frames_inferred"] = counters.get("frames_inferred", 0) + len(batch)
        analyzed = 0
        for b_idx, (frame_idx, frame) in enumerate(batch):
            if batch_output.ndim == 3:
                frame_out = batch_output[b_idx : b_idx + 1]
            else:
                frame_out = batch_output
            detections, raw_count = _postprocess(
                frame_out, frame.shape[1], frame.shape[0], input_size,
                confidence_threshold=confidence_threshold,
                enabled_class_indexes=enabled_class_indexes,
            )
            if counters is not None:
                counters["raw_detections_total"] = counters.get("raw_detections_total", 0) + raw_count
                counters["filtered_detections_total"] = counters.get("filtered_detections_total", 0) + len(detections)
            _apply_frame_detections(
                detections, frame_idx, frame, contour_mode, model_dir, detector_tracks, track_cursors, counters
            )
            analyzed += 1
        return analyzed
    except Exception:
        pass

    # Batch failed: fall back to per-frame
    analyzed = 0
    for frame_idx, frame in batch:
        tensor = _preprocess(frame, input_size)
        try:
            raw_output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
            if counters is not None:
                counters["frames_inferred"] = counters.get("frames_inferred", 0) + 1
            detections, raw_count = _postprocess(
                raw_output, frame.shape[1], frame.shape[0], input_size,
                confidence_threshold=confidence_threshold,
                enabled_class_indexes=enabled_class_indexes,
            )
            if counters is not None:
                counters["raw_detections_total"] = counters.get("raw_detections_total", 0) + raw_count
                counters["filtered_detections_total"] = counters.get("filtered_detections_total", 0) + len(detections)
            _apply_frame_detections(
                detections, frame_idx, frame, contour_mode, model_dir, detector_tracks, track_cursors, counters
            )
            analyzed += 1
        except Exception:
            pass
    return analyzed


def _detect_composite_body(
    project: ProjectDocument,
    payload: dict,
    report,
    ensure_not_cancelled,
) -> DetectionSummary:
    """Composite orchestration: shared frame sampling across multiple detectors.

    This path is entered when `payload["backend"] == "composite"`. It selects
    the minimal set of detectors for the requested categories, opens the
    video capture once, decodes each sampled frame once, and runs every
    detector on that shared frame. Tracks from all detectors are merged into
    a single flat list; each detector keeps its own native label so the UI
    can tell which backend produced which mask.
    """
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)

    device_pref = str(payload.get("device") or project.detector_config.get("device", "auto"))
    vram_saving = bool(payload.get("vram_saving_mode", False))
    contour_mode = str(payload.get("contour_mode") or "none")
    # precise_face_contour: forwarded from frontend but not yet used.
    # Planned: add extra SAM2 point prompt for face category detections.
    confidence_threshold = float(payload.get("confidence_threshold", 0.28))
    sample_every = int(payload.get("sample_every") or 0)
    max_samples = int(payload.get("max_samples") or 120)

    enabled_categories = payload.get("enabled_label_categories")
    categories_list = (
        [str(c) for c in enabled_categories] if isinstance(enabled_categories, list) else []
    )
    genitalia_preferred = str(payload.get("genitalia_preferred_backend") or "nudenet_320n")
    backend_names = _select_backends_for_categories(categories_list, genitalia_preferred)

    report("preparing", 2.0, f"Preparing composite detection ({', '.join(backend_names)})")
    ensure_not_cancelled()

    # Build detector contexts. Any missing model raises MODEL_NOT_FOUND
    # enriched with which categories triggered its inclusion.
    contexts: list[_DetectorContext] = []
    for backend_name in backend_names:
        required_by = []
        if backend_name == "erax_v1_1":
            required_by = [c for c in categories_list if c == "intercourse"]
        elif backend_name.startswith("nudenet"):
            required_by = [c for c in categories_list if c in ("female_face", "male_face", "male_genitalia", "female_genitalia")]
        report("loading_model", 8.0, f"Loading detector model: {backend_name}")
        try:
            ctx = _build_detector_context(
                backend_name=backend_name,
                model_dir=model_dir,
                payload=payload,
                device_pref=device_pref,
                vram_saving=vram_saving,
                enabled_categories=categories_list,
                required_by=required_by,
            )
        except DetectVideoError as exc:
            exc.details.setdefault("detector_backend", "composite")
            exc.details.setdefault("composite_backends", backend_names)
            exc.details.setdefault("empty_reason", "model_load_failed")
            raise
        contexts.append(ctx)

    device_labels = sorted({ctx.provider_label for ctx in contexts})
    composite_device_label = "+".join(device_labels) if device_labels else "CPU"

    report("probing_video", 18.0, "Opening source video")
    capture = cv2.VideoCapture(project.video.source_path)
    if not capture.isOpened():
        raise DetectVideoError(
            "VIDEO_OPEN_FAILED",
            "OpenCV could not open the source video for detection.",
            {"source_video": project.video.source_path},
        )

    sampled_indexes = _sampled_frame_indexes(
        project.video.frame_count, project.video.fps,
        sample_every=sample_every, max_samples=max_samples,
        start_frame=payload.get("start_frame"), end_frame=payload.get("end_frame"),
    )
    report("sampling_frames", 28.0, "Sampling frame indexes", current=0, total=len(sampled_indexes))

    frames_decoded = 0
    allow_parallel = True
    try:
        total_samples = len(sampled_indexes)
        for pos, frame_index in enumerate(sampled_indexes):
            ensure_not_cancelled()
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            frames_decoded += 1
            report(
                "running_inference",
                32.0 + ((pos / max(total_samples, 1)) * 55.0),
                f"Running composite inference ({composite_device_label})",
                current=pos,
                total=total_samples,
            )
            allow_parallel = _run_frame_on_contexts(
                contexts, frame_index, frame,
                confidence_threshold, contour_mode, model_dir,
                allow_parallel,
            )
    finally:
        capture.release()

    ensure_not_cancelled()

    # Merge tracks from every context. Each context keeps its own sequential
    # track ids (detector-track-N), so renumber when merging to keep ids unique
    # across backends.
    merged_tracks: list[MaskTrack] = []
    for ctx in contexts:
        for track in ctx.detector_tracks:
            track.keyframes.sort(key=lambda item: item.frame_index)
            merge_held_segments(track)  # W5: normalise adjacent/overlapping same-state segments
        # Stitch and filter per-backend tracks before merging across backends.
        ctx.detector_tracks = stitch_tracks(ctx.detector_tracks)
        ctx.detector_tracks = filter_ephemeral_tracks(ctx.detector_tracks)
        for track in ctx.detector_tracks:
            new_id = f"{ctx.backend_name}-{len(merged_tracks) + 1}"
            track.track_id = new_id
            track.label = f"{ctx.backend_name} {len(merged_tracks) + 1}"
            merged_tracks.append(track)

    # Aggregate counters across contexts for the summary.
    agg_frames_inferred = sum(ctx.counters.get("frames_inferred", 0) for ctx in contexts)
    agg_raw = sum(ctx.counters.get("raw_detections_total", 0) for ctx in contexts)
    agg_filtered = sum(ctx.counters.get("filtered_detections_total", 0) for ctx in contexts)
    agg_track_candidates = sum(ctx.counters.get("track_candidates_total", 0) for ctx in contexts)
    analyzed_frames = max((ctx.counters.get("frames_inferred", 0) for ctx in contexts), default=0)
    agg_contour_mode_counts: dict[str, int] = {}
    for ctx in contexts:
        for k, v in ctx.counters.items():
            if k.startswith("contour_") and k.endswith("_frames"):
                agg_contour_mode_counts[k] = agg_contour_mode_counts.get(k, 0) + v

    report("building_tracks", 92.0, "Building detector tracks", current=len(merged_tracks), total=len(merged_tracks))
    report("finalizing", 96.0, "Finalizing detection result", current=analyzed_frames, total=len(sampled_indexes))

    empty_reason: str | None = None
    if not merged_tracks:
        if frames_decoded == 0:
            empty_reason = "frame_decode_failed"
        elif agg_raw == 0:
            empty_reason = "no_raw_detections"
        elif agg_filtered == 0:
            empty_reason = "filtered_all"
        elif agg_track_candidates > 0:
            empty_reason = "track_assembly_failed"
        else:
            empty_reason = "unknown"

    # For composite, model_name / model_path / device surface the list of
    # backends that actually ran so the UI can explain what happened.
    composite_model_names = ", ".join(ctx.model_name for ctx in contexts)
    composite_model_paths = ", ".join(str(ctx.model_path) for ctx in contexts)
    devices = {ctx.device for ctx in contexts}
    resolved_device = "+".join(sorted(devices)) if devices else "cpu"

    return DetectionSummary(
        tracks=merged_tracks,
        analyzed_frames=analyzed_frames,
        created_tracks=len(merged_tracks),
        model_name=composite_model_names,
        device=resolved_device,
        sampled_frame_indexes=sampled_indexes,
        detector_backend="composite",
        model_path=composite_model_paths,
        requested_device=device_pref,
        resolved_device=resolved_device,
        frames_queued=len(sampled_indexes),
        frames_decoded=frames_decoded,
        frames_inferred=agg_frames_inferred,
        raw_detections_total=agg_raw,
        filtered_detections_total=agg_filtered,
        track_candidates_total=agg_track_candidates,
        empty_reason=empty_reason,
        contour_mode_counts=agg_contour_mode_counts,
    )


def detect_project_video(project: ProjectDocument, payload: dict) -> DetectionSummary:
    progress_callback = payload.get("_progress_callback")
    cancel_requested = payload.get("_cancel_requested")

    def report(stage: str, percent: float, message: str, current: int = 0, total: int = 0) -> None:
        if callable(progress_callback):
            progress_callback(stage=stage, percent=percent, message=message, current=current, total=total)

    def ensure_not_cancelled(message: str = "Detection was cancelled.") -> None:
        if callable(cancel_requested) and cancel_requested():
            raise DetectCancelledError(message)

    if not project.video:
        raise DetectVideoError(
            "SOURCE_VIDEO_MISSING",
            "A source video is required before detection can run.",
        )

    # P1-3: composite backend routes through its own orchestrator that loads
    # only the detectors actually needed for the selected categories and
    # shares frame sampling across them.
    backend_peek = str(
        payload.get("backend") or project.detector_config.get("backend", "nudenet_320n")
    )
    if backend_peek == "composite":
        return _detect_composite_body(project, payload, report, ensure_not_cancelled)

    model_path, model_name = _resolve_model_path(project, payload)
    if not model_path.exists():
        raise DetectVideoError(
            "MODEL_NOT_FOUND",
            f"Required detector model is missing: {model_name}",
            {"model_name": model_name, "model_path": str(model_path)},
        )

    report("preparing", 2.0, "Preparing detection")
    ensure_not_cancelled()

    device_pref = str(payload.get("device") or project.detector_config.get("device", "auto"))
    vram_saving = bool(payload.get("vram_saving_mode", False))
    detector_backend_name = str(
        payload.get("backend") or project.detector_config.get("backend", "nudenet_320n")
    )
    report("loading_model", 10.0, f"Loading detector model: {model_name}")
    try:
        session, device = _build_session(model_path, device_pref, vram_saving=vram_saving)
    except DetectVideoError as exc:
        # Enrich load-failure details with the full diagnostic context we
        # would otherwise return in DetectionSummary so callers can build a
        # single "why is it broken" story for the user.
        enrichment = {
            "detector_backend": detector_backend_name,
            "model_name": model_name,
            "model_path": str(model_path),
            "requested_device": device_pref,
            "empty_reason": "model_load_failed",
        }
        for key, value in enrichment.items():
            exc.details.setdefault(key, value)
        raise
    device_label = _session_device_label(session.get_providers())
    _log(f"[device] session ready: device={device} ({device_label})")
    report("loading_model", 18.0, f"モデル読み込み完了 ({device_label})")

    # inference_resolution: payload overrides model default
    default_input_size = 640 if "640" in model_name else 320
    raw_res = payload.get("inference_resolution")
    input_size = int(raw_res) if raw_res and int(raw_res) > 0 else default_input_size

    # batch_size: forced to 1 in vram_saving mode
    batch_size = max(1, int(payload.get("batch_size") or 1))
    if vram_saving:
        batch_size = 1

    # contour_mode: none / fast / balanced / quality
    contour_mode = str(payload.get("contour_mode") or "none")
    # precise_face_contour: forwarded from frontend but not yet used.
    # Planned: add extra SAM2 point prompt for face category detections.

    # enabled_label_categories -> allowed NudeNet class indexes (None = accept all)
    enabled_categories = payload.get("enabled_label_categories")
    enabled_class_indexes = _enabled_class_indexes(
        enabled_categories if isinstance(enabled_categories, list) else None,
        backend_name=detector_backend_name,
    )

    # model_dir for quality contour (SAM2 check)
    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)

    report("probing_video", 20.0, "Opening source video")
    capture = cv2.VideoCapture(project.video.source_path)
    if not capture.isOpened():
        raise DetectVideoError(
            "VIDEO_OPEN_FAILED",
            "OpenCV could not open the source video for detection.",
            {"source_video": project.video.source_path},
        )

    confidence_threshold = float(payload.get("confidence_threshold", 0.28))
    sample_every = int(payload.get("sample_every") or 0)
    max_samples = int(payload.get("max_samples") or 120)
    sampled_indexes = _sampled_frame_indexes(
        project.video.frame_count, project.video.fps,
        sample_every=sample_every, max_samples=max_samples,
        start_frame=payload.get("start_frame"), end_frame=payload.get("end_frame"),
    )
    report("sampling_frames", 30.0, "Sampling frame indexes", current=0, total=len(sampled_indexes))
    detector_tracks: list[MaskTrack] = []
    track_cursors: list[_TrackCursor] = []
    analyzed_frames = 0
    frames_decoded = 0
    counters: dict[str, int] = {
        "frames_inferred": 0,
        "raw_detections_total": 0,
        "filtered_detections_total": 0,
        "track_candidates_total": 0,
    }

    try:
        current_batch: list[tuple[int, np.ndarray]] = []
        processed_samples = 0
        total_samples = len(sampled_indexes)
        for frame_index in sampled_indexes:
            ensure_not_cancelled()
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                processed_samples += 1
                continue
            frames_decoded += 1
            current_batch.append((frame_index, frame))
            if len(current_batch) >= batch_size:
                report(
                    "running_inference",
                    35.0 + ((processed_samples / max(total_samples, 1)) * 50.0),
                    f"推論実行中 ({device_label})",
                    current=processed_samples,
                    total=total_samples,
                )
                analyzed_frames += _run_batch(
                    session, current_batch, input_size, confidence_threshold,
                    enabled_class_indexes, contour_mode, model_dir, detector_tracks, track_cursors,
                    counters=counters,
                )
                processed_samples += len(current_batch)
                current_batch = []
        if current_batch:
            report(
                "running_inference",
                35.0 + ((processed_samples / max(total_samples, 1)) * 50.0),
                f"推論実行中 ({device_label})",
                current=processed_samples,
                total=total_samples,
            )
            analyzed_frames += _run_batch(
                session, current_batch, input_size, confidence_threshold,
                enabled_class_indexes, contour_mode, model_dir, detector_tracks, track_cursors,
                counters=counters,
            )
            processed_samples += len(current_batch)
    finally:
        capture.release()

    ensure_not_cancelled()
    report("building_tracks", 90.0, "Building detector tracks", current=len(detector_tracks), total=len(detector_tracks))
    for track in detector_tracks:
        track.keyframes.sort(key=lambda item: item.frame_index)
        merge_held_segments(track)  # W5: normalise adjacent/overlapping same-state segments

    # Post-detection track quality: stitch fragments then filter ephemeral.
    detector_tracks = stitch_tracks(detector_tracks)
    detector_tracks = filter_ephemeral_tracks(detector_tracks)

    report("finalizing", 96.0, "Finalizing detection result", current=analyzed_frames, total=len(sampled_indexes))

    # Decide why the result is empty so the UI can tell the user what actually
    # went wrong instead of just "DETECTION_EMPTY".
    empty_reason: str | None = None
    if not detector_tracks:
        if frames_decoded == 0:
            empty_reason = "frame_decode_failed"
        elif counters["raw_detections_total"] == 0:
            empty_reason = "no_raw_detections"
        elif counters["filtered_detections_total"] == 0:
            empty_reason = "filtered_all"
        elif counters["track_candidates_total"] > 0:
            empty_reason = "track_assembly_failed"
        else:
            empty_reason = "unknown"

    return DetectionSummary(
        tracks=detector_tracks,
        analyzed_frames=analyzed_frames,
        created_tracks=len(detector_tracks),
        model_name=model_name,
        device=device,
        sampled_frame_indexes=sampled_indexes,
        detector_backend=detector_backend_name,
        model_path=str(model_path),
        requested_device=device_pref,
        resolved_device=device,
        frames_queued=len(sampled_indexes),
        frames_decoded=frames_decoded,
        frames_inferred=counters["frames_inferred"],
        raw_detections_total=counters["raw_detections_total"],
        filtered_detections_total=counters["filtered_detections_total"],
        track_candidates_total=counters["track_candidates_total"],
        empty_reason=empty_reason,
        contour_mode_counts={
            k: v for k, v in counters.items()
            if k.startswith("contour_") and k.endswith("_frames")
        },
    )
