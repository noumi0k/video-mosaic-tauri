# Auto Mosaic ドキュメントハブ

最終更新: 2026-04-14

この README は入口専用です。詳細な仕様や作業ログは各フォルダに分け、ここでは「今どれを読むべきか」だけを示します。

## まず読むもの

| 目的 | 文書 |
|---|---|
| 製品の目的と不変原則を確認する | [01_requirements/00_product-vision.md](01_requirements/00_product-vision.md) |
| 現在の実装済み機能を確認する | [00_human/02_current-features.md](00_human/02_current-features.md) |
| 現行アーキテクチャを確認する | [02_design/01_architecture-and-ui.md](02_design/01_architecture-and-ui.md) |
| 現在の残タスクを確認する | [03_planning/01_remaining-tasks.md](03_planning/01_remaining-tasks.md) |
| 5月レビュー資料を確認する | [04_review/README.md](04_review/README.md) |
| Tauri 移行の引き継ぎ準備を確認する | [05_handoff/README.md](05_handoff/README.md) |

## 現在の前提

- 現行本線は PySide6 版です。
- Tauri 移行は再検討対象ですが、旧 Tauri 資料をそのまま現行正本として扱わないでください。
- 検出モデル、GPU、輪郭抽出は差し替えと fallback を前提に扱います。
- AI 検出結果は候補であり、ユーザーの手動編集を優先します。
- 古い作業ログや完了済みの Claude 依頼は [99_archive/](99_archive/) に隔離します。

## フォルダ構成

| フォルダ | 役割 |
|---|---|
| [00_human/](00_human/) | 人間向けの概要、現在できること、P4 の説明 |
| [00_engineering/](00_engineering/) | 実装レビューや AI エージェント向けの入口 |
| [01_requirements/](01_requirements/) | 製品要件、マスク要件、P4 要件 |
| [02_design/](02_design/) | アーキテクチャ、UI、マスク仕様、検出モデル抽象化 |
| [03_planning/](03_planning/) | 現行残タスク、短期計画、方針整理 |
| [03_development/](03_development/) | 開発運用メモの置き場 |
| [04_review/](04_review/) | 第三者レビュー向け資料 |
| [05_handoff/](05_handoff/) | PySide6 から Tauri など別実装へ引き継ぐための資料 |
| [marketing/](marketing/) | LP など製品紹介ドラフト。現行仕様の正本ではない |
| [99_archive/](99_archive/) | 過去資料、旧前提、完了済み作業ログ |

## 用途別リンク

### 要件

- [01_requirements/00_product-vision.md](01_requirements/00_product-vision.md)
- [01_requirements/01_core-product-requirements.md](01_requirements/01_core-product-requirements.md)
- [01_requirements/02_mask-track-requirements.md](01_requirements/02_mask-track-requirements.md)
- [01_requirements/03_p4-retraining-hub.md](01_requirements/03_p4-retraining-hub.md)

### 設計

- [02_design/01_architecture-and-ui.md](02_design/01_architecture-and-ui.md)
- [02_design/02_mask-spec.md](02_design/02_mask-spec.md)
- [02_design/03_ui-design-plan.md](02_design/03_ui-design-plan.md)
- [02_design/04_detector-abstraction.md](02_design/04_detector-abstraction.md)
- [02_design/05_model-switcher-ui-design.md](02_design/05_model-switcher-ui-design.md)

### 計画

- [03_planning/01_remaining-tasks.md](03_planning/01_remaining-tasks.md)
- [03_planning/02_future-retraining-memo.md](03_planning/02_future-retraining-memo.md)
- [03_planning/03_erax-local-retraining-implementation-plan.md](03_planning/03_erax-local-retraining-implementation-plan.md)
- [03_planning/04_p3-review-checklist.md](03_planning/04_p3-review-checklist.md)
- [03_planning/05_2026-05-pinky-review-plan.md](03_planning/05_2026-05-pinky-review-plan.md)
- [03_planning/06_model-distribution-policy.md](03_planning/06_model-distribution-policy.md)
- [03_planning/07_model-onboarding-ux-resolution.md](03_planning/07_model-onboarding-ux-resolution.md)

### レビュー

- [04_review/01_review-guide.md](04_review/01_review-guide.md)
- [04_review/02_model-setup-guide.md](04_review/02_model-setup-guide.md)
- [04_review/03_feedback-checklist.md](04_review/03_feedback-checklist.md)
- [04_review/04_known-limitations.md](04_review/04_known-limitations.md)
- [04_review/05_full-manual-test-procedure.md](04_review/05_full-manual-test-procedure.md)
- [04_review/06_codebase-audit-2026-04-13.md](04_review/06_codebase-audit-2026-04-13.md)
- [04_review/07_engine-ui-gap-report.md](04_review/07_engine-ui-gap-report.md)

### Tauri 引き継ぎ

- [05_handoff/README.md](05_handoff/README.md)
- [05_handoff/pyside6-source-handoff-prompt.md](05_handoff/pyside6-source-handoff-prompt.md)
- 旧 Tauri 資料は [99_archive/tauri_migration_backend_plan.md](99_archive/tauri_migration_backend_plan.md) と [99_archive/unimplemented-features-tauri.md](99_archive/unimplemented-features-tauri.md) にあります。再利用時は現行 PySide6 実装との差分確認が必要です。

## 変更ルール

- 実装済みの正本は、コード・テスト・手動確認手順に接続してください。
- 要件は [01_requirements/](01_requirements/) に置き、設計は [02_design/](02_design/) に置いてください。
- 短期計画やレビュー到達のための作業順は [03_planning/](03_planning/) に置いてください。
- 完了済みの PM プロンプト、Claude 作業報告、旧前提資料は [99_archive/](99_archive/) に移してください。
- README は入口に留め、同じ説明を複数箇所へ増やさないでください。

