# コードベース全体診断レポート

**日付**: 2026-04-13  
**目的**: AIエージェント主導で構築したコードベースの構造的負債・不要ファイル・設計逸脱を洗い出す  

---

## 1. 総評

プロジェクト構造は**想定より良好**。AIエージェント構築にもかかわらず、レイヤ分離（domain / infra / ui / utils）は概ね維持されており、孤立ファイルや重複モジュールは検出されなかった。

ただし以下の構造的課題が存在する：

| 重要度 | 問題 |
|--------|------|
| **Critical** | `main_window.py` が 2965行・約100メソッドに肥大化 |
| **High** | `tracking_service.py` が 1388行・47メソッドに肥大化 |
| **Medium** | `utils/image_ops.py` が domain 層（Keyframe）に依存 |
| **Low** | 不要ファイル・一時ディレクトリがルート直下に残存 |

---

## 2. ファイル構成

### 2.1 全体規模

| 領域 | ファイル数 | 備考 |
|------|-----------|------|
| `app/` | 87 .py | 本体コード |
| `tests/` | 71 .py | ユニット62 + E2E 5 + conftest等 |
| `docs/` | 43 .md | 要件・設計・レビュー・アーカイブ |
| `scripts/` | 7 .py | ベンチマーク・診断ツール |

### 2.2 ディレクトリ構成

```
app/
├── main.py, bootstrap.py, cli.py, config.py, gpu_config.py
├── logging_config.py, startup_checks.py, dep_checker.py
├── application/
│   └── runtime_services.py          # DI コンテナ
├── domain/
│   ├── label_schema.py, engine_registry.py
│   ├── models/   (6ファイル)        # データクラス
│   └── services/ (11ファイル)       # ビジネスロジック
├── infra/
│   ├── ai/      (8ファイル)         # ML推論アダプタ
│   ├── device/  (3ファイル)         # GPU/CPU管理
│   ├── storage/ (4ファイル)         # JSON永続化
│   └── video/   (4ファイル)         # OpenCV/FFmpeg
├── ui/          (22ファイル)        # PySide6 コンポーネント
├── utils/       (4ファイル)         # 補間・幾何・画像処理
└── runtime/                         # 環境・パス・ONNX
```

### 2.3 不要ファイル・一時ディレクトリ

| パス | 状態 | 対応 |
|------|------|------|
| `Pyside6docs.zip` (85KB) | 未追跡・不要 | 削除推奨 |
| `tmpf2f4o0bo/` | 一時ディレクトリ残留 | 削除推奨 |
| `.pytest_cache/`, `.pytest-tmp/`, `pytest_tmp_run/` | テスト副産物 | .gitignore で対応 |
| `.codex-test-dir/`, `codex_tmp/` | Claude Code 副産物 | .gitignore で対応 |

### 2.4 孤立ファイル

**検出なし。** 全87ファイルが相互参照されており、未使用モジュールは存在しない。

### 2.5 `__init__.py`

全15個がドキュメント文字列のみ（または空）。再エクスポートなし。名前空間パッケージとして正常。

---

## 3. Domain 層（models + services）

### 3.1 Models

| ファイル | 行数 | 主要クラス |
|---------|------|-----------|
| detection.py | 15 | `Detection` |
| export_job.py | 132 | `ExportJob`, `ExportJobStatus` |
| keyframe.py | 69 | `Keyframe` |
| mask_track.py | 141 | `MaskTrack`, `MaskStyle` |
| project.py | 201 | `Project`, `ExportPreset` |
| video_meta.py | 26 | `VideoMeta` |

**評価**: 全て軽量なデータクラス。責務明確。問題なし。

### 3.2 Services

| ファイル | 行数 | メソッド数 | 主要責務 |
|---------|------|-----------|---------|
| tracking_service.py | **1388** | **47** | トラッキングパイプライン全体 |
| contour_service.py | 743 | 27 | 輪郭抽出（GrabCut/SAM2） |
| mask_edit_service.py | 601 | 31 | キーフレーム編集・補間 |
| detection_service.py | 442 | 10 | 物体検出パイプライン |
| export_service.py | 408 | 13 | 動画エクスポート |
| continuity_service.py | 306 | 7 | キーフレーム連続性検証 |
| project_edit_service.py | 165 | 7 | プロジェクトトラック管理 |
| danger_detector.py | 143 | 4 | 危険フレーム検出 |
| render_service.py | 121 | 5 | フレーム描画 |
| history_service.py | 84 | 14 | Undo/Redo管理 |
| export_size_calculator.py | 60 | 2 | ファイルサイズ計算 |

### 3.3 サービス間依存

```
export_service → render_service → mask_edit_service
tracking_service → contour_service
```

**単方向・循環なし。** 健全。

### 3.4 Qt 依存

