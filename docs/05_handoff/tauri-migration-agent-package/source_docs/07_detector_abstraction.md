# 検出バックエンド抽象化 — 実装指示プロンプト

## 目的

検出バックエンドを切り替え可能にし、NudeNet と EraX-Anti-NSFW-V1.1 を比較検証できる基盤を作る。
「EraX の方が上」とは決め打ちせず、まず比較可能な構造を作ることを優先する。

---

## 前提条件

公開情報から以下は確認済みである。

- NudeNet は 320n がデフォルトであり、pip パッケージに同梱される ONNX モデルは `320n.onnx` のみ
- NudeNet 640m モデルは公式 GitHub releases に存在するが、別途ダウンロードが必要な場合がある
- NudeNet には 18 クラスの公開ラベルがある
- EraX-Anti-NSFW-V1.1 は実在し、YOLO11 系、5 クラス構成、640x640 入力の公開モデルである
- ただし、EraX が NudeNet より高精度・高速であることは現時点では未確定であり、実データで比較検証が必要

したがって、今回の実装は「NudeNet 改善」および「EraX 比較導入」を可能にするための基盤整備を主目的とする。

---

## 既存アーキテクチャ（必ず把握してから実装すること）

以下は既に実装済みである。実装前に必ず該当ファイルを読むこと。

| コンポーネント | ファイル | 役割 |
|---|---|---|
| `ModelRunner` (ABC) | `app/infra/ai/model_runner.py` | 検出器の抽象基底クラス。`load()`, `detect()`, `detect_batch()`, `is_available()` を定義 |
| `NudeNetAdapter` | `app/infra/ai/nudenet_adapter.py` | `ModelRunner` 実装。ONNX Runtime ベース、GPU/CPU フォールバック付き |
| `DetectionService` | `app/domain/services/detection_service.py` | `runner: ModelRunner` を DI で受け取り、フレーム読込→リサイズ→推論→正規化を実行 |
| `label_mapper` | `app/infra/ai/label_mapper.py` | `LABEL_MAP`, `LABEL_GROUPS`, `LABEL_CATEGORIES`, `normalize_label()` によるラベル正規化 |
| `GpuConfig` | `app/gpu_config.py` | 推論パラメータの永続化 (`gpu_config.json`)。`sample_every`, `inference_resolution`, `confidence_threshold` 等 |
| `DeviceManager` | `app/infra/device/device_manager.py` | GPU/CPU 検出・選択。`get_onnx_providers()` で ONNX プロバイダ一覧を返す |
| `DetectionWorker` | `app/ui/detection_worker.py` | QThread。`DetectionService` → `TrackingService` を非同期で順次実行 |
| `Detection` | `app/domain/models/detection.py` | `frame_index, label, score, bbox` の dataclass |

### 設計上の重要な制約

- **`DetectionService` は既に DI 対応**: コンストラクタで `runner: ModelRunner` を受け取る。検出器切替は `ModelRunner` の実装を差し替えるだけで実現可能。
- **新たな抽象クラスを作らないこと**: `BaseNSFWDetector` 等の追加は不要。既存の `ModelRunner` ABC を使用する。
- **`DetectionService` 自体の変更は最小限にすること**: 推論パイプライン（リサイズ、バッチ、prefetch）は検出器非依存で動作する。

---

## 実装方針

**別モードとして先に UI 分離するのではなく、内部の検出バックエンドを差し替え可能にする設計を優先すること。**

理由:
- 同一 UI・同一後段処理のまま検出器だけ比較できる
- 将来的に他モデル追加が容易
- 早期に UX を複雑化しない
- 実測前に「高精度モード」などを固定しないため安全

---

## 実装要件

### 1. NudeNet のモデル切替対応

`NudeNetAdapter` を拡張し、320n / 640m の切替を可能にする。

- `NudeNetAdapter.__init__()` に `model_variant: str = "320n"` パラメータを追加
- `DEFAULT_MODEL_NAME` を動的に解決 (`"320n.onnx"` or `"640m.onnx"`)
- 640m モデルファイルが存在しない場合は 320n にフォールバックし、ログで警告
- `inference_resolution` / `confidence_threshold` は既に `GpuConfig` → `DetectionService` 経由で設定可能なため、追加実装は不要
- 必要であればクラス別 threshold の適用を将来拡張として検討してよいが、初回は不要

---

### 2. EraXAdapter の追加

`app/infra/ai/erax_adapter.py` に `EraXAdapter(ModelRunner)` を新規作成する。

