# レビュー前最終実装 完了報告

作成日: 2026-04-14  
依頼元: `docs/03_planning/14_claude-final-pre-review-implementation-prompt.md`  
参照: `docs/03_planning/13_claude-erax-pt-conversion-prompt.md`  
ステータス: 実装・テスト完了

---

## 1. 変更ファイル一覧

### 実装（新規）

| ファイル | 内容 |
|---------|------|
| `app/infra/ai/erax_export.py` | EraX 専用 `.pt → .onnx` 変換サービス。`is_ultralytics_available()` と `export_erax_pt_to_onnx()` の2関数、`EraxExportError` 例外 |
| `tests/test_erax_export.py` | 変換サービスの単体テスト（mock ベース、5件） |

### 実装（更新）

| ファイル | 内容 |
|---------|------|
| `app/ui/model_management_dialog.py` | 3状態（available/needs_conversion/missing）に拡張。EraX 専用の「ONNX に変換」ボタンを追加。`resolve_engine_file_status()` ヘルパを追加 |
| `app/ui/i18n.py` | `model_mgmt.status.needs_conversion`、`model_mgmt.convert`、`model_mgmt.ultralytics_missing` 等のキーを追加 |
| `scripts/install_deps.py` | `_export_erax_to_onnx()` を `app/infra/ai/erax_export.py` に委譲。誤誘導の `.pt fallback` 記述を訂正 |
| `tests/test_model_management_dialog.py` | 3状態・変換ボタンの可視性/活性/成功/失敗のテストを10件追加（計21件） |

### ドキュメント更新

| ファイル | 内容 |
|---------|------|
| `docs/03_planning/06_model-distribution-policy.md` | 「`.pt` のまま runtime で使える」記述を訂正。変換導線が UI から到達可能になった旨を反映 |
| `docs/04_review/01_review-guide.md` | 3状態と EraX `.pt → .onnx` 変換ボタンを追記。「任意 `.pt` 汎用変換は未実装」を明記 |
| `docs/04_review/02_model-setup-guide.md` | EraX の `.pt → .onnx` 変換セクションを新設。3状態の意味を記載 |
| `docs/04_review/04_known-limitations.md` | 「EraX 専用のみ実装、任意 `.pt` 汎用変換は非対応」を明記 |
| `docs/04_review/05_full-manual-test-procedure.md` | 10-H 節（EraX 変換の手動テスト）を新設 |

### 計画資料（新規）

| ファイル | 内容 |
|---------|------|
| `docs/03_planning/15_final-pre-review-completion-report.md` | 本ファイル |

---

## 2. EraX `.pt → .onnx` 変換導線の仕様

### 配置

- ロジック: `app/infra/ai/erax_export.py`
- 公開 API:
  - `is_ultralytics_available() -> bool`
  - `export_erax_pt_to_onnx(pt_path: Path, onnx_path: Path, *, imgsz: int = 640, opset: int = 12) -> Path`
  - `EraxExportError`（失敗時に送出）
- 呼び出し元:
  - `scripts/install_deps.py`（setup.bat 時）
  - `app/ui/model_management_dialog.py`（管理ダイアログ）
- 変換設定: `ultralytics.YOLO(pt).export(format="onnx", imgsz=640, opset=12, dynamic=False)`

### EraX 専用である理由

- `EraXAdapter` は `.onnx` のみを読む実装
- 配布元が `.pt` だけを提供している
- 他のエンジン（NudeNet 等）は `.onnx` が配布されているため変換は不要
- **任意の `.pt` を一般変換する導線は実装しない**（方針）

---

## 3. `ultralytics` あり / なしの場合の挙動

| 状態 | `setup.bat` 実行時 | 管理ダイアログでの挙動 |
|------|-------------------|------------------------|
| `ultralytics` あり | `.onnx` を自動生成 | `.pt` のみの状態では「変換が必要」が表示され、「ONNX に変換」ボタンが**有効** |
| `ultralytics` なし | `.pt` のみダウンロードされ `.onnx` は生成されない。警告メッセージでユーザーに案内 | ボタンは**無効化**、ツールチップに「ultralytics が必要です」案内 |
| `.pt` がない | EraX 自体ダウンロード失敗の場合は手動配置案内 | 「モデルファイルなし」で変換ボタン非表示 |

---

## 4. `erax_v1_1.pt` のみ存在する場合の UI 表示

| 列 | 表示 |
|----|------|
| モデル名 | `EraX v1.1` |
| 利用可否 | **`変換が必要`** |
| モデルファイル | `models/erax_v1_1.onnx`（想定パス） |
| 対応対象カテゴリ | `男性器, 女性器, 胸部, 臀部, 性的シーン` |

