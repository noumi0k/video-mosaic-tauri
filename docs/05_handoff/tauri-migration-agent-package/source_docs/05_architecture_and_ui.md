# Architecture And UI

## Current package structure

- `app/domain/`
  - Business models, label taxonomy, editing/tracking/rendering/export services.
- `app/infra/`
  - Detector adapters, device probing, video I/O, storage, ffmpeg/ffprobe integration.
- `app/application/`
  - Runtime service composition and backend orchestration shared by UI/CLI.
- `app/runtime/`
  - Path policy, environment diagnostics, installer/runtime helpers.
- `app/ui/`
  - PySide6 UI, dialogs, widgets, worker threads, display-only state.
- `app/utils/`
  - Small pure helpers.

## Current entry points

- GUI bootstrap: [app/bootstrap.py](/h:/mosicprogect/mosic2/app/bootstrap.py)
- CLI bootstrap: [app/cli.py](/h:/mosicprogect/mosic2/app/cli.py)
- Development setup: [scripts/setup_dev.py](/h:/mosicprogect/mosic2/scripts/setup_dev.py)
- Environment check: [scripts/check_env.py](/h:/mosicprogect/mosic2/scripts/check_env.py)

## Boundary rules

- `ui` can depend on `application`, `domain`, `infra`, `config`, and `runtime`.
- `application` can depend on `domain`, `infra`, `config`, and `runtime`, but not `ui`.
- `infra` must not depend on `ui` or `application`.
- `domain` must not depend on `ui` or `application`.
- Runtime/configuration should not depend on AI adapter-specific taxonomy in `infra`.

These rules are checked by [tests/test_architecture_boundaries.py](/h:/mosicprogect/mosic2/tests/test_architecture_boundaries.py).

## Important current limitations

- `domain/services` still directly uses some infrastructure implementations. That is acceptable for now, but is a migration target if the backend becomes more modular.
- `MainWindow` still owns a large amount of interaction logic. Runtime construction has been pushed out, but UI event handling is still PySide6-centric.
- Packaging remains development-oriented. Nuitka-based distribution is the planned next step.
