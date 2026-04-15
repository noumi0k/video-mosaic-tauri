# Backend Stabilization and Tauri Migration Notes

## Current structure

- `app/ui`: PySide6 widgets, dialogs, worker threads, display state.
- `app/domain`: project models and core editing/export/detection services.
- `app/infra`: detector adapters, video I/O, ffmpeg/ffprobe, storage, device probing.
- `app/application`: runtime service composition for UI-independent orchestration.
- `app/runtime`: path resolution, config location policy, environment diagnostics.
- `scripts`: development setup, environment check, diagnostics, benchmarks.

## Current Tauri blockers

- `MainWindow` previously built detectors, device manager, ffmpeg exporter, and runtime services directly.
- Runtime paths were anchored to the repository layout (`data/`, `models/`) with limited override support.
- Startup checks were UI entry concerns instead of a reusable backend concern.
- There was no stable subprocess-friendly interface for future frontend integration.
- `setup.bat` and `setup.sh` were installer-like shells instead of explicit development setup entry points.

## What was changed now

- Moved runtime service construction into `app/application/runtime_services.py`.
- Added `app/runtime/paths.py` to centralize project paths, user-editable data, logs, settings, and model locations.
- Added `app/runtime/environment.py` and `app/cli.py` so the backend can be queried with structured CLI commands.
- Kept PySide6 as the current UI, but made it consume a composed runtime instead of creating one itself.
- Kept setup focused on development use: create venv, install deps, download models, run environment checks.

## Recommended Tauri integration

- Preferred first step: Python subprocess + CLI + JSON output.
- Reason:
  - Lowest migration cost from the current codebase.
  - Works with the new `app/application` service composition without inventing HTTP or IPC too early.
  - Keeps heavy video/inference logic in Python while Tauri owns the desktop shell.
  - Easier to debug and package incrementally than a local API server.

## Suggested migration phases

1. Keep PySide6 for development while Tauri frontend work starts.
2. Add task-oriented CLI commands that accept JSON input and return JSON output.
3. Move long-running operations behind job-oriented services in `app/application`.
4. Let Tauri call Python as a subprocess for detection/export.
5. Remove PySide6-only flows once Tauri reaches feature parity.

## Dependency inventory

| Dependency | Current usage | Reusable in Tauri | Notes |
|---|---|---|---|
| `PySide6` | Current desktop UI, dialogs, worker threads | No | Replace with Tauri frontend. |
| `opencv-python` | Frame read/write fallback, image processing | Yes | Backend dependency. |
| `numpy` | Frame tensors and geometry data | Yes | Backend dependency. |
| `imageio-ffmpeg` | ffmpeg executable discovery | Yes | Useful until packaging strategy changes. |
| `nudenet` | Detection backend and packaged 320n model | Yes | Backend dependency. |
| `onnxruntime` / `onnxruntime-gpu` | ONNX inference | Yes | Backend dependency; keep provider probing separate from UI. |
| `torch` | Optional CUDA DLL support and EraX/ultralytics runtime | Yes | Optional backend dependency. |
| `ultralytics` | Optional EraX `.pt` runtime/export path | Yes | Optional; avoid hard dependency unless EraX is required. |
| `ffmpeg` | Export encoding and audio mux | Yes | Keep as external tool with explicit path checks. |
| `ffprobe` | Fast metadata read | Yes | Optional because OpenCV fallback exists. |
| `320n.onnx` | Required NudeNet model | Yes | Treat as backend asset. |
| `erax_v1_1.onnx` / `.pt` | Optional detector backend | Yes | Backend asset. |
| `sam2_tiny_*.onnx` | Optional contour quality backend | Yes | Backend asset. |
| Windows shell scripts | Development setup convenience | No | Replace with Tauri packaging / task runner later. |

## Paths and storage policy

- Development defaults remain repository-local for now:
  - `data/config`
  - `data/logs`
  - `data/temp`
  - `data/exports`
  - `models`
- Future packaging/Tauri can override with environment variables:
  - `AUTO_MOSAIC_DATA_DIR`
  - `AUTO_MOSAIC_SETTINGS_DIR`
  - `AUTO_MOSAIC_LOG_DIR`
  - `AUTO_MOSAIC_TEMP_DIR`
  - `AUTO_MOSAIC_EXPORT_DIR`
  - `AUTO_MOSAIC_MODEL_DIR`
  - `AUTO_MOSAIC_FFMPEG_PATH`
  - `AUTO_MOSAIC_FFPROBE_PATH`

## Deferred until Tauri

- Final installer/exe packaging.
- PySide6-specific UX refinement.
- HTTP API layer.
- Native Tauri job management and frontend state synchronization.