ダイアログ下部:
- 「選択したモデルに切替」ボタン: 無効（`.onnx` が無いため切替不可）
- 「ONNX に変換」ボタン: EraX 行を選択すると表示。`ultralytics` の有無で有効/無効が決まる
- 注記: `.pt` からの変換は EraX v1.1 専用である旨を明示

---

## 5. 変換成功 / 失敗時の挙動

### 成功時
1. ユーザーが「ONNX に変換」ボタンを押す
2. ボタンが「変換中...」テキストで無効化（二重実行防止）
3. `export_erax_pt_to_onnx()` が `.onnx` を生成
4. 成功メッセージを `QMessageBox.information` で表示
5. テーブルが再計算され、EraX 行が「利用可能」に更新
6. 「選択したモデルに切替」ボタンが有効になる

### 失敗時
1. `EraxExportError`（または想定外の例外）が `QMessageBox.critical` で表示
2. `_converting` フラグが `False` に戻り、ダイアログは操作可能
3. アプリ本体は落ちない
4. 既存の `.pt` / `.onnx` 状態は維持

---

## 6. `.pt` fallback に関する文書修正内容

| ファイル | 変更前 | 変更後 |
|---------|--------|--------|
| `scripts/install_deps.py` (comment) | 「ultralytics 未インストール時は .pt のまま EraXAdapter fallback」 | 「`EraXAdapter` は `.onnx` のみ読む。`.pt` しか無い場合は変換が必要」に訂正 |
| `scripts/install_deps.py` (docstring) | 「ultralytics を使って runtime で .pt を読める」 | 「`.onnx` 未生成の場合 EraX 検出は利用不可、後で管理 UI から変換」に訂正 |
| `scripts/install_deps.py` (warn message) | 「EraXAdapter will use the .pt via ultralytics at runtime.」 | 「EraX detection requires erax_v1_1.onnx; retry later from the management dialog.」に訂正 |
| `docs/03_planning/06_model-distribution-policy.md` | 「EraXAdapter は .pt と .onnx の両方対応」「.pt で動作可能」 | 「`EraXAdapter` は `.onnx` のみ。`.pt` しかない場合は EraX 検出利用不可」に訂正 |
| `docs/04_review/02_model-setup-guide.md` | `.pt → .onnx` 変換への言及なし | EraX 専用変換の説明を新設 |
| `docs/04_review/04_known-limitations.md` | 変換導線の記述なし | EraX 専用のみ実装、任意 `.pt` 汎用変換は非対応であることを明記 |
| `docs/04_review/05_full-manual-test-procedure.md` | 10-H 不在 | 10-H 節（EraX 変換手動テスト）を新設 |

---

## 7. `.gitignore` / 未追跡生成物の確認結果

`.gitignore` の下記エントリが有効であることを `git check-ignore -v` で確認:

| パス | マッチしたルール |
|------|----------------|
| `data/config/gpu_config.json` | `.gitignore:58 /data/config/` |
| `data/export_queue.json` | `.gitignore:59 /data/export_queue.json` |
| `data/training/erax` | `.gitignore:66 /data/training/` |
| `Pyside6docs.zip` | `.gitignore:70 /Pyside6docs.zip` |

`git status --short` に上記4件は現れない。`git add -A` しても誤コミット対象にならない。

手動テスト 10-F Step 5 の `Ctrl+S` 誤誘導は前セッションで修正済み。確認のみ実施。

---

## 8. 実行したテストと結果

| コマンド | 結果 |
|---------|------|
| `pytest tests/test_erax_export.py -v` | **5 passed** |
| `pytest tests/test_model_management_dialog.py -v` | **21 passed** (11 既存 + 10 新規) |
| `pytest tests/test_category_menu_engine_sync.py -v` | **5 passed** |
| `pytest tests/test_real_model_smoke.py -v` | **2 passed, 2 skipped** |
| `pytest tests/test_gpu_config.py -v` | **34 passed** |
| `pytest tests/test_engine_registry.py -v` | **10 passed** |
| `pytest tests/test_gpu_settings_dialog.py -v` | **5 passed** |
| `pytest tests/ --ignore=tests/e2e -q` | **744 passed, 2 skipped** (13.9s) |
| `pytest tests/e2e -q` | **83 passed** (2.8s) |
| 合計 | **827 passed / 2 skipped / 0 failed** |

---

## 9. 実モデル smoke test の結果

| モデル | ファイル | 結果 |
|-------|---------|------|
| NudeNet 320n | `models/320n.onnx` 存在 | **PASS**（単色画像で検出が例外なく `list` を返す） |
| NudeNet 640m | `models/640m.onnx` 無し | SKIP（`Model file missing`） |
| EraX v1.1 | `models/erax_v1_1.onnx` 無し（`.pt` は存在） | SKIP（`Model file missing`） |
| missing model fallback | — | **PASS**（runner の `is_available() is False`） |

`erax_v1_1.onnx` が無いため smoke test は skip されるが、管理ダイアログでは「変換が必要」として表示され、`ultralytics` 導入後に変換できる。

