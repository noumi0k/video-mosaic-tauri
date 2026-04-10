# Auto Mosaic Tauri完全新規構築 詳細要件仕様書 v2.1

作成日: 2026-04-02  
対象: 既存資料を参照しつつ、既存 PySide6 実装コードは再利用せず、Tauri フロントエンド + Python バックエンド構成で完全新規構築するための詳細要件仕様書  
文書区分: 設計履歴・参照資料

> 現在の作業正本ではありません。現行実装の責務境界と不変条件は `docs/engineering/current-implementation.md`、実装済み / 未実装 backlog は `docs/project/unimplemented-features.md` を優先してください。

---

## 0. 文書の位置づけ

本仕様書は、提供された既存資料群から以下を抽出・統合し、Tauri 前提で再構成した実装仕様である。

- コア製品要求
- マスクトラック要求
- 現行アーキテクチャ境界
- Tauri 移行方針
- 現在の学習モデル構成
- 将来メモ扱いだった「教師データ保存」「再学習」「インストーラ」の具体化

なお、**自動再学習の本実装**、**教師データ保存の本実装**、**最終インストーラ設計**は、元資料では将来検討・保留寄りの扱いだったため、本仕様書ではその思想を壊さずに、ローカル前提・明示的 opt-in 前提で実装可能な要件へ補完している。

---

## 1. 背景と目的

本ソフトは、ローカル動画に対して AI が初期マスク候補を生成し、ユーザーが時間軸上でそれを編集し、最終的にモザイク付き動画として書き出すデスクトップアプリである。

再構築後の目的は次の通りとする。

1. PySide6 固有 UI への依存を切り離し、Tauri を用いた保守しやすいデスクトップ UI に置き換える。
2. 重い動画処理・推論・書き出しは Python 側に集約するが、既存コードは流用せず、新しい責務分離で実装し直す。
3. 編集の中心概念を「断片マスク」ではなく「持続する mask track」に統一する。
4. 将来の精度改善につながる教師データ保存とローカル再学習を、プライバシーを壊さず本実装できる設計にする。
5. 最終的に一般ユーザーへ配布可能な Windows 向けインストーラまで含めて完成形を定義する。

---

## 2. 本仕様の前提

### 2.1 プロダクト原則

- 完全ローカル実行
- オフライン利用前提
- AI は候補生成の補助であり、最終品質はユーザー確認を前提とする
- 漏れ防止を優先し、必要なら保守的に広めのマスクを許容する
- UI・内部データ・書き出しはすべて mask track を中心概念とする

### 2.2 Tauri 再構築の原則

- 既存 PySide6 実装は仕様参照用であり、コード流用対象にしない
- Tauri フロントエンド、Rust シェル、Python バックエンド、CLI 境界、ジョブ管理のすべてを新規設計する
- 旧資料から引き継ぐのは「機能要件」「振る舞い要件」「データ要件」「モデル要件」であり、ファイル構成やクラス実装は拘束条件にしない
- Tauri と Python の連携は、**第一段階では HTTP ではなく subprocess + CLI + JSON I/O** を正式採用する
- 長時間処理は同期 RPC ではなく job 化する
- UI 状態とバックエンド状態の境界を明確にする

### 2.3 サポート対象 OS

- 主対象: Windows 10 / 11
- 準対象: macOS, Linux
- 最終インストーラ本実装は Windows を最優先とする

---
### 2.4 完全新規構築ポリシー

- 旧 PySide6 版のコード、クラス名、ディレクトリ構成、UI 実装は**参照資料**であり、移植前提にしない
- 旧実装から引き継ぐのは、製品要求、mask track の振る舞い、モデル構成、保存要件、受け入れ基準のみとする
- 旧プロジェクト JSON との互換は必須要件にしない。必要な場合は **importer** を別機能として実装する
- 新規実装では、テスト、ロギング、ジョブ管理、エラー体系、設定体系も含めて作り直す
- 既存不具合や設計上の癖を持ち込まないことを優先し、コード流用による短期的な実装速度は追わない

### 2.5 完全新規構築を選ぶ場合の影響

#### 利点
- PySide6 由来の UI 制約や密結合を持ち込まない
- Tauri 向けに最初から責務分離、ジョブ設計、状態管理を最適化できる
- 既存コードの暫定実装や歴史的経緯に引きずられない
- テストしやすい API / データ構造を最初から定義できる

#### コスト
- 動画入出力、検出、追跡、編集、保存、書き出し、設定、ログ、診断をすべて再実装する必要がある
- 旧挙動と同等品質に達するまで検証期間が長くなる
- 既存プロジェクトデータの互換性は自動では得られない
- インストーラ、更新、アンインストーラも新方式で作り直す必要がある

#### 本仕様における判断
本仕様は**コード再利用なしの完全新規構築**を正式方針とする。ただし、旧資料は要求定義と受け入れ基準の参照元として使う。

---

## 3. 既存資料から抽出した現行必須機能

本再構築で引き継ぐ必須機能は以下とする。

