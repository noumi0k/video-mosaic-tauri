# Auto Mosaic — PySide6 機能の Tauri 版実装状況

最終更新: 2026-04-10  
対象: `H:\mosicprogect\taurimozaic` main ブランチ

---

## 1. 危険フレーム一覧の左パネル統合

### PySide6 実装内容
- `app/ui/danger_warnings_section.py` — スクロール可能な警告一覧ウィジェット
- 各行: アイコン / フレーム番号 / 理由 / トラックラベル / 確認トグル
- ヘッダー常時表示 + ▼▶ 折りたたみ（×ボタン廃止済み）
- 確認トグル: 未確認→「確認」/ 確認済み→「✓ 確認済み」/ 再クリックで解除
- シグナル: `frame_selected(int)` / `warning_resolved(int, bool)`
- `track_list_panel.py` 最上部に埋め込み
- `main_window.py` から行クリック時に `_seek_to_frame()` 接続

### Tauri 実装状況: ❌ 未実装
- `dangerousFrames.ts` で危険フレーム検出は実装済み
- export 前の `window.confirm` ダイアログのみ
- **不足**: 左パネル統合、確認トグル、行クリックシーク、折りたたみ

---

## 2. タイムライン危険マーカー

### PySide6 実装内容
- `timeline_widget.py` ルーラー上端に ▲ マーカー描画
- 色分け: long_gap=オレンジ / area_jump=スカイブルー / track_lost=赤ピンク
- サイズ: ±6px
- 確認済み → 半透明グレー化
- ルーラークリック時 8px 以内の危険マーカーへスナップ
- `set_danger_markers(markers)` API
- `main_window.py` から左パネルと同時にマーカー反映

### Tauri 実装状況: ❌ 未実装
- TimelineView に in/out マーカーはあるが、危険フレームマーカーなし

---

## 3. 全体検出前の上書き確認ダイアログ

### PySide6 実装内容
- `main_window.py` の `detect_masks()` で既存トラック有無を確認
- 3択ダイアログ:
  1. 手動編集を保護して検出 (manual/user_locked を壊さない)
  2. すべて上書きして検出
  3. キャンセル
- 既存トラック件数・手動編集済み件数を文言に含む
- 翻訳文言は `app/ui/i18n.py` に追加

### Tauri 実装状況: ❌ 未実装
- 確認なしで即検出開始 (`replace_detector_tracks` で全置換)

---

## 4. 区間検出 IoU マージロジック

### PySide6 実装内容
- `apply_range_detection_results()` で既存トラックと新検出を ラベル+IoU で対応付け
- IoU 閾値: 0.1
- マッチ時: 区間外 KF 全保持、manual 保護 KF 保持、区間内のみ更新
- 未マッチ: 新規トラック追加
- 区間内 KF なし: 完全無変更
- `preserve_manual` フラグで manual 保護 ON/OFF
- 既知制限: 完全交差時の誤マッチ、中間位置の IoU 不足 → `[KNOWN_LIMIT]` テスト

### Tauri 実装状況: ⚠️ 部分実装
- `start_frame`/`end_frame` でフレーム範囲限定は実装済み
- **不足**: `replace_detector_tracks` は全置換。IoU ベース対応付けなし

---

## 5. 辺ダブルクリック頂点追加

### PySide6 実装内容
- `preview_canvas.py` の `mouseDoubleClickEvent()` 新設
- `_resolve_edge_target()` で辺近傍判定
- 辺近傍ダブルクリック → 頂点追加
- マスク中央の広い領域 → 追加しない
- 右クリック → コンテキストメニューのみ (即時 emit 削除済み)

### Tauri 実装状況: ❌ 未実装
- CanvasStagePanel で右クリックメニューからの頂点追加は可能
- ダブルクリック頂点追加なし

---

## 6. Recovery ダイアログ

