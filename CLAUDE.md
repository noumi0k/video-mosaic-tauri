# CLAUDE.md

## Project
Auto Mosaic is a fully local/offline Tauri desktop app with a Python backend. The primary editing model is the mask track, and automatic detection only proposes starting points for user editing.

## Start Here
Read these first:
1. `docs/engineering/current-implementation.md`
2. `docs/project/unimplemented-features.md`
3. `docs/project/ai-handoff.md`
4. This file for stable Claude-specific operating rules

## Non-Negotiables
- Use `subprocess + CLI + JSON I/O` for Tauri ↔ Python integration.
- Keep `stdout` JSON-only.
- Send logs and diagnostics to `stderr`.
- Treat backend project state as authoritative.
- Protect manual edits and manual keyframes from automated replacement.
- Keep CPU fallback available even if GPU/CUDA is broken.
- Use jobs for long-running work.
- Keep raw Windows paths in the backend; `asset.localhost` is display-only.

## Current Focus
- Keep the implemented persistent mask track and segment/state behavior from regressing.
- Keep detect/export behavior safe around manual edits.
- Keep long-running work job-based with progress, cancel, and status.
- Use `docs/engineering/current-implementation.md` as the current source of truth; treat older architecture docs as references.

## Working Style
- Prefer domain-first fixes over UI-first hacks.
- If a change affects state, make the backend rules explicit before polishing the view.
- Keep the scope narrow and avoid unrelated cleanup.
- When touching detection, export, or project persistence, assume manual edits are precious and must survive.

## Scope Control
- Do not expand into feature work beyond the requested fix.
- Do not rewrite adjacent systems unless they block the task.
- Do not add speculative backlog details here; use `docs/project/unimplemented-features.md` for that.
- Do not move invariant enforcement into the frontend.

## Test Expectations
- Run the smallest meaningful tests for the touched area.
- Prefer focused backend tests for state and CLI changes.
- If tests cannot be run, explain the blocker clearly.

## Final Report Format
1. Changed files
2. Checks run
3. Important behavior changes
4. Remaining risks or follow-ups