1. 動画ファイルの読み込み
2. メタ情報取得（解像度、fps、総フレーム数、長さ）
3. AI による自動マスク候補生成
4. 候補のトラック化
5. タイムライン上でのトラック確認
6. プレビュー上での直接編集
7. キーフレーム編集
8. 区間補間
9. モザイクプレビュー
10. 編集済み動画の書き出し
11. 書き出しジョブ管理
12. キャンセル可能な書き出し
13. GPU 利用と CPU フォールバック
14. プロジェクト保存 / 再読込
15. モデル差し替え可能な構造
16. 永続的 mask track 編集
17. manual 編集保護
18. 品質モード向け輪郭抽出
19. 将来の教師データ保存・再学習の接続余地

---

## 4. 確認できた学習モデル / 推論資産

### 4.1 提供画像から確認できた実ファイル

- `320n.onnx`
- `erax_v1_1.pt`
- `sam2_tiny_encoder.onnx`
- `sam2_tiny_decoder.onnx`

### 4.2 既存資料から確認できたモデル構成

#### 必須モデル
- **NudeNet 320n ONNX**
  - 役割: 標準の初期検出バックエンド
  - ファイル: `models/320n.onnx`
  - 位置づけ: デフォルト検出器

#### 任意・比較用モデル
- **NudeNet 640m ONNX**
  - 役割: 高精度寄り比較バックエンド
  - ファイル: `models/640m.onnx`
  - 備考: 手動配置前提

- **EraX-Anti-NSFW-V1.1**
  - 役割: 比較用・代替検出バックエンド
  - ファイル候補: `models/erax_v1_1.pt`, `models/erax_v1_1.onnx`
  - 備考: `.pt` から ONNX 変換に対応する

#### 任意・品質向上モデル
- **SAM2 tiny encoder / decoder ONNX**
  - 役割: 輪郭品質モード、bbox から高品質セグメンテーション
  - ファイル: `models/sam2_tiny_encoder.onnx`, `models/sam2_tiny_decoder.onnx`
  - 備考: 未配置時は安全にフォールバックする

### 4.3 モデル利用方針

- Tauri 版でも、モデル依存コードは Python `infra/ai` に閉じ込める
- 検出器差し替えは `ModelRunner` / `DetectorFactory` の責務とする
- UI はモデル種別を直接知らず、設定値として backend 名だけを扱う
- 推論結果は内部正規ラベルへ変換して後段へ渡す

---

## 5. スコープ

### 5.1 本仕様に含む

- Tauri フロントエンド
- Python バックエンド
- CLI / JSON ブリッジ
- ジョブ管理
- 動画読込、検出、追跡、編集、書き出し
- プロジェクト保存
- GPU 設定
- モデル管理
- 教師データ保存本実装
- 自動再学習本実装
- Windows 向け最終インストーラ

### 5.2 本仕様に含まない

- クラウド同期
- 自動外部アップロード
- 複数ユーザー共同編集
- モバイルアプリ
- ブラウザ版
- サーバー常駐前提の API 提供

---

## 6. 全体アーキテクチャ

### 6.1 採用構成

```text
[Tauri App]
  ├─ Rust shell
  ├─ Web UI (HTML/CSS/TS)
  ├─ Job state store
  ├─ Window/menu/file dialogs
  └─ Python process manager
         │
         ▼
[Python Backend Process]
  ├─ backend/application   # usecase orchestration / jobs / CLI handlers
  ├─ backend/domain        # track, keyframe, edit, render, export rules
  ├─ backend/infra         # ai, video, storage, ffmpeg/ffprobe, device
  ├─ backend/runtime       # path policy / environment / installer helpers
  └─ backend/cli.py        # subprocess entry point with JSON I/O
```

### 6.1.1 新規実装時の推奨リポジトリ構成

```text
auto-mosaic/
  frontend/                 # Tauri Web UI (TypeScript)
  src-tauri/                # Rust shell / commands / packaging
  backend/
    cli.py
    application/
    domain/
    infra/
    runtime/
    tests/
  assets/
  installer/
  docs/
```

- `frontend/`, `src-tauri/`, `backend/` はすべて新規作成する
- 旧 `app/ui` などのパスへ合わせる必要はない
- 旧資料の名称は読み替え可能だが、新実装ではこの構成を正本とする

### 6.2 層責務

#### Tauri 側
- ウィンドウ管理
- ファイル選択
- UI レンダリング
- キーボードショートカット
- 状態表示
- ジョブの開始要求・進捗表示・キャンセル要求
- インストーラ後の起動導線

#### Python 側
- 動画解析
- フレーム読込
- AI 推論
- マスクトラック生成
- 補間
- プレビュー用描画素材生成
- 書き出し
- プロジェクト保存
- 教師データ保存
- 再学習

### 6.3 境界ルール

- Tauri 側は Python の内部モジュール構造を知らない
- Python 側は Tauri の UI 状態を知らない
- 連携は JSON スキーマとジョブイベントに限定する
- UI でしか意味を持たない表示情報は Python に持ち込まない
- 学習モデルや検出器ごとの差異は後段サービスに漏らさない

---

## 7. Python と Tauri の繋ぎ合わせ要件（最重要）

この章は本仕様書の最重要章とする。

### 7.1 採用方式

**Tauri → Python は subprocess 起動 + task-oriented CLI + JSON 入出力** を採用する。

