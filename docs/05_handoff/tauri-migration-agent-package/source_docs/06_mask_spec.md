# マスク動作 実装要件仕様書

> **対象**: `app/domain/services/tracking_service.py`, `app/domain/services/contour_service.py`, `app/infra/ai/label_mapper.py`, `app/gpu_config.py`
> **最終更新**: 2026-03-25
> **ステータス**: 実装中（Phase 1-2 完了、Phase 3 未着手）

---

## 1. 用語定義

| 用語 | 定義 |
|------|------|
| **トラック (MaskTrack)** | 1つの追跡対象に対応するマスクの時系列。label, keyframes, state を持つ |
| **キーフレーム (Keyframe)** | 特定フレームにおけるマスクの形状情報。bbox, points, contour_points を持つ |
| **検出 (Detection)** | NudeNet が1フレームから返す個別の検出結果。label, bbox, score |
| **輪郭 (Contour)** | 検出 bbox からピクセルレベルで抽出した物体の境界線 |
| **ラベルグループ (label_group)** | 同一身体部位の表記揺れを統合したグループ（例: breast + areola → breast_group） |
| **stitch** | 分断されたトラック断片を後段で結合する処理 |

---

## 2. 全体アーキテクチャ

```
NudeNet 検出
  │
  ▼
ラベルフィルタ (LABEL_CATEGORIES)
  │  ユーザーが選択したカテゴリのみ通過
  ▼
TrackingService.build_tracks()
  │
  ├── 前段: detection → track マッチング
  │     active 優先 → lost 再接続 → 新規作成
  │
  ├── 中段: キーフレーム生成 + 輪郭抽出
  │     contour_mode に応じた手法選択
  │
  ├── 後段: stitch (断片トラック結合)
  │
  └── 最終: ephemeral track 除去
        min_track_length_to_keep 未満を削除
```

---

## 3. トラックライフサイクル

### 3.1 状態遷移図

```
                    検出あり
  ┌──────────────────────┐
  │                      ▼
  │    ┌─────────────────────┐
  │    │       active         │
  │    │  (検出に結びついている) │
  │    └─────────┬───────────┘
  │              │ max_frame_gap フレーム未検出
  │              ▼
  │    ┌─────────────────────┐
  └────│        lost          │
  再検出 │ (一時的に見失った)    │
       └─────────┬───────────┘
                 │ lost_grace_frames 超過
                 ▼
       ┌─────────────────────┐
       │      inactive        │
       │  (終了確定)           │
       └─────────────────────┘
```

### 3.2 状態定義

| 状態 | 内部値 | 意味 | マッチング対象 |
|------|--------|------|---------------|
| **active** | `"active"` | 直近フレームで検出に結びついている | 最優先でマッチ |
| **lost** | `"lost"` | 一時的に未検出だが再接続候補 | active の次にマッチ |
| **inactive** | `"inactive"` | 猶予超過で終了。再接続対象外 | マッチしない |

### 3.3 閾値（TrackingConfig 現在値）

| パラメータ | 値 | 意味 |
|-----------|-----|------|
| `max_frame_gap` | 30 | active → lost に遷移するまでの未検出フレーム数 |
| `lost_grace_frames` | 60 | lost → inactive に遷移するまでの猶予フレーム数 |
| `reassoc_distance_ratio` | 1.5 | 再関連付けの距離上限比率 |
| `min_track_length_to_keep` | 3 | 最終出力に残す最小キーフレーム数 |
| `min_auto_keyframes` | 2 | ephemeral フィルタの閾値 |

### 3.4 保護ルール

- **user_locked トラック**: ユーザーが手動編集したトラックは自動削除しない
- **manual キーフレーム**: `source="manual"` のキーフレームは `auto`/`predicted` で上書きしない
- **re-detected**: lost → active に復帰したキーフレームに付与される source

---

## 4. トラックマッチング

### 4.1 マッチング優先順位（絶対条件）

detection が来たとき、以下の順で判定する:

```
1. active トラックにマッチするか？ → YES → 既存トラックに追加
2. lost トラックに再接続できるか？ → YES → トラック復帰
3. どちらにも当てはまらない       → 新規トラック作成
```

**「active にマッチしなければ即 new track」は禁止。**
必ず lost を経由する。

### 4.2 マッチングスコア計算

`_compute_match_score()` で以下の4要素を加重平均:

