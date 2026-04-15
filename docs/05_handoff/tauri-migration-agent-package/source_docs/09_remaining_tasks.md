# Auto Mosaic — PySide6 版 残タスク一覧

最終更新: 2026-04-13 (MR-01〜MR-06 完了)  
対象ブランチ: `main`

---

## 1. 文書の目的

本書は **現行 PySide6 本線（main ブランチ）** の残タスクを一元管理するためのものです。

2026-04-09 の実装監査（実コードベースで全サービス・UI・テストを精査）の結果を反映しています。  
旧来の `unimplemented-features.md`（現 `docs/99_archive/unimplemented-features-tauri.md`）は Tauri 版を想定した別系統の残件表であり、現行の残タスク管理には使用しません（詳細は文書末尾を参照）。

---

## 2. 現在の前提

- **本線は PySide6（Qt for Python）一本**。Tauri 実装はリポジトリに存在しない。
- 主要な編集機能・サービスはすでに実装済みである。本書は「ゼロから設計する指示書」ではなく「あと何が必要か」を示す残タスク表である。
- P0（最優先・ブロッカー級）のタスクは現時点で存在しない。旧一覧で P0 に挙げられていた「Persistent Mask Track・検出区間外編集・auto fallback・manual anchor 継承」はすべて実装済みであることを確認している。

---

## 3. 現在すでに成立していること

以下は実装済みであることを実コードで確認している。残タスク表に再記載しない。

| 機能領域 | 実装状態 |
|---------|---------|
| 動画オープン・VideoMeta 読み込み | ✅ FFprobe + OpenCV |
| project save / load（JSON） | ✅ ProjectStore |
| preview canvas（表示・ドラッグ・スケール・頂点編集） | ✅ PreviewCanvas |
| timeline（スクラブ・ズーム・スクロール・マーカー） | ✅ TimelineWidget、Ctrl+ホイール対応 |
| keyframe 管理（追加・削除・複製・移動・補間） | ✅ MaskEditService |
| track 管理（作成・削除・複製・分割・表示切替） | ✅ ProjectEditService |
| 自動検出（全フレーム・単フレーム） | ✅ DetectionService + DetectionWorker |
| 自動検出 Progress UI（進捗・ステップ・キャンセル） | ✅ ProgressDialog + DetectionWorker シグナル |
| AI 区間検出（In/Out マーカー・範囲限定検出・manual 保護） | ✅ TimelineWidget + MainWindow + DetectionService/Worker |
| Persistent Mask Track（active/lost/inactive 状態遷移） | ✅ TrackingService |
| 検出区間外での shape 保持・編集 | ✅ resolve_keyframe が interpolated で保持 |
| auto fallback / continuity 評価（3段） | ✅ ContinuityService |
| manual anchor 前方継承 | ✅ ContinuityService._remap_shape() |
| manual キーフレーム保護（protect_manual） | ✅ MaskEditService.upsert_keyframe() |
| GrabCut / SAM2 / HSV 輪郭抽出 | ✅ ContourService（3モード） |
| 動画書き出し（非同期・キャンセル・GPU フォールバック） | ✅ ExportService + ExportWorker |
| export queue 管理 UI | ✅ ExportQueueDialog |
| undo / redo（Ctrl+Z/Y） | ✅ HistoryService（最大100件） |
| keyframe source 視覚区別（6色マーカー） | ✅ TimelineWidget |
| GPU / デバイス設定ダイアログ | ✅ GpuSettingsDialog |
| 依存関係チェック・インストールダイアログ | ✅ DepChecker + DepInstallDialog |
| runtime / GPU 設定 browse 導線 | ✅ GpuSettingsDialog |
| 初回セットアップ導線（setup.bat → run_ui.bat） | ✅ setup.bat / bootstrap.py |
| タイムライン 縦スクロール（トラック数オーバーフロー対応） | ✅ _TimelineCanvas バーチャルスクロール + auto-scroll |
| トラック単位の書き出し対象制御（export_enabled） | ✅ MaskTrack.export_enabled + ExportService フィルタ + UI |
| 書き出し対象外トラックの視覚区別 | ✅ プレビュー・タイムライン両方で半透明+ドット線表示 |
| 660件のユニットテスト | ✅ tests/ ディレクトリ（一部はオプション AI 依存あり） |
| E2E テスト基盤（pytest-qt） | ✅ tests/conftest.py + tests/e2e/test_smoke.py（10 件）|

