# 初回 Contract Freeze

この文書は Phase 5 の最小で安全な初手です。Tauri 側 React UI にはまだ入らず、PySide6 正本から Tauri backend test へ移すための contract を固定します。

作成時点では Tauri 側コードを変更せず、次の code diff に直結する contract と fixture を `docs/tauri-migration/` 配下へ残した。その後、実装フェーズとして `H:\mosicprogect\taurimozaic` 側に PySide6 project v1 migration adapter と専用 backend test を追加した。`taurimozaic` は writable root 外だったため、コード変更とテスト実行は承認付きで行った。

## 0.1 実装反映状況

反映済み:

- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\domain\project.py`
  - PySide6 project v1 payload を検出する `_is_pyside6_project_v1_payload()` を追加した。
  - `project_version/source_video_path/video_meta/mask_tracks/export_preset` を Tauri `schema_version=2` の `ProjectDocument` payload に変換する migration helper を追加した。
  - `Keyframe.source` は `auto/re-detected -> detector + detector_accepted`、`anchor_fallback -> detector + detector_anchored`、`manual -> manual` に変換する。
  - PySide6 `user_locked` または manual keyframe がある track は `user_edited=True` / `source=manual` に寄せ、後続 AI 検出の `replace_detector_tracks()` で置換されないようにした。
  - Tauri native の `user_locked=True` detector track も `replace_detector_tracks()` で置換されないよう、`is_detection_replaceable()` に `not self.user_locked` を追加した。
  - PySide6 track lifetime は `_pyside6_lifetime` として `style` に保持する。
  - PySide6 の通常検出範囲は `confirmed` または `detected` segment にし、`last_tracked_frame > end_frame` は `predicted` segment として分離する。
- `H:\mosicprogect\taurimozaic\apps\backend\tests\test_pyside6_project_migration.py`
  - PySide6 project v1 payload の schema v2 migration、display URL 拒否、`user_locked` track の AI 検出置換保護、未編集 detector track の置換可能性、predicted tail segment、source_detail mapping をテストした。
- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\api\commands\__init__.py`
  - command package を lazy import 化した。`load_project` のような軽量 command import が `export_video` / `detect_video` の `cv2` 依存に巻き込まれないようにした。
- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\api\cli_main.py`
  - CLI の command loading を requested command のみ import する形へ変更した。`load-project` 実行時に全 command を読み込んで `detect_video -> cv2` に落ちる問題を避けるため。

検証済み:

- `python -m pytest apps/backend/tests/test_pyside6_project_migration.py`
  - 8 passed
- `python -m pytest apps/backend/tests/test_domain_track.py apps/backend/tests/test_pyside6_project_migration.py`
  - 37 passed
- `python -m py_compile apps/backend/src/auto_mosaic/api/cli_main.py apps/backend/src/auto_mosaic/api/commands/__init__.py apps/backend/src/auto_mosaic/domain/project.py apps/backend/tests/test_pyside6_project_migration.py`
  - passed
- `python -m auto_mosaic.api.cli_main load-project`
  - PySide6 project v1 の BOM なし最小 JSON を入力し、`cv2` が無い system Python でも schema v2 migration と JSON response が成功することを確認した。
- `git diff --check -- apps/backend/src/auto_mosaic/api/cli_main.py apps/backend/src/auto_mosaic/api/commands/__init__.py apps/backend/src/auto_mosaic/domain/project.py apps/backend/tests/test_pyside6_project_migration.py`
  - whitespace error なし。Git の CRLF warning のみ。

未検証:

- `test_source_detail.py` は現在使われた Python 3.14 環境に `numpy` が無いため collection で停止した。これは今回の差分の assertion failure ではない。
- `test_cli_smoke.py` は現在使われた Python 3.14 環境に `cv2` が無いため、今回の環境では実行していない。

## 1. 根拠ファイル

### PySide6 側の根拠

- `mosic2/app/domain/models/project.py`
- `mosic2/app/domain/models/mask_track.py`
- `mosic2/app/domain/models/keyframe.py`
- `mosic2/app/domain/models/video_meta.py`
- `mosic2/app/infra/storage/project_store.py`

確認済み:

- PySide6 の `ProjectStore.save()` は `Project.to_dict()` を UTF-8 JSON として保存する。
- top-level は `project_version`, `project_id`, `source_video_path`, `video_meta`, `mask_tracks`, `export_preset` である。
- `Keyframe.source` は `auto`, `manual`, `interpolated`, `predicted`, `re-detected`, `anchor_fallback` を取りうる。
- `MaskTrack.source` は `auto`, `user-adjusted`, `re-detected` を取りうる。

### Tauri 側の根拠

- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\domain\project.py`
- `H:\mosicprogect\taurimozaic\apps\desktop\src\types.ts`
- `H:\mosicprogect\taurimozaic\apps\desktop\src\jobProgress.ts`
- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\infra\ai\detect_jobs.py`
- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\infra\video\export_jobs.py`
- `H:\mosicprogect\taurimozaic\apps\backend\src\auto_mosaic\infra\runtime_jobs.py`

