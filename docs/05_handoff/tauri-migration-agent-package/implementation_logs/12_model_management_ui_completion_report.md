# 検出モデル管理 UI 最低限版 実装完了報告

作成日: 2026-04-14  
依頼元: `docs/03_planning/10_claude-model-management-ui-prompt.md`  
ステータス: 実装・テスト完了

---

## 1. 変更ファイル一覧

### 実装（コード）

| ファイル | 変更内容 |
|---------|---------|
| `app/domain/engine_registry.py` | `EngineInfo` に `model_filename` フィールドを追加（各エンジンに `.onnx` ファイル名を紐付け） |
| `app/ui/model_management_dialog.py` | **新規**: 検出モデル管理ダイアログ（最小版） |
| `app/ui/main_window.py` | メニュー「設定 > 検出モデル管理...」追加、カテゴリメニューを「対応のみ表示」へ、`_apply_engine_change()` を共通化 |
| `app/ui/i18n.py` | `model_mgmt.*` キー群を追加、`engine.unsupported_category_tip` を削除 |

### テスト（新規）

| ファイル | 追加テスト数 |
|---------|-------------|
| `tests/test_model_management_dialog.py` | 11件（管理ダイアログの表示・選択・シグナル・外部同期） |
| `tests/test_category_menu_engine_sync.py` | 5件（エンジン切替時のカテゴリ残留なし、古い設定での非表示） |
| `tests/test_real_model_smoke.py` | 4件（実モデル smoke、skip ガード付き） |

### レビュー資料（更新）

| ファイル | 変更内容 |
|---------|---------|
| `docs/04_review/01_review-guide.md` | 「検出モデル管理ダイアログ」節を追加、カテゴリメニュー挙動を「除外方式」に合わせて文言修正 |
| `docs/04_review/02_model-setup-guide.md` | 「手順 4: 導入状況の確認」を新設、管理ダイアログでの確認手順を記載 |
| `docs/04_review/04_known-limitations.md` | 「エンジン管理ダイアログ（完全版）」→「最低限版を実装」へ、未知ラベル対応/学習UIが未実装である旨を明記 |
| `docs/04_review/05_full-manual-test-procedure.md` | 10-F Step 3 にカテゴリ除外確認を追加、10-G（管理ダイアログ手動テスト）を新設 |

---

## 2. 検出モデル管理 UI の仕様

### 導線

メニュー「設定 > 検出モデル管理...」からダイアログを開く。ツールバーの「詳細設定...」（デバイス/推論設定）とは別導線。

### ダイアログ構成

`QTableWidget`（4列）で既知モデル 3 行を表示:

| 列 | 内容 |
|----|------|
| モデル名 | `NudeNet 320n` / `NudeNet 640m` / `EraX v1.1` |
| 利用可否 | `利用可能` または `モデルファイルなし` |
| モデルファイル | 想定パス（例: `H:/mosicprogect/mosic2/models/320n.onnx`） |
| 対応対象カテゴリ | 日本語カテゴリ名のカンマ区切り（例: `胸部, 女性器, 男性器, 腹部, 臀部, 顔`） |

下部:
- 「現在選択中: {モデル名}」ラベル
- 「SAM2 は輪郭エンジンのためこの一覧には表示されません。」注記
- 「選択したモデルに切替」ボタン（accent色）
  - 現在選択と同じ / 利用不可な行を選んだ場合は無効化
- 「閉じる」ボタン

### 信号

`engine_change_requested(str)` — 適用ボタン押下時に backend ID を発火。`MainWindow._apply_engine_change()` が受け取り、ツールバーコンボ・カテゴリメニュー・ステータスラベル・検出器を一括更新。

### 除外したもの（プロンプトの「今回入れない UI」準拠）

- App 内ダウンロード
- 公式配布ページ一覧
- モデル追加ウィザード
- 未知モデルのラベル対応編集
- 学習状態ランプ
- 教師データ保存 ON/OFF
- モデルのインポート/エクスポート
- PT → ONNX 変換

---

## 3. 対象カテゴリ同期の修正内容

### 方式の変更