---

## 4. 完了済みタスク

### P1 — 全項目完了 ✅

| ID | タスク | 完了コミット | 内容 |
|----|--------|-------------|------|
| P1-1 | 書き出し設定 UI | `fb2d9f2f` | ExportSettingsDialog 新規作成。コーデック・解像度・音声モード・保存先を書き出し前に選択可能に。12テスト追加 |
| P1-2 | 楕円の軸別リサイズ | `8c78e5cf` | 辺中点ハンドル4点を追加し、横幅・縦幅を独立変更可能に。`scale_track_axis(factor_x, factor_y)` 新設。11テスト追加 |
| P1-3 | 共通 Progress UX 統一 | `b50662b4` | BusyWorker + BusyProgressScope を追加。単フレーム検出を非同期化しindeterminate ProgressDialogを表示。14テスト追加 |

### Phase B2 — AI 区間検出 ✅

| ID | タスク | 完了コミット | 内容 |
|----|--------|-------------|------|
| B2-1 | AI 区間検出 | `2dfe17a5` `93c3395e` | タイムライン In/Out マーカー UI（`[` `]` ボタン・I/O キー）、ツールバーを QToolButton+InstantPopup に変更し「全区間検出 / 選択区間のみ検出」プルダウン化、DetectionService/Worker に start_frame/end_frame 追加、既存マスク確認ダイアログ（manual 保護 / 全上書き / キャンセル） |
| B2-2 | 誤マージ回帰テスト | `18b284a7` | `apply_range_detection_results` のマージアルゴリズムを自動テストで検証。5ケース（近接・manual 保護・接近・交差・消失）＋エッジケース 計 28 テスト |

> **既知制限（マージアルゴリズム）**: greedy IoU 1パスのため、2対象が完全に位置を入れ替えた場合（交差後）に ID スワップが発生する。`[KNOWN_LIMIT]` テストで文書化済み。改善候補: Hungarian 法・トラジェクトリ重み付け・manual トラック優先マッチング。

### UI リデザイン — Phase 1 & 2 完了 ✅

| フェーズ | 完了コミット | 内容 |
|---------|-------------|------|
| Phase 1 | `02684462` | 全UI文言を日本語に統一（55翻訳キー追加）。パネルヘッダーにアクセント下線。Preview border除去。ツールバーグルーピング |
| Phase 2 | `f3bdb87e` | レイアウト配分見直し（Preview拡大、Timeline高さ増）。Inspector セクション再編（動画情報を最下部折りたたみへ）。ツールバー15→10ボタン。ステータスバーから冗長項目除去。TrackList密度改善 |

---

## 5. 残タスク一覧

### P0 — なし

---

### P2 — 中優先

#### ~~P2-1: 頂点追加・削除ホバー UI~~ ✅ 採用せず・正式導線確定

| 項目 | 内容 |
|------|------|
| **判断** | ホバー UI（辺ホバーで＋バッジ・頂点ホバーで×バッジ）を試験実装したが、再現性・安定性の問題（シーン再構築タイミングとの競合）により採用しなかった |
| **正式導線** | **辺をダブルクリック → 頂点追加**（`mouseDoubleClickEvent` + `_resolve_edge_target`）、**頂点を Alt＋右クリック → 頂点削除**（`mousePressEvent` + 右クリック Alt 判定）。右クリックコンテキストメニューからも追加・削除可能 |
| **コード状態** | `_VertexHoverState` dataclass・ホバー判定・バッジ描画・`consume_vertex_hover_delete` をすべて削除。ダブルクリック・右クリックの導線のみ残存 |

#### ~~P2-2: 書き出し前の危険フレーム確認ダイアログ~~ ✅ Phase 1 + 2 完了

