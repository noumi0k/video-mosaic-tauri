from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from auto_mosaic.application.responses import failure, success
from auto_mosaic.infra.ai.model_catalog import ONNX_MAGIC_BYTES, ModelSpec, get_model_spec_map
from auto_mosaic.runtime.paths import ensure_runtime_dirs


_HTML_SIGNATURES = (b"<!DOCTYPE", b"<html", b"<!doctype")
_GIT_LFS_SIGNATURE = b"version https://git-lfs.github.com"
_MIN_MODEL_BYTES = 1024


class ModelFetchCancelled(Exception):
    pass


def _verify_downloaded_file(path: Path, spec: ModelSpec | None = None) -> None:
    """Verify a downloaded file before it is promoted to its final path.

    Raises ValueError with a descriptive message if any check fails.
    Checks are applied cheapest-first:
    1. File exists and is at least _MIN_MODEL_BYTES.
    2. First bytes are not HTML markup (auth-redirect / error page).
    3. Magic bytes match spec.valid_magic_bytes (or ONNX_MAGIC_BYTES for
       .onnx files when spec is absent); skipped when spec.valid_magic_bytes
       is explicitly None (e.g. PyTorch .pt files).
    4. File size matches spec.expected_size when known.
    5. SHA-256 matches spec.expected_sha256 when known.
    """
    if not path.exists():
        raise ValueError(f"File does not exist: {path}")

    size = path.stat().st_size
    if size < _MIN_MODEL_BYTES:
        raise ValueError(
            f"File is too small ({size} bytes); minimum {_MIN_MODEL_BYTES} bytes expected."
            " Likely a partial download or an error-page response."
        )

    header = path.read_bytes()[:16]

    if any(header.startswith(sig) or header.lstrip().startswith(sig) for sig in _HTML_SIGNATURES):
        raise ValueError(
            "Downloaded file is an HTML page, not a model file."
            " The server returned an authentication error or redirect."
            " Check the download URL and required request headers."
        )

    # Git LFS pointer detection: the file is a ~130-byte text pointer,
    # not the actual binary model.  Re-download with proper LFS handling.
    head_bytes = path.read_bytes()[:256]
    if _GIT_LFS_SIGNATURE in head_bytes:
        raise ValueError(
            "Downloaded file is a Git LFS pointer, not the actual model binary."
            " Use the GitHub Releases API asset URL instead of the raw file URL."
        )

    if spec is not None:
        magic = spec.valid_magic_bytes          # None means skip the check
    else:
        magic = ONNX_MAGIC_BYTES if path.suffix.lower() == ".onnx" else None

    if magic is not None and header[0] not in magic:
        raise ValueError(
            f"File header byte 0x{header[0]:02x} is not a recognised magic byte"
            f" for this model type."
            " The file may be corrupt or in an unexpected format."
        )

    if spec is not None and spec.expected_size is not None and size != spec.expected_size:
        raise ValueError(
            f"File size {size} bytes does not match expected {spec.expected_size} bytes."
            " The download may be incomplete or the upstream asset was updated."
        )

    if spec is not None and spec.expected_sha256:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != spec.expected_sha256:
            raise ValueError(
                f"SHA-256 checksum mismatch."
                f" Expected {spec.expected_sha256},"
                f" got {digest}."
            )


