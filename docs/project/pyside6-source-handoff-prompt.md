# PySide6 Source Handoff Prompt

Last updated: 2026-04-14

Use this prompt for the AI agent working in the PySide6 implementation when
preparing source-of-truth documents for the Tauri project.

## Required Documents

Ask the PySide6-side agent to produce these documents:

1. `PY_SIDE6_FEATURE_INVENTORY.md`
   - Complete implemented feature list.
   - Feature status: implemented, partial, broken, deprecated.
   - User-facing workflow for each feature.
   - Important UI entry points and shortcuts.
   - Known edge cases.

2. `PY_SIDE6_DOMAIN_MODEL.md`
   - Project file schema.
   - Mask track schema.
   - Keyframe schema.
   - Segment/lifetime/tracking concepts.
   - Manual edit and lock semantics.
   - Export preset schema.
   - Migration-sensitive fields.

3. `PY_SIDE6_JOB_AND_PROCESSING_MODEL.md`
   - Detect workflow.
   - Tracking workflow.
   - Export workflow.
   - Progress/cancel/error behavior.
   - Worker/process/thread model.
   - Intermediate artifacts and cleanup rules.

4. `PY_SIDE6_DETECTION_AND_MODEL_CONFIG.md`
   - Detector backends.
   - Model file names and expected locations.
   - Labels/categories.
   - Thresholds and defaults.
   - GPU/CPU behavior.
   - Fallback behavior.

5. `PY_SIDE6_EXPORT_PARITY_SPEC.md`
   - Exact export behavior.
   - Segment/state rendering rules.
   - Mosaic strength mapping.
   - Resolution/bitrate/audio rules.
   - FFmpeg/OpenCV fallback behavior.
   - Known differences from the Tauri implementation if any.

6. `PY_SIDE6_UI_WORKFLOW_SPEC.md`
   - Main screen workflow.
   - Timeline behavior.
   - Canvas editing behavior.
   - Inspector behavior.
   - Keyboard shortcuts.
   - Save/open/autosave behavior.
   - Warnings and confirmation dialogs.

7. `PY_SIDE6_PARITY_TEST_CASES.md`
   - Minimal fixture projects.
   - Manual edit preservation scenarios.
   - Range detect scenarios.
   - Export scenarios.
   - Model missing/broken scenarios.
   - Cancel/interruption scenarios.
   - Expected output for each scenario.

8. `PY_SIDE6_KNOWN_BUGS_AND_DESIGN_DEBTS.md`
   - Known bugs.
   - Fragile assumptions.
   - Behaviors that should not be ported.
   - Behaviors that should be preserved exactly.

## Prompt To Send To The PySide6-Side Agent

```text
You are working in the existing PySide6 Auto Mosaic implementation. The goal is
to produce source-of-truth handoff documents for rebuilding or completing the
Tauri + React + Python backend version.

Do not modify application code unless necessary to inspect behavior. Focus on
documentation. Read the PySide6 codebase and produce the following files in a
handoff_docs/ directory:

1. PY_SIDE6_FEATURE_INVENTORY.md
2. PY_SIDE6_DOMAIN_MODEL.md
3. PY_SIDE6_JOB_AND_PROCESSING_MODEL.md
4. PY_SIDE6_DETECTION_AND_MODEL_CONFIG.md
5. PY_SIDE6_EXPORT_PARITY_SPEC.md
6. PY_SIDE6_UI_WORKFLOW_SPEC.md
7. PY_SIDE6_PARITY_TEST_CASES.md
8. PY_SIDE6_KNOWN_BUGS_AND_DESIGN_DEBTS.md

Important constraints:
- Be concrete. Reference exact files, classes, functions, and method names.
- Separate implemented behavior from intended behavior.
- Mark uncertain points explicitly as "needs human confirmation".
- Capture defaults and constants, not just feature names.
- For project data, include example JSON snippets for project, track, keyframe,
  detector config, export preset, and any job/progress state if present.
- For workflows, describe the user action, code path, state mutation, persisted
  data, and expected UI feedback.
- For detection/export, document cancellation, progress reporting, failure
  behavior, and fallback behavior.
- For manual edits, document exactly when AI/detection is allowed to replace
  tracks/keyframes and when it must preserve them.
- For export, document segment/state rendering rules and do not reduce behavior
  to last-keyframe-hold unless the PySide6 implementation actually does that.
- For known bugs, distinguish "bug to avoid porting" from "quirk users rely on".

Expected output style:
- Write in Markdown.
- Use tables for schema fields and feature matrices.
- Include file references for every non-obvious claim.
- Keep each document self-contained enough that a different agent can implement
  from it without reading the entire PySide6 repository first.

After writing the documents, provide a short summary:
- What documents were created.
- Which areas are most important for Tauri parity.
- Which areas still need human confirmation.
- Which PySide6 behaviors should not be copied.
```

## How To Use The Result In This Tauri Project

After the PySide6-side documents are created:

1. Copy only the handoff documents into this repository under
   `docs/pyside6-source/`.
2. Compare them with `docs/engineering/current-implementation.md`.
3. Convert gaps into `docs/project/unimplemented-features.md`.
4. Do not add speculative backlog items to `AGENTS.md` or `CLAUDE.md`.
5. Preserve the Tauri project rules:
   - Backend state is source of truth.
   - Raw Windows paths stay in backend data.
   - `asset.localhost` is display-only.
   - Long-running work is job-based.
   - Manual edits and manual keyframes are protected.

