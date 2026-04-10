# Auto Mosaic — Tauri 版 実装状況チェックリスト

最終更新: 2026-04-10 (PySide6 版タスク一覧をベースに Tauri 版で再確認)  
対象: `H:\mosicprogect\taurimozaic` main ブランチ

---

## 1. 文書の目的

本書は PySide6 版の残タスク一覧 (`mosic2/pyside6_remaining_tasks.md`) をベースに、Tauri 版の実装状況を再確認したものである。

---

## 2. コア機能の実装状況

| # | 機能 | Tauri 版 | 根拠 |
|---|------|---------|------|
| 1 | 動画オープン・VideoMeta 読み込み | ✅ | `open_video.py` + `probe.py` (FFprobe + OpenCV) |
| 2 | project save / load (JSON) | ✅ | `save_project.py` + `load_project.py` + schema migration |
| 3 | preview canvas (表示・ドラッグ・スケール・頂点編集) | ✅ | `CanvasStagePanel.tsx` (ellipse move/resize, polygon vertex ops) |
| 4 | timeline (スクラブ・ズーム・スクロール・マーカー) | ✅ | `TimelineView.tsx` (zoom steps, ruler sync, KF markers) |
| 5 | keyframe 追加 | ✅ | `create_keyframe.py` + K ショートカット |
| 6 | keyframe 削除 | ✅ | `delete_keyframe.py` + Shift+K ショートカット |
| 7 | keyframe 移動 | ✅ | `move_keyframe.py` + [/] ショートカット |
| 8 | keyframe 補間 (ellipse + polygon) | ✅ | `mask_continuity.py` interpolate_ellipse / interpolate_polygon |
| 9 | keyframe 複製 | ❌ | PySide6 の `duplicate_keyframe()` 相当なし。Ctrl+D 未実装 |
| 10 | track 作成 | ✅ | `create_track.py` + N ショートカット |
| 11 | track 削除 | ✅ | `App.tsx handleDeleteTrack()` + Delete ショートカット |
| 12 | track 表示切替 | ✅ | `update_track.py` + H ショートカット |
| 13 | track 複製 | ❌ | PySide6 の `ProjectEditService.duplicate_track()` 相当なし |
| 14 | track 分割 | ❌ | PySide6 の `ProjectEditService.split_track()` 相当なし |
| 15 | 自動検出 (全フレーム) | ✅ | `detect_video.py` + `start_detect_job.py` |
| 16 | 単フレーム検出 | ❌ | PySide6 の `detect_current_frame()` 相当なし。Ctrl+Shift+D 未実装 |
| 17 | 検出 Progress UI | ✅ | `JobPanel.tsx` (status, progress, cancel) |
| 18 | 範囲検出 (In/Out マーカー) | ✅ | `TimelineView.tsx` in/out markers + detect payload start/end_frame |
| 19 | Persistent Mask Track | ✅ | `track_quality.py` (stitching, filtering) + state field |
| 20 | 検出区間外 shape 保持・編集 | ✅ | `mask_continuity.py resolve_for_editing()` |
| 21 | auto fallback / continuity 評価 | ✅ | `mask_continuity.py` (ACCEPT / ACCEPT_ANCHORED / REJECT) |
| 22 | manual anchor 前方継承 | ✅ | `mask_continuity.py get_active_manual_anchor()` (60frame decay) |
| 23 | manual keyframe 保護 | ✅ | `project.py MaskTrack.apply_domain_rules()` + user_edited |
| 24 | 輪郭抽出 (GrabCut / SAM2 / HSV) | ✅ | `detect_video.py` (none / fast / balanced / quality) |
| 25 | 動画書き出し (非同期・キャンセル) | ✅ | `export.py` (FFmpeg h264 pipe + OpenCV fallback) |
| 26 | 書き出し解像度プリセット | ✅ | source / 720p / 1080p / 4K + auto bitrate |
| 27 | export queue 管理 | ⚠️ | 1ジョブのみ。PySide6 の `ExportQueueDialog` 相当の複数ジョブキューなし |
| 28 | undo / redo | ✅ | `editorHistory.ts` + Ctrl+Z / Ctrl+Shift+Z |
| 29 | keyframe source 視覚区別 | ✅ | `timelineSegmentDisplay.ts` (manual, auto, anchored, interpolated, predicted) |
| 30 | GPU / デバイス設定 | ✅ | `DetectorSettingsModal.tsx` (auto/cuda/cpu, ONNX version) |
| 31 | 依存関係チェック | ✅ | `doctor.py` + UI model status 表示 |
| 32 | セットアップ導線 | ✅ | `setup_environment.py` + `fetch_models.py` |
| 33 | ユニットテスト | ✅ | backend 10ファイル / frontend 10ファイル (~540件) |
| 34 | E2E テスト | ❌ | Tauri 版に E2E テスト基盤なし |

