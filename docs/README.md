# Auto Mosaic ドキュメント

Auto Mosaic のドキュメント入口です。
読む人によって必要な粒度が違うため、まず入口を 2 つに分けています。

## 入口

| 読む人 | 入口 | 内容 |
|--------|------|------|
| ユーザー / レビュー担当 / 仕様を先に把握したい人 | [human/](./human/) | アプリの目的、使い方、現在できることをわかりやすく説明 |
| エンジニア / AI エージェント | [engineering/](./engineering/) | 現行実装の正本、責務境界、不変条件、作業時の読み順 |

まず人間向けの全体像を読むなら [human/product-spec.md](./human/product-spec.md)。
実装作業に入るなら [engineering/current-implementation.md](./engineering/current-implementation.md) を正本として読みます。
安定化フェーズ完了後の新規開発方針は [project/README.md](./project/README.md) を入口にし、PySide6 同等編集体験チェックリストを中核ロードマップとして扱います。

---

## ドキュメント一覧

### [human/](./human/) — 人間向け仕様

| ファイル | 内容 |
|----------|------|
| [README.md](./human/README.md) | 人間向けドキュメントの入口 |
| [product-spec.md](./human/product-spec.md) | Auto Mosaic の仕様、使い方、実装済み/未実装の概要 |

### [engineering/](./engineering/) — エンジニア / AI 向け正本

| ファイル | 内容 |
|----------|------|
| [README.md](./engineering/README.md) | エンジニア / AI 向けドキュメントの入口 |
| [current-implementation.md](./engineering/current-implementation.md) | 現行実装の責務境界、不変条件、実装済み状態 |

### [review/](./review/) — 動作確認・テスト手順

| ファイル | 内容 |
|----------|------|
| [review-quickstart.md](./review/review-quickstart.md) | レビュー用パッケージの起動手順 |
| [review-checklist.md](./review/review-checklist.md) | 一通りの機能を確認するチェックリスト |
| [review-guide-detect-fix.md](./review/review-guide-detect-fix.md) | AI 検出機能を重点的に確認する手順 |

### [project/](./project/) — 進捗と状態

| ファイル | 内容 |
|----------|------|
| [README.md](./project/README.md) | Project ドキュメントの入口。安定化後の開発中核資料への読み順 |
| [unimplemented-features.md](./project/unimplemented-features.md) | 実装済み機能と未実装機能の一覧 |
| [pyside6-editing-experience-parity-checklist.md](./project/pyside6-editing-experience-parity-checklist.md) | 安定化後の主ロードマップ。PySide6 同等編集体験の機能チェックリストと開発フェーズ票 |
| [pyside6-ui-structure-reference.md](./project/pyside6-ui-structure-reference.md) | PySide6 版 UI 構成、ボタン配置、メニュー構成の参照資料 |
| [ai-handoff.md](./project/ai-handoff.md) | 直近作業の handoff log |
| [pyside6-remaining-tasks.md](./project/pyside6-remaining-tasks.md) | PySide6 版との比較履歴 |
| [未実装機能一覧.md](./project/未実装機能一覧.md) | `unimplemented-features.md` への日本語ショートカット |

### [development/](./development/) — 開発環境の準備

| ファイル | 内容 |
|----------|------|
| [setup.md](./development/setup.md) | 開発環境の構築手順 |
| [install.md](./development/install.md) | インストール方針と配布パッケージ構成 |
| [gpu-compatibility.md](./development/gpu-compatibility.md) | GPU の動作確認済みバージョン一覧 |
| [gpu-diagnostics.md](./development/gpu-diagnostics.md) | GPU 診断コマンド |

### [architecture/](./architecture/) — 要件定義・設計履歴・参照資料

完成像としての要件定義と、設計履歴・詳細参照資料が混在します。
現行実装の判断は [engineering/current-implementation.md](./engineering/current-implementation.md) を優先し、ここは「実現すべき完成図」と「過去の設計履歴」を確認するために使います。

| ファイル | 内容 |
|----------|------|
| [要件定義書.md](./architecture/要件定義書.md) | **完成図としての要件定義 (target spec)。実装詳細は含まず、ユーザー価値・ドメイン不変条件・非機能要件を定義する** |
| [requirements-spec-v2.1.md](./architecture/requirements-spec-v2.1.md) | 詳細要件仕様の履歴 |
| [tauri-from-scratch-spec.md](./architecture/tauri-from-scratch-spec.md) | from-scratch 実装方針の履歴 |
| [p4-retraining-requirements.md](./architecture/p4-retraining-requirements.md) | 教師データ保存・ローカル再学習の要件整理 |

### [operations/](./operations/) — 運用・管理

| ファイル | 内容 |
|----------|------|
| [uninstall.md](./operations/uninstall.md) | アンインストール方法と注意点 |

### [tauri-migration/](./tauri-migration/) — 移行調査アーカイブ

旧版 PySide6 から Tauri 版へ移行する際の調査・計画記録です。
移行は完了済みのため、通常の作業判断では正本にしません。