| 項目 | 内容 |
|------|------|
| **完了コミット** | `b966a182` `eb400e6d` |
| **Phase 1: ドメインサービス + ダイアログ** | `DangerousFrameDetector`（3基準: 長い KF 間隔・面積急変・predicted KF）、`DangerousFramesDialog`（3択: 確認/無視/キャンセル）、`MainWindow._check_dangerous_frames_before_export()` 統合。31テスト追加 |
| **Phase 2: レビュー UI** | タイムラインルーラーに理由別カラーの ▲ マーカー表示（クリックでスナップシーク）、左パネルに `DangerWarningsSection` 統合（折りたたみ可能・ヘッダー常時表示）、「確認」トグルボタン（✓ 確認済み ↔ 確認、誤操作時に解除可能）、確認済みでも行クリックでフレーム移動可 |
| **残 Phase 3 候補** | confidence を補助指標として追加（単独警告にはしない、他条件との複合のみ） |

#### ~~P2-3: E2E テスト強化~~ ✅ 完了（83 件 E2E テスト）

| 項目 | 内容 |
|------|------|
| **概要** | 「動画読込→検出→キーフレーム編集→書き出し」のフル操作フローを自動テストとして整備する |
| **完了済み** | `tests/conftest.py`、`tests/e2e/test_smoke.py`（10件）、`tests/e2e/test_keyframe_flow.py`（10件）、`tests/e2e/test_danger_frame_flow.py`（22件）、`tests/e2e/test_range_detection_flow.py`（14件）、`tests/e2e/test_export_flow.py`（11件）、`tests/e2e/test_crash_recovery_flow.py`（17件: RecoveryStore CRUD・auto_save_tick・起動時検出・復元後 dirty・保存後 cleanup）。全 83 件 PASS、2.37 s |
| **pytest-qt deadlock 対策** | `qtbot.addWidget` を使わず `yield` + 明示 teardown（`current_project = None → close → deleteLater`）。詳細は memory `feedback_pytest_qt_addwidget.md` |

#### ~~P2-4: export queue 永続化~~ ✅ 完了（Phase A + B）

| 項目 | 内容 |
|------|------|
| **概要** | エクスポートキューをアプリ再起動後も復元できるよう永続化する |
| **Phase A 完了** | `ExportJob.to_dict()` / `from_dict()`（running→interrupted 変換含む）、`ExportQueueStore`（atomic write、completed フィルタ、corrupted file safe 読み込み）、`RuntimeServices.queue_store`、`ExportQueueDialog` への `queue_store` 統合（init 時 load、add/remove/status 変更で `_persist()`）、`_status_text` に `interrupted` 追加、`_start_all_jobs` で interrupted も再開対象化。`tests/test_export_queue_store.py` 26 件 |
| **Phase B 完了** | 起動時に queued/interrupted ジョブがあれば通知ダイアログ（`_check_queue_on_startup`、recovery チェックと正しくシーケンス）。ステータスセル色分け（interrupted=amber / error=red / running=blue）。メニュー「書き出し > 書き出しキューを表示」追加で恒常導線を確保 |

#### ~~P2-5: crash recovery~~ ✅ 完了

| 項目 | 内容 |
|------|------|
| **完了コミット** | `18b284a7`以降 |
| **実装内容** | `RecoveryStore`（atomic write）、`RecoveryDialog`、`_auto_save_tick`（60秒タイマー＋最初のdirty時即時書き込み）、closeEvent flush、startupチェック。27テスト追加 |

---

### P3 — 後優先

> **2026-04-11 人間レビュー結果により、P3-4 / P3-6 / P3-8 を再 open し、P3-9 を新規追加した。**
> 旧定義ではなく以下の再整理後タスクが正本。

#### ~~P3-5: Undo 件数・操作名表示~~ ✅ 完了

| 項目 | 内容 |
|------|------|
| **完了内容** | `HistoryService.push(state, label)` に操作名を追加。`undo_label()` / `redo_label()` / `undo_count()` / `redo_count()` 新設。ステータスバーに `_status_undo` ラベル（`↩ N  操作名` 形式）を永続表示。各 `_commit_history_state()` 呼び出しに日本語ラベル付与。7テスト追加。 |