**なし。** domain 層は PySide6 に一切依存していない。設計方針通り。

### 3.5 問題点

#### **[High] tracking_service.py の肥大化**
- 1388行・47メソッドは突出して大きい
- トラッキング、マッチング、キーフレーム構築、光フロー計算、輪郭再利用判定が混在
- **根本原因**: トラッキングパイプラインの各フェーズが分離されていない
- **対応案**: マッチング / フロー計算 / キーフレーム構築 を独立サービスに分割

#### **[Medium] contour_service.py の複雑性**
- 743行・27メソッドは合理的範囲だが、設定値が多く複数パスモード（HSV/SAM/GrabCut/balanced）管理が複雑
- 現時点では分割不要だが、モード追加時に注意

---

## 4. UI 層

### 4.1 ファイル一覧

| ファイル | 行数 | 分類 |
|---------|------|------|
| **main_window.py** | **2965** | **Critical: 肥大** |
| timeline_widget.py | 1249 | 大規模 |
| preview_canvas.py | 957 | 大規模 |
| export_settings_dialog.py | 925 | 大規模 |
| export_queue_dialog.py | 829 | 大規模 |
| track_list_panel.py | 636 | 中〜大 |
| display_state.py | 371 | 中規模 |
| property_panel.py | 370 | 中規模 |
| theme.py | 355 | 中規模 |
| i18n.py | 336 | 中規模 |
| danger_warnings_section.py | 276 | 中規模 |
| gpu_settings_dialog.py | 257 | 中規模 |
| shortcut_help_dialog.py | 227 | 小〜中 |
| dep_install_dialog.py | 210 | 小〜中 |
| detection_worker.py | 203 | 小〜中 |
| recovery_dialog.py | 180 | 小規模 |
| progress_dialog.py | 161 | 小規模 |
| dangerous_frames_dialog.py | 131 | 小規模 |
| shortcuts.py | 97 | 小規模 |
| collapsible_section.py | 63 | 小規模 |
| edit_command_guide.py | 52 | 小規模 |
| export_worker.py | 45 | 小規模 |

### 4.2 ロジック混入

**UI → domain service 依存は一方向で循環なし。** ロジック混入は検出されなかった。

- 幾何計算（線分距離、座標変換）は UI 描画に必要な最小限
- ビットレート計算は `ExportSizeCalculator` サービスに委譲済み

### 4.3 問題点

#### **[Critical] main_window.py の肥大化（2965行）**
- プロジェクト管理、検出フロー、レンダリング、履歴、リカバリー、書き出しが全て混在
- 約100メソッド、30以上のサービス/マネージャーを直接保有
- **根本原因**: MainWindow が「コーディネータ」の域を超えて「全機能の窓口」になっている
- **放置コスト**: 機能追加のたびに肥大化が加速。修正時の影響範囲特定が困難に
- **対応案**:
  - 検出フロー → `DetectionController` に抽出
  - エクスポートフロー → `ExportController` に抽出
  - プロジェクト管理 → `ProjectController` に抽出
  - MainWindow は子コントローラを保持してイベント中継するだけにする

#### **[Medium] timeline_widget.py（1249行）**
- 描画コード密度が高い（~600行が QPainter 描画）
- 描画ヘルパーの分離余地あり

#### **[Medium] export 関連ダイアログ（settings: 925行 + queue: 829行）**
- 単体では機能として妥当だが、2ファイル合計 1754行は重い
- プリセット管理ロジックの domain 層への移動を検討

---

## 5. Infra 層

### 5.1 構成（23ファイル、2,443行）

| サブディレクトリ | ファイル数 | 評価 |
|----------------|-----------|------|
| ai/ | 8 | 良好。ML推論アダプタ、ファクトリで抽象化 |
| device/ | 3 | 優秀。層間依存なし |
| storage/ | 4 | 良好。domain モデルの永続化専用 |
| video/ | 4 | 良好。ffmpeg/cv2 ラッパー |

### 5.2 依存方向

- Storage → domain models: **正当**（永続化レイヤの責務）
- Video → VideoMeta: **正当**（メタデータ抽象化）
- AI → domain.label_schema: **正当**（re-export のみ）

**問題なし。** infra 層は境界を守っている。

---

## 6. Utils 層

### 6.1 構成（4ファイル、474行）

| ファイル | 行数 | 主要関数 |
|---------|------|---------|
| interpolation.py | 225 | イージング、bbox/ポイント/スカラー補間 |
| image_ops.py | 170 | モザイク適用、ポリゴン展開・回転 |
| geometry.py | 81 | bbox 幾何演算、ポリゴン生成 |

### 6.2 問題点