| 要素 | 重み | 計算方法 |
|------|------|---------|
| IoU | `match_iou_weight` = 0.3 | bbox 同士の Intersection over Union |
| 距離 | `match_distance_weight` = 0.4 | 中心距離を max_edge で正規化、1.0 - normalized |
| 面積類似度 | `match_area_weight` = 0.2 | min(area1, area2) / max(area1, area2) |
| アスペクト比類似度 | `match_aspect_weight` = 0.1 | 1.0 - \|aspect1 - aspect2\| / max(aspect1, aspect2) |

### 4.3 マッチング最低スコア

| 対象 | 閾値 | 意味 |
|------|------|------|
| active トラック | `match_min_score_active` = 0.25 | これ未満のスコアは active マッチ不可 |
| lost トラック | `match_min_score_lost` = 0.20 | lost の方が閾値を緩くして再接続しやすくする |

### 4.4 マッチング条件（禁止事項）

- **label 単独でのマッチングは禁止**: 必ず空間情報（IoU, 距離, 面積, アスペクト比）を併用
- **同一フレームの二重割当禁止**: 1つの detection を複数トラックに割り当てない
- **label_group による候補絞り込み**: 同じ label_group のトラックのみマッチ候補とする

### 4.5 複数人同時出現の保護

同じ label の別個体が同時に存在する場合:
- 近い方・整合性の高い方にのみマッチ
- 同一フレーム内で同じトラックへの二重割当を禁止
- label だけでの統合は絶対にしない

---

## 5. 後段 stitch（断片トラック結合）

### 5.1 位置づけ

stitch は**補助**であり、主たる修正は前段のマッチング改善。
「大量生成して後からマージ」ではなく、「前段で乱立を抑え、残った断片だけ stitch で吸収」。

### 5.2 stitch 条件

2つのトラックを結合するには、以下を**すべて**満たす必要がある:

| 条件 | 閾値 | 意味 |
|------|------|------|
| 同一 label_group | — | 異なる部位は結合しない |
| フレーム gap | `stitch_max_frame_gap` = 40 | 時間的に近い |
| overlap フレーム | `stitch_max_overlap_frames` ≤ 1 | 同時に存在する期間が短い |
| 中心距離比 | `stitch_max_center_distance_ratio` ≤ 1.5 | 空間的に近い |
| 面積類似度 | `stitch_min_area_similarity` ≥ 0.35 | サイズが近い |
| アスペクト比類似度 | `stitch_min_aspect_similarity` ≥ 0.45 | 形が近い |
| 総合スコア | `stitch_min_score` ≥ 0.40 | 加重平均が閾値以上 |

### 5.3 stitch スコア加重

| 要素 | 重み |
|------|------|
| IoU | `stitch_iou_weight` = 0.35 |
| 距離 | `stitch_distance_weight` = 0.30 |
| 面積 | `stitch_area_weight` = 0.20 |
| アスペクト比 | `stitch_aspect_weight` = 0.15 |

---

## 6. 短命トラック除去

### 6.1 ルール

`build_tracks()` の最終段で `_filter_ephemeral_tracks()` を実行:

- auto キーフレーム数が `min_track_length_to_keep` (= 3) 未満 → 除去
- **例外**: `user_locked = True` のトラックは保護
- **例外**: `source != "auto"` のキーフレームを持つトラックは保護

### 6.2 目的

- 1-2 フレームだけの誤検出ノイズを最終出力から排除
- UI 上でユーザーが理解できない数のマスク表示を防止

---

## 7. ラベルフィルタ

### 7.1 構造

```
LABEL_CATEGORIES（ユーザー向けカテゴリ）
  ├── genital_m: ("男性器", {penis, male_genitalia_exposed})
  ├── genital_f: ("女性器", {vulva, female_genitalia_exposed})
  ├── breast:    ("胸",     {breast, areola, exposed_breast, female_breast_exposed})
  ├── buttocks:  ("臀部",   {buttocks, anus, exposed_anus})
  ├── belly:     ("腹部",   {belly})
  └── face:      ("顔",     {face_female, face_male})
```

### 7.2 デフォルト有効カテゴリ

```python
DEFAULT_ENABLED_CATEGORIES = {"genital_m", "genital_f", "breast", "buttocks"}
```

- `face` と `belly` はデフォルト無効（ノイズトラックの主因）
- ユーザーが GPU 設定ダイアログで変更可能

### 7.3 フィルタ適用タイミング

- NudeNet 推論は**全ラベル**で実行（推論自体は変えない）
- 推論結果の `detections` を `build_allowed_labels()` で**後フィルタ**
- `DetectionWorker` と `detect_current_frame` の**両方**に適用

### 7.4 ラベルグループ（内部統合用）

