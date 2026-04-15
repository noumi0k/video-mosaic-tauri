# Prompt For The Tauri Migration AI Agent

You are working on the Tauri migration of Auto Mosaic.

The current source-of-truth implementation is the PySide6 implementation represented by the documents in this package. The existing Tauri implementation is far behind: it stopped before even passing the initial detection review. Do not assume the Tauri codebase is close to parity.

Your job is not to blindly port old Tauri documents. Your job is to compare the current Tauri implementation against the current PySide6 behavior and close the gap in a controlled order.

## Required First Pass

1. Read `GAP_WARNING.md`.
2. Read `DOCUMENT_MANIFEST.md`.
3. Inspect the Tauri codebase directly.
4. Produce a parity matrix with:
   - Feature
   - PySide6 expected behavior
   - Tauri current behavior
   - Status: `missing`, `partial`, `implemented`, or `needs human confirmation`
   - Files likely involved
   - Test or manual verification needed
5. Do not implement broad UI polish until the initial review workflow is viable.

## Priority Order

1. Project/domain model and persistence parity.
2. Video load, preview, timeline, and editable mask track basics.
3. Detection workflow, model file handling, and installed-model-only engine selection.
4. Manual edit protection and keyframe/track continuity.
5. Range detection and cancellation/progress behavior.
6. Export behavior and preview/export parity.
7. Review guide workflow parity.
8. UI polish and wording.

## Current PySide6 Docs To Treat As Authoritative

Use the docs under `source_docs/` first. Use `implementation_logs/` only to understand recent changes. Use `stale_tauri_refs/` only to understand what the old Tauri plan used to say.

## Output Expected From You

Before implementation:

- A gap matrix.
- A proposed implementation sequence.
- Any human-confirmation questions.

After each implementation slice:

- Files changed.
- Behavior implemented.
- Tests run.
- Remaining gap against PySide6.

