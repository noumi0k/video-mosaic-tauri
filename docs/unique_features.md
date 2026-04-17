# Auto Mosaic — 独自機能ドキュメント

> **用途**: このドキュメントは、本ソフトを別の言語・フレームワークで再実装する際に、  
> 汎用的な編集ソフトには存在しない「Auto Mosaic 固有の概念・仕組み・アルゴリズム」を伝えるための仕様書である。  
> 汎用機能の詳細は `feature_list.md` を参照。

---

## カテゴリ一覧

1. [トラックライフサイクル管理](#1-トラックライフサイクル管理)
2. [ユーザー修正保護（manual キーフレーム保護）](#2-ユーザー修正保護manual-キーフレーム保護)
3. [輪郭自動抽出パイプライン（ContourService）](#3-輪郭自動抽出パイプラインcontourservice)
4. [Optical Flow 輪郭追従（ContourFollowService）](#4-optical-flow-輪郭追従contourfollow-service)
5. [アンカーベース継続性検証（ContinuityService）](#5-アンカーベース継続性検証continuityservice)
6. [キーフレームソース管理](#6-キーフレームソース管理)
7. [書き出し対象フラグ（export_enabled）](#7-書き出し対象フラグexport_enabled)
8. [危険フレーム検出（DangerousFrameDetector）](#8-危険フレーム検出dangerousframedetector)
9. [GPU / デバイス自動切替（DeviceManager）](#9-gpu--デバイス自動切替devicemanager)
10. [マルチエンジン検出アーキテクチャ（DetectorFactory）](#10-マルチエンジン検出アーキテクチャdetectorfactory)
11. [EraX モデル自動変換パイプライン](#11-erax-モデル自動変換パイプライン)
12. [カテゴリ・ラベルレジストリシステム](#12-カテゴリラベルレジストリシステム)
13. [書き出しキューとジョブ状態管理](#13-書き出しキューとジョブ状態管理)
14. [プロジェクトスナップショットと Undo 設計](#14-プロジェクトスナップショットと-undo-設計)
15. [モザイク強度パラメータ設計](#15-モザイク強度パラメータ設計)
16. [タイムライン凡例と状態可視化](#16-タイムライン凡例と状態可視化)

---

## 1. トラックライフサイクル管理

### 概要
Auto Mosaic では、マスクをフレーム単位で作成・破棄するのではなく、**トラック（MaskTrack）** という連続的な単位として管理する。トラックは以下の 3 つの状態を遷移する。

```
active ─(未検出フレームが max_frame_gap を超えた)──→ lost
  ↑                                                    │
  └─────(再検出で再関連付け)───────────────────────────┘
                                                        │
                                              (lost_grace_frames を超えた)
                                                        ↓
                                                    inactive
```

| 状態 | 意味 | プレビュー | 書き出し |
|---|---|---|---|
| `active` | 現在フレームで検出済み | 通常表示 | 対象 |
| `lost` | 一時的に未検出（予測補完中） | グレー表示（点線） | 対象（予測位置） |
| `inactive` | 猶予超過で無効化 | 非表示（設定次第） | 対象外 |

### パラメータ（TrackingConfig）
| パラメータ | デフォルト | 説明 |
|---|---|---|
| `max_frame_gap` | 60 フレーム | active → lost に遷移するまでの未検出許容フレーム数 |
| `lost_grace_frames` | 120 フレーム | lost → inactive に遷移するまでの猶予フレーム数 |
| `reassoc_distance_ratio` | 1.2 | 再関連付け時の距離判定比（bbox サイズの何倍まで許容するか） |

### 意図と効果
- 短い遮蔽（人が物の後ろを通る等）でトラックが消えない。
- 再登場した対象は同じトラック ID で継続する。
- ユーザーが手動編集したトラックは `user_locked` フラグで保護され、自動削除されない。

---

## 2. ユーザー修正保護（manual キーフレーム保護）

### 概要
ユーザーがプレビュー上で直接編集（移動・スケール・頂点編集）したキーフレームには `source = "manual"` が付与される。このキーフレームは、後から実行する AI 自動検出・再トラッキングによって **上書きされない**。

### 仕組み
- `MaskEditService.upsert_keyframe()` の `protect_manual=True`（デフォルト）が有効な場合、挿入対象フレームに `source = "manual"` のキーフレームが既に存在する場合は処理をスキップする。
- トラックには `user_locked` フラグがある。これが `True` のトラックは `TrackingService` による自動削除・置き換えの対象外になる。

### キーフレームソース優先順
1. `manual`（最優先、上書き不可）
2. `re-detected`（lost 状態から再検出で復帰）
3. `anchor_fallback`（ContinuityService が修正したキーフレーム）
4. `auto`（AI 検出の直接結果）
5. `contour_follow`（Optical Flow 追従）
6. `predicted`（motion 予測補完）
7. `interpolated`（キーフレーム間の線形補間、メモリ上のみ）

---

## 3. 輪郭自動抽出パイプライン（ContourService）

### 概要
AI 検出（NudeNet 等）は矩形の bbox を返す。これをより精密な多角形形状（輪郭）に変換するパイプライン。

### パイプライン手順
```
NudeNet bbox
    │
    ▼
ROI 拡張（bbox を一定率で外側に広げ、対象を完全に含む領域を確保）
    │
    ▼
GrabCut 前景抽出
（フレーム画像から人体/物体の輪郭を確率的に分離する）
    │
    ▼
morphology 処理（ノイズ除去・穴埋め）
    │
    ▼
最大輪郭抽出（最も大きい連続輪郭を選択）
    │
    ▼
輪郭平滑化
    │
    ▼
approxPolyDP（頂点数を削減して扱いやすい多角形に近似）
    │
    ▼
polygon キーフレームとして保存
```

### フォールバック
GrabCut が失敗した場合（低コントラスト・小さすぎる bbox など）は、元の bbox をそのまま矩形多角形に変換して使用する。呼び出し元は必ずこのフォールバックを実装すること。

### 輪郭モード（ContourConfig）
| モード | アルゴリズム | 速度 | 精度 |
|---|---|---|---|
| `none` | bbox のみ（輪郭抽出なし） | 最速 | 低 |
| `fast` | GrabCut 1 iteration, kernel 3x3 | 速い | 中 |
| `balanced` | GrabCut 5 iteration, kernel 5x5 | 中 | 高 |
| `quality` | GrabCut + SAM2 tiny ONNX 補助 | 遅い | 最高 |

### SAM2 品質モード
`quality` モードでは SAM2 tiny（Segment Anything Model 2）の ONNX モデルをロードし、GrabCut の結果を SAM2 のセグメンテーション結果でリファインする。encoder（エンコーダ）+ decoder（デコーダ）の 2 モデル構成。

---

## 4. Optical Flow 輪郭追従（ContourFollowService）

### 概要
Lucas-Kanade Sparse Optical Flow を使い、キーフレームが設定されていないフレームに対して輪郭の動きを自動的に追従させる。

### 動作
1. 開始キーフレームの輪郭頂点をフィーチャーポイントとして設定する。
2. 前後の方向（`forward` / `backward`）に 1 フレームずつ Optical Flow でポイントを追跡する。
3. 追跡結果を新しいキーフレームとして保存する（`source = "contour_follow"`）。

### 停止条件
以下のいずれかに該当した場合、追従を自動停止する。

| 停止コード | 条件 |
|---|---|
| `no_start_kf` | 開始キーフレームが存在しない |
| `no_pts` | フィーチャーポイントがゼロ |
| `no_frame` | フレームの読み込みに失敗 |
| `manual_kf` | 手動キーフレームに到達（上書きしない） |
| `existing_kf` | 既存キーフレームに到達 |
| `failure` | Optical Flow 計算失敗 |
| `area_change` | 輪郭面積が閾値以上変化（追従迷子検出） |
| `video_end` | 動画の末端に到達 |
| `cancelled` | ユーザーキャンセル |

---

## 5. アンカーベース継続性検証（ContinuityService）

### 概要
ユーザーが手動編集した後、後続の auto キーフレームが形状的に「突飛」でないかを検証し、問題があれば修正する仕組み。

### 3 段フォールバック
| 優先度 | 方法 | 条件 |
|---|---|---|
| 1 | アンカー形状 + auto の位置（位置のみ自動に従い、形状はアンカーを流用） | 面積比・中心シフトが閾値内 |
| 2 | アンカー形状 + 直前の安定フレームの位置 | 1 が失敗した場合 |
| 3 | 直前フレームをそのままホールド | 2 も失敗した場合 |

### 検証対象（ContinuityConfig の閾値）
- 面積比（auto / anchor の面積比）: デフォルト 0.3〜3.0 倍の範囲外は NG
- 中心シフト: bbox の対角線長の一定割合以上の移動は NG
- アスペクト比変化: 大幅な縦横比変化は NG

---

## 6. キーフレームソース管理

### 概要
各キーフレームには `source` フィールドがあり、その形状がどのように生成されたかを追跡する。

### source 値の一覧
| source | 意味 | 編集可否 | 自動上書き可否 |
|---|---|---|---|
| `manual` | ユーザーが手動で編集 | ○ | × |
| `auto` | AI 検出の直接結果 | ○ | ○ |
| `interpolated` | キーフレーム間の線形補間（描画時に計算、保存されない） | 参照のみ | - |
| `predicted` | motion 予測による補完 | ○ | ○ |
| `re-detected` | lost 状態から再検出で復帰 | ○ | ○ |
| `anchor_fallback` | ContinuityService が修正したキーフレーム | ○ | ○ |
| `contour_follow` | Optical Flow による追従 | ○ | ○ |

### タイムラインでの視覚表現
| source | マーカー色 |
|---|---|
| `manual` | 白 |
| `auto` / `interpolated` | 金色 |
| `predicted` | 灰色 |
| `re-detected` | 薄青 |
| `contour_follow` | 緑 |

---

## 7. 書き出し対象フラグ（export_enabled）

### 概要
トラックには「表示フラグ（visible）」とは独立した「書き出し対象フラグ（export_enabled）」が存在する。これにより、プレビューでは見えるが書き出し動画には反映しないという細かい制御が可能。

### 動作
- `export_enabled = False` のトラックは書き出し時の `RenderService.resolve_tracks()` で除外される。
- プレビュー上では半透明・ドット線・グレーで表示され、視覚的に区別できる。

### visible との違い
| フラグ | プレビュー表示 | 書き出しへの反映 |
|---|---|---|
| `visible = True` / `export_enabled = True` | 表示 | 対象 |
| `visible = True` / `export_enabled = False` | 表示（グレー・ドット線） | 対象外 |
| `visible = False` / `export_enabled = True` | 非表示 | 対象（書き出しに反映） |
| `visible = False` / `export_enabled = False` | 非表示 | 対象外 |

---

## 8. 危険フレーム検出（DangerousFrameDetector）

### 概要
書き出しを実行する前に、モザイクの「抜け」や「不自然な変化」が生じそうなフレームを自動検出し、ユーザーに警告する品質チェック機能。

### 検出する危険パターン
| 種類 | 条件 | 意味 |
|---|---|---|
| `long_gap` | 連続するキーフレーム間の距離が設定値（デフォルト 30 フレーム）以上 | 長い補間区間でマスクがずれる可能性がある |
| `area_jump` | 隣接キーフレーム間でマスク面積が急激に変化（デフォルト 3 倍以上） | マスクが突然大きく変形する可能性がある |
| `track_lost` | 書き出し範囲内に `predicted` ソースのキーフレームが存在する | AI 予測補完に頼っている区間が書き出しに含まれる |

### ユーザーの選択肢
- **レビュー**: 問題フレームに移動して手動修正する。
- **このまま書き出し**: 警告を無視して書き出しを続行する。
- **キャンセル**: 書き出しを中止する。

---

## 9. GPU / デバイス自動切替（DeviceManager）

### 概要
AI 推論・モザイク処理を GPU（CUDA）または CPU で実行するかを自動的に判断し、ビジネスロジック層から CUDA 固有のコードを隠蔽する。

### 動作
1. 起動時に CUDA の利用可否・VRAM 空き容量・ONNX Runtime GPU プロバイダの存在を確認する。
2. `preference`（auto / cuda / cpu）に基づいてデバイスを選択する。
3. GPU 初期化失敗または OOM（メモリ不足）エラーが発生した場合は自動的に CPU にフォールバックする。

### 提供する情報
- `DeviceStatus`: アクティブデバイス、CUDA 利用可否、ONNX GPU プロバイダ有無、VRAM 空き容量（MB）。
- `get_onnx_providers()`: ONNX Runtime に渡す ExecutionProvider リスト（GPU 優先）。
- `get_torch_device()`: PyTorch デバイスオブジェクト。

### 設定の永続化
`data/gpu_config.json` に `GpuConfig` データクラスとして保存される。

---

## 10. マルチエンジン検出アーキテクチャ（DetectorFactory）

### 概要
複数の AI 検出モデルを統一インターフェース（`ModelRunner` 抽象クラス）でラップし、エンジンを切り替えても呼び出し元のコードを変更しなくて済む設計。

### 対応エンジン
| バックエンド ID | モデル | 対象カテゴリ |
|---|---|---|
| `nudenet` | NudeNet 320n（ONNX） | NSFW ラベル（genital, breast 等） |
| `nudenet_640m` | NudeNet 640m（ONNX） | NSFW ラベル（高精度） |
| `erax_v1_1` | EraX v1.1（ONNX） | NSFW ラベル |
| `yolo_v3_tiny` | YOLOv3 Tiny（ONNX） | COCO 80 カテゴリ |
| `yolo_v3` | YOLOv3（ONNX） | COCO 80 カテゴリ |
| `ssd_resnet34_1200` | SSD ResNet34（ONNX） | COCO 80 カテゴリ |

### フォールバック
`DetectorFactory.create(backend, ..., strict=False)` の場合、指定エンジンが利用できなければ NudeNet にフォールバックする。`strict=True` の場合は例外を投げる。

### ModelRunner インターフェース
```
load(device_manager)   # モデルをメモリに読み込む
detect(image_bgr)      # 1 フレームを推論 → Detection リスト
detect_batch(images)   # バッチ推論 → Detection リストの 2D 配列
is_available()         # モデルファイルが存在し使用可能か
```

---

## 11. EraX モデル自動変換パイプライン

### 概要
EraX モデルは PyTorch 形式（`.pt`）で配布されるが、本ソフトは ONNX 形式（`.onnx`）での推論のみサポートする。そのため、アプリ起動時に `.pt` → `.onnx` 変換を自動的に試みる。

### 変換フロー
```
アプリ起動
    │
    ▼
models/ ディレクトリに .pt ファイルが存在するか確認
    │（存在する）
    ▼
.onnx ファイルが既に存在するか確認
    │（存在しない）
    ▼
try_auto_export_erax() を実行
    │
    ├─（成功）→ .onnx ファイルを models/ に保存
    │
    └─（失敗）→ ステータスバーに通知
                モデル管理ダイアログで手動変換手順を案内
```

### 変換コード
`app/infra/ai/erax_export.py` の `export_torch()` が PyTorch の `torch.onnx.export()` を呼び出す。

---

## 12. カテゴリ・ラベルレジストリシステム

### 概要
複数の検出エンジンは異なるラベル名を使用する（例: NudeNet は `EXPOSED_PENIS`、EraX は独自名）。これらを統一されたカテゴリ体系に正規化し、エンジンをまたいでフィルタリングできるようにする。

### 構成要素
1. **LABEL_MAP（label_schema.py）**: エンジン固有のラベル名を正規化ラベルにマッピング。  
   例: `EXPOSED_PENIS` → `penis`、`EXPOSED_BREAST_F` → `breast_f`

2. **LABEL_CATEGORIES（label_schema.py）**: 正規化ラベルを論理グループ（カテゴリ）にまとめる。  
   例: `genital_m` カテゴリ → `{penis, anus_m}` のラベルセット

3. **CategorySet / CategoryGroup / CategoryItem（category_presets.py）**: UI 表示用の階層構造。モデルごとのカテゴリを大分類グループ・個別項目で整理する。

4. **engine_registry.py**: エンジン ID からそのエンジンがサポートするカテゴリの `frozenset` を返す。

5. **DEFAULT_ENABLED_CATEGORIES**: デフォルトで有効にするカテゴリ（`genital_m`, `genital_f`, `breast`, `buttocks`）。

### 目的
- ユーザーがカテゴリ単位で検出対象を選択できる（エンジン固有のラベルを意識しなくて済む）。
- エンジンを変更しても同じカテゴリフィルタが適用される。

---

## 13. 書き出しキューとジョブ状態管理

### 概要
書き出し処理はキューで管理され、ジョブ状態が永続化される。アプリが再起動してもキューが維持される。

### ジョブ状態遷移
```
queued → running → completed
                 → canceled
                 → error
                 → interrupted（アプリ強制終了時）
```

### ExportJob の保持情報
- `job_id`: ユニーク ID
- `project_snapshot`: ジョブ登録時点のプロジェクト状態（後から編集されても書き出し内容は変わらない）
- `output_dir` / `file_name`: 出力先
- `settings`: 書き出し設定（ExportPreset）
- `status`: 現在の状態
- `progress_percent` / `stage_text` / `eta_text`: 進捗情報
- `created_at` / `started_at` / `finished_at`: タイムスタンプ

### 書き出し進捗フェーズ
`preparing` → `rendering` → `encoding` → `muxing` → `finalizing`

---

## 14. プロジェクトスナップショットと Undo 設計

### 概要
Undo/Redo は「コマンドパターン（操作の逆操作を記録する）」ではなく、**プロジェクト全体のスナップショットをスタックに積む** 方式を採用している。

### 設計の理由
- 操作の逆操作を実装するコストが高い（特に AI 検出・トラッキングなど複雑な操作）。
- プロジェクトデータが JSON シリアライズ可能な純粋なデータ構造であるため、ディープコピーが容易。

### 実装
- `HistoryService.push(state, label)`: `Project.snapshot()` を呼び、現在のプロジェクト状態を辞書に変換してスタックに積む。
- `HistoryService.undo()`: スタックを 1 つ戻し、`Project.from_dict()` で状態を復元して返す。
- `is_dirty()`: 最後に `mark_clean()` が呼ばれた後に変更があるかどうかを返す（保存済みフラグ管理）。

### 上限
デフォルト 100 段階（設定可能）。上限を超えると最古のスナップショットが削除される。

---

## 15. モザイク強度パラメータ設計

### 概要
モザイクの「強度（mosaic_strength）」は 2〜100 の整数値で表現される。数値の意味はピクセルブロックのサイズに反比例する形で設計されており、直感的な操作が可能。

### 計算式
```python
# モザイクブロックサイズ = 対象領域の幅 / mosaic_strength
block_size = max(1, int(roi_width / mosaic_strength))
```

- `mosaic_strength = 2` → ブロックサイズが最大（最も粗い）
- `mosaic_strength = 100` → ブロックサイズが最小（最も細かい、ほぼ元画像に近い）

### スタイルの継承ルール
1. キーフレームに個別の `mosaic_strength` が設定されている場合はそれを使用。
2. なければトラックの `MaskStyle.mosaic_strength` を使用。
3. なければプロジェクトの `ExportPreset.mosaic_strength` を使用。

---

## 16. タイムライン凡例と状態可視化

### 概要
タイムライン上のキーフレームマーカーの色は、キーフレームがどのように生成されたか（source）と、トラックの現在の状態（active / lost / inactive）を表す。ユーザーが常に状態を把握できるよう、凡例が常時表示される。

### キーフレームマーカーの色
| 色 | source | 意味 |
|---|---|---|
| 金色 | `auto` / `interpolated` | AI 自動生成または補間 |
| 白 | `manual` | ユーザー手動入力（保護済み） |
| 灰色 | `predicted` | motion 予測補完（確実性が低い） |
| 薄青 | `re-detected` | lost 状態から再検出で復帰 |
| 緑 | `contour_follow` | Optical Flow 追従 |

### トラックレーンの表示状態
| 状態 | 表示スタイル |
|---|---|
| `active` | 通常表示（実線） |
| `lost` | 点線・半透明 |
| `inactive` | 非表示（またはさらに暗い表示） |
| `export_enabled = False` | グレー・ドット線 |
| `user_locked` | ロックアイコン表示 |

### プレビューキャンバスのモードバッジ
プレビュー右上に常時表示されるバッジにより、現在の操作モードを視覚的に通知する。

| バッジ | 状態 |
|---|---|
| 「移動モード」 | マスクを移動・スケールできる状態 |
| 「頂点編集モード」 | 多角形の頂点を編集できる状態 |
| 「再生中」 | 動画が再生中（編集操作は無効） |