#### ~~P3-7a: ショートカット整備~~ ✅ 完了

| 項目 | 内容 |
|------|------|
| **完了内容** | `app/ui/shortcuts.py` に単一の真実のソースとなるレジストリ作成（`ShortcutEntry`、9カテゴリ、26エントリ）。業務用動画編集ソフト（Premiere/Resolve/AE）の慣習に揃えて再設計。新規追加: `Home` / `End`、`↑` / `↓`、`Ctrl+Shift+Z`、`Ctrl+Shift+R`、`Ctrl+E`。`edit_command_guide.py` から未実装の `V` キー削除。CLAUDE.md のショートカット表をカテゴリ別に再構成。9テスト追加。 |

#### ~~P3-7b: F1 キーショートカット一覧ダイアログ~~ ✅ 完了

| 項目 | 内容 |
|------|------|
| **完了内容** | `app/ui/shortcut_help_dialog.py` 新規作成。`ShortcutHelpDialog` モーダル: 検索ボックス、カテゴリヘッダー、キーチップ表示、「該当なし」プレースホルダ、Esc / Enter で閉じる。`MainWindow._show_shortcut_help()` を `QMessageBox` 暫定実装から差し替え。テスト 10 件。F1 案内のステータスバー常時表示は P3-7a+ で実装済み。 |

#### ~~🔄 P3-6（改訂）: トラック順序 UX 修正 Phase A~~ ✅ 完了 (2026-04-12)

> **2026-04-11 人間レビューで差し替え。** 旧定義「右クリックメニュー拡張」は採用せず（要望が薄い）、代わりに「選択で順序が変わる挙動の修正」へ差し替え。既に実装された右クリックメニューは残したままでよい（害はない）が、今回のスコープ外。

| 項目 | 内容 |
|------|------|
| **完了内容** | `display_state.py:_timeline_sort_key()` から `is_selected` 優先を削除し、`(order_index, label, track_id)` のみで安定ソートに変更。キャンバス描画 z-order（`_canvas_sort_key()`）は描画順として選択を最前面に保つのが正しいためそのまま維持（リスト順序とは別関心事）。テスト 2 件追加: 選択状態を切り替えてもタイムライン順序が変わらないこと（3 トラック総当たり）、左パネルの groups 側も同様。既存の `test_timeline_order_is_stable_across_frame_changes` は維持。 |
| **Phase B（保留）** | ドラッグ&ドロップでの手動並べ替え。`MaskTrack.order_index: int` の正式フィールド化、永続化、TrackListPanel に DnD。規模大きいため別フェーズ。 |

#### 🔄 P3-4（再評価中）: 差分オーバーレイの位置づけ見直し

> **2026-04-12 人間レビューで「主機能から格下げ」と判断。** 実際の編集で「薄いワイヤーフレームが出るだけ」で判断材料になっていないため、ツールバーから撤去して実験機能扱いにする。機能自体は残すが、UI の一等地からは外す。

| 項目 | 内容 |
|------|------|
| **経緯** | 2026-04-11 にツールバーボタン追加で可視化（コミット c594999a）したが、実運用で価値が薄いことが確認された。 |
| **対応** | (1) ツールバーから `_diff_overlay_toolbar_action` を削除。(2) View メニューラベルに `(実験的)` を付加。(3) ショートカット `Shift+M` と左パネルのトグル、`TrackListPanel` の設定は残す。(4) テストはツールバー系の 3 件を削除、View/パネル/ショートカット系の 16 件は維持。 |
| **なぜ残すか** | 内部ロジック・描画・3 系統同期は完成しており、実装コストは既に払われている。完全削除せず「使いたいユーザーが使える」状態で置いておく。 |

#### ⏸ オニオンスキン: 必要性再評価

> **2026-04-12 追記。** 差分オーバーレイと同じ補助表示系。主機能から外す判断はしないが、必要性の再評価対象として記録。変更は当面しない（`CollapsibleSection` 内、初期展開のまま）。

#### ~~🔄 P3-8（再 open）: 書き出し UI 再設計~~ ✅ 完了 (2026-04-12)

