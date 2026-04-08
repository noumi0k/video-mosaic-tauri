from __future__ import annotations

from auto_mosaic.api.commands import doctor as doctor_cmd
from auto_mosaic.api.commands import fetch_models as fetch_models_cmd
from auto_mosaic.application.responses import success
from auto_mosaic.infra.ai.model_catalog import get_model_spec_map
from auto_mosaic.runtime.paths import ensure_runtime_dirs


def _step(step_id: str, label: str, status: str, detail: str) -> dict:
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "detail": detail,
    }


def run(payload: dict) -> dict:
    progress_callback = payload.get("_progress_callback")
    cancel_requested = payload.get("_cancel_requested")
    ensure_not_cancelled = payload.get("_ensure_not_cancelled")

    def report(*, state: str = "running", stage: str, message: str, progress_percent: float | None, is_indeterminate: bool = False, can_cancel: bool = True) -> None:
        if callable(progress_callback):
            progress_callback(
                state=state,
                stage=stage,
                message=message,
                progress_percent=progress_percent,
                is_indeterminate=is_indeterminate,
                can_cancel=can_cancel,
            )

    def guard(message: str = "初期環境セットアップを中断しました。") -> None:
        if callable(cancel_requested) and cancel_requested():
            raise RuntimeError(message)
        if callable(ensure_not_cancelled):
            ensure_not_cancelled(message)

    # P0-2: mode splits the responsibilities of this command cleanly.
    #   "env_only"   = initial environment check (dirs, ffmpeg, ONNX Runtime,
    #                  CUDA probe). NEVER downloads models.
    #   "fetch_only" = model inventory rescan + fetch missing models. Does NOT
    #                  re-check ffmpeg / probe GPU / etc.
    #   "full"       = legacy behavior (default), runs everything.
    mode = str(payload.get("mode") or "full").lower()
    if mode not in ("env_only", "fetch_only", "full"):
        mode = "full"

    # In env_only mode we must never fetch, regardless of flags from old clients.
    if mode == "env_only":
        auto_fetch_required = False
        fetch_optional = False
    else:
        auto_fetch_required = bool(payload.get("auto_fetch_required", True))
        fetch_optional = bool(payload.get("fetch_optional", False))
    paths = payload.get("paths")

    steps: list[dict] = []
    warnings: list[str] = []
    fetch_summary: dict = {}
    environment_summary: dict = {}

    runtime_dirs = ensure_runtime_dirs(paths)
    report(stage="runtime_dirs", message="書き込み先を確認中", progress_percent=12.0)
    steps.append(
        _step(
            "runtime_dirs",
            "Runtime directories",
            "ok",
            f"Prepared data_dir={runtime_dirs.data_dir} and model_dir={runtime_dirs.model_dir}.",
        )
    )

    guard()
    report(stage="doctor", message="環境確認中", progress_percent=28.0, is_indeterminate=True)
    doctor_response = doctor_cmd.run({"paths": paths, **payload})
    doctor_data = doctor_response.get("data", {})

    ffmpeg_ok = bool(doctor_data.get("ffmpeg", {}).get("found"))
    ffprobe_ok = bool(doctor_data.get("ffprobe", {}).get("found"))
    runtime_summary = doctor_data.get("runtime", {})
    unwritable = [name for name, entry in runtime_summary.items() if entry.get("writable") is False]

    if mode in ("env_only", "full"):
        report(stage="ffmpeg", message="ffmpeg / ffprobe を確認中", progress_percent=42.0)
        steps.append(
            _step(
                "ffmpeg",
                "ffmpeg / ffprobe",
                "ok" if ffmpeg_ok and ffprobe_ok else "warning",
                "ffmpeg and ffprobe are available."
                if ffmpeg_ok and ffprobe_ok
                else "ffmpeg or ffprobe is missing. Detection bootstrap can continue, but media workflows remain limited.",
            )
        )

        report(stage="runtime_writable", message="runtime ディレクトリを確認中", progress_percent=56.0)
        steps.append(
            _step(
                "runtime_writable",
                "Writable runtime paths",
                "ok" if not unwritable else "warning",
                "All runtime folders are writable."
                if not unwritable
                else "These runtime folders are not writable: " + ", ".join(unwritable),
            )
        )

    required_models = doctor_data.get("models", {}).get("required", [])
    optional_models = doctor_data.get("models", {}).get("optional", [])
    missing_required = [item for item in required_models if not item.get("exists")]
    missing_optional = [item for item in optional_models if not item.get("exists")]

    # Track before/after counts for the fetch summary regardless of mode so
    # the frontend can display a consistent "x/y" result.
    required_before = f"{len(required_models) - len(missing_required)}/{len(required_models)}"
    optional_before = f"{len(optional_models) - len(missing_optional)}/{len(optional_models)}"

    if mode != "fetch_only":
        report(stage="model_check", message="必須モデルを確認中", progress_percent=68.0)
        steps.append(
            _step(
                "model_check",
                "Detector models",
                "ok" if not missing_required else "warning",
                f"Required ready: {required_before}"
                + (f" | Optional ready: {optional_before}" if optional_models else ""),
            )
        )

    fetch_results: list[dict] = []
    spec_map = get_model_spec_map()

    # In fetch_only mode, fetch missing required models (and optional ones if
    # the caller explicitly listed them via payload["model_names"]), without
    # re-running environment checks.
    should_fetch = auto_fetch_required or mode == "fetch_only"

    if should_fetch:
        guard()
        # Caller may pass an explicit shortlist (e.g. the "Fetch missing
        # models" button) which should take precedence over auto-computed
        # missing lists.
        explicit_names = payload.get("model_names")
        if isinstance(explicit_names, list) and explicit_names:
            names_to_fetch = [str(n) for n in explicit_names]
        else:
            names_to_fetch = [item["name"] for item in missing_required]
            if fetch_optional:
                names_to_fetch.extend(
                    item["name"]
                    for item in missing_optional
                    if spec_map.get(item["name"]) is not None and spec_map[item["name"]].url
                )

        if names_to_fetch:
            report(stage="model_fetch", message="不足モデルを取得中", progress_percent=78.0, is_indeterminate=True)
            fetch_response = fetch_models_cmd.run(
                {
                    "model_names": names_to_fetch,
                    "paths": paths,
                    "_progress_callback": progress_callback,
                    "_cancel_requested": cancel_requested,
                    "_ensure_not_cancelled": ensure_not_cancelled,
                }
            )
            if fetch_response.get("ok"):
                fetch_data = fetch_response.get("data", {})
            else:
                fetch_data = fetch_response.get("error", {}).get("details", {})
                warnings.extend(fetch_response.get("warnings", []))

            fetch_results = fetch_data.get("results", [])
            downloaded = sum(1 for item in fetch_results if item.get("status") == "downloaded")
            skipped = sum(1 for item in fetch_results if item.get("status") == "skipped")
            failed = sum(1 for item in fetch_results if item.get("status") == "failed")

            steps.append(
                _step(
                    "model_fetch",
                    "Fetch missing models",
                    "warning" if failed else "ok",
                    f"downloaded={downloaded}, skipped={skipped}, failed={failed}",
                )
            )
            if failed:
                warnings.append("One or more model downloads failed during setup.")
        else:
            steps.append(
                _step(
                    "model_fetch",
                    "Fetch missing models",
                    "ok",
                    "No downloadable models were missing.",
                )
            )

    onnxruntime = doctor_data.get("onnxruntime", {})
    has_cuda = "CUDAExecutionProvider" in (onnxruntime.get("providers") or [])
    if mode in ("env_only", "full"):
        report(stage="gpu_probe", message="GPU を確認中", progress_percent=92.0)
        steps.append(
            _step(
                "gpu_probe",
                "GPU probe",
                "ok" if has_cuda else "warning",
                "CUDAExecutionProvider is available."
                if has_cuda
                else "CUDA provider is unavailable. CPU fallback remains available.",
            )
        )

    # --- Post-fetch rescan (fetch_only / full): re-read model inventory from
    # the filesystem so before/after counts reflect actual state, not the
    # fetch_models command's view. ---
    required_after = required_before
    optional_after = optional_before
    still_missing: list[str] = [item["name"] for item in missing_required]
    if should_fetch and fetch_results:
        rescan = doctor_cmd.run({"paths": paths, **payload})
        rescan_models = rescan.get("data", {}).get("models", {})
        rescan_required = rescan_models.get("required", [])
        rescan_optional = rescan_models.get("optional", [])
        rescan_missing_required = [item for item in rescan_required if not item.get("exists")]
        rescan_missing_optional = [item for item in rescan_optional if not item.get("exists")]
        required_after = f"{len(rescan_required) - len(rescan_missing_required)}/{len(rescan_required)}"
        optional_after = f"{len(rescan_optional) - len(rescan_missing_optional)}/{len(rescan_optional)}"
        still_missing = [item["name"] for item in rescan_missing_required]
        # Refresh the variables used for "ready" so the aggregate reflects
        # the post-fetch state in full mode.
        missing_required = rescan_missing_required

    if should_fetch:
        downloaded = sum(1 for item in fetch_results if item.get("status") == "downloaded")
        skipped = sum(1 for item in fetch_results if item.get("status") == "skipped")
        failed = sum(1 for item in fetch_results if item.get("status") == "failed")
        fetch_summary = {
            "required_before": required_before,
            "required_after": required_after,
            "optional_before": optional_before,
            "optional_after": optional_after,
            "downloaded": downloaded,
            "failed": failed,
            "skipped": skipped,
            "still_missing": still_missing,
        }

    if mode in ("env_only", "full"):
        environment_summary = {
            "python": doctor_data.get("python", {}),
            "onnxruntime": onnxruntime,
            "cuda": {"available": has_cuda},
            "ffmpeg": doctor_data.get("ffmpeg", {}),
            "ffprobe": doctor_data.get("ffprobe", {}),
            "writable_paths": runtime_summary,
        }

    if mode == "env_only":
        ready = ffmpeg_ok and ffprobe_ok and not unwritable
    elif mode == "fetch_only":
        ready = not still_missing
    else:
        ready = (
            ffmpeg_ok
            and ffprobe_ok
            and not missing_required
            and not unwritable
            and all(step["status"] != "failed" for step in steps)
        )

    if ready:
        summary = "Initial environment setup completed. Required detection prerequisites are ready."
    else:
        summary = "Initial environment setup completed with warnings. Review missing requirements before detection."

    report(stage="finalizing", message="完了処理中", progress_percent=100.0, can_cancel=False)

    return success(
        "setup-environment",
        data={
            "mode": mode,
            "ready": ready,
            "summary": summary,
            "steps": steps,
            "fetch_results": fetch_results,
            "fetch_summary": fetch_summary,
            "environment_summary": environment_summary,
        },
        warnings=[*doctor_response.get("warnings", []), *warnings],
    )