確認済み:

- Tauri backend の `ProjectDocument` は `schema_version = 2` を現行 schema として扱う。
- Tauri backend の legacy migration は `schema_version < 2` を処理するが、現状の入力キーは `tracks`, `video`, `name` を前提としており、PySide6 の `mask_tracks`, `video_meta`, `source_video_path` を直接変換しない。
- したがって PySide6 project v1 JSON は、現行 Tauri backend にそのまま渡すべきではない。adapter / migration layer が必要である。

## 2. 最小 fixture

次の fixture を追加した。

- `docs/tauri-migration/fixtures/pyside6-project-v1-minimal.json`

目的:

- PySide6 `ProjectStore.save()` 由来の JSON 形状を後続の Tauri backend test に渡す。
- `source_video_path`, `video_meta`, `mask_tracks`, `export_preset` の変換漏れを検出する。
- auto keyframe と manual keyframe が同じ track にある場合の `user_locked` / manual protection を検証する。

注意:

- fixture の `bbox` は normalized `[x, y, w, h]` として置いている。ただし座標系の最終 contract は renderer / canvas 側の再確認が必要であり、ここでは migration test 用の最小形状に限定する。
- 実動画ファイル `C:\video\sample.mp4` は存在を要求しない。path validation が raw Windows path を受けるかを見るための値である。

## 3. Project mapping

| PySide6 v1 | Tauri v2 | 初期方針 | 状態 |
| --- | --- | --- | --- |
| `project_version` | `schema_version` | `project_version == 1` を PySide6 v1 として検出し、Tauri `schema_version = 2` に変換する | 実装必要 |
| `project_id` | `project_id` | そのまま保持する | 実装必要 |
| なし | `version` | Tauri の `CURRENT_PROJECT_VERSION` か migration 固定値を入れる | 未定 |
| なし | `name` | project path があれば stem、なければ `project_id` 由来の仮名を入れる | 未定 |
| なし | `project_path` | 読み込み元 file path がある場合のみ設定する | 未定 |
| `source_video_path` | `video.source_path` | raw local path として移す。`asset.localhost` 等は拒否する | 実装必要 |
| `video_meta.width` | `video.width` | そのまま保持する | 実装必要 |
| `video_meta.height` | `video.height` | そのまま保持する | 実装必要 |
| `video_meta.fps` | `video.fps` | そのまま保持する | 実装必要 |
| `video_meta.frame_count` | `video.frame_count` | そのまま保持する | 実装必要 |
| `video_meta.duration_sec` | `video.duration_sec` | そのまま保持する | 実装必要 |
| なし | `video.readable` | migration 時点では `true` を仮置きするか、probe 結果で再評価する | 未定 |
| なし | `video.warnings` / `errors` | migration warning を入れられるようにする | 未定 |
| なし | `video.first_frame_shape` | `null` | 実装必要 |
| `mask_tracks` | `tracks` | track adapter で変換する | 実装必要 |
| `export_preset` | `export_preset` | Tauri の `normalize_export_preset()` に合わせるが、落ちる field は warning にする | 実装必要 |
| なし | `detector_config` | `{}` | 実装必要 |
| なし | `paths` | `{}` または project path 由来 | 未定 |

## 4. MaskTrack mapping