#### 理由
- 現行バックエンド構成を最も低コストで再利用できる
- ローカル HTTP サーバーを新設せずに済む
- デバッグ容易性が高い
- インストーラ時の閉域構成を保ちやすい
- 長時間処理を job 化しやすい

### 7.2 連携方式の詳細

#### 7.2.1 2系統通信

1. **同期コマンド系**
   - 入力: JSON
   - 出力: JSON
   - 用途: メタ情報取得、プロジェクト読込、設定取得など短時間処理

2. **長時間ジョブ系**
   - 入力: JSON
   - 出力: `job_id` を即返却
   - 進捗: ファイルベースイベントまたは stdout の NDJSON ストリーム
   - 用途: 検出、再解析、書き出し、教師データ生成、再学習

### 7.3 Python CLI インターフェース

正式な CLI エントリポイントは `python -m backend.cli` とする。

#### 7.3.1 コマンド一覧

```text
backend.cli env-check
backend.cli open-video
backend.cli create-project
backend.cli load-project
backend.cli save-project
backend.cli detect
backend.cli build-tracks
backend.cli render-preview-frame
backend.cli export-video
backend.cli capture-training-data
app.cli list-training-datasets
app.cli train-model
app.cli get-settings
app.cli set-settings
app.cli cancel-job
app.cli get-job-status
```

#### 7.3.2 入力方法

- 標準入力で JSON を受け取る
- 大きな payload はファイルパス参照を許可する
- バイナリフレームそのものを大量に JSON 直載せしない

#### 7.3.3 出力方法

- 短時間処理: 標準出力へ単一 JSON
- 長時間処理: 最初に `accepted` JSON、その後 NDJSON イベント

### 7.4 JSON 契約

#### 7.4.1 共通レスポンス

```json
{
  "ok": true,
  "command": "open-video",
  "data": {},
  "error": null,
  "warnings": []
}
```

#### 7.4.2 エラー形式

```json
{
  "ok": false,
  "command": "detect",
  "data": null,
  "error": {
    "code": "MODEL_NOT_FOUND",
    "message": "models/320n.onnx was not found",
    "details": {
      "expected_path": "..."
    }
  },
  "warnings": []
}
```

### 7.5 ジョブ管理要件

#### 7.5.1 ジョブ種別
- detection_job
- track_rebuild_job
- export_job
- training_capture_job
- retraining_job
- model_conversion_job

#### 7.5.2 ジョブ状態
- queued
- starting
- running
- cancelling
- cancelled
- completed
- failed

#### 7.5.3 ジョブイベント
- accepted
- progress
- phase_changed
- artifact_created
- warning
- completed
- failed
- cancelled

#### 7.5.4 進捗イベント例

```json
{
  "type": "progress",
  "job_id": "job_xxx",
  "phase": "inference",
  "current": 120,
  "total": 500,
  "percent": 24.0,
  "message": "Running detector on sampled frames"
}
```

### 7.6 Tauri 側プロセスマネージャ要件

Tauri 側は Python プロセスを直接乱立させてはならない。

#### 7.6.1 必須責務
- Python 実行パスの解決
- 初回起動時の環境チェック
- 同時実行ジョブ数の制御
- 標準出力 / 標準エラーの監視
- ジョブキャンセル時のプロセス終了制御
- アプリ終了時の残ジョブ後始末

#### 7.6.2 実装方針
- 短時間処理は都度 subprocess 起動でよい
- 長時間ジョブは専用ワーカープロセス起動または再利用可能 worker を使う
- 1 本の動画に対する重いジョブの同時実行は原則 1 本まで
- 書き出し中の同一 project に対する破壊的編集コマンドは UI 側でロックする

### 7.7 ファイル受け渡し要件

#### 7.7.1 直接 JSON で渡すもの
- 設定
- トラックメタ情報
- キーフレーム情報
- job パラメータ
- 小規模なプレビュー結果メタ情報

#### 7.7.2 ファイル参照で渡すもの
- 動画ファイル
- プロジェクトファイル
- 書き出し先
- 一時プレビュー画像
- 学習用 crop 画像
- モデルファイル

### 7.8 プレビュー連携要件

Tauri 側キャンバス描画には 2 方式を許可する。

1. **軽量ベクタ方式**
   - Python が現在フレームの mask track / keyframe / polygon を JSON 返却
   - Tauri 側が canvas/SVG で描画
   - 編集向き

2. **プレビュー画像方式**
   - Python がレンダリング済みフレーム PNG/JPEG を返却
   - Tauri 側は表示のみ
   - モザイク確認向き

正式採用はハイブリッドとし、通常編集はベクタ方式、最終見た目確認はプレビュー画像方式とする。

### 7.9 編集イベントの橋渡し

Tauri 側で行った操作は、必ず domain の意味を持つイベントとして Python に渡す。

例:
- `select_track`
- `move_track`
- `resize_ellipse`
- `move_vertex`
- `insert_vertex`
- `delete_vertex`
- `add_keyframe`
- `delete_keyframe`
- `split_track`
- `toggle_track_visibility`
- `update_track_style`

UI 座標のまま保存してはならず、必ず動画座標系へ正規化する。

### 7.10 Undo/Redo 連携

