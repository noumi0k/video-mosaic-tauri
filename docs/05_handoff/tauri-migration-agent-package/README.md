# Tauri Migration Agent Package

Last updated: 2026-04-14

This folder is the handoff package for an AI agent working on the Tauri migration.

The Tauri implementation is far behind the current PySide6 implementation. Treat the old Tauri state as an early prototype that has not passed even the initial detection review. Do not assume parity.

## Start Here

1. Read [AGENT_PROMPT.md](AGENT_PROMPT.md).
2. Read [GAP_WARNING.md](GAP_WARNING.md).
3. Use [DOCUMENT_MANIFEST.md](DOCUMENT_MANIFEST.md) to decide which copied source documents to read.
4. Treat [source_docs/](source_docs/) as the current PySide6-side source-of-truth snapshot.
5. Treat [stale_tauri_refs/](stale_tauri_refs/) as historical context only.
6. Treat [implementation_logs/](implementation_logs/) as recent execution history, not as the primary source of truth.

The copied docs in `source_docs/` are flattened snapshots. Some links inside those copied files may refer to their original paths in the main `docs/` tree; use [DOCUMENT_MANIFEST.md](DOCUMENT_MANIFEST.md) as the package navigation source.

## Folder Layout

| Folder | Purpose |
|---|---|
| [source_docs/](source_docs/) | Curated copies of current PySide6 docs that define the target behavior |
| [stale_tauri_refs/](stale_tauri_refs/) | Old Tauri-era documents. Useful for context, not authoritative |
| [implementation_logs/](implementation_logs/) | Recent PySide6 implementation completion reports |

## Critical Rule

The migration agent must first inventory the current Tauri implementation, then compare it against the PySide6 snapshot. Implementing from old Tauri docs alone will recreate a much older product state.
