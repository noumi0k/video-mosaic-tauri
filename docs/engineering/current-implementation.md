# Auto Mosaic 現行実装 正本

最終更新: 2026-04-17 (目視レビュー 1 st 反映済み: KF 色仕様修正 / Ctrl+Shift+R / Ctrl+M / save dialog scope 修正 / inline-project mutation)

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
- 2026-04-17 review pass 以降、**手動作成マスクの内部表現は polygon を正本にする**。楕円ボタンも bbox 内接の polygon 頂点列を生成して保存し、全マスクが頂点編集できる状態を優先する。
- backend / UI は既存 AI 検出由来の `shape_type="ellipse"` を引き続き読める必要がある。つまり保存正本は polygon 優先だが、読み取り互換として ellipse 対応は維持する。

Keyframe には `rotation` (度、±180 正規化) がある。ellipse の回転は `cv2.ellipse(angle)` と `ctx.ellipse(rotation_rad)` に反映され、`_lerp_rotation` で最短路補間される。

## 7. 検出

### Unsaved (inline) project mutation

- 2026-04-17 レビューで「編集操作の都度 save dialog が出る」問題が指摘された (`feedback_save_dialog_scope.md`)。
- 全ての mutation command (`create-track` / `update-track` / `duplicate-track` / `split-track` / `create-keyframe` / `update-keyframe` / `delete-keyframe` / `move-keyframe` / `save-project`) は payload の `project_path` が falsy のとき `project` (inline payload) に fallback する (`_project_mutation.load_project_for_mutation`)。
- `_project_mutation.persist_project` は `path=None` のとき `atomic_write_text` をスキップし、response の `project_path` を `None` にする。
- frontend の `projectRefForMutation()` が `project.project_path` の有無で `{ project_path }` または `{ project }` を自動選択する。未保存状態でトラック作成・編集を続けられる。
- 明示的な保存 (Ctrl+S / Ctrl+Shift+S / File メニュー) のみが save dialog を開く。Export は queue が file-backed のため、未保存時はダイアログを開かず「Ctrl+S で保存してから書き出してください」エラーを表示する。

### Timeline keyframe marker colors (feature_list §5-1)

| source | background | 意味 |
| --- | --- | --- |
| `manual` | `#FFFFFF` (白) | ユーザー手動入力 |
| `auto` / `detector` | `#F5C518` (金) | AI 検出の直接結果 |
| `auto-anchored` (`source_detail = detector_anchored`) | 金 + 青リング | anchor 修正済み |
| `predicted` | `#9CA3AF` (灰) | motion 予測補完 |
| `re-detected` | `#60A5FA` (薄青) | lost 状態から再検出 |
| `contour_follow` | `#22C55E` (緑) | Optical Flow 追従 |
| `interpolated` | `#E0E0E0` (薄灰) | 補間 (メモリ上のみ、通常は表示されない) |
| `anchor_fallback` | auto-anchored と同扱い | ContinuityService による修正 |

### Track editing (duplicate / split)

- `duplicate-track`: 選択 track を `keyframes` / `segments` / `style` の deepcopy と新 `track_id` (`track-<uuid4>`) で複製。`label` には ` (copy)` を付与、`user_edited=True` / `user_locked=False` で manual 意図マーク。
- `split-track`: `split_frame` を境に keyframes を分配し、境界を跨ぐ segments はトリムして両側へ分散。左右どちらかの keyframes が空になる分割は `SPLIT_EMPTY_SIDE` で拒否。右側 track は ` (split)` label + 新 `track_id`、元 track は in-place 更新 + `mark_user_edited()`。

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

### Installed model management (2026-04-17)

- CLI commands: `list-installed-models` / `delete-installed-model`。
- `list-installed-models` は `model_dir` 直下の `.onnx` / `.pt` を走査し、`doctor._check_model_file` で integrity を判定する。catalog 未登録ファイルは `known: false` で表示する。
- `delete-installed-model` は `^[A-Za-z0-9._\-]+$` と `resolve().relative_to(model_dir)` で path traversal を二重防御する。存在しないファイルは `deleted: false` を返す冪等削除。
- frontend は右アサイドに「導入済みモデル」パネルを追加し、ファイル名 / サイズ / status / source_label と削除ボタンを表示する。削除後は `list-installed-models` と `doctor` を再読込する。

## 9. Export

Export は Python backend の責務。
Frontend は設定と job/cancel/status 表示を扱う。

現行で扱う設定:

- `resolution`: `source`, `720p`, `1080p`, `4k`
- `mosaic_strength`
- `audio_mode`: `mux_if_possible` (legacy), `video_only` (legacy), `copy_if_possible`, `encode`, `none` (→ `video_only` 正規化)。`copy_if_possible` は `-c:a copy`、`encode` は `-c:a aac -b:a 192k`、`mux_if_possible` は従来通り `-c:a aac`
- `bitrate_kbps`: `null` なら auto
- `bitrate_mode`: `auto` (解像度依存の preset) / `manual` (`bitrate_kbps` 指定必須) / `target_size` (`target_size_mb` 指定必須、`kbps = mb * 8192 / duration_sec`)
- `fps_mode`: `source` / `custom` (`fps_custom` (0<x≤240) 指定必須)。ffmpeg への `-r <output_fps>` で出力タイミングを書き換え
- `video_codec`: `h264` (libx264 / h264_nvenc/qsv/amf) / `vp9` (libvpx-vp9、GPU エンコーダなし)
- `container`: `auto` (出力拡張子から推論) / `mp4` / `mov` / `webm`。h264 は mp4/mov、vp9 は webm のみ互換 (`_resolve_codec_container` で command 層から validation)。音声コーデックはコンテナに従う (mp4/mov → aac、webm → libopus)
- `encoder`: `auto`, `gpu`, `cpu`