- 真の履歴管理は Python 側の project state に持つ
- Tauri 側は `undo` / `redo` コマンドを送るだけにする
- UI 側で独自に履歴を持たない
- 履歴エントリには操作名・対象 track_id・frame_index を含める

### 7.11 連携禁止事項

- Tauri から Python 内部モジュールを直接 import すること
- UI 側で推論結果のラベル統合ロジックを持つこと
- Python 側が HTML / CSS 表示都合の状態を保持すること
- 長時間処理を同期待ちし続けて UI をフリーズさせること
- ローカル HTTP API を初期実装で前提にすること

---

## 8. 機能要件

### 8.1 動画入出力

#### 8.1.1 動画読み込み
- MP4 / MOV / MKV / AVI / WebM を対象とする
- ffprobe でメタ情報取得を優先し、失敗時は OpenCV フォールバック
- 読み込み時に以下を取得する
  - width
  - height
  - fps
  - frame_count
  - duration_sec
  - audio stream presence
  - codec/container summary

#### 8.1.2 サムネイル / 先頭フレーム表示
- 動画読み込み直後に先頭フレームを表示する
- 長尺動画でも初期応答を遅らせない

### 8.2 自動検出

- 検出対象カテゴリを選べること
- サンプリング間隔を設定できること
- 推論解像度を設定できること
- confidence threshold を設定できること
- detector backend を切り替えられること
- GPU/CPU を切り替えられること
- バックエンド差異は label_mapper で吸収し、後段は共通 `Detection` 形式で処理すること

### 8.3 マスクトラック生成

- 検出結果を mask track として時間方向に接続できること
- 1対象につき、できるだけ 1 本の track を維持すること
- 一時的未検出で track を即終了しないこと
- `active / lost / inactive` のライフサイクルを持つこと
- `auto / manual / interpolated / predicted / re-detected` の source を持つこと
- 今後拡張として `held / uncertain` 区間を扱えること

### 8.4 マスク編集

- プレビュー上で選択できること
- 移動できること
- 楕円サイズ変更できること
- polygon 頂点編集できること
- キーフレーム追加 / 削除ができること
- manual keyframe は自動処理で上書きしないこと
- track 分割 / 複製 / 削除ができること
- 必要に応じて手動で新規 track を作成できること

### 8.5 補間 / 欠落区間対応

- キーフレーム間は線形補間を標準とする
- 短い欠落は hold/predict で持続できること
- 補間不能時は直前形状保持または bbox フォールバックを使うこと
- 欠落区間は UI 上で区別表示できること

### 8.6 輪郭抽出

- `none / fast / balanced / quality` モードを持つこと
- `fast`: HSV 肌色マスク等の軽量処理
- `balanced`: GrabCut 系
- `quality`: SAM2 tiny 使用
- 輪郭抽出失敗時は必ず bbox フォールバックすること

### 8.7 プレビュー

- パス表示とモザイク表示を切り替えられること
- 非選択 track も表示できること
- 現在フレームの全有効マスクを確認できること
- 再生中は編集ロックできること

### 8.8 書き出し

- MP4 / MOV / WebM 出力
- H.264 優先
- 720p / 1080p / 4K / 元解像度選択
- ビットレート設定
- 音声 copy_if_possible
- GPU エンコード ON/OFF
- キュー管理
- キャンセル可能
- 一時ファイル掃除

### 8.9 プロジェクト保存

- プロジェクト JSON 保存 / 再読込ができること
- 保存内容に動画参照、track、keyframe、スタイル、設定、モデル設定、教師データ設定を含むこと
- 互換バージョン番号を持つこと

---

## 9. UI / UX 要件（Tauri版）

### 9.1 画面構成

- 上部: メニュー / ツールバー
- 左: Track List Panel
- 中央: Preview Canvas
- 右: Property / Effect Control Panel
- 下: Timeline Panel
- 最下部: Status Bar / Job Area

### 9.2 UI 原則

- 編集対象単位は mask track とする
- instance の乱立をそのまま UI に出さない
- track の存在区間、欠落区間、manual 区間を視覚区別する
- ダークテーマを標準とする
- Premiere Pro 風の情報密度を目指す

### 9.3 Timeline 要件

- トラックレーン表示
- キーフレーム可視化
- 現在位置表示
- ズーム / スクロール
- track 別表示/非表示
- predicted/interpolated/uncertain の視覚区別

### 9.4 Property Panel 要件

- 選択 track 情報
- モザイク強度
- expand_px
- feather
- shape type
- current keyframe info
- source 表示
- ロック状態

### 9.5 Job UI 要件

- 実行中ジョブ一覧
- フェーズ表示
- 進捗バー
- 推定残り時間
- キャンセルボタン
- 完了 artifact への導線

---

## 10. データモデル要件

### 10.1 Project

```ts
Project {
  projectVersion: number
  projectId: string
  sourceVideoPath: string
  videoMeta: VideoMeta
  maskTracks: MaskTrack[]
  exportPreset: ExportPreset
  detectorConfig: DetectorConfig
  trainingConfig: TrainingConfig
  metadata: Record<string, unknown>
}
```

### 10.2 VideoMeta