| | 変更前 | 変更後 |
|-|--------|--------|
| 非対応カテゴリの扱い | `setEnabled(False)` でグレーアウト表示 | **メニュー項目から除外**（描画しない） |
| 根拠 | 旧 i18n `engine.unsupported_category_tip` | 補足条件 2「現在モデルのカテゴリだけ表示」 |

### 関連する整合

- `_populate_category_menu()` が `get_engine_categories(current_backend)` を主ソースとして使用
- `_trim_unsupported_categories()` は既存の `normalize_enabled_categories()` を呼び出すだけの薄いラッパーとして維持
- 古い `gpu_config.json` に非対応カテゴリが残っていた場合でも、`GpuConfig.load()` 時点で正規化されるため、UI には最初から出ない

### カテゴリが空になる場合のフォールバック

`normalize_enabled_categories()` のロジック（変更前から存在、今回は踏襲）:
1. 入力のうち現在エンジンの `supported_categories` に含まれるものだけを残す
2. 1 の結果が空なら、`DEFAULT_ENABLED_CATEGORIES ∩ supported_categories` にフォールバック
3. 未知エンジンは入力をそのまま返す（安全側）

### 共通化

`_on_engine_combo_changed()` と `_apply_engine_change()` を切り分け、管理ダイアログから呼ぶ場合にも同じ副作用（設定保存・検出器再構築・ツールバー同期・カテゴリメニュー更新・ステータス更新）が走るように統一。

---

## 4. 各モデルの利用可否・検出確認結果

本リポジトリの `models/` 配下の状況と、smoke test の実行結果:

| モデル | ファイル | 状態 | smoke test |
|-------|---------|------|-----------|
| NudeNet 320n | `models/320n.onnx` | 配置済 | **PASS**（単色画像で `detect()` が list を返し、例外なし） |
| NudeNet 640m | `models/640m.onnx` | 未配置 | SKIP（`Model file missing`） |
| EraX v1.1 | `models/erax_v1_1.onnx` | `.pt` のみ存在し `.onnx` 無し | SKIP（`Model file missing`） |

`.pt` を `.onnx` に変換する導線はこのセッションでは扱わない（プロンプトの「PT → ONNX 汎用変換」は除外項目）。

---

## 5. モデル未配置時の挙動

- 管理ダイアログで「モデルファイルなし」と表示される
- その行を選択しても「選択したモデルに切替」ボタンは無効のまま
- ツールバーのコンボで未配置モデルを選ぼうとした場合は、`DetectorFactory.create` 側のフォールバックで既存通り `NUDENET_BACKEND` に落ちる（本セッションでは変更なし）
- `test_missing_model_gracefully_reports_unavailable` で runner の `is_available() is False` をテスト化

---

## 6. 追加・更新したテスト

### 新規テストクラス

- `ModelManagementDialogTests`（11件）
  - 3モデルすべて列挙されること
  - `model_dir=None` 時に全て「モデルファイルなし」
  - ファイル存在時に「利用可能」
  - 初期選択が `current_backend`
  - 日本語カテゴリ名表示（内部 ID の非露出）
  - apply ボタンの有効/無効ロジック（現在モデル / 未配置モデル / 利用可能な別モデル）
  - apply でシグナル発火
  - 未配置モデルでは apply しても発火しない
  - `set_current_backend()` が既存シグナルを再発火させない

- `CategoryMenuEngineSyncTests`（5件）
  - NudeNet / EraX 選択時にメニューが現在モデルのカテゴリのみ
  - NudeNet → EraX 切替で `face` / `belly` がメニューと config から消える
  - EraX → NudeNet 切替で `sexual_context` がメニューと config から消える
  - 古い設定（EraX + face）で起動しても UI に `face` が出ない

- `test_real_model_smoke.py`（4件）
  - 3モデル × smoke（skip ガード付き）
  - 未配置モデルは `is_available() == False`

### 既存テストの実行

全て PASS。削除・緩和なし。

---

## 7. 実行したテストと結果

| コマンド | 結果 |
|---------|------|
| `pytest tests/test_model_management_dialog.py -v` | **11 passed** |
| `pytest tests/test_category_menu_engine_sync.py -v` | **5 passed** |
| `pytest tests/test_real_model_smoke.py -v` | **2 passed, 2 skipped** |
| `pytest tests/ --ignore=tests/e2e -q` | **729 passed, 2 skipped** (12.2s) |
| `pytest tests/e2e -q` | **83 passed** (2.6s) |
| 合計 | **812 passed / 2 skipped / 0 failed** |

