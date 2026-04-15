# Gap Warning

The current PySide6 implementation is substantially ahead of the older Tauri implementation.

Known handoff premise:

- The Tauri side stopped at a much earlier stage.
- It has not passed the initial detection review.
- The feature gap is large enough that the Tauri agent should not do small patch work first.
- The correct first step is inventory and parity mapping.

## Do Not Assume These Exist In Tauri

The Tauri agent must verify each item locally before claiming parity:

- Current detection model management UI.
- Installed-model-only engine selection.
- Model acquisition guidance tab.
- Device / inference settings cleanup.
- Current contour-mode wording and hidden SAM2/tiny implementation naming.
- Manual edit and manual keyframe protection behavior.
- Range detection behavior.
- Track/keyframe continuity and interpolation behavior.
- Export queue and export parity with preview.
- Recovery/autosave behavior.
- Full review workflow described in the PySide6 review docs.

## Expected Migration Approach

1. Inventory the Tauri codebase and UI state.
2. Mark each feature as `missing`, `partial`, `implemented`, or `needs human confirmation`.
3. Compare against [DOCUMENT_MANIFEST.md](DOCUMENT_MANIFEST.md).
4. Build the missing foundation first: domain model, project schema, job model, detection workflow, manual edit protection, export behavior.
5. Only after the core review workflow passes, move to polish and secondary UI parity.