```ts
VideoMeta {
  width: number
  height: number
  fps: number
  frameCount: number
  durationSec: number
  hasAudio: boolean
  container?: string
  videoCodec?: string
}
```

### 10.3 MaskTrack

```ts
MaskTrack {
  trackId: string
  label: string
  labelGroup: string
  startFrame: number
  endFrame: number | null
  visible: boolean
  state: "active" | "lost" | "inactive" | "finished"
  source: "auto" | "user-adjusted" | "re-detected"
  confidence: number
  userLocked: boolean
  userEdited: boolean
  style: MaskStyle
  keyframes: Keyframe[]
  segments: MaskSegment[]
  motionHistory: number[][]
  associationHistory: Record<string, unknown>[]
}
```

### 10.4 Keyframe

```ts
Keyframe {
  frameIndex: number
  shapeType: "ellipse" | "polygon"
  points: number[][]
  bbox: [number, number, number, number]
  contourPoints?: number[][]
  confidence: number
  source: "auto" | "manual" | "interpolated" | "predicted" | "re-detected"
  rotation: number
  opacity: number
  expandPx?: number | null
  feather?: number | null
  isLocked?: boolean
}
```

### 10.5 ExportPreset

```ts
ExportPreset {
  container: "mp4" | "mov" | "webm"
  videoCodec: string
  audioMode: "copy_if_possible" | "aac" | "none"
  targetResolution: "source" | "720p" | "1080p" | "4k"
  bitrateMbps?: number
  useGpuEncode: boolean
}
```

### 10.6 DetectorConfig

```ts
DetectorConfig {
  backend: "nudenet_320n" | "nudenet_640m" | "erax_v1_1"
  device: "auto" | "cuda" | "cpu"
  sampleEvery: number
  maxSamples: number
  inferenceResolution: number
  confidenceThreshold: number
  contourMode: "none" | "fast" | "balanced" | "quality"
  enabledLabelCategories: string[]
  preciseFaceContour: boolean
  vramSavingMode: boolean
}
```

---

## 11. トラッキング / マスク仕様要件

### 11.1 基本ルール

- 新規 track 作成は最後の手段
- 判定順は `active -> lost -> persistent absorption -> new track`
- manual keyframe を自動で上書きしない
- 検出切れのたびに track を乱立させない
- UI と書き出しで別の存在期間判定を使わない

### 11.2 状態

#### Track state
- active
- lost
- inactive
- finished

#### Segment state
- confirmed
- predicted
- interpolated
- held
- uncertain

#### Keyframe source
- auto
- manual
- predicted
- interpolated
- re-detected

### 11.3 マッチング要件

- label_group で候補絞り込み
- IoU
- center distance
- area similarity
- aspect similarity
- motion consistency
- same-frame duplicate prevention

### 11.4 Stitch 要件

- 前段マッチング改善が主
- stitch は補助
- chain stitch を許容
- overlap やフレーム gap に閾値を持つ

### 11.5 フォールバック要件

- contour reuse
- contour refresh
- previous contour fallback
- bbox fallback

### 11.6 パフォーマンス要件

- デフォルト fast モードで GrabCut 常用より大幅高速化
- 長尺動画でも途中保存やジョブ再試行が可能
- GPU 失敗時は CPU 自動フォールバック

---

## 12. 検出バックエンド要件

### 12.1 共通抽象

```python
class ModelRunner:
    def load(self) -> None
    def detect(self, image_bgr) -> list[dict]
    def detect_batch(self, images_bgr) -> list[list[dict]]
    def is_available(self) -> bool
```

### 12.2 DetectorFactory

- backend 名から生成
- 未知 backend は明示エラー
- 利用不可なら安全な fallback を行う

### 12.3 ラベル正規化

- 内部ラベルへ統一
- 後段に detector 固有ラベルを流さない
- `LABEL_MAP`, `LABEL_GROUPS`, `LABEL_CATEGORIES` を Python 側の正本とする

### 12.4 モデル配置

- 必須: `320n.onnx`
- 任意: `640m.onnx`, `erax_v1_1.onnx`, `erax_v1_1.pt`, `sam2_tiny_*.onnx`
- モデル不足時は UI 上に不足状態を表示できること

---

## 13. 教師データ保存の本実装要件

この章は本仕様書で正式に追加する。

### 13.1 基本方針

- デフォルトは **OFF**
- 保存先はローカルのみ
- 外部送信は行わない
- ユーザーが明示的に ON にしたときのみ保存する
- 削除しやすさを最優先する

### 13.2 目的

- 人間が修正した結果を将来の学習データとして再利用する
- どこで AI が失敗したかを記録する
- 学習用 crop / mask / metadata を整然と残す

### 13.3 保存単位

教師データは**動画全体ではなく、対象領域中心の最小単位**で保存する。

保存単位:
- frame-level crop
- track-level sample group
- project-level dataset manifest

### 13.4 保存対象

#### 必須
- project_id
- source_video_hash
- frame_index
- timestamp_sec
- model_name
- model_version
- detector_config snapshot
- initial_label
- initial_bbox
- initial_confidence
- final_label
- final_bbox
- final_shape_type
- final_polygon or mask reference
- keyframe_source history
- human_verified