```
LABEL_GROUPS（トラッキング内部の label_group）
  ├── breast_group:    breast, areola, exposed_breast, female_breast_exposed
  ├── torso_group:     belly
  ├── buttocks_group:  buttocks, anus, exposed_anus
  ├── genital_f_group: vulva, female_genitalia_exposed
  └── genital_m_group: penis, male_genitalia_exposed
```

- マッチング時に `label_group()` で候補を絞り込む
- 表記揺れ（例: `breast` と `areola`）を同一トラックとして扱える
- label 単独マッチングとは異なる（空間情報は必須）

---

## 8. 輪郭抽出モード

### 8.1 モード一覧

| モード | 手法 | 速度 | 精度 | 用途 |
|--------|------|------|------|------|
| `none` | bbox → 楕円/多角形のみ | <1ms | ★ | 最速。輪郭不要な場合 |
| `fast` | HSV 肌色マスク + morphology + findContours | 5-15ms | ★★ | **デフォルト**。検出パイプライン用 |
| `balanced` | GrabCut（従来手法） | 300-600ms | ★★★ | オンデマンド。高品質が必要な場合 |
| `quality` | SAM2 tiny (ONNX)（予定） | 30-80ms (GPU) | ★★★★★ | 将来実装。最高精度 |

### 8.2 デフォルト: `fast`

```python
# GpuConfig
contour_mode: ContourMode = "fast"

# TrackingConfig
contour_mode: ContourMode = "fast"
```

### 8.3 fast モード詳細（HSV 肌色マスク）

```
bbox 領域切り出し（10% 膨張）
  → HSV 変換
  → 肌色範囲でマスク生成
      HSV_SKIN_RANGES = [
        ((0, 20, 70), (20, 255, 255)),     # 一般的な肌色
        ((160, 20, 70), (180, 255, 255)),   # 赤みがかった肌色
      ]
  → bbox 内側を重み付け（外側の肌色を抑制）
  → morphology open/close（3x3 楕円カーネル）
  → findContours → 最大輪郭
  → approxPolyDP 平滑化
  → ROI 座標 → フレーム座標変換
```

失敗時: 空リストを返す → 呼び出し元が bbox フォールバック

### 8.4 balanced モード詳細（GrabCut）

```
bbox 領域切り出し（roi_expand_ratio 膨張）
  → simple_mask 生成（Otsu 二値化ベース）
  → GrabCut スキップ判定
      - simple_mask が十分 → スキップ
      - face ラベル → スキップ
      - 低信頼度 → スキップ
      - 小さい bbox → スキップ
  → GrabCut 実行（rect 初期化、反復数は動的調整）
  → 失敗時は simple_mask にフォールバック
  → morphology clean
  → 最大輪郭抽出
  → 平滑化（scipy.ndimage.gaussian_filter1d）
  → approxPolyDP 簡略化
```

### 8.5 quality モード（SAM2 tiny — 将来実装）

- SAM2 tiny の ONNX モデルを使用（~40MB）
- bbox をプロンプトとして入力 → ピクセルレベルのセグメンテーション
- 動画ネイティブのメモリ機構によるフレーム間追跡（将来活用）
- モデルファイル未配置時は balanced にフォールバック

### 8.6 輪郭の再利用 (contour reuse)

連続フレームで毎回輪郭を計算しない最適化:

| パラメータ | 値 | 意味 |
|-----------|-----|------|
| `contour_reuse_enabled` | true | 再利用を有効にする |
| `contour_refresh_interval_frames` | 10 | N フレームごとに再計算 |
| `contour_reuse_area_delta_ratio` | 0.15 | 面積変化がこれ以下なら再利用 |
| `contour_reuse_aspect_delta_ratio` | 0.15 | アスペクト比変化がこれ以下なら再利用 |
| `contour_reuse_center_shift_ratio` | 0.15 | 中心移動がこれ以下なら再利用 |
| `contour_reuse_confidence_floor` | 0.45 | 信頼度がこれ以上で再利用 |

再利用判定: 前フレームの輪郭を bbox 変形で適用。
条件を満たさない場合のみ新規に輪郭を計算。

contour_mode ごとに effective_* メソッドで閾値を動的調整:
- `fast`: 緩い閾値（再利用を積極的に行い速度優先）
- `quality`: 厳しい閾値（頻繁に再計算して精度優先）

### 8.7 フォールバック階層

```
1. contour reuse（前フレームの輪郭を変形）
      ↓ 失敗
2. contour refresh（現フレームで新規に輪郭抽出）
      ↓ 失敗
3. previous contour fallback（前フレームの輪郭を bbox 変換で適用）
      ↓ 失敗
4. bbox fallback（bbox → 8頂点多角形）
```

---

