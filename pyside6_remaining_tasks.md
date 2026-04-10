# Auto Mosaic — PySide6 機能の Tauri 版実装状況

最終更新: 2026-04-10  
対象: `H:\mosicprogect\taurimozaic` main ブランチ

---

## 1. 書き出しまわり

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 書き出し設定ダイアログ（コーデック/解像度/音声/保存先） | ✅ | `ExportSettingsModal.tsx` (resolution/mosaic/audio/bitrate) |
| 書き出し前の危険フレーム確認 (KFギャップ/面積急変/predicted) | ✅ | `dangerousFrames.ts` + export 前 confirm |
| 危険フレーム確認ダイアログ (3択: 確認/無視/キャンセル) | ✅ | `window.confirm` で実装 |
| 危険フレーム一覧の左パネル統合 (行クリックシーク/確認トグル) | ❌ | confirm ダイアログのみ。左パネル統合・確認トグルなし |
| タイムライン上の危険マーカー (色分け/クリックシーク) | ❌ | タイムラインマーカー未実装 |

## 2. マスク編集・キーフレーム編集

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 楕円マスクの軸別リサイズ (辺中点ハンドル) | ✅ | `CanvasStagePanel.tsx` edge handles |
| 辺ダブルクリックで頂点追加 | ❌ | 右クリックメニューからのみ |
| 右クリック時の頂点追加バグ修正 | ✅ | Tauri 版では発生しない (DOM イベント) |
| keyframe 複製 (Ctrl+D) | ✅ | `handleDuplicateKeyframe` |
| keyframe 追加・補間・Undo/Redo の E2E テスト | ❌ | E2E テスト基盤なし |

## 3. AI 検出まわり

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 全体検出 | ✅ | `detect_video.py` + job polling |
| 全体検出時の上書き確認ダイアログ (3択) | ❌ | 確認なしで即検出開始 |
| AI 区間検出 (In/Out マーカー + ショートカット) | ✅ | I/O キー + start_frame/end_frame |
| 区間外不変の保証 | ✅ | start_frame/end_frame でフレーム範囲限定 |
| manual 保護付き区間再検出 | ✅ | `user_locked` / `user_edited` 保護 |
| 区間検出結果のマージ (ラベル+IoU) | ⚠️ | `replace_detector_tracks` で全置換。PySide6 のような IoU ベース対応付けなし |
| 誤マージ回帰テスト | ❌ | E2E テスト基盤なし |
| 単フレーム検出 (Ctrl+Shift+D) | ✅ | `handleDetectCurrentFrame` |
| NudeNet v3.4 クラスインデックス (18クラス対応) | ✅ | 修正済み (male_genitalia=14, male_face=12) |

## 4. マスクトラックの保持・終了まわり

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| Persistent Mask Track (active/lost/inactive) | ✅ | `track_quality.py` stitching + filtering |
| 検出区間外での shape 保持・編集 | ✅ | `resolve_for_editing` (held semantics) |
| auto fallback / continuity 評価 (3段) | ✅ | `mask_continuity.py` ACCEPT/ACCEPT_ANCHORED/REJECT |
| manual anchor 前方継承 | ✅ | `get_active_manual_anchor` (60 frame decay) |
| manual keyframe 保護 | ✅ | `apply_domain_rules` + `user_edited` |
| マスク残留バグ修正 (消失後もモザイクが残る) | ✅ | `resolve_for_render` segment gate |
| 範囲外延長ヒント (K で延長) | ❌ | ヒント表示なし |
| K ヒントのノイズ削減 | ❌ | 未実装 |

## 5. Progress UX

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 共通 Progress UX (BusyWorker/BusyProgressScope) | ✅ | `JobPanel.tsx` で runtime/detect/export 共通表示 |
| 単フレーム検出の非同期化 | ✅ | job 方式で非同期実行 |
| 長時間処理の共通パターン化 | ✅ | job polling + terminal state 処理 |

