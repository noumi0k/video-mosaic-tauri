# エンジニア / AI 向けドキュメント入口

このフォルダは、Auto Mosaic を実装・修正する人と AI エージェント向けの入口です。
現行実装に対する作業判断では、このフォルダを古い移行計画や from-scratch 仕様より優先します。

## 正本 / 中核資料

| 目的 | ドキュメント |
|------|--------------|
| 現行実装の責務境界と不変条件 | [current-implementation.md](./current-implementation.md) |
| PySide6 機能差の解消計画 | [pyside6-gap-closure-plan.md](./pyside6-gap-closure-plan.md) |
| 検出ジョブ台帳移行計画 | [job-ledger-migration-plan.md](./job-ledger-migration-plan.md) |
| 実装済み / 未実装の状態 | [../project/unimplemented-features.md](../project/unimplemented-features.md) |
| 安定化後の開発ロードマップ | [../project/pyside6-editing-experience-parity-checklist.md](../project/pyside6-editing-experience-parity-checklist.md) |
| PySide6 UI 参照資料 | [../project/pyside6-ui-structure-reference.md](../project/pyside6-ui-structure-reference.md) |
| 直近の handoff log | [../project/ai-handoff.md](../project/ai-handoff.md) |

## 参考資料

| 目的 | ドキュメント |
|------|--------------|
| 詳細要件の履歴 | [../architecture/requirements-spec-v2.1.md](../architecture/requirements-spec-v2.1.md) |
| from-scratch 方針の履歴 | [../architecture/tauri-from-scratch-spec.md](../architecture/tauri-from-scratch-spec.md) |
| PySide6 との比較 | [../project/pyside6-remaining-tasks.md](../project/pyside6-remaining-tasks.md) |
| Tauri 移行調査アーカイブ | [../tauri-migration/README.md](../tauri-migration/README.md) |

## 作業時の読み順

### 安定化フェーズ中

1. [current-implementation.md](./current-implementation.md)
2. [../project/unimplemented-features.md](../project/unimplemented-features.md)
3. [../project/ai-handoff.md](../project/ai-handoff.md)
4. `AGENTS.md` または `CLAUDE.md`

`ai-handoff.md` は直近の時系列 log です。末尾の next step は古くなるため、現在の実装判断は `current-implementation.md` と `unimplemented-features.md` を優先します。

### 安定化フェーズ完了後

1. [../project/pyside6-editing-experience-parity-checklist.md](../project/pyside6-editing-experience-parity-checklist.md)
2. [../project/pyside6-ui-structure-reference.md](../project/pyside6-ui-structure-reference.md)
3. [../project/unimplemented-features.md](../project/unimplemented-features.md)
4. [current-implementation.md](./current-implementation.md)
5. [../project/ai-handoff.md](../project/ai-handoff.md)

安定化フェーズ完了後の新規開発は、`pyside6-editing-experience-parity-checklist.md` のIDとフェーズを作業単位にします。PySide6版UIは再現対象ではなく、Tauri版UIを設計するための参照資料として扱います。