| PySide6 v1 | Tauri v2 | 初期方針 | 状態 |
| --- | --- | --- | --- |
| `track_id` | `track_id` | そのまま保持する | 実装必要 |
| `label` | `label` | そのまま保持する | 実装必要 |
| `start_frame` / `end_frame` | `segments` または read model 派生 | explicit `segments` を生成するかは未定。何も生成しないと Tauri は keyframe 範囲から render span を合成するため、PySide6 の track lifetime とズレうる | 未定 |
| `visible` | `visible` | そのまま保持する | 実装必要 |
| `style` | `style` | そのまま保持する | 実装必要 |
| `keyframes` | `keyframes` | keyframe adapter で変換する | 実装必要 |
| `state` (`active/lost/inactive`) | `state` | 文字列として保持可能だが UI 表示意味は要確認 | 未定 |
| `source` (`auto/user-adjusted/re-detected`) | `source` | `auto/re-detected -> detector`, `user-adjusted -> manual` が候補。ただし final ではない | 未定 |
| `last_detected_frame` | なし | warning 付きで drop、または debug metadata に逃がす | 未定 |
| `last_tracked_frame` | `segments` 候補 | predicted tail に関わるため drop 禁止。segment 生成ルールが必要 | 未定 |
| `missing_frame_count` | なし | warning 付きで drop 候補 | 未定 |
| `confidence` | `confidence` | そのまま保持する | 実装必要 |
| `user_locked` | `user_locked` | そのまま保持する | 実装必要 |
| `motion_history` | なし | warning 付きで drop 候補 | 未定 |
| `association_history` | なし | warning 付きで drop 候補 | 未定 |

## 5. Keyframe mapping

| PySide6 v1 | Tauri v2 | 初期方針 | 状態 |
| --- | --- | --- | --- |
| `frame_index` | `frame_index` | そのまま保持する | 実装必要 |
| `shape_type` | `shape_type` | `ellipse` / `polygon` を保持する | 実装必要 |
| `points` | `points` | そのまま保持する | 実装必要 |
| `bbox` | `bbox` | そのまま保持する | 実装必要 |
| `confidence` | `confidence` | そのまま保持する | 実装必要 |
| `source=manual` | `source=manual`, `is_locked=true` 候補 | manual protection のため lock 付与候補。ただし Tauri 既存 UI の編集仕様と要確認 | 未定 |
| `source=auto` | `source=detector`, `source_detail=detector_accepted` 候補 | Tauri 既存 detector 由来と同じ扱いにする案。ただし PySide6 由来であることを保持すべきか未定 | 未定 |
| `source=re-detected` | `source=detector`, `source_detail` 候補 | `detector_accepted` だけでは re-detected 情報を失う。別 detail が必要か未定 | 未定 |
| `source=anchor_fallback` | `source=detector` または `source=manual` 以外 | anchor fallback の render/edit 意味が重い。即決禁止 | 未定 |
| `source=interpolated/predicted` | stored keyframe として保持するか未定 | Tauri 側では segment/resolver で表現する可能性が高い。実 keyframe として保存するか gate にする | 未定 |
| `contour_points` | `contour_points` | そのまま保持する | 実装必要 |
| `rotation` | `rotation` | そのまま保持する | 実装必要 |
| `opacity` | `opacity` | そのまま保持する | 実装必要 |
| `expand_px` | `expand_px` | そのまま保持する | 実装必要 |
| `feather` | `feather` | そのまま保持する | 実装必要 |

## 6. Job status contract

Tauri UI 表示用の最小 normalized state は次とする。

```text
queued | starting | running | cancelling | cancelled | completed | failed
```

現行対応:

| 種別 | backend 値 | UI normalized | 根拠 |
| --- | --- | --- | --- |
| runtime | `queued/starting/running/cancelling` | 同じ | `runtime_jobs.py`, `types.ts` |
| runtime | `cancelled/completed/failed` | 同じ | `runtime_jobs.py`, `types.ts` |
| detect | `queued/running` | 同じ | `detect_jobs.py`, `jobProgress.ts` |
| detect | `succeeded` | `completed` | `jobProgress.ts` |
| detect | `cancelled` | `cancelled` | `detect_jobs.py`, `jobProgress.ts` |
| detect | `interrupted` | `failed` | `jobProgress.ts` |
| detect | `idle` | `queued` | `jobProgress.ts` |
| export | `phase=completed` | `completed` | `jobProgress.ts` |
| export | `phase=cancelled` | `cancelled` | `jobProgress.ts` |
| export | `phase=failed` | `failed` | `jobProgress.ts` |
| export | その他 phase | `running` または `cancelling` | `jobProgress.ts` |