FFmpeg pipe export を優先し、失敗または unavailable の場合は OpenCV fallback を使う。
音声は `mux_if_possible` のとき ffmpeg で source audio を mux する。
GPU encoder は `auto` / `gpu` / `cpu` を扱う。
`auto` では `h264_nvenc` → `h264_qsv` → `h264_amf` を優先し、runtime failure 時は `libx264` へ再試行する。
エクスポート前には frontend 側で最新 project state を必ず保存する。
モザイク適用は `expand_px` と `feather` を export path で反映する。
`ellipse` 形状は `rotation` (度) を `cv2.ellipse(angle)` に渡して描画する。

### Export queue (2026-04-17)

- queue state は `user-data/export-queue/queue.json` に 1 ファイル配列で永続化される。
- CLI commands: `list-export-queue`, `enqueue-export`, `update-export-queue-item`, `remove-export-queue-item`, `clear-terminal-export-queue`.
- `queue_id` は `[A-Za-z0-9._-]{1,128}` のみ許可。
- `list-export-queue` は起動/再接続時に `running` を `interrupted` へ coerce し、`recovered_interrupted` 件数を返す。
- 実行 drive loop は frontend 側に置く。queue item を 1 件ずつ `queued → running → completed/failed` と遷移させ、`export-video` はその transition 内から呼び出す。

### Export preset

- preset は `user-data/presets/{name}.json` に 1 ファイル 1 preset で保存される (`name` は `[A-Za-z0-9 ._-]{1,128}`)。
- CLI commands: `list-export-presets`, `save-export-preset`, `delete-export-preset`.
- `export-video` 自体の受け入れフィールドは既存通り (`mosaic_strength` / `audio_mode` / `resolution` / `bitrate_kbps` / `encoder`)。video codec / container / fps / quality 詳細 (M-B03) は未対応。

### Recovery snapshots (2026-04-17)

- snapshot は `user-data/recovery/{snapshot_id}.json` に保存される (`snapshot_id` は `[A-Za-z0-9._-]{1,128}`)。
- CLI commands: `save-recovery-snapshot`, `list-recovery-snapshots`, `delete-recovery-snapshot`.
- レコードは `{ id, project, read_model, timestamp, confirmed_danger_frames }`。壊れた JSON は `list-recovery-snapshots` の `broken[]` に隔離される。
- confirmed danger frames (書き出し前レビュー済みフレームのキー) は snapshot 側に保存する方針。project ファイルには載せない。

### Detect settings persistence (2026-04-17)

- detect 設定 (`backend` / `device` / `confidence_threshold` / `sample_every` / `max_samples` / `inference_resolution` / `batch_size` / `contour_mode` / `precise_face_contour` / `vram_saving_mode` / `selected_categories`) は `user-data/config/detect-settings.json` に単一オブジェクトとして永続化される。
- CLI commands: `load-detect-settings`, `save-detect-settings`。
- `save-detect-settings` は型のみ検証し、enum 値自体は検証しない。未知のフィールドは破棄、型が合わないフィールドも無視 (silent drop)。
- `load-detect-settings` は壊れた JSON を `broken: true, settings: null` として返す (success レスポンス)。
- frontend は mount 時に `load-detect-settings` を呼び、取得した値で state を hydrate。以後は detect 関連 state が変化すると 800ms debounce で `save-detect-settings` を呼ぶ。
- 永続化された設定が存在する場合は doctor ベースの device/batch 既定値をスキップし、ユーザー設定を優先する。

### Danger warning flow (export 前)

`window.confirm` は使わない。未確認の danger frame が残っている場合のみ 3 択 modal を開く:

1. **詳細を確認 (書き出し中断)** — 最初の danger frame へ seek して書き出しをキャンセル。
2. **そのまま書き出し (全件確認済み)** — 対象フレームを `confirmedDangerFrames` に追加して export へ進む。
3. **キャンセル** — 何もしない。

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

- persistent workflow completion — **完了 (2026-04-17)**
  - file-backed recovery は `user-data/recovery/{id}.json` に移行、backend に `save/list/delete-recovery-snapshot` command あり
  - export 前 danger modal (詳細確認 / 書き出し / キャンセル) で `window.confirm` を置換
  - confirmed danger frames は recovery snapshot に保存 (project 本体は汚染しない)
- export workflow completion — **部分完了 (2026-04-17)**
  - multi-job export queue: `user-data/export-queue/queue.json` + frontend drive loop
  - queue persistence / `running → interrupted` 復元 + `再実行` 導線
  - user-defined export preset: `user-data/presets/{name}.json`、Export Settings Modal の preset セレクタ
  - **残**: M-B03 (video codec / container / fps / quality 詳細)
- regression prevention — **部分完了 (2026-04-17)**
  - export output の複数フレーム差分検証 (M-E03)
  - recovery の再起動シナリオ backend 検証 (M-E02 backend 部分)
  - **残**: M-E01 Tauri 実ウィンドウ E2E (tauri-driver / playwright 導入が必要)
- editing UX completion — **全項目完了 (M-C01〜M-C10)。目視レビュー待ち**
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