#### 推奨
- edit_duration_ms
- edit_operation_count
- vertex_add_count
- vertex_delete_count
- vertex_move_total
- track_move_distance
- initial_to_final_iou
- reused_auto_mask
- rebuilt_from_scratch
- rejected_auto_detection

#### 任意
- uncertain flag
- scene tag
- comments

### 13.5 保存ファイル構成

```text
data/training/
  datasets/
    dataset_YYYYMMDD_HHMMSS/
      manifest.json
      items/
        item_000001/
          input_crop.png
          preview_before.png
          preview_after.png
          initial_mask.json
          final_mask.json
          meta.json
```

### 13.6 画像保存方針

- 入力動画全体はコピーしない
- 必要最小範囲の crop を保存する
- crop にはコンテキスト margin を持たせる
- 元動画への参照は hash と frame index で持つ

### 13.7 保存トリガー

- manual keyframe 確定時
- export 完了時に使用区間のみまとめて抽出
- 明示的な「教師データ書き出し」実行時

正式仕様では、**export 完了時の確定区間抽出** を標準とする。

### 13.8 UI 要件

- 設定画面に「教師データ保存」トグル
- 保存先選択
- 保存容量見積もり表示
- 何を保存するかの説明表示
- データ一覧 / 削除導線
- project 単位 / dataset 単位削除

### 13.9 安全要件

- 外部送信禁止
- 既定で暗黙保存しない
- 削除時は manifest と関連ファイルを一括削除
- 保存された dataset は project から参照可能

### 13.10 受け入れ基準

- ON のときだけ保存される
- crop, 初期予測, 最終結果, メタ情報が一式残る
- 後で再学習ジョブがそのまま読める構造である
- ユーザーが削除できる

---

## 14. 自動再学習の本実装要件

この章も本仕様書で正式に追加する。

### 14.1 基本方針

- **ローカル再学習** を第一段階の正式仕様とする
- 外部アップロードなし
- ユーザーの同意なしに自動学習開始しない
- まずは教師あり fine-tuning を採用する
- 強化学習や連合学習は本実装対象外とする

### 14.2 目的

- ユーザーの修正結果から、その環境専用に検出精度を改善する
- 苦手ケースを局所改善する
- モデル比較・更新の基盤を整備する

### 14.3 学習対象

初期段階では以下のどちらかを採用可能とする。

1. **EraX / YOLO 系の再学習**
   - `.pt` ベース fine-tuning
   - 最も実装現実性が高い候補

2. **検出器ではなく補助 refinement モデルの学習**
   - bbox 補正 / mask refinement の軽量学習

**NudeNet ONNX 直再学習は前提にしない。**  
NudeNet は推論用 backend とし、再学習実務は YOLO 系か補助モデルで行う構成を正式採用候補とする。

### 14.4 学習パイプライン

```text
Teacher Dataset
  -> dataset validator
  -> train/val split
  -> augmentation
  -> training job
  -> checkpoint selection
  -> evaluation report
  -> model registry
  -> optional promote to active backend
```

### 14.5 学習ジョブ要件

- Python 側 job として実行
- GPU 有無で自動切替
- 長時間ジョブ UI を持つ
- 学習ログ保存
- 途中失敗時 resume 可能であることが望ましい

### 14.6 データ前処理要件

- 入力 crop 正規化
- bbox / polygon から学習ラベル生成
- train/val split
- 重複除去
- 極端に小さい / 壊れたサンプル除外
- ラベル分布レポート生成

### 14.7 学習設定

```ts
TrainingConfig {
  enabled: boolean
  mode: "manual" | "scheduled_local"
  targetModel: "erax_v1_1" | "refiner_v1"
  batchSize: number
  epochs: number
  imageSize: number
  learningRate: number
  useGpu: boolean
  minSamplesToTrain: number
  autoPromoteIfBetter: boolean
}
```

### 14.8 実行モード

#### 14.8.1 manual
- ユーザーが明示実行
- 標準モード

#### 14.8.2 scheduled_local
- ローカル環境で夜間などに学習
- ただし初期リリースでは OFF 推奨

### 14.9 モデルレジストリ

```text
data/models/
  registry.json
  custom/
    erax_finetuned_20260402_001/
      weights.pt
      config.json
      metrics.json
      source_dataset_manifest.json
```

### 14.10 評価指標

- precision
- recall
- mAP or task-equivalent metric
- validation loss
- inference speed
- false negative emphasis metric

### 14.11 モデル昇格条件

- 学習後、既存 active backend より改善が明確な場合のみ promote 候補とする
- 自動昇格は OFF を標準とする
- 昇格前に比較レポートを表示する

### 14.12 UI 要件

- 学習データ数表示
- 学習開始ボタン
- 学習設定画面
- 学習ログ表示
- 学習済みモデル一覧
- active model 切替
- 失敗時の理由表示

### 14.13 安全要件

- 外部送信なし
- 生動画全体は学習入力にしない
- crop / 最終マスク中心
- 学習前に必要サンプル数をチェック
- ディスク空き容量チェック
- GPU 利用時の VRAM 不足検知

### 14.14 受け入れ基準