---

## 8. レビュー前に残るリスク

### ブロッカー

なし。

### 非ブロッカー（提出後判断でよい範囲）

| # | 項目 | 現状 | 備考 |
|---|------|------|------|
| 1 | 640m.onnx / erax_v1_1.onnx の配布 | 未同梱（方針通り） | 手順書通りに手動配置する前提。レビューアには事前連絡を推奨 |
| 2 | EraX の `.pt` → `.onnx` 変換 | 手動 | `erax_v1_1.pt` は存在するが `.onnx` は未配置。PT → ONNX 変換はレビュー対象外 |
| 3 | モデル自動再スキャン | 未実装 | モデル追加後はアプリ再起動が必要（既知制限として 04 に記載） |
| 4 | モデル管理ダイアログのリサイズ挙動 | 最小幅 560px | 列幅は ResizeToContents / Stretch で自動。高 DPI での手動検証が望ましい |
| 5 | signal ループ | `blockSignals` 済 | `set_current_backend()` 時に選択行を更新するが、`itemSelectionChanged` が発火して `_update_apply_button_state` のみ走る（意図通り） |

### 設計上の判断点（確認推奨）

- 管理ダイアログは **モードレス表示** ではなく `exec()` のモーダル。ツールバーでの切替と同時に開いたままにするユースケースは想定していない。もし「開いたまま作業」が必要ならモードレスに変更可能（本セッションでは最小スコープを優先）。
- エンジン切替時に管理ダイアログ側の `set_current_backend()` を呼ぶ導線は今回入れていない（モーダルなので不要）。モードレス化する場合は MainWindow からダイアログへ backend 同期が必要。

---

## 9. 受け入れ基準との対応

| 受け入れ基準 | 充足 |
|-------------|------|
| 検出モデル管理 UI の最低限版が存在する | ✅ `设定 > 検出モデル管理...` |
| NudeNet 320n / 640m / EraX v1.1 の導入済み / 未導入状態が分かる | ✅ 利用可否列 |
| SAM2 が検出モデル一覧に出ていない | ✅ `list_registered_engines()` は検出エンジンのみ。ダイアログ下部に注記 |
| エンジン切替時に対象カテゴリフィルタが現在モデルのカテゴリへ更新される | ✅ `_sync_category_menu_to_engine()` → `_populate_category_menu()` |
| 旧モデルの対象カテゴリが次モデルに残留しない | ✅ メニュー除外 + `normalize_enabled_categories()` |
| 古い `gpu_config.json` でも UI・検出・保存が壊れない | ✅ load/save で正規化、テスト済 |
| モデルファイルが存在する既知モデルでは通常検出の smoke test が通る | ✅ 320n で PASS、他は未配置で SKIP |
| モデルファイルが存在しない環境では実モデル検出テストが skip される | ✅ `onnxruntime`/`nudenet`/ファイル存在の3段ガード |
| レビュー資料が実装状態と矛盾していない | ✅ 01/02/04/05 更新済 |
| App 内ダウンロード、公式配布ページ一覧、未知ラベル対応編集、学習 UI は実装していない | ✅ すべて未実装のまま（04_known-limitations に明記） |

---

## 10. コミット提案

前セッションと同じく 2 分割を推奨:

### コミット 1: 実装 + テスト + レビュー資料（中身の変更）

- `app/domain/engine_registry.py`
- `app/ui/model_management_dialog.py`（新規）
- `app/ui/main_window.py`
- `app/ui/i18n.py`
- `tests/test_model_management_dialog.py`（新規）
- `tests/test_category_menu_engine_sync.py`（新規）
- `tests/test_real_model_smoke.py`（新規）
- `docs/04_review/01_review-guide.md`
- `docs/04_review/02_model-setup-guide.md`
- `docs/04_review/04_known-limitations.md`
- `docs/04_review/05_full-manual-test-procedure.md`

### コミット 2: 計画資料（依頼プロンプト + 完了報告）

- `docs/03_planning/10_claude-model-management-ui-prompt.md`（PM プロンプト）
- `docs/03_planning/12_model-management-ui-completion-report.md`（本ファイル）