---

## 3. PySide6 P1 タスク対応状況

| ID | PySide6 タスク | Tauri 版 | 備考 |
|----|---------------|---------|------|
| P1-1 | 書き出し設定 UI | ⚠️ | 解像度セレクタはあるが、コーデック/音声/ビットレートの詳細ダイアログなし |
| P1-2 | 楕円の軸別リサイズ | ✅ | `CanvasStagePanel.tsx` edge handles |
| P1-3 | 共通 Progress UX 統一 | ✅ | `JobPanel.tsx` で runtime / detect / export を共通表示 |

---

## 4. PySide6 P2 タスク対応状況

| ID | PySide6 タスク | Tauri 版 | 備考 |
|----|---------------|---------|------|
| P2-1 | 頂点追加・削除ホバー UI | ❌ | 右クリック / コンテキストメニューからは操作可能。ホバー UI なし |
| P2-2 | 危険フレーム確認ダイアログ | ✅ | `dangerousFrames.ts` + export 前 confirm ダイアログ |
| P2-3 | E2E テスト | ❌ | Tauri 版に E2E テスト基盤なし |
| P2-4 | export queue 永続化 | ❌ | 1ジョブのみ、永続化なし |
| P2-5 | crash recovery | ⚠️ | autosave (60秒) はあるが、recovery dialog なし |

---

## 5. PySide6 P3 タスク対応状況

| ID | PySide6 タスク | Tauri 版 | 備考 |
|----|---------------|---------|------|
| P3-1 | 教師データ保存 | ❌ | 未実装 |
| P3-2 | ローカル自動再学習 | ❌ | 未実装 |
| P3-3 | installer / updater | ❌ | review package のみ。正式 installer なし |
| P3-4 | 差分オーバーレイ / オニオンスキン | ❌ | 未実装 |
| P3-5 | Undo 件数・操作名表示 | ❌ | undo/redo ボタンのみ。件数表示なし |
| P3-6 | 右クリックメニュー (トラック一覧) | ❌ | TrackDetailPanel にボタンはあるがコンテキストメニューなし |
| P3-7 | F1 ショートカット一覧 | ❌ | 未実装 |
| P3-8 | export profile プリセット | ❌ | 解像度セレクタのみ。保存可能プリセットなし |

---

## 6. Tauri 版で新規実装済み (PySide6 にない機能)

| 機能 | 備考 |
|------|------|
| PySide6 v1 project migration | v1 → v2 自動変換 + source mapping |
| Git LFS ポインタ検出 | モデルダウンロード時の追加保護 |
| FFmpeg h264 パイプエンコード | PySide6 は FFmpeg wrapper、Tauri は rawvideo pipe |
| dev.cmd 起動ショートカット | ルート直下に配置 |

---

## 7. 未実装サマリー

### すぐ実装可能 (小規模)
- [ ] keyframe 複製 (Ctrl+D)
- [ ] 単フレーム検出 (Ctrl+Shift+D)
- [ ] F1 ショートカット一覧
- [ ] Undo 件数表示

### 中規模
- [ ] track 複製・分割
- [ ] 書き出し設定詳細ダイアログ
- [ ] export queue (複数ジョブ)
- [ ] crash recovery dialog
- [ ] 頂点ホバー UI
- [ ] オニオンスキン

### 大規模 (将来)
- [ ] E2E テスト基盤
- [ ] 教師データ保存
- [ ] ローカル再学習
- [ ] 正式 installer / updater

---

*本文書の改訂は実装の進捗に合わせて都度行う。*