#### 依存戦略

- **推奨**: ONNX 形式 (`.onnx`) を `onnxruntime` で直接読む。現行アーキテクチャと一致し、追加依存が不要
- **代替**: ultralytics 経由の `.pt` 読み込み。ただし PyTorch (~2GB) が依存に加わるため、ONNX で動作確認できない場合のみ採用
- プロジェクト依存を軽量に保つことを優先する

#### 実装要件

- `ModelRunner` の `load()`, `detect()`, `detect_batch()`, `is_available()` を実装
- `load()` でモデルファイルの存在確認。なければ `is_available()` は `False` を返す
- `detect()` の出力を `{"label": str, "score": float, "bbox": [x, y, w, h]}` に正規化すること（`NudeNetAdapter._normalize_results()` と同じ形式）
- GPU/CPU フォールバックは `NudeNetAdapter` のパターン（`_resolve_providers()` → `_retry_on_cpu()`）を踏襲
- モデル配置先: `data/models/erax_v1_1.onnx`（既存の `data/models/` ディレクトリを使用）
- モデルロード失敗時の例外処理を実装し、`_load_error` に記録

---

### 3. EraX ラベルマッピング

`app/infra/ai/label_mapper.py` の既存テーブルに EraX ラベルを追加統合する。**新ファイルは作らないこと。**

- `LABEL_MAP` に EraX の 5 クラス → 内部ラベルのマッピングを追加
- EraX のラベル名はモデルのメタデータ (`session.get_modelmeta()` の custom_metadata_map 等) から取得して確認
- `LABEL_GROUPS` / `LABEL_CATEGORIES` は必要に応じて更新
- `normalize_label()` は既存ロジック（大文字化→MAP 検索→小文字化）で対応できるはず。対応できない場合のみロジックを拡張

注意:
- NudeNet の 18 クラス体系と EraX の 5 クラス体系は異なるため、マッピング先は既存の内部ラベル（`penis`, `vulva`, `breast` 等）に合わせること
- 後段処理（TrackingService 等）が検出器の違いを意識しないことを確認

---

### 4. DetectorFactory の実装

`app/infra/ai/detector_factory.py` を新規作成する。

```python
class DetectorFactory:
    @staticmethod
    def create(
        backend: str,  # "nudenet_320n", "nudenet_640m", "erax_v1_1"
        model_dir: Path,
        device_manager: DeviceManager | None = None,
    ) -> ModelRunner:
        ...
```

- 返り値は `ModelRunner`。呼び出し元は具体クラスを知らなくてよい
- 不明な backend 名は `ValueError` を送出
- 指定バックエンドが `is_available() == False` の場合、ログ警告して NudeNet 320n にフォールバック
- UI 側に `if detector == ...` の分岐が散らばらないよう、このファクトリで一元管理すること

---

### 5. GpuConfig への設定追加

`app/gpu_config.py` の `GpuConfig` に以下のフィールドを追加する。

```python
detector_backend: str = "nudenet_320n"  # "nudenet_320n" | "nudenet_640m" | "erax_v1_1"
```

- `gpu_config.json` に永続化される
- 既存フィールドとの互換性を維持（フィールド追加のみ、既存フィールドの変更なし）
- 古い設定ファイル（`detector_backend` キーなし）読み込み時はデフォルト値が使われるため後方互換

---

### 6. MainWindow での配線変更

`app/ui/main_window.py` で現在 `NudeNetAdapter` を直接生成している箇所を `DetectorFactory.create()` に置換する。

- `GpuConfig.detector_backend` の値を `DetectorFactory` に渡す
- `DetectionService(runner=factory_created_runner, ...)` で注入
- GPU 設定ダイアログにバックエンド選択のドロップダウンを追加
- バックエンド変更時は次回検出実行時に反映（即時リロード不要）

---

### 7. 比較ベンチマークモード（開発用）

`scripts/benchmark_detectors.py` としてスタンドアロンスクリプトを作成する。**UI には組み込まない。**

#### 機能

- 指定動画に対して複数の検出器を順次実行できる
- フレームごとの検出結果を JSON に保存する

#### 出力形式 (`benchmark_results.json`)

```json
[
  {
    "detector": "nudenet_320n",
    "frame_index": 0,
    "class_name": "penis",
    "score": 0.87,
    "bbox": [100, 200, 50, 80],
    "inference_ms": 12.3
  }
]
```

