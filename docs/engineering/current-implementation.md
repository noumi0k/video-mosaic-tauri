# Auto Mosaic 現行実装 正本

最終更新: 2026-04-17

この文書は、現行リポジトリで作業するエンジニア / AI エージェント向けの正本です。
人間向けの説明は [../human/product-spec.md](../human/product-spec.md) に置き、ここでは実装判断に必要な境界、不変条件、実装済み状態を扱います。

## 1. システム構成

- Frontend: `apps/desktop`
- Desktop shell: Tauri 2
- UI: React + TypeScript
- Backend: `apps/backend`
- Backend runtime: Python 3.12 前提
- AI inference: ONNX Runtime。GPU は optional、CPU fallback は必須
- Video processing: FFmpeg + OpenCV fallback
- Tauri から Python への通信: `subprocess + CLI + JSON I/O`

## 2. 境界ルール

- `stdout` は machine-readable JSON 専用。
- log、diagnostics、traceback、native library の出力は `stderr` へ逃がす。
- Frontend は backend の内部 Python module を直接扱わない。
- Backend は Tauri / React の表示都合を project state に持ち込まない。
- Backend project state が source of truth。
- UI は backend state の projection として扱う。

## 3. パスと表示 URL

- Persisted project data には raw local Windows path を入れる。
- `asset.localhost` や display URL は frontend 表示専用。
- Backend に display URL を渡してはならない。
- `video.source_path` は raw local path として検証される。
- `file://`, `http://`, `https://`, `asset://` 系を project の raw path として保存しない。

## 4. Project model

現行 schema は `CURRENT_PROJECT_SCHEMA_VERSION = 2`。

Project は主に次を持つ。

- `project_id`
- `version`
- `schema_version`
- `name`
- `project_path`
- `video`
- `tracks`
- `detector_config`
- `export_preset`
- `paths`

PySide6 project v1 は migration adapter で Tauri schema v2 へ変換される。
この migration は、keyframe source、track source、manual edit protection、segment 化、export preset 正規化を含む。

## 5. Mask track の不変条件

編集の中心は isolated keyframe ではなく `MaskTrack`。

`MaskTrack` は次を持つ。

- `track_id`
- `label`
- `state`
- `source`
- `visible`
- `export_enabled`
- `keyframes`
- `label_group`
- `user_locked`
- `user_edited`
- `confidence`
- `style`
- `segments`

`export_enabled` は既定 `True`。レガシー payload は normalize で `True` 補完され、schema version は据え置き (v2)。`False` の track は export でスキップされ、preview では破線 outline のみ表示してモザイクを適用しない。`visible` と独立した責務で、UI 上の非表示と export からの除外を別々に制御する。

`user_edited` が true、または manual keyframe を含む track は manual 意図を持つ。
`source == "detector"` の track でも、manual 意図が入った時点で `source` は manual 側へ寄る。

自動検出で置換してよいのは、`source == "detector"` かつ `user_edited == false` かつ `user_locked == false` の track だけ。

## 6. Segment と shape 解決

Export では renderable segment を使う。
単純な last-keyframe hold に戻してはならない。

Renderable segment state:

- `confirmed`
- `held`
- `predicted`
- `interpolated`
- `uncertain`
- `active`
- `detected`

`resolve_active_keyframe(frame_index)` は export 用で、renderable span の外では `None` を返す。
`resolve_shape_for_editing(frame_index)` は編集用で、最初の keyframe 以後なら検出範囲外でも直近 shape を返せる。

Keyframe には `rotation` (度、±180 正規化) がある。ellipse の回転は `cv2.ellipse(angle)` と `ctx.ellipse(rotation_rad)` に反映され、`_lerp_rotation` で最短路補間される。

## 7. 検出

Backend command は `detect-video`, `start-detect-job`, `run-detect-job`, `get-detect-status`, `get-detect-result`, `cancel-detect-job`, `list-detect-jobs`, `cleanup-detect-jobs` を持つ。

検出結果の反映ルール:

- 全体検出では replaceable detector track を置換する。
- `start_frame` / `end_frame` 付きの範囲検出では IoU merge を使い、範囲外 keyframe と manual keyframe を保護する。
- broken / missing model は worker 起動前の preflight で失敗させる。
- worker が native crash した場合も job state と result/status の整合性を壊さない方向で扱う。

## 8. Model / doctor / runtime

Model 管理は file existence だけで判断しない。
`doctor` と `fetch_models` は integrity-based に扱う。

現行方針:

- model status は `missing`, `broken`, `installed` を区別する。
- HTML redirect / Git LFS pointer / tiny file / invalid ONNX magic / expected size / SHA-256 を検査する。
- temp download を verify してから final path へ promote する。
- `browser_download_url` ではなく、必要に応じて GitHub API asset URL と header を使う。
- detect 前に required model の integrity を確認する。
- review-runtime は vendor ABI と Python minor version を一致させる。

