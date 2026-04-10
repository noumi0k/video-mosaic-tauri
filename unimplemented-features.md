# 未実装機能一覧

最終更新: 2026-04-10

## 1. 実装済み (今回の移行作業で完了)

### 1.1 PySide6 移行コア
- [x] PySide6 project v1 → Tauri schema v2 migration adapter
- [x] Keyframe source mapping (auto→detector, manual→manual, anchor_fallback→detector_anchored)
- [x] user_locked / user_edited track の AI 検出置換保護
- [x] Polygon interpolation (resample + align + lerp) — backend + frontend
- [x] Ellipse interpolation (bbox + rotation + confidence + opacity)
- [x] expand_px / feather interpolation
- [x] Track stitching (180 frame gap, spatial similarity)
- [x] Ephemeral track filter (min 2 keyframes)
- [x] Matching gap 拡大 (12→60 frames, PySide6 同等)

### 1.2 ランタイム・検出
- [x] Dev mode runtime 解決 (CARGO_MANIFEST_DIR + venv 自動検出)
- [x] Backend venv セットアップ (Python 3.12 + cv2 + numpy + onnxruntime)
- [x] AI 検出 → UI 反映の race condition 修正
- [x] reconcile_job_state: result.json 存在時に succeeded に修正
- [x] Frontend: 未処理 terminal ジョブの再ポーリング

### 1.3 Export
- [x] FFmpeg h264 パイプエンコード (OpenCV フォールバック付き)
- [x] 解像度プリセット (source / 720p / 1080p / 4K)
- [x] 自動ビットレート (解像度連動) + 手動指定
- [x] Audio mux (ffmpeg 1パス)
- [x] UI 解像度セレクタ

### 1.4 編集・UI
- [x] Undo / Redo (Ctrl+Z / Ctrl+Shift+Z)
- [x] Track 作成 / 削除ボタン
- [x] キーボードショートカット (Arrow, Space, K, Shift+K, [, ], H, N, Delete, Ctrl+S, I, O)
- [x] 未保存ガード (New / Open / Open Video 前の確認)
- [x] 自動保存 (60秒間隔、保存済みプロジェクトのみ)
- [x] 範囲検出 (I/O マーカー + start_frame/end_frame)
- [x] 危険フレーム検出 (export 前警告: KFギャップ, エリア急変, 低信頼度)
- [x] モデル取得 HTML/LFS 対策 (Git LFS ポインタ検出追加)

### 1.5 既存実装 (移行前から動作)
- [x] subprocess + CLI + JSON I/O 連携
- [x] project save / load / save as
- [x] track / keyframe 選択同期
- [x] inspector 編集 (bbox, points, shape_type)
- [x] canvas 直接編集 (ellipse 移動/リサイズ, polygon 頂点操作)
- [x] timeline (tracks, keyframes, playhead, zoom, ruler)
- [x] export / cancel / progress polling
- [x] doctor / model integrity / review package
- [x] 再生同期 (video ↔ currentFrame 双方向)

## 2. 未実装 (P2: 中優先)

### 2.1 オニオンスキン
- [ ] 前後フレームの keyframe shape を半透明で重ねて表示
- [ ] toggle UI (CanvasStagePanel)

### 2.2 GPU エンコーダ選択
- [ ] h264_nvenc / h264_qsv / h264_amf の検出と選択
- [ ] GPU エンコード失敗時の CPU フォールバック
- [ ] UI: GPU toggle

### 2.3 Export キュー
- [ ] 複数 export ジョブの逐次実行
- [ ] キュー永続化と recovery

### 2.4 E2E テスト
- [ ] canvas drag ベースの実操作テスト
- [ ] review package 起動後の一連フローテスト

## 3. 未実装 (P3: 後優先)

### 3.1 教師データ保存
- [ ] opt-in UI
- [ ] crop / 初期予測 / 最終結果 / metadata 保存
- [ ] dataset manifest 生成

### 3.2 ローカル再学習
- [ ] training dataset validator
- [ ] retraining job
- [ ] 学習済みモデル管理

### 3.3 最終 installer / updater
- [ ] Windows 正式 installer
- [ ] auto updater
- [ ] アンインストーラ

### 3.4 Crash recovery
- [ ] atomic write + recovery dialog
- [ ] 中断ジョブの自動検出と復帰

## 4. 優先順位まとめ

| 優先度 | 状態 | 内容 |
|--------|------|------|
| P0 | **全完了** | Persistent mask track, 検出外編集, continuity/fallback, manual anchor 継承 |
| P1 | **全完了** | Timeline zoom, export parity, progress UX, keyboard shortcuts, autosave, range detect |
| P2 | 残4件 | オニオンスキン, GPU エンコーダ, export キュー, E2E テスト |
| P3 | 残3件 | 教師データ, 再学習, installer, crash recovery |