> **2026-04-11 人間レビューで再 open、2026-04-12 修正完了。** プリセット刷新・サイズ計算・ユーザー定義・ヘルプテキストは従前の完了扱いを維持しつつ、UI の誤設定誘発を 5 点解消。

| 項目 | 内容 |
|------|------|
| **完了内容** | (1) **解像度アップスケール防止**: `_populate_resolution_combo()` で入力解像度を超える項目を「— 入力より大きいため無効」付きでグレーアウト（`QStandardItemModel` の `setEnabled(False)`）。(2) **手動ビットレートスライダー**: `QSlider` を `QSpinBox` と並列配置、`blockSignals` で双方向同期、スライダー範囲超過時は spin のまま・スライダーはクランプ。(3) **ビットレートモード排他表示**: `_manual_bitrate_row_indices` / `_target_size_row_indices` を追跡、`QFormLayout.setRowVisible()` でモードに応じ非該当行を完全非表示化。(4) **目標ファイルサイズ初期値補正**: `_initialize_target_size_from_estimate()` で auto モードの推定サイズを 10 MB 単位に丸めて target_file_size_mb のデフォルトに流用（既に bitrate_mode="target_size" のプリセットは尊重、duration=0 は補正スキップ）。(5) **音声ビットレート「再エンコード時のみ表示」**: `_audio_bitrate_row_indices` を setRowVisible で制御、"copy_if_possible" / "none" のときは行ごと非表示、"re_encode" のときのみ表示。従前の「disabled で見せる」方式は廃止。テスト 19 件追加、計 52 件 PASS。 |

#### ~~P3-10（新規）: 状態ラベルの整理と用語刷新~~ ✅ 完了 (2026-04-12)

> **2026-04-12 追加 / 同日完了。** 人間レビューで「interp / select の意味が伝わっていない」「状態ラベルの分かりにくさが UX に一番効く」と指摘されたもの。

| 項目 | 内容 |
|------|------|
| **完了内容** | (1) **i18n 用語刷新**: `frame_state.active` → 「検出フレーム」 / `interpolated` → 「補間フレーム」 / `predicted` → 「予測フレーム」 / `selected` → 「編集中」。`track.state_active` → 「有効」（「検出中」から変更、frame_state との語彙衝突解消）。(2) **重複表示解消**: `_TrackItem._frame_state_text()` は選択中なら「編集中」単独、非選択なら frame_state のラベルを返す。`_track_range_text()` から `track.state` の表示を削除して `"0-100f"` のみに。下インスペクタの `track_state_label` は維持。(3) **`(+pred to Nf)` 日本語化**: `_track_range_text()` / `_track_range_summary()` / `set_track_info()` の 3 箇所で `(予測延長 〜Nf)` に変更（UI-B1 も同時解消）。(4) テスト: 13 件追加（frame_state 5 件・track.state 3 件・`_frame_state_text` ヘルパ 3 件・範囲表示 2 件更新）、計 163 件 PASS。 |

#### P3-9（新規・⏸ 保留）: Undo 履歴ツリー表示

> **2026-04-11 追加 / 同日保留。** P3-5 の Undo 件数表示の発展として、履歴全体を左パネルに表示し、任意の過去状態へ一気にジャンプできるようにする。**P3-6 / P3-4 / P3-8 を先に片付けるため、一旦保留**。設計メモは本セクションに残す。

