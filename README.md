# Auto Mosaic

動画内の特定領域に自動でモザイクをかけるデスクトップアプリケーションです。

AI が「ここにモザイクが必要そう」という候補を提案し、あなたがそれを確認・調整して、モザイク入りの動画を書き出します。
すべての処理はあなたのPC上で完結するため、動画がインターネットに送信されることはありません。

---

## 主な機能

- **AI 自動検出** — ボタンひとつで、モザイクをかけるべき領域を AI が自動で検出します
- **マスクトラック編集** — 時間軸に沿ってモザイク領域を管理。1フレームずつ作業する必要はありません
- **手動編集の保護** — 手作業で調整した部分は AI の再検出で上書きされません
- **動画書き出し** — 解像度やビットレートを選んで、モザイク付き動画をファイルとして保存できます
- **完全オフライン** — ネット接続不要。プライバシーを気にせず使えます

## 使い方の流れ

```
動画を開く → AI 検出 → 確認・調整 → 書き出し
```

1. 編集したい動画ファイルを開く
2. AI 検出ボタンで、モザイク候補を自動生成
3. タイムライン上で位置や大きさを確認・修正
4. 書き出しボタンで、モザイク入りの動画を保存

---

## プロジェクト構成

```
taurimozaic/
├── apps/
│   ├── desktop/          画面まわり（Tauri + React）
│   └── backend/          AI処理・動画処理（Python）
├── docs/                 ドキュメント一式
├── models/               AI モデルファイル
├── scripts/              ビルド・配布用スクリプト
├── installer/            インストーラ関連
└── tools/                開発補助ツール
```

| フォルダ | 役割 |
|---------|------|
| `apps/desktop/` | ユーザーが操作する画面部分。Tauri（Rust）と React（TypeScript）で構成 |
| `apps/backend/` | AI による検出、動画の加工・書き出しなどの重い処理を担当。Python で動作 |
| `docs/` | すべてのドキュメントを目的別に整理。**[詳細はこちら](./docs/README.md)** |
| `models/` | AI の学習済みモデルファイルの置き場所 |

## 技術構成

| 要素 | 技術 |
|------|------|
| デスクトップシェル | Tauri 2 (Rust) |
| フロントエンド | React + TypeScript |
| バックエンド | Python 3.12 |
| AI 推論 | ONNX Runtime（GPU対応、CPU フォールバックあり） |
| 動画処理 | FFmpeg + OpenCV |
| フロント↔バックエンド連携 | subprocess + CLI + JSON I/O |

## ドキュメント

すべてのドキュメントは [`docs/`](./docs/README.md) フォルダにまとまっています。

| 目的 | 場所 |
|------|------|
| まず入口を選びたい | [docs/README.md](./docs/README.md) |
| 人間向けに仕様を理解したい | [docs/human/product-spec.md](./docs/human/product-spec.md) |
| エンジニア/AI向けの現行実装正本を読みたい | [docs/engineering/current-implementation.md](./docs/engineering/current-implementation.md) |
| アプリを試しに動かしたい | [docs/review/review-quickstart.md](./docs/review/review-quickstart.md) |
| 開発環境を作りたい | [docs/development/setup.md](./docs/development/setup.md) |
| 実装状況を知りたい | [docs/project/unimplemented-features.md](./docs/project/unimplemented-features.md) |
| 過去の詳細設計資料を読みたい | [docs/architecture/requirements-spec-v2.1.md](./docs/architecture/requirements-spec-v2.1.md) |

---

## AI エージェント向け

このプロジェクトで AI エージェントが作業する場合は、以下を先に読んでください。

1. [`docs/engineering/current-implementation.md`](./docs/engineering/current-implementation.md) — 現行実装の正本
2. [`docs/project/unimplemented-features.md`](./docs/project/unimplemented-features.md) — 実装状況一覧
3. [`docs/project/ai-handoff.md`](./docs/project/ai-handoff.md) — 直近の作業ログ
4. [`CLAUDE.md`](./CLAUDE.md) — Claude 向け作業ルール
5. [`AGENTS.md`](./AGENTS.md) — エージェント全般向けルール