#### Phase 1 で収集する指標

- 平均推論時間（検出器別）
- フレームごとの検出数
- クラス別検出数
- 連続フレーム間の検出安定性（同一クラスの bbox IoU）

#### Phase 2 で追加検討する指標（今回は実装しない）

- 検出揺れ（フレーム間の bbox 変動量）
- 位置ジャンプ
- 一時消失パターン
- 小対象の検出率
- 誤検出が多い場面の分類

---

### 8. 後段処理との分離

以下を遵守していることを確認する。

**禁止事項:**
- `TrackingService`, `ContourService`, `RenderService` に `if detector == ...` の分岐を入れること
- クラス名差異を後段で直接吸収すること

**推奨:**
- 検出器の違いは `label_mapper.py` の `normalize_label()` で吸収する
- `Detection` dataclass に `detector_name` フィールドは追加しない（本番パスに影響させない）
- 検出直後の正規化レイヤー（`_detect_frame_impl` 内の `normalize_label()` 呼び出し）が全検出器で共通に動作することを確認

---

## 実装前に必ず調べること

以下は実装着手前に必ず調査し、結果をコメントまたはログに記録すること。

1. **NudeNet 640m**: 公式 GitHub releases からダウンロード可能か、ファイル名は `640m.onnx` で正しいか
2. **EraX ONNX 形式**: HuggingFace 等で `.onnx` が配布されているか確認。なければ ultralytics で `.pt` → `.onnx` エクスポートが必要
3. **EraX ラベル名**: モデルメタデータから 5 クラスの具体名を取得し、`LABEL_MAP` のマッピングを確定
4. **EraX ライセンス**: 商用利用・再配布条件を確認
5. **依存衝突**: ultralytics を入れる場合、既存の onnxruntime / numpy / opencv との互換性を確認
6. **モデル初回ダウンロード時の UX**: 手動配置で十分か、ダウンローダーが必要か判断

---

## 実装順序

1. `DetectorFactory` + `GpuConfig` 拡張（切替の骨格）
2. `NudeNetAdapter` のモデル切替対応（320n / 640m）
3. `label_mapper.py` に EraX ラベル追加
4. `EraXAdapter` 実装
5. `MainWindow` 配線変更 + GPU 設定ダイアログ更新
6. ベンチマークスクリプト作成
7. 既存テスト (115 件) の通過確認 + 新規テスト追加

---

## 設計判断

### 今は「完全な別 UI モード」にしない

現時点では以下のようなユーザー向けモード分離は保留とする。

- 標準モード
- 高精度モード
- 高速モード

理由:
- 実測比較がまだ済んでいないため
- モード名と実性能が一致しないリスクがあるため
- まずは内部切替で妥当性確認を行う方が安全なため

---

## 将来拡張

評価結果に応じて、将来的には以下を検討してよい。

- ユーザー向けのプリセット化（標準 / 高精度 / 高速）
- 動画内容に応じた自動切替
- クラスごとの検出器併用
- YOLO + 後段分類器の複合構成
- モデルの自動ダウンロード機構

ただし、これらは比較評価完了後に判断すること。

---

## やらないこと（スコープ外を明示）

- ユーザー向けモード分離（標準 / 高精度 / 高速）
- デフォルト検出器の EraX への切替
- `Detection` dataclass への `detector_name` フィールド追加
- 高度な評価分析ツール（Phase 2）
- モデルの自動ダウンロード機構（Phase 2）
- 新たな抽象基底クラス（`BaseNSFWDetector` 等）の作成

---

## 期待する成果物

1. `NudeNetAdapter` の 320n / 640m 切替対応
2. `EraXAdapter(ModelRunner)` の実装
3. `label_mapper.py` への EraX ラベル統合
4. `DetectorFactory` の実装
5. `GpuConfig` への `detector_backend` 追加
6. `MainWindow` の配線変更 + GPU 設定ダイアログ更新
7. `scripts/benchmark_detectors.py` ベンチマークスクリプト
8. 既存テスト通過確認 + 新規テスト
9. 現時点の所感（どの検出器が有望か、どの課題が残るか、次に何を検証すべきか）

---

## 重要な注意

- 「EraX の方が上」と決め打ちしないこと
- 公開情報と実測結果を分けて記述すること
- 推測でデフォルト切替しないこと
- まず比較可能な構造を作ることを優先すること
- 既存の `ModelRunner` / `DetectionService` / `label_mapper` を最大限再利用すること