#### **[Medium] image_ops.py の Keyframe 依存**
- `apply_mosaic_to_keyframe()` が `domain.models.Keyframe` を引数に取る
- utils は汎用ツール層であるべきで、domain 型への依存は設計違反
- **対応案**: プリミティブ引数 (bbox, points, shape_type 等) に変更するか、当該関数を `render_service` に移動

---

## 7. テスト

### 7.1 規模

| 区分 | ファイル数 | 行数 |
|------|-----------|------|
| ユニットテスト | 62 | ~11,100 |
| E2E テスト | 5 | ~1,500 |
| 合計 | 67 | ~12,600 |

### 7.2 カバレッジ

| 領域 | カバー率 | 備考 |
|------|---------|------|
| domain/services | 10/11 (91%) | render_service のみ欠落 |
| storage | 4/4 (100%) | |
| utils | 3/3 (100%) | |
| domain/models | 0/6 (0%) | フィクスチャ経由で間接カバー |
| infra/ai | 3/8 (37%) | 外部依存のためモック前提 |
| infra/video | 2/4 (50%) | writer/exporter 欠落 |

### 7.3 テスト未対応モジュール

- `app/domain/services/render_service.py`
- `app/domain/models/*`（全6モデル、間接テストのみ）
- `app/infra/ai/mobile_sam_adapter.py`, `onnxruntime_utils.py`
- `app/infra/video/cv_video_writer.py`, `ffmpeg_exporter.py`

---

## 8. 問題一覧（優先度順）

| # | 重要度 | 区分 | 問題 | 根本原因 | 対応方針 |
|---|--------|------|------|---------|---------|
| 1 | **Critical** | Must fix | `main_window.py` 2965行 | 全機能のコーディネーションが集中 | Controller 抽出で分割 |
| 2 | **High** | Should fix | `tracking_service.py` 1388行 | パイプラインフェーズ未分離 | マッチング/フロー/KF構築を独立化 |
| 3 | **Medium** | Should fix | `utils/image_ops.py` の Keyframe 依存 | utils が domain 型を知っている | 引数のプリミティブ化 or 関数移動 |
| 4 | **Medium** | Nice to have | `timeline_widget.py` 1249行 | 描画コードの密度 | 描画ヘルパー分離 |
| 5 | **Medium** | Nice to have | export ダイアログ 2ファイル計1754行 | プリセット管理が UI に同居 | プリセットロジックの domain 移動 |
| 6 | **Low** | Nice to have | 不要ファイル残存 | 一時ファイル未清掃 | 削除 + .gitignore |
| 7 | **Low** | Nice to have | render_service テスト欠落 | 書き漏れ | テスト追加 |

---

## 9. 良好な点

問題だけでなく、設計として正しく機能している点も記録する：

- **レイヤ分離は維持されている**: domain → infra → ui の依存方向が守られ、循環なし
- **domain/services に Qt 依存なし**: 設計方針通り
- **サービス間依存が単方向**: export → render → mask_edit、tracking → contour
- **孤立ファイルなし**: 87ファイル全てが使用されている
- **テスト充実**: 67ファイル・12,600行。domain services 91% カバー
- **Models が軽量**: 全てデータクラスで責務明確
- **Infra 層の境界が健全**: アダプタパターンが正しく適用されている

---

## 10. 推奨アクション

### 今すぐ着手すべき（Critical / High）

1. **`main_window.py` の分割**
   - 検出・エクスポート・プロジェクト管理を Controller クラスに抽出
   - MainWindow はイベント中継 + レイアウト管理のみに縮小
   - 目標: 1000行以下

2. **`tracking_service.py` の分割**
   - マッチングロジック → `TrackMatchingService`
   - 光フロー計算 → `FlowEstimationService`（または utils）
   - キーフレーム構築 → 既存 `MaskEditService` と統合検討
   - 目標: 各ファイル 400行以下

### 次に対応（Medium）

3. `image_ops.py` の Keyframe 依存解消
4. `timeline_widget.py` の描画ヘルパー分離
5. `render_service.py` テスト追加

### 余裕があれば（Low）

6. 不要ファイル削除 + .gitignore 整備
7. infra/ai, infra/video のテスト補強

---

## 11. 辛口総括

AIエージェント構築の割に構造は崩壊していない。レイヤ分離、依存方向、テスト量はいずれも合格水準。「AIが書いたから全部やり直し」という状況ではない。

しかし **`main_window.py` の 2965行は明確な構造負債**。現時点で「動いている」が、機能追加のたびにこのファイルが膨らみ続ける構造になっている。これは AI エージェントの典型的な癖で、「既存ファイルに追記する」ことを繰り返した結果。

`tracking_service.py` も同様の傾向で、パイプラインの全フェーズを1ファイルに押し込んでいる。

**今の段階で分割しておけば、コストは低い。** これ以上機能を追加してからでは、分割の難度が跳ね上がる。