### PySide6 実装内容
- `app/ui/recovery_dialog.py` — 復元/削除/後で決める/閉じる
- `app/infra/storage/recovery_store.py` — recovery ファイル読み書き・一覧・削除・atomic 保存
- `project_id` (UUID) ベースで recovery 識別
- 起動後 300ms で `data/temp/*.recovery.json` 検索 → ダイアログ表示
- 復元時: project セット → dirty 状態 → `can_undo=False` の clean history → recovery 削除
- `closeEvent()` の保存/破棄/キャンセル分岐
- 保存成功時 recovery cleanup

### Tauri 実装状況: ⚠️ 部分実装
- 自動保存 60秒 (`autosaveTimerRef`) は実装済み
- 未保存ガード (`confirmDiscardIfDirty`) は実装済み
- **不足**: recovery ファイル管理、起動時 recovery ダイアログ、project_id ベース識別

---

## 7. 独立 transport UI

### PySide6 実装内容
- `timeline_widget.py` 内の transport bar として整理
- Preview 直下 / Timeline 上側 / 中央基準の配置
- QPainter 描画アイコン: skip_back/step_back/play/pause/step_fwd/skip_fwd
- 4 状態対応: Normal/Active/Pressed/Disabled
- 左右対称思想: 戻し系=左、送り系=右、再生/停止=中央
- ダークテーマ対応、DPI 100%/125%/150% 確認済み

### Tauri 実装状況: ⚠️ 部分実装
- HTML5 `<video controls>` による再生/一時停止は動作
- Space キーで play/pause
- Arrow キーでフレーム送り/戻し
- **不足**: 独立 transport ボタン群、QPainter 相当のアイコン描画

---

## 8. 日本語 UI 統一

### PySide6 実装内容
- `app/ui/i18n.py` 中心に `tr()` 経由の日本語文言化
- 対象: メニューバー/ツールバー/PropertyPanel/TrackListPanel/KF一覧/警告/ヒント/検出/transport tooltip
- Phase 1: 55翻訳キー追加、パネルヘッダーアクセント
- Phase 2: レイアウト配分見直し、Inspector 再編
- UTF-8 前提、`?` `�` 混入チェック

### Tauri 実装状況: ⚠️ 部分実装
- `uiText.ts` で主要文言は日本語化済み
- **不足**: ボタン類の英語残り (Undo/Redo/Export/+ Track 等)、tooltip 未翻訳

---

## 9. サマリー: 実装済み vs 未実装

### 実装済み (PySide6 と同等以上)

| カテゴリ | 機能 |
|---------|------|
| 書き出し | 設定ダイアログ (解像度/ビットレート/音声/モザイク) |
| 書き出し | 危険フレーム検出 + export 前 confirm |
| 編集 | 楕円軸別リサイズ、KF 複製 (Ctrl+D) |
| 検出 | 全体検出 / 区間検出 (I/O) / 単フレーム検出 |
| 検出 | manual 保護 / user_locked / continuity fallback |
| 検出 | NudeNet v3.4 全18クラス対応 |
| トラック | Persistent Track / 検出外 shape 保持 |
| トラック | 作成 / 削除 / 複製 / 分割 / 表示切替 |
| 操作 | Undo/Redo + 件数表示 |
| 操作 | キーボードショートカット 16種 |
| 安全 | 自動保存 60秒 / 未保存ガード |
| Progress | JobPanel 共通表示 |

### 未実装 (PySide6 にあって Tauri にないもの)

| # | 機能 | 規模 |
|---|------|------|
| 1 | 危険フレーム左パネル統合 (確認トグル/行クリックシーク/折りたたみ) | 中 |
| 2 | タイムライン危険マーカー (色分け/スナップ/確認済みグレー化) | 中 |
| 3 | 全体検出前の上書き確認ダイアログ (3択) | 小 |
| 4 | 区間検出 IoU マージロジック (ラベル+IoU 対応付け) | 大 |
| 5 | 辺ダブルクリック頂点追加 | 小 |
| 6 | Recovery ダイアログ (起動時復元/project_id 識別) | 中 |
| 7 | 独立 transport UI (中央帯ボタン群) | 中 |
| 8 | 日本語 UI 統一 (ボタン/tooltip の英語残り解消) | 小 |

---

*本文書の改訂は実装の進捗に合わせて都度行う。*
