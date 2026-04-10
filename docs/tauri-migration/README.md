# PySide6 から Tauri への移行調査

このディレクトリは、Auto Mosaic の PySide6 実装を Tauri ベースへ移行するための調査、設計、計画、レビュー専用の作業領域です。

既存の `docs/` 配下にある要件、設計、開発メモとは別管理にします。既存ドキュメントは参照元として扱いますが、このディレクトリ内の文書は今回の移行作業で作成する移行専用の成果物です。既存ドキュメントの移動、改名、上書きは行いません。

## 読む順番

1. `README.md`
   - このディレクトリの目的、各ファイルの役割、現状分析と提案計画の境界を示します。
2. `01_current-architecture-pyside6.md`
   - `モザイク2` 側の現行 PySide6 実装を正本として、現行構成、処理フロー、依存、暗黙仕様、移行リスクを整理します。
3. `02_pyside6-vs-tauri-architecture-comparison.md`
   - 現行 PySide6 構成と既存 Tauri 側構成を比較し、責務分離、runtime、packaging、command 境界、ファイルアクセス、非同期処理の差分を整理します。
4. `03_tauri-migration-plan.md`
   - 比較結果を踏まえ、段階的に実装へ進むための移行計画、成功条件、リスク、フェーズ分割、直近タスクを定義します。
5. `04_tauri-migration-plan-review.md`
   - `03_tauri-migration-plan.md` を厳しめに自己レビューし、事故りやすい点、抜け漏れ、順序修正、採用すべき修正版方針を明記します。

## 現状分析と提案計画の境界

- `README.md` は案内文書です。
- `01_current-architecture-pyside6.md` は現状分析です。根拠は原則として `モザイク2` ディレクトリ内のコード、設定、既存ドキュメントから採ります。Tauri 側の同名機能は、移行元仕様の判定には使いません。
- `02_pyside6-vs-tauri-architecture-comparison.md` は比較分析です。PySide6 側の仕様根拠は `モザイク2` 側、Tauri 側の構成根拠は Tauri 側コードベースから分けて扱います。
- `03_tauri-migration-plan.md` からが提案と実行計画です。現行仕様の再現と、Tauri 化に伴う再設計候補を混同しないように記述します。
- `04_tauri-migration-plan-review.md` は計画の批判的レビューです。レビュー結果は `03_tauri-migration-plan.md` に反映し、反映済み箇所を明記します。

## 記述ルール

- 確認済みの事実、推測、未確認事項を分けます。
- 「現行仕様」は `モザイク2` 側の実装を優先して判断します。
- `docs/99_archive/` などの過去メモは履歴資料として扱い、現在仕様の根拠にする場合はその限界を明記します。
- 検証していない内容は完了扱いしません。