Backend Python 変更後に review build を作る場合は `npm.cmd run review:runtime` を実行する。

## 9. Export

Export は Python backend の責務。
Frontend は設定と job/cancel/status 表示を扱う。

現行で扱う設定:

- `resolution`: `source`, `720p`, `1080p`, `4k`
- `mosaic_strength`
- `audio_mode`: `mux_if_possible`, `video_only`
- `bitrate_kbps`: `null` なら auto
- `encoder`: `auto`, `gpu`, `cpu`

FFmpeg pipe export を優先し、失敗または unavailable の場合は OpenCV fallback を使う。
音声は `mux_if_possible` のとき ffmpeg で source audio を mux する。
GPU encoder は `auto` / `gpu` / `cpu` を扱う。
`auto` では `h264_nvenc` → `h264_qsv` → `h264_amf` を優先し、runtime failure 時は `libx264` へ再試行する。
エクスポート前には frontend 側で最新 project state を必ず保存する。
モザイク適用は `expand_px` と `feather` を export path で反映する。

## 10. Frontend 状態

`apps/desktop/src/App.tsx` は現在も大きめの shell で、主に次を持つ。

- project open / save / new
- preview source setup
- selection coordination
- shared job launch / polling
- high-level activity / error status
- detect / export orchestration
- autosave timer
- keyboard shortcuts

主要 editor surface:

- `components/TimelineView.tsx`
- `components/CanvasStagePanel.tsx`
- `components/MosaicPreviewCanvas.tsx`
- `components/TrackDetailPanel.tsx`
- `components/KeyframeDetailPanel.tsx`
- `components/JobPanel.tsx`
- `components/DangerWarningsPanel.tsx`

現在の最低限フローとして、open video → detect → mask edit → export は Tauri window 上で一周確認済み。

今後の UI 整理では、backend domain rule を frontend convenience のために変えない。
必要なら `App.tsx` から hooks / controller へ分離するが、振る舞い変更と混ぜない。

## 11. Job model

長時間処理は job-based。
Runtime jobs、detect jobs、export は Job Panel に集約する。

代表 state:

- `queued`
- `starting`
- `running`
- `cancelling`
- `cancelled`
- `completed` / `succeeded`
- `failed`
- `interrupted`

Cancel は request-based。
既に terminal state の job を `cancelling` に戻してはならない。

## 12. 差分管理とロードマップ

安定化フェーズ完了後は、実装済み / 未実装を次の 3 層で管理する。

- 製品仕様の母集団: [../feature_list.md](../feature_list.md), [../unique_features.md](../unique_features.md)
- 現行 Tauri 実装との差分一覧: [../project/missing-feature-matrix.md](../project/missing-feature-matrix.md)
- 実装順序と受け入れ条件: [../project/unimplemented-features.md](../project/unimplemented-features.md)

現在残っている大きな領域は次。

- persistent workflow completion
  - file-backed recovery
  - export 前 danger warning の正式 review 導線
- export workflow completion
  - export queue
  - queue persistence / interrupted restore
  - richer export settings / preset management
- regression prevention
  - Tauri E2E
  - recovery / export output verification
- editing UX completion
  - preview operation mode badge (M-C06 partial)
  - onion skin (M-C07)
  - UI 言語切替 (M-C09)
  - diff overlay (M-C08 deferred 維持、再評価は Phase D 完了後)
- future feature track
  - AI detect performance tuning
  - contour follow
  - teacher dataset
  - local retraining
  - installer / updater

## 13. 計画資料の使い分け

今後の判断順序は次のとおり。

1. この文書
2. [../project/missing-feature-matrix.md](../project/missing-feature-matrix.md)
3. [../project/unimplemented-features.md](../project/unimplemented-features.md)
4. 実装コードとテスト

次の文書は補助資料として使う。

- [../project/pyside6-editing-experience-parity-checklist.md](../project/pyside6-editing-experience-parity-checklist.md): PySide6 比較ベースの機能 ID と過去フェーズ票
- [../project/pyside6-ui-structure-reference.md](../project/pyside6-ui-structure-reference.md): PySide6 UI 観察記録
- [../project/ai-handoff.md](../project/ai-handoff.md): dated handoff log

次の文書は履歴参照用であり、通常の作業判断の正本にはしない。

- [../project/pyside6-remaining-tasks.md](../project/pyside6-remaining-tasks.md)
- [../architecture/requirements-spec-v2.1.md](../architecture/requirements-spec-v2.1.md)
- [../architecture/tauri-from-scratch-spec.md](../architecture/tauri-from-scratch-spec.md)
- [../tauri-migration/](../tauri-migration/)