---

## 10. 受け入れ基準との対応

| 受け入れ基準 | 充足 |
|-------------|------|
| `erax_v1_1.pt` だけある状態が `変換が必要` として表示される | ✅ `resolve_engine_file_status` が判定、UI が表示 |
| `ultralytics` がある場合に EraX 専用で `.pt → .onnx` 変換できる | ✅ ボタンが有効、`export_erax_pt_to_onnx()` が動作 |
| `ultralytics` がない場合に変換不可理由が分かる | ✅ ボタン無効、ツールチップに案内 |
| `erax_v1_1.onnx` が生成された後、管理 UI で EraX が `利用可能` になる | ✅ 成功時に `_refresh_rows()` を呼ぶ |
| 変換失敗時にアプリ全体が落ちない | ✅ `EraxExportError` を `QMessageBox.critical` で表示 |
| 任意 `.pt` 汎用変換を実装していない | ✅ EraX 以外に変換導線は出さない（テスト済） |
| `.pt` fallback に関する古い文書・コメントのズレが修正されている | ✅ `install_deps.py` / 06 / 02 / 04 / 05 更新 |
| 実行時生成物が誤コミット対象にならない | ✅ `.gitignore` 有効、`git check-ignore` で確認 |
| レビュー資料が現状と矛盾していない | ✅ 01/02/04/05 更新済 |
| unit / E2E / smoke test が pass または適切に skip される | ✅ 827 pass / 2 skip / 0 fail |
| 人間レビュー開始可否を判断できる | ✅ 本報告のセクション 11 参照 |

---

## 11. 人間レビュー開始可否

### 結論

**人間レビューを開始して問題ありません。**

### 実機で確認してほしい項目（自動テストでカバーできない）

1. ツールバーのエンジンコンボに3モデル名が並び、切替がスムーズなこと
2. ステータスバーが常に現在モデル名を表示していること
3. 「設定 > 検出モデル管理...」ダイアログが開き、3行が正しく表示されること
4. EraX の `.pt` しかない状態で「変換が必要」と表示され、`ultralytics` がある場合に変換が動作すること
5. 「詳細設定...」ダイアログのタイトルが「デバイス / 推論設定」になっていること
6. 動画を読み込んで検出実行→マスク編集→書き出しの golden path が通ること
7. ダークテーマが全てのダイアログに適用されていること（管理ダイアログ含む）

### レビュー前に残るリスク

| 重要度 | 項目 | 対応 |
|--------|------|------|
| 中 | EraX の `.pt` を実際に変換する smoke test は環境依存のため CI 未実施 | 開発機で一度手動で実行済みの場合は OK。未実行ならレビュー前に1回通しておくと安心 |
| 低 | 管理ダイアログは `exec()` によるモーダル。「開いたまま別作業」のユースケースは今回未対応 | プロンプト 14 のスコープ外として据え置き |
| 低 | ダークテーマと `QMessageBox`・`QTableWidget` の配色チェックは実機確認が必要 | 既存ダイアログと同じ QSS が効くため問題は低い |
| 低 | 変換時に UI スレッドがブロックされる | 変換は数十秒〜数分かかりうるが、本プロンプトの「小さな実装」制約から非同期化は未対応。UI 上は「変換中...」で明示される |

### 今後（レビュー後）の候補

- 非同期変換（QThread）
- モデル再スキャンのボタン化
- モデル管理ダイアログのモードレス化
- 公式配布ページへのリンク（ブラウザ起動のみ、アプリ内 DL は禁止）

これらは全てレビュー後のフィードバックを受けてから判断する。

---

## 12. コミット提案

前セッション踏襲で2分割:

### コミット 1: 実装 + テスト + 既存レビュー資料修正

- `app/infra/ai/erax_export.py`（新規）
- `app/ui/model_management_dialog.py`
- `app/ui/i18n.py`
- `scripts/install_deps.py`
- `tests/test_erax_export.py`（新規）
- `tests/test_model_management_dialog.py`
- `docs/03_planning/06_model-distribution-policy.md`
- `docs/04_review/01_review-guide.md`
- `docs/04_review/02_model-setup-guide.md`
- `docs/04_review/04_known-limitations.md`
- `docs/04_review/05_full-manual-test-procedure.md`

### コミット 2: 計画資料（依頼プロンプト 13/14 + 完了報告 15）

- `docs/03_planning/13_claude-erax-pt-conversion-prompt.md`
- `docs/03_planning/14_claude-final-pre-review-implementation-prompt.md`
- `docs/03_planning/15_final-pre-review-completion-report.md`

`docs/03_planning/11_claude-refactor-audit-prompt.md` は今回のスコープ外の既存依頼。コミットするかは PM 判断。

`README.md` / `docs/README.md` の変更も今回のスコープ外。