未決定:

- detect job の `starting` が backend 実体として存在しない場合、UI が期待する `starting` をどう扱うか。
- detect `interrupted` を常に `failed` 扱いでよいか。cancel flag 由来なら user-facing には `cancelled` に近い場合がある。
- export job は phase と state が分離していないため、queue item state と status phase の統合規則が必要。

## 7. Runtime / doctor contract

初期 gate:

- `run_backend_command` から Python backend を起動する時、backend root、data dir、model dir、UTF-8、review-runtime path が明示されること。
- backend doctor は少なくとも writable dirs、ffmpeg、ffprobe、required model、ONNX Runtime、CUDA session test、EraX state を返すこと。
- doctor の `ready` は「UI が起動した」ではなく「最低限の runtime が使える」判定にする。
- model / ffmpeg / CUDA 不足は failure ではなく structured warning / error として UI が説明できる形にする。

未決定:

- PySide6 の `data/config/gpu_config.json` と Tauri 側 detector config の移行要否。
- PySide6 の `models/320n.onnx`, `erax_v1_1.pt`, `sam2_tiny_*` と Tauri 側 model registry の名前差分。

## 8. 後続 Tauri backend test 候補

Tauri repo に書き込める状態になったら、最初に次を追加する。

候補ファイル:

- `apps/backend/tests/test_pyside6_project_migration.py`

test 1:

- 入力: `docs/tauri-migration/fixtures/pyside6-project-v1-minimal.json` 相当の payload。
- 期待: `ProjectDocument.from_payload()` へ直接渡す前に migration adapter が `schema_version=2` の payload に変換する。
- 期待: `project_id`, `video.source_path`, `video.width/height/fps/frame_count/duration_sec`, `tracks[0].track_id`, `tracks[0].keyframes` が保持される。
- 期待: `source_video_path` が `asset.localhost` なら `SOURCE_VIDEO_PATH_INVALID` 相当で拒否される。

test 2:

- 入力: `source=manual` の keyframe を含む track。
- 期待: manual keyframe が detector replace で失われない。
- 期待: `user_edited` または `user_locked` の扱いが明示される。

test 3:

- 入力: `last_tracked_frame > end_frame` の PySide6 track。
- 期待: predicted tail を drop する場合は warning が出る。segment 化する場合は render span が明示される。

実行候補:

```powershell
$env:PYTHONPATH='apps/backend/src'
python -m pytest apps/backend/tests/test_pyside6_project_migration.py
```

## 9. 後続 frontend test 候補

候補ファイル:

- `apps/desktop/src/jobProgress.test.ts`

追加観点:

- detect `succeeded -> completed`。
- detect `interrupted -> failed`。ただし cancel flag 由来の扱いは未定として test name に残す。
- export `preparing/rendering_frames/muxing_audio -> running`。
- export cancelling flag がある場合は `cancelling`。
- runtime `queued/starting/running/cancelling/cancelled/completed/failed` がそのまま出る。

実行候補:

```powershell
npm.cmd run test --workspace apps/desktop -- jobProgress
```

## 10. Acceptance criteria

この初回 contract freeze を次に進めてよい条件:

- PySide6 v1 と Tauri v2 の top-level field 差分が説明されている。
- PySide6 `mask_tracks` が Tauri `tracks` に自動では入らないことが明記されている。
- source / source_detail / segment state の未定箇所が未定として残っている。
- job status の normalized vocabulary が固定されている。
- runtime / doctor を初期 gate として扱う方針が明記されている。
- 次に追加すべき Tauri backend test file と test command が明記されている。

## 11. この段階で完了と呼ばないこと

- Tauri backend で PySide6 project v1 が読めるとはまだ言わない。
- Tauri UI の移植に着手済みとは言わない。
- export parity が取れたとは言わない。
- GPU / model / ffmpeg / review-runtime が検証済みとは言わない。

ここで完了したのは、次の安全な code diff を backend migration test に絞るための初期 contract freeze である。
