# AGENTS.md

## Purpose
Auto Mosaic is a fully local, offline desktop app built with a Tauri frontend and a Python backend. The editing model is centered on mask tracks, and AI is only used to generate initial mask candidates that the user can refine.

## Read First
Before starting any task, read these files first:
1. `docs/engineering/current-implementation.md`
2. `docs/project/unimplemented-features.md`
3. `docs/project/ai-handoff.md`

Then use this file as the stable operating rule set.

## System Shape
- Frontend lives in `apps/desktop` and owns the user experience.
- Backend lives in `apps/backend` and owns domain rules, project state, file I/O, and processing logic.
- Tauri talks to Python through `subprocess + CLI + JSON I/O`.
- `stdout` is for machine-readable JSON only.
- Logs, diagnostics, and non-JSON text must go to `stderr`.
- Backend project state is the source of truth. The UI should mirror it, not redefine it.
- The core editing concept is the mask track, not isolated keyframes.
- Manual edits and manual keyframes are protected domain state. Automated processing must not erase them.
- GPU acceleration is an option, not a startup dependency. CPU fallback must always remain available.
- Long-running work should be job-based with progress, cancel, and status handling.

## Non-Negotiable Rules
- Never mix display URLs and raw file paths.
- Treat `asset.localhost` and similar display-only URLs as frontend display values only.
- Persist and pass raw local Windows paths to the backend.
- Do not rely on the frontend to enforce backend invariants.
- Do not let UI convenience distort backend domain design.
- Do not overwrite user-edited tracks or keyframes with re-detection.
- Do not revert export logic to simplistic last-keyframe-hold behavior if segment/state logic is available.
- Do not put logs on `stdout`, even temporarily.
- Do not make GPU/CUDA failure block app startup.
- Prefer preserving existing manual intent over recomputing from scratch.

## Working Style
- Keep changes small and coherent.
- Make backend and domain invariants explicit first, then adapt UI projections.
- Favor clear command boundaries over ad hoc cross-layer calls.
- When a feature spans frontend and backend, define the backend contract first.
- When state is ambiguous, trust the persisted project document and domain rules.
- Avoid adding speculative backlog items to stable rule files.

## Windows and Local Runtime Notes
- Use absolute local Windows paths in persisted project data.
- Be careful with `localhost`, asset URLs, and path encoding.
- Assume the project must run on a third-party Windows PC with different tool availability.
- Keep CPU fallback paths working even when CUDA, drivers, or native extras are missing.

## Verification And Reporting
- Run the smallest relevant tests for the change.
- If tests are not run, say why.
- Report:
  - what changed
  - what was verified
  - what remains risky
  - the next logical step