| 項目 | 内容 |
|------|------|
| **概要** | 左パネルに「履歴」セクションを追加。Undo 履歴の各エントリを縦並びで表示（操作名 + 番号）、現在位置をハイライト、クリックでその時点まで巻き戻し。VS Code の Timeline / Photoshop の History パネル相当。 |
| **モデル拡張** | `HistoryService.get_history() -> list[tuple[int, str]]`（全エントリの (index, label) を返す）、`HistoryService.jump_to_index(n: int) -> dict \| None`（任意 index に移動して state を返す、clean index の扱いも含む） |
| **UI** | `TrackListPanel` に `HistoryTreeSection` を新設（`CollapsibleSection` 使用、初期展開）。`QListWidget` 風にエントリを並べ、現在位置を accent 色でハイライト、クリックで `history_jump_requested(index)` シグナル発火。 |
| **MainWindow 連携** | シグナルを受けて `history_service.jump_to_index(n)` → `_restore_project_state()` → `_update_dirty_ui()`。`_commit_history_state()` / `undo()` / `redo()` のたびに履歴セクションを再描画。 |
| **完了条件** | (1) HistoryService 拡張 + テスト。(2) HistoryTreeSection 新規 UI + テスト。(3) MainWindow 統合。(4) 履歴 100 件の上限を超えた場合の挙動維持。(5) 左パネル「履歴」セクション、初期展開、クリックジャンプ動作。 |
| **スコープ外** | ブランチ表現（Git 的な木構造）、操作の diff 表示、履歴のエクスポート。あくまで直線的な履歴リスト。 |

---

### Phase 4 — 重量タスク（別途計画）

P3 とは独立した大規模タスク。着手前に設計フェーズを設けること。

#### P4-1: 教師データ保存

| 項目 | 内容 |
|------|------|
| **概要** | 編集済みプロジェクトの確定マスクを教師データとしてローカル保存する機能 |
| **何が不足しているか** | opt-in UI・保存先管理・件数/容量表示・プロジェクト単位削除・dataset manifest 生成がすべて未実装 |
| **なぜ必要か** | ユーザー固有データで検出モデルを改善するためのデータ蓄積が必要 |
| **備考** | `docs/03_planning/02_future-retraining-memo.md` に設計メモあり。P4-2 の前提 |

#### P4-2: ローカル自動再学習

| 項目 | 内容 |
|------|------|
| **概要** | 蓄積した教師データを使ってローカルでモデルを再学習し、検出精度を向上させる |
| **何が不足しているか** | training job・val/train split・学習ログ・モデル一覧・active モデル切替・比較レポート・ロールバックがすべて未実装 |
| **なぜ必要か** | 汎用モデルでは精度が不十分な場合に、ユーザー環境でファインチューニングする手段が必要 |
| **備考** | P4-1 の教師データ保存が前提。VRAM・ディスク・サンプル数の事前チェックも必要 |

#### P4-3: installer / updater / uninstaller

| 項目 | 内容 |
|------|------|
| **概要** | 非開発者が使える Windows 向け正式インストーラと、更新・アンインストール手段を提供する |
| **何が不足しているか** | 現状は `setup.bat` による開発者向けセットアップのみ。一般配布には不十分 |
| **なぜ必要か** | 製品配布段階では非開発者がセットアップできる形式が必要 |
| **備考** | NSIS / Inno Setup / Nuitka 等が候補。Python 依存の同梱方法の設計が先決 |

---

### UI polish backlog — 低優先

UIリデザイン Phase 1/2 の過程で検出された軽微な改善項目。P2/P3 とは独立して、余力があるときに片付ける。

| ID | 項目 | 内容 |
|----|------|------|
| ~~UI-B1~~ | ~~TrackList predicted tail 英語混じり~~ | ✅ P3-10 で同時解消（`(予測延長 〜Nf)` に変更） |
| UI-B2 | CollapsibleSection スタイル集約 | インライン QSS を `theme.py` のグローバル QSS に移動 |
| UI-B3 | 位置調整セクションの初期折りたたみ | 使用頻度が低いため `expanded=False` を検討 |
| UI-B4 | export_enabled ハンドラの重複排除 | `_on_export_enabled_changed` と `_on_export_enabled_by_id` が同構造のコピー。visibility 側も同様。将来まとめて共通化する |
| UI-B5 | タイムライン二重描画の抑制 | `_sync_tracks_to_ui` → `set_tracks` + `_update_preview` → `set_current_frame` で `update()` が2回走る。バッチ更新 or フラグによる抑制を検討 |

---

## 6. 着手順序（推奨）