## 9. キーフレーム形状

### 9.1 形状タイプ

| shape_type | 用途 | points の意味 |
|------------|------|--------------|
| `ellipse` | penis, face 等の丸い対象 | bbox ベースの楕円パラメータ |
| `polygon` | 複雑な形状の対象 | 頂点座標リスト [[x, y], ...] |

### 9.2 形状選択ルール

```python
ELLIPSE_LABELS = {"penis", "genital_contact", "mouth_contact", "manual"}
ELLIPSE_LABEL_PREFIXES = ("face",)
```

上記に該当 → `ellipse`、それ以外 → `polygon`

### 9.3 キーフレーム source

| source | 意味 |
|--------|------|
| `auto` | 自動検出で生成 |
| `manual` | ユーザーが手動で編集 |
| `interpolated` | 2つのキーフレーム間を線形補間 |
| `predicted` | lost 状態での予測位置 |
| `re-detected` | lost → active に復帰した時の検出 |

---

## 10. 検出パイプライン設定

### 10.1 GpuConfig（ユーザー設定、永続化）

| パラメータ | デフォルト | 意味 |
|-----------|-----------|------|
| `device` | `"auto"` | デバイス選択: auto / cuda / cpu |
| `sample_every` | 10 | N フレームごとに検出 |
| `max_samples` | 0 | 最大サンプル数（0=無制限） |
| `inference_resolution` | 640 | 推論解像度 px（0=元解像度） |
| `batch_size` | 4 | バッチサイズ |
| `confidence_threshold` | 0.45 | 検出信頼度閾値 |
| `contour_mode` | `"fast"` | 輪郭抽出モード |
| `precise_face_contour` | false | 顔の精密輪郭を有効にする |
| `enabled_label_categories` | genital_m, genital_f, breast, buttocks | 検出対象カテゴリ |
| `vram_saving_mode` | false | VRAM 節約モード |

### 10.2 パフォーマンス実測値（RTX 3090, 95分 1080p 動画）

| フェーズ | 時間 | 備考 |
|---------|------|------|
| フレーム読み込み | 131秒 | resolution=0 時。640px なら短縮 |
| NudeNet 推論 | 172秒 | resolution=0 時。640px なら 1/3-1/4 |
| GrabCut 輪郭 | 909秒 | **ボトルネック**。fast モードで 25秒に短縮 |
| トラック生成 | 8秒 | stitch, filter 含む |
| **合計** | **~20分** | fast モード適用で **~5分** に短縮見込み |

---

## 11. MaskStyle（表示スタイル）

トラック単位のモザイク表示設定:

| パラメータ | 範囲 | デフォルト | 意味 |
|-----------|------|-----------|------|
| `mosaic_strength` | 2-100 | 20 | モザイクのピクセルサイズ |
| `expand_px` | 0-200 | 12 | マスク領域の拡張ピクセル数 |
| `feather` | 0- | 0 | マスク境界のぼかし幅 |

キーフレーム単位で `expand_px`, `feather` を上書き可能（None = トラックのデフォルト）。

---

## 12. データモデル

### 12.1 MaskTrack

```python
@dataclass
class MaskTrack:
    track_id: str           # UUID
    label: str              # 正規化済みラベル
    start_frame: int        # 検出開始フレーム
    end_frame: int          # 検出終了フレーム
    visible: bool           # UI 表示/非表示
    style: MaskStyle        # モザイクスタイル
    keyframes: list[Keyframe]
    state: TrackState       # "active" | "lost" | "inactive"
    source: TrackSource     # "auto" | "user-adjusted" | "re-detected"
    last_detected_frame: int
    last_tracked_frame: int
    missing_frame_count: int
    confidence: float
    user_locked: bool       # ユーザー編集保護
    motion_history: list[list[float]]       # bbox 中心の移動差分履歴
    association_history: list[dict]          # マッチング/再接続イベント履歴
```

### 12.2 Keyframe

```python
@dataclass
class Keyframe:
    frame_index: int
    shape_type: ShapeType       # "ellipse" | "polygon"
    points: list[list[float]]   # 最終表示ポイント
    bbox: list[float]           # [x, y, w, h]
    confidence: float
    source: SourceType          # "auto" | "manual" | "interpolated" | "predicted" | "re-detected"
    contour_points: list[list[float]]  # 高精度輪郭（GrabCut/HSV/SAM2 由来）
    rotation: float             # 回転角度
    opacity: float              # 不透明度
    expand_px: int | None       # スタイル上書き
    feather: int | None         # スタイル上書き
```

### 12.3 _TrackBuffer（内部のみ）