def _download_to_path(
    url: str,
    target_path: Path,
    *,
    request_headers: dict[str, str] | None = None,
    progress_callback=None,
    cancel_requested=None,
    model_name: str | None = None,
    model_index: int | None = None,
    model_total: int | None = None,
    spec: ModelSpec | None = None,
) -> int:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    total_bytes = 0
    try:
        req = urllib.request.Request(url, headers=request_headers or {})
        with urllib.request.urlopen(req, timeout=120) as response, tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".download",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type.lower():
                raise ValueError(
                    f"URL が HTML ページを返しました（認証エラーまたはリンク切れの可能性）。"
                    f" Content-Type: {content_type} / URL: {url}"
                )
            expected_bytes = response.headers.get("Content-Length")
            try:
                expected_total = int(expected_bytes) if expected_bytes else None
            except ValueError:
                expected_total = None
            if callable(progress_callback):
                progress_callback(
                    stage="downloading",
                    message=f"{model_name or target_path.name} を取得中",
                    progress_percent=0.0 if expected_total else None,
                    is_indeterminate=expected_total is None,
                    current=model_index,
                    total=model_total,
                    extra={
                        "model_name": model_name or target_path.name,
                        "bytes_downloaded": 0,
                        "bytes_total": expected_total,
                    },
                )
            while True:
                if callable(cancel_requested) and cancel_requested():
                    raise ModelFetchCancelled(f"{model_name or target_path.name} の取得を中断しました。")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                total_bytes += len(chunk)
                if callable(progress_callback):
                    progress_percent = None
                    is_indeterminate = True
                    if expected_total and expected_total > 0:
                        progress_percent = (total_bytes / expected_total) * 100.0
                        is_indeterminate = False
                    progress_callback(
                        stage="downloading",
                        message=f"{model_name or target_path.name} を取得中",
                        progress_percent=progress_percent,
                        is_indeterminate=is_indeterminate,
                        current=model_index,
                        total=model_total,
                        extra={
                            "model_name": model_name or target_path.name,
                            "bytes_downloaded": total_bytes,
                            "bytes_total": expected_total,
                        },
                    )
            handle.flush()
            os.fsync(handle.fileno())

        # Verify integrity of the temp file BEFORE promoting it to the
        # final path.  If verification fails, the temp file is deleted and
        # the target is never touched.
        _verify_downloaded_file(temp_path, spec)
        temp_path.replace(target_path)
        return total_bytes
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def run(payload: dict) -> dict:
    progress_callback = payload.get("_progress_callback")
    cancel_requested = payload.get("_cancel_requested")
    ensure_not_cancelled = payload.get("_ensure_not_cancelled")

    def report(**kwargs):
        if callable(progress_callback):
            progress_callback(**kwargs)

    def guard(message: str = "モデル取得を中断しました。") -> None:
        if callable(cancel_requested) and cancel_requested():
            raise ModelFetchCancelled(message)
        if callable(ensure_not_cancelled):
            ensure_not_cancelled(message)

    requested_names = payload.get("model_names")
    if not isinstance(requested_names, list) or not requested_names:
        return failure(
            "fetch-models",
            "MODEL_LIST_REQUIRED",
            "Provide at least one model name.",
        )

    runtime_dirs = ensure_runtime_dirs(payload.get("paths"))
    model_dir = Path(runtime_dirs.model_dir)
    spec_map = get_model_spec_map()
    results: list[dict] = []
    warnings: list[str] = []
    total_models = len(requested_names)

    for index, raw_name in enumerate(requested_names, start=1):
        guard()
        if not isinstance(raw_name, str) or not raw_name.strip():
            results.append(
                {
                    "name": str(raw_name),
                    "status": "failed",
                    "message": "Model name must be a non-empty string.",
                    "path": None,
                }
            )
            continue

        name = raw_name.strip()
        spec = spec_map.get(name)
        target_path = model_dir / name
        report(
            stage="model_check",
            message=f"{name} を確認中",
            progress_percent=((index - 1) / max(total_models, 1)) * 100.0,
            is_indeterminate=False,
            current=index - 1,
            total=total_models,
            extra={"model_name": name},
        )
        if spec is None:
            results.append(
                {
                    "name": name,
                    "status": "failed",
                    "message": "Unknown model name.",
                    "path": str(target_path),
                }
            )
            continue

        if target_path.exists():
            try:
                _verify_downloaded_file(target_path, spec)
                # Integrity check passed — the installed file is good.
                results.append(
                    {
                        "name": name,
                        "status": "skipped",
                        "message": "Already available.",
                        "path": str(target_path),
                        "source": spec.source_label,
                    }
                )
                continue
            except ValueError:
                # File is present but broken — fall through to re-download.
                pass

        if not spec.url:
            note = spec.note or "This model is not directly downloadable in the review build."
            warnings.append(note)
            results.append(
                {
                    "name": name,
                    "status": "skipped",
                    "message": note,
                    "path": str(target_path),
                    "source": spec.source_label,
                }
            )
            continue

        try:
            downloaded_bytes = _download_to_path(
                spec.url,
                target_path,
                request_headers=spec.request_headers or None,
                progress_callback=report,
                cancel_requested=cancel_requested,
                model_name=name,
                model_index=index,
                model_total=total_models,
                spec=spec,
            )
            # Verification was already performed inside _download_to_path
            # before the temp file was promoted.  This progress event is kept
            # for UI parity; no additional verification step is needed here.
            report(
                stage="verifying",
                message=f"{name} を検証中",
                progress_percent=(index / max(total_models, 1)) * 100.0,
                is_indeterminate=False,
                current=index,
                total=total_models,
                extra={"model_name": name},
            )
            results.append(
                {
                    "name": name,
                    "status": "downloaded",
                    "message": "Downloaded and verified successfully.",
                    "path": str(target_path),
                    "bytes": downloaded_bytes,
                    "source": spec.source_label,
                }
            )
        except ModelFetchCancelled:
            raise
        except Exception as exc:
            results.append(
                {
                    "name": name,
                    "status": "failed",
                    "message": str(exc),
                    "path": str(target_path),
                    "source": spec.source_label,
                }
            )

    # After download loop: if EraX PT was just downloaded and ultralytics is
    # available, attempt automatic ONNX conversion within this job.
    _ERAX_PT = "erax_nsfw_yolo11s.pt"
    _ERAX_ONNX = "erax_nsfw_yolo11s.onnx"
    erax_just_downloaded = any(
        r["name"] == _ERAX_PT and r["status"] == "downloaded" for r in results
    )
    if erax_just_downloaded and not (model_dir / _ERAX_ONNX).exists():
        guard()
        from auto_mosaic.infra.ai.model_converter import convert_erax_pt_to_onnx, ultralytics_available  # noqa: PLC0415
        if ultralytics_available():
            report(
                stage="converting",
                message="EraX PT → ONNX 変換中 (ultralytics)",
                progress_percent=None,
                is_indeterminate=True,
                current=None,
                total=None,
                extra={"model_name": _ERAX_ONNX},
            )
            conv_result = convert_erax_pt_to_onnx(model_dir / _ERAX_PT, model_dir / _ERAX_ONNX)
            if conv_result.get("ok"):
                results.append({
                    "name": _ERAX_ONNX,
                    "status": "converted",
                    "message": "Converted from PT successfully.",
                    "path": conv_result.get("onnx_path"),
                })
            else:
                warnings.append(
                    f"EraX ONNX 変換失敗: {conv_result.get('reason') or 'unknown error'}"
                )
                results.append({
                    "name": _ERAX_ONNX,
                    "status": "failed",
                    "message": f"Conversion failed: {conv_result.get('reason')}",
                    "path": str(model_dir / _ERAX_ONNX),
                })
        else:
            warnings.append(
                "ultralytics が未インストールのため EraX の ONNX 変換をスキップしました。"
                " pip install ultralytics を実行後、setup-erax action='convert' で変換できます。"
            )

    downloaded = sum(1 for item in results if item["status"] == "downloaded")
    skipped = sum(1 for item in results if item["status"] == "skipped")
    failed = sum(1 for item in results if item["status"] == "failed")

    report(
        stage="finalizing",
        message="取得結果を整理中",
        progress_percent=100.0,
        is_indeterminate=False,
        can_cancel=False,
        current=total_models,
        total=total_models,
    )

    if failed:
        failed_names = [item["name"] for item in results if item["status"] == "failed"]
        error_msg = f"次のモデルの取得に失敗しました: {', '.join(failed_names)}"
        _SAM2 = {"sam2_tiny_encoder.onnx", "sam2_tiny_decoder.onnx"}
        requested_set = set(requested_names)
        if _SAM2 & set(failed_names) and _SAM2 <= requested_set:
            error_msg += " (SAM2 は encoder と decoder の両方が必要です)"
        return failure(
            "fetch-models",
            "MODEL_FETCH_FAILED",
            error_msg,
            details={
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
                "results": results,
                "model_dir": str(model_dir),
            },
            warnings=warnings,
        )

    return success(
        "fetch-models",
        data={
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
            "results": results,
            "model_dir": str(model_dir),
        },
        warnings=warnings,
    )