| 順序 | タスク | 状態 | 根拠 |
|------|--------|------|------|
| ~~1~~ | ~~P2-5: crash recovery~~ | ✅ 完了 | — |
| ~~2~~ | ~~P2-2: 危険フレーム確認~~ | ✅ 完了 | — |
| ~~3~~ | ~~P2-3: E2E テスト~~ | ✅ 完了 | — |
| ~~4~~ | ~~P2-4: export queue 永続化~~ | ✅ 完了 | — |
| ~~5~~ | ~~P2-1: 頂点ホバー UI~~ | ✅ 採用せず | ホバー UI 試験実装→不採用。ダブルクリック追加・右クリック削除を正式導線に確定 |

**P2 全件完了。P3 は人間レビュー後の再整理を経て残り 4 タスクを実施中。**

P3 着手順序（2026-04-11 人間レビュー後）:

| 順序 | タスク | 状態 | 備考 |
|------|--------|------|------|
| ~~1~~ | ~~P3-5: Undo 件数・操作名~~ | ✅ 完了 | — |
| ~~2~~ | ~~P3-7a: ショートカット整備~~ | ✅ 完了 | — |
| ~~3~~ | ~~P3-7b: F1 ショートカット一覧ダイアログ~~ | ✅ 完了 | — |
| ~~4~~ | ~~P3-6 Phase A: トラック順序 UX 修正~~ | ✅ 完了 (2026-04-12) | — |
| ~~5~~ | ~~P3-8: 書き出し UI 再設計~~ | ✅ 完了 (2026-04-12) | 人間レビューで合格 |
| ~~6~~ | ~~P3-10: 状態ラベル整理~~ | ✅ 完了 (2026-04-12) | 用語刷新、重複解消、`(予測延長 〜Nf)` |
| - | P3-4: 差分オーバーレイ | ✅ 格下げ完了 (2026-04-12) | ツールバー撤去、View メニュー (実験的) として残存 |
| - | オニオンスキン | ⏸ 必要性再評価 | 現状維持 |
| 7 | P3-9: Undo 履歴ツリー表示 | ⏸ 保留 | 必要になったら再開 |
| 8 | P3-6 Phase B: DnD 並べ替え | ⏸ 保留 | 必要になったら追加 |

**P3 再整理後の判定**:
- 旧 P3-6「右クリックメニュー」は実装済みのまま残す（害はない、今回スコープ外）
- 旧 P3-4 / P3-8 はロジック完了、UI 修正フェーズとして継続
- P3-9 は P3-5 の発展として新規
- Phase 4（P4-1/2/3）は P3 完了後に別途計画する

**5月レビュー向け（MR シリーズ）**:
- ~~MR-01 タイムライン縦スクロール~~ ✅ 完了 (2026-04-13)
- ~~MR-02 書き出し対象フラグ分離~~ ✅ 完了 (2026-04-13)
- ~~MR-03 編集リアクション改善~~ ✅ 完了 (2026-04-13)
- ~~MR-04 後ろ向き追跡 UI 導線~~ ✅ 完了 (2026-04-13)
- ~~MR-05 検出エンジン選択 UI 基盤~~ ✅ 完了 (2026-04-13)
- ~~MR-06 レビュー用パッケージ準備~~ ✅ 完了 (2026-04-13) → `docs/04_review/`
- 詳細は `05_2026-05-pinky-review-plan.md` を参照

---

## 7. 旧ドキュメントの扱い

### `unimplemented-features.md`（現 `docs/99_archive/unimplemented-features-tauri.md`）

この文書は、廃止された Tauri 移植版を前提とした残件表である。現行 PySide6 実装に対して以下の問題がある。

- P0 として挙げていた「Persistent Mask Track・検出区間外編集・auto fallback・manual anchor 継承」は、現行 main に実装済みである
- 「タイムラインズーム」「keyframe source 視覚区別」「Progress UI」等も実装済みである
- Tauri 固有の課題（CLI 連携・subprocess 設計等）が混在している

**取り扱い**: `docs/99_archive/unimplemented-features-tauri.md` に移動済み。参照目的のみで保持する。  
現行残タスクの正本は本文書（`docs/03_planning/01_remaining-tasks.md`）を使用すること。

---

*本文書の改訂は実装の進捗に合わせて都度行う。*