## 6. UI リデザイン・操作導線

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 日本語 UI 正本化 | ⚠️ | `uiText.ts` で部分的。ボタン類は英語混在 |
| パネルヘッダー階層化 | ✅ | CSS `nle-panel-header` |
| Preview 主役化 | ✅ | HTML video 中央配置 |
| ツールバー整理 | ✅ | ヘッダーにグルーピング |
| Inspector 並び替え (高頻度を上位) | ✅ | TrackDetail + KeyframeDetail 分離 |
| タイムライン左側からのトラック選択 | ✅ | `TimelineView` track name click |
| transport (play/pause/step) 再配置 | ⚠️ | HTML5 video controls 依存。独立 transport UI なし |
| QPainter アイコン化 | — | Tauri は DOM/CSS ベースなので不要 |
| DangerWarningsSection の左パネル統合 | ❌ | 左パネルに危険フレーム一覧なし |
| track 複製 | ✅ | `handleDuplicateTrack` |
| track 分割 | ✅ | `handleSplitTrack` |

## 7. Crash Recovery

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 自動保存 (60秒/dirty時) | ✅ | `autosaveTimerRef` |
| 起動時 recovery 検出 + ダイアログ | ❌ | autosave はあるが recovery dialog なし |
| RecoveryStore (atomic write) | ⚠️ | `save_project.py` は通常保存。recovery 専用ストアなし |
| 復元後 dirty 化 | ❌ | recovery フローなし |
| 保存成功時 recovery cleanup | ❌ | recovery ファイルの管理なし |
| closeEvent dirty ガード (保存/破棄/キャンセル) | ✅ | `confirmDiscardIfDirty` (New/Open/Open Video) |
| project_id ベースの recovery 識別 | ❌ | recovery フローなし |

## 8. E2E / UI テスト基盤

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| pytest-qt / qtbot 基盤 | — | Tauri は Web ベース。pytest-qt は不要 |
| smoke テスト | ❌ | Tauri frontend E2E テストなし |
| キーフレームフロー E2E | ❌ | |
| 危険フレームフロー E2E | ❌ | |
| 区間検出フロー E2E | ❌ | |
| backend ユニットテスト | ✅ | 10ファイル ~400件 |
| frontend ユニットテスト | ✅ | 10ファイル ~140件 |

## 9. 運用・ドキュメント

| 機能 | Tauri 版 | 備考 |
|------|---------|------|
| 実装状況チェックリスト | ✅ | 本文書 |
| 移行ドキュメント (contract freeze) | ✅ | `docs/tauri-migration/` 5文書 |
| テスト件数管理 | ✅ | backend 255+ / frontend 140+ |

---

## 10. サマリー

### 実装済み (PySide6 と同等)

- 書き出し設定ダイアログ (解像度/ビットレート/音声/モザイク強度)
- 危険フレーム検出 + export 前警告
- 楕円軸別リサイズ
- keyframe 複製 (Ctrl+D) / 単フレーム検出 (Ctrl+Shift+D)
- AI 全体検出 / 区間検出 (I/O マーカー)
- manual 保護 / user_locked / continuity fallback
- Persistent Mask Track / 検出外 shape 保持
- 共通 Progress UX (JobPanel)
- track 複製 / 分割 / 作成 / 削除
- Undo/Redo + 件数表示
- 自動保存 (60秒) / 未保存ガード
- キーボードショートカット (16種)
- NudeNet v3.4 全18クラス対応

### 未実装 (PySide6 にあって Tauri にないもの)

**中規模:**
- 危険フレーム一覧の左パネル統合 (確認トグル/行クリックシーク)
- タイムライン上の危険マーカー (色分け表示)
- 全体検出前の上書き確認ダイアログ (3択)
- 区間検出のマージロジック (IoU ベース対応付け)
- 辺ダブルクリック頂点追加
- 起動時 recovery ダイアログ
- 独立 transport UI (play/pause/step ボタン)
- 日本語 UI の統一 (ボタン類の英語残り)

**大規模:**
- E2E テスト基盤 (Playwright / Vitest 等)
- RecoveryStore + project_id ベース recovery

---

*本文書の改訂は実装の進捗に合わせて都度行う。*
