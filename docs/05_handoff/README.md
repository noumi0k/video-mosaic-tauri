# 実装引き継ぎドキュメント

このフォルダは、PySide6 実装から Tauri + React + Python backend など別実装へ移行する可能性に備えた引き継ぎ資料の置き場です。

## 現在の文書

| 文書 | 役割 |
|---|---|
| [pyside6-source-handoff-prompt.md](pyside6-source-handoff-prompt.md) | PySide6 側の AI エージェントに、Tauri 移行用の正本ドキュメント生成を依頼するためのプロンプト |
| [tauri-migration-agent-package/](tauri-migration-agent-package/) | Tauri 移行 AI エージェントへ渡すための文書パッケージ |

## 使い方

1. [pyside6-source-handoff-prompt.md](pyside6-source-handoff-prompt.md) を PySide6 実装側の作業エージェントに渡します。
2. 生成された handoff docs を `docs/05_handoff/pyside6-source/` のような専用サブフォルダに置きます。
3. 旧 Tauri 資料を使う場合は、[../99_archive/tauri_migration_backend_plan.md](../99_archive/tauri_migration_backend_plan.md) と [../99_archive/unimplemented-features-tauri.md](../99_archive/unimplemented-features-tauri.md) を参考資料として扱い、現行 PySide6 実装との差分を必ず確認します。
4. すぐに Tauri 側へ渡す場合は、[tauri-migration-agent-package/README.md](tauri-migration-agent-package/README.md) から読ませます。

## 注意

- 旧 Tauri 資料は現行正本ではありません。
- 移行時の正本は、現行 PySide6 実装から抽出した feature inventory、domain model、job model、export parity、UI workflow、parity test cases です。
- Tauri 移行の判断前に、PySide6 固有 UI と domain / infra の再利用可能部分を分けてください。