```python
@dataclass
class _TrackBuffer:
    track_id: str
    label: str
    keyframes: list[Keyframe]
    last_bbox: list[float]
    last_frame_index: int
    missing_count: int
    state: str                  # "active" | "lost" | "inactive"
    confidence: float
    motion_history: list[list[float]]
    association_history: list[dict]
```

---

## 13. 受け入れ条件

### 13.1 トラック数の抑制

- [ ] 同一対象が 1〜数フレーム見失われても、同名マスクが量産されない
- [ ] 同じ対象に対して track_id が頻繁に切り替わらない
- [ ] 最終的なマスク数が UI 上でユーザーが理解できる数に収まる

### 13.2 複数人対応

- [ ] 同一 label の複数対象が同時にいても誤統合しない
- [ ] label 単独での統合は行わない
- [ ] 空間情報（IoU, 距離, 面積, アスペクト比）を必ず使用

### 13.3 パフォーマンス

- [ ] デフォルト設定 (`fast` モード) で GrabCut 比 50倍以上高速
- [ ] 95分動画の全自動検出が 10分以内に完了（RTX 3090）
- [ ] `inference_resolution=640` がデフォルトで適用される

### 13.4 ユーザー保護

- [ ] `user_locked` トラックは自動処理で削除・変更されない
- [ ] `manual` キーフレームは `auto`/`predicted` で上書きされない
- [ ] 再生中は編集不可（`_ensure_editing_unlocked()`）

### 13.5 フォールバック

- [ ] 輪郭抽出失敗時は bbox フォールバックが必ず動作
- [ ] GPU 失敗時は CPU に自動切り替え
- [ ] SAM2 モデル未配置時は balanced にフォールバック
- [ ] NudeNet 未利用時は手動トラック追加で運用可能

---

## 14. 将来の拡張予定

| 項目 | 優先度 | 概要 |
|------|--------|------|
| SAM2 tiny ONNX 統合 | 高 | quality モードの実体。bbox プロンプト → セグメンテーション |
| SAM2 動画追跡活用 | 中 | SAM2 のメモリ機構でフレーム間追跡。TrackingService の大部分を代替可能 |
| 検出間隔の動的調整 | 中 | シーンの動きが少ない区間は sample_every を大きくする |
| GPU バッチ推論 | 低 | 複数フレームを同時に NudeNet に投入 |
| トラック merge UI | 低 | ユーザーが手動で2つのトラックを結合 |
| エクスポート設定 UI | 中 | コーデック・音声モード・保存先ダイアログ |

---

## 付録 A: 設定ファイル

### gpu_config.json（`data/gpu_config.json`）

```json
{
  "device": "auto",
  "sample_every": 10,
  "max_samples": 0,
  "inference_resolution": 640,
  "batch_size": 4,
  "confidence_threshold": 0.45,
  "contour_mode": "fast",
  "precise_face_contour": false,
  "enabled_label_categories": ["genital_m", "genital_f", "breast", "buttocks"],
  "vram_saving_mode": false
}
```

### TrackingConfig 全閾値一覧

```python
# ── 輪郭モード ──
contour_mode: "fast"
precise_face_contour: False

# ── トラックライフサイクル ──
max_frame_gap: 30           # active → lost
lost_grace_frames: 60       # lost → inactive
reassoc_distance_ratio: 1.5

# ── マッチングスコア ──
match_iou_weight: 0.3
match_distance_weight: 0.4
match_area_weight: 0.2
match_aspect_weight: 0.1
match_min_score_active: 0.25
match_min_score_lost: 0.20

# ── 短命トラック除去 ──
min_auto_keyframes: 2
min_track_length_to_keep: 3

# ── stitch ──
stitch_enabled: True
stitch_max_frame_gap: 40
stitch_max_overlap_frames: 1
stitch_max_center_distance_ratio: 1.5
stitch_min_bbox_iou: 0.0
stitch_min_area_similarity: 0.35
stitch_min_aspect_similarity: 0.45
stitch_min_score: 0.40
stitch_iou_weight: 0.35
stitch_distance_weight: 0.30
stitch_area_weight: 0.20
stitch_aspect_weight: 0.15

# ── 輪郭再利用 ──
contour_reuse_enabled: True
contour_refresh_interval_frames: 10
contour_reuse_area_delta_ratio: 0.15
contour_reuse_aspect_delta_ratio: 0.15
contour_reuse_center_shift_ratio: 0.15
contour_reuse_confidence_floor: 0.45
contour_reuse_confidence_drop: 0.18
contour_reuse_min_points: 12

# ── 拡張ピクセル ──
expand_px: 12
```