- 保存済み dataset から再学習を実行できる
- 学習ログ、成果物、評価結果が残る
- 学習済みモデルを active backend として選択できる
- 元モデルへロールバックできる

---

## 15. 最終インストーラ設計要件

### 15.1 配布対象

Windows 向け正式配布物は以下の 2 コンポーネント構成とする。

1. **Tauri アプリ本体**
2. **Python runtime bundle + AI backend assets**

### 15.2 インストーラ方式

- Windows 標準向けに MSI または NSIS 系を正式採用候補とする
- 初期正式版では **one-folder install** を基本とする
- one-file への過度な圧縮は行わない

### 15.3 同梱物

- Tauri executable
- Python 埋め込み runtime または venv 相当 bundle
- 必須 Python パッケージ
- ffmpeg / ffprobe
- 必須モデル `320n.onnx`
- 設定テンプレート
- ライセンス / 利用上の注意

### 15.4 任意ダウンロード物

以下は基本インストールに必須としない。

- `640m.onnx`
- `erax_v1_1.onnx` / `.pt`
- `sam2_tiny_*`
- 再学習用大型依存

これらは「追加コンポーネント」として管理する。

### 15.5 インストール後ディレクトリ設計

```text
%LOCALAPPDATA%/AutoMosaic/
  app/
  runtime/
  models/
  data/
    config/
    logs/
    temp/
    exports/
    training/
```

または環境変数 override を許可する。

### 15.6 初回起動フロー

1. Python runtime の存在確認
2. 必須モデル確認
3. ffmpeg / ffprobe 確認
4. GPU 環境確認
5. data directories 作成
6. 設定ファイル生成
7. 必要なら不足コンポーネント案内

### 15.7 オンライン / オフライン戦略

- 基本はオフラインで動作可能にする
- 追加モデル導入のみ任意オンライン
- 完全オフライン運用でも必須機能が成立すること

### 15.8 更新戦略

- アプリ更新とモデル更新を分離する
- アプリ更新時に user data を消さない
- 学習済み custom model を保護する
- major version 変更時は migration 実行

### 15.9 アンインストール要件

#### 15.9.1 アンインストール方法

正式版では次の 3 経路を提供する。

1. **Windows の「インストール済みアプリ」から削除**
   - 設定 > アプリ > インストールされているアプリ > Auto Mosaic > アンインストール
2. **スタートメニューの「Auto Mosaic Uninstall」から削除**
   - 専用アンインストーラを起動する
3. **コマンドラインから削除**
   - MSI 採用時: `msiexec /x {ProductCode}`
   - NSIS 採用時: `uninstall.exe /S`（サイレント削除用）

#### 15.9.2 アンインストーラが削除する対象

**標準削除**では以下を削除する。

- Tauri executable
- Rust / Web UI バンドル
- Python runtime bundle
- 同梱 Python パッケージ
- ffmpeg / ffprobe
- 必須同梱モデル
- スタートメニュー項目
- デスクトップショートカット
- レジストリのアプリ登録情報
- ファイル関連付け（採用時のみ）

#### 15.9.3 ユーザーデータの扱い

アンインストーラ実行時に、次のいずれかを選択できること。

1. **アプリ本体のみ削除**
   - project
   - exports
   - logs
   - training data
   - custom model
   - user settings
   を残す
2. **キャッシュと一時ファイルのみ追加削除**
   - `temp/`, `cache/`, 一時ジョブファイルを削除
3. **完全削除**
   - user data, project, export, training, custom model, settings をすべて削除

#### 15.9.4 削除対象ディレクトリ

```text
%LOCALAPPDATA%/AutoMosaic/
  app/
  runtime/
  models/
  data/
    config/
    logs/
    temp/
    cache/
    exports/
    training/
    projects/
```

- 標準削除では `app/`, `runtime/` を削除対象とする
- `data/` と `models/` の user-generated 領域はユーザー選択に応じて削除する

#### 15.9.5 UI 表示要件

アンインストーラは削除前に、少なくとも次を表示すること。

- 何が削除されるか
- project / export / training / custom model が残るか消えるか
- 後から手動削除が必要な場所
- 完全削除を選ぶと元に戻せないこと

#### 15.9.6 手動アンインストール手順（サポート文書にも記載）

自動アンインストーラが失敗した場合に備え、以下の手順をサポート文書へ記載する。

1. Windows のアプリ一覧から Auto Mosaic を削除する
2. 残っている `%LOCALAPPDATA%/AutoMosaic/` を確認する
3. 不要なら `data/temp`, `data/cache`, `logs` を削除する
4. 完全削除したい場合のみ `projects`, `exports`, `training`, `custom models` も削除する

#### 15.9.7 受け入れ基準

- アンインストール後にアプリ本体が起動しない
- 標準削除時にユーザーデータが不意に消えない
- 完全削除時に主要保存データが残らない
- 再インストール後に user data 残置ケースでは project を再利用できる

### 15.10 インストーラ UI 要件

- 標準インストール / カスタムインストール
- 追加モデル選択
- GPU 推奨表示
- 保存先設定
- ショートカット作成
- 既存ユーザーデータ保持可否

### 15.11 受け入れ基準

- クリーンな Windows 環境で起動できる
- Python 未導入環境でも動作する
- 必須機能が初回起動から使える
- アップデートで project と custom model が壊れない

---

## 16. パス / ストレージ方針

### 16.1 論理パス

- config
- logs
- temp
- exports
- models
- training datasets
- custom trained models

### 16.2 環境変数 override

- `AUTO_MOSAIC_DATA_DIR`
- `AUTO_MOSAIC_SETTINGS_DIR`
- `AUTO_MOSAIC_LOG_DIR`
- `AUTO_MOSAIC_TEMP_DIR`
- `AUTO_MOSAIC_EXPORT_DIR`
- `AUTO_MOSAIC_MODEL_DIR`
- `AUTO_MOSAIC_FFMPEG_PATH`
- `AUTO_MOSAIC_FFPROBE_PATH`

### 16.3 データ分離

- アプリ本体とユーザーデータは分離
- モデル本体とユーザー学習済みモデルも分離
- temp はいつでも掃除可能であること

---

## 17. セキュリティ / プライバシー要件

- 入力動画を外部送信しない
- 教師データ保存は明示 opt-in
- 再学習はローカル実行
- 外部共有は本仕様外
- ログに動画パス以外のセンシティブ内容を過剰に残さない
- 何が保存されるかを UI で明示する

---

## 18. 非機能要件

### 18.1 性能
- 長尺動画でもジョブとして安定実行できること
- UI をブロックしないこと
- GPU 利用時は CPU より短い実行時間が期待できること

### 18.2 信頼性
- 途中失敗時に reason が見えること
- export 失敗で project が壊れないこと
- dataset capture / training 失敗時も本体動作を巻き込まないこと

### 18.3 拡張性
- detector backend 追加可能
- contour backend 追加可能
- Tauri UI の画面改善が Python 本体を壊さないこと

### 18.4 保守性
- JSON 契約が明文化されていること
- Python 側のサービスが UI 非依存であること
- テストしやすい pure logic を優先すること

---

## 19. テスト要件

### 19.1 Python 単体テスト
- label normalization
- bbox / polygon interpolation
- track lifecycle
- stitch
- manual protection
- export config validation
- training dataset manifest generation
- retraining config validation

### 19.2 Python 結合テスト
- open video -> detect -> track build -> save -> load
- export job
- teacher data capture job
- retraining job dry-run
- GPU unavailable fallback

### 19.3 Tauri 側テスト
- subprocess invocation
- JSON parse
- job progress rendering
- cancel flow
- file dialog -> project open/save

### 19.4 E2E テスト
- 新規動画読込
- 自動検出
- track 編集
- モザイク書き出し
- 教師データ保存
- 再学習実行
- 学習済みモデル切替

---

## 20. 実装フェーズ

### Phase 1: バックエンド境界固定
- CLI 契約確定
- job manager 導入
- runtime paths 整理
- settings API 整理

### Phase 2: Tauri UI 骨格
- shell
- preview/timeline/layout
- project open/save
- job panel

### Phase 3: 編集ワークフロー移植
- track list
- preview editing
- keyframe ops
- property panel
- undo/redo

### Phase 4: export / GPU / model settings
- export dialog
- detector backend settings
- contour settings
- hardware diagnostics

### Phase 5: 教師データ保存本実装
- dataset manifest
- crop generation
- deletion UI
- storage quotas

### Phase 6: 再学習本実装
- training jobs
- model registry
- evaluation report
- active model switching

### Phase 7: 最終インストーラ
- Windows packaging
- bundled runtime
- first-run bootstrap
- updater strategy

---

## 21. 受け入れ基準

### 21.1 プロダクト成立
- 動画読込、検出、編集、書き出しが Tauri 版で成立する
- 旧 PySide6 実装に依存せず主要機能が完結する

### 21.2 ブリッジ成立
- Tauri から Python を JSON 契約で呼び出せる
- 長時間処理が job 化され、進捗・失敗・キャンセルが見える

### 21.3 track 編集成立
- 同一対象の track が過剰に乱立しない
- manual keyframe が自動処理で壊れない
- UI と書き出しの存在区間が一致する

### 21.4 学習拡張成立
- 教師データ保存が opt-in で動作する
- ローカル再学習が実行できる
- 学習済みモデルを切り替えられる

### 21.5 配布成立
- Windows 未開発環境にインストールして起動できる
- 必須モデル込みで基本機能が動作する

---

## 22. 開発上の重要な判断

1. **Tauri と Python の結合は subprocess + CLI + JSON を正本とする**
2. **mask track を中心概念とし、UI・内部・書き出しで一貫させる**
3. **教師データ保存と再学習はローカル-only / opt-in を正式採用する**
4. **NudeNet は推論基盤、再学習は YOLO/EraX 系または補助モデル中心で設計する**
5. **Windows 最終配布では Python 同梱を前提とする**

---

## 23. 参考として継承した既存ファイル群

- `README.md`
- `01_core-product-requirements.md`
- `02_mask-track-requirements.md`
- `MASK_SPEC.md`
- `persistent_mask_track_requirements.md`
- `01_architecture-and-ui.md`
- `tauri_migration_backend_plan.md`
- `future_retraining_design_memo.md`
- `prompt_detector_abstraction.md`
