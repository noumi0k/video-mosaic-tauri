# PySide6 構成と Tauri 構成の比較

この文書は、`mosic2/` の現行 PySide6 実装と、`H:\mosicprogect\taurimozaic` の既存 Tauri 実装を比較します。

重要な前提として、移行元仕様の根拠は `mosic2/` 側です。Tauri 側に似た機能があっても、ここでは「移行先の現在実装」として比較し、PySide6 側の仕様確定には使いません。

## 調査対象

### PySide6 側

- `mosic2/app/`
- `mosic2/scripts/`
- `mosic2/tests/`
- `mosic2/README.md`
- `mosic2/CLAUDE.md`
- `mosic2/pyside6_remaining_tasks.md`
- `mosic2/docs/`

### Tauri 側

- `H:\mosicprogect\taurimozaic\AGENTS.md`
- `H:\mosicprogect\taurimozaic\CLAUDE.md`
- `H:\mosicprogect\taurimozaic\AI_HANDOFF.md`
- `H:\mosicprogect\taurimozaic\unimplemented-features.md`
- `H:\mosicprogect\taurimozaic\tauri_auto_mosaic_detailed_requirements_spec_v2_1.md`
- `H:\mosicprogect\taurimozaic\ai_agent_from_scratch_tauri_spec.md`
- `H:\mosicprogect\taurimozaic\apps/backend/`
- `H:\mosicprogect\taurimozaic\apps/desktop/`
- `H:\mosicprogect\taurimozaic\apps/user-data/`
- `H:\mosicprogect\taurimozaic\apps/desktop/src-tauri/`
- `H:\mosicprogect\taurimozaic\scripts/prepare-review-runtime.ps1`
- `H:\mosicprogect\taurimozaic\docs/`

補足: `H:\mosicprogect\mosic2-tauri` にも Tauri shell POC と PySide6 系コードが存在します。ただし、ユーザー指定の `apps/backend`, `apps/desktop`, `apps/user-data`, `apps/desktop/src-tauri` 構成と一致する主対象は `H:\mosicprogect\taurimozaic` です。比較の主対象は `taurimozaic` に限定します。

## 1. 現行 PySide6 構成の特徴

PySide6 側は単一 Python アプリとしてまとまっています。

- `app/main.py` -> `app/bootstrap.py` -> `MainWindow`
- UI は `app/ui/` の PySide6 コードで構築
- 長時間処理は `DetectionWorker` / `ExportWorker` の `QThread`
- domain/service/infra は `app/domain`, `app/infra`, `app/application/runtime_services.py` に分離
- project 保存は `Project.to_dict()` / `ProjectStore` の JSON
- runtime path は `AppPaths.resolve()` が `project_root/data`, `models`, env override を解決
- setup は `setup.bat`, `setup.sh`, `run_ui.bat`, `scripts/setup_dev.py`, `scripts/install_deps.py`

実プロジェクト上の意味:

PySide6 側は「同一 Python process 内で GUI と backend service が動く」ため、`MainWindow` が domain object を直接持ち、service を直接呼び、history commit と UI 同期を即時に行えます。これは開発速度では有利ですが、Tauri にすると process 境界、JSON 境界、job 境界、path 境界が現れます。

## 2. Tauri 構成の特徴

Tauri 側は `taurimozaic` monorepo です。

- Frontend: `apps/desktop`
  - React 19、TypeScript、Vite
  - `App.tsx` が editor shell、project open/save、preview、selection、job polling を持つ
  - `CanvasStagePanel.tsx`, `TimelineView.tsx`, `TrackDetailPanel.tsx`, `KeyframeDetailPanel.tsx`, `JobPanel.tsx`, `DetectorSettingsModal.tsx`
- Rust shell: `apps/desktop/src-tauri`
  - `src/lib.rs` に `run_backend_command` Tauri command
  - Python subprocess を起動し、stdin JSON、stdout JSON を扱う
  - asset protocol 有効、dialog plugin 有効
  - `resources/review-runtime` を bundle resource として持つ
- Backend: `apps/backend`
  - `auto_mosaic.api.cli_main` が JSON CLI entry point
  - `auto_mosaic.domain.project` が `ProjectDocument`, `MaskTrack`, `Keyframe`, `MaskSegment`
  - `auto_mosaic.domain.mask_continuity` が continuity / write decision / render/edit resolver
  - `auto_mosaic.infra.ai.detect_video` が ONNX/OpenCV detection
  - `auto_mosaic.infra.video.export` が export
  - `runtime.paths` が `user-data`, `models` を解決
- User data: `apps/user-data`
  - dev default の runtime data。`temp/export-jobs` などが存在
- Review runtime:
  - `scripts/prepare-review-runtime.ps1`
  - `apps/desktop/src-tauri/resources/review-runtime`
  - Python、backend、vendor、models、ffmpeg を stage

実プロジェクト上の意味:

Tauri 側はすでに「subprocess + CLI + JSON I/O」「stdout JSON-only」「job status polling」を軸にしています。これは移行先として正しい方向ですが、現行 PySide6 の保存形式や編集 semantics と完全一致しているわけではありません。

## 3. 両者の責務分離の違い

| 観点 | PySide6 | Tauri |
|---|---|---|
| UI と backend の境界 | 同一 Python process 内の service 呼び出し | Tauri command -> Rust -> Python subprocess -> CLI JSON |
| UI 状態 | `MainWindow` が強く保持 | `App.tsx` が React state と polling state を保持 |
| domain 正本 | Python domain object | Python backend project document |
| 表示 projection | `EditorDisplayService`, `RenderService.resolve_tracks()` | backend `ProjectDocument.build_read_model()` と frontend helper |
| 長時間処理 | `QThread` + Qt signal | job id + status JSON + polling |
| path 解決 | `AppPaths.resolve()` | Rust `resolve_runtime_context()` + Python `ensure_runtime_dirs()` |

実プロジェクト上の意味:

PySide6 では GUI coordinator が domain object を直接更新できるため、境界が甘くても動きます。Tauri では command payload と保存 JSON が境界になります。したがって、`MainWindow` に埋まっている「どう merge するか」「いつ dirty にするか」「いつ history に積むか」をそのまま React に寄せると、backend 正本という Tauri 側の非交渉ルールと衝突します。

## 4. UI 実装の違い

### PySide6

- `PreviewCanvas` は `QGraphicsView` ベース
- `TimelineWidget` は Qt paint/event に依存
- `PropertyPanel`, `TrackListPanel` は Qt widget
- edit operation は signal を `MainWindow` が受けて domain service を呼ぶ
- 動画 preview は `CvVideoReader` で frame を読み、`RenderService` で mosaic preview を作り、canvas に表示

### Tauri

- 中央 preview は HTML `<video>` + overlay の `CanvasStagePanel`
- file display は `convertFileSrc()` による asset URL
- backend に渡す path は raw Windows path
- `CanvasStagePanel` は normalized bbox/points を DOM/SVG で直接編集
- `TimelineView` は segment bar と keyframe marker を React で描画
- `maskShapeResolver.ts` が frontend 側で backend `resolve_for_editing` を mirrored implementation として持つ

実プロジェクト上の意味:

Tauri の preview は「動画再生はブラウザの `<video>`、mask overlay は React」という構造です。PySide6 のように backend が毎フレームを読んで preview frame を描く構造とは違います。これは軽くて自然ですが、プレビューと export の完全一致を保証しにくいです。特に Tauri 側では `resolveForEditing` を TypeScript に写しているため、backend `resolve_for_editing` とズレるリスクがあります。

## 5. 配布 / packaging / runtime 同梱の違い

### PySide6

- 開発導線は `.venv` と `setup.bat` / `setup.sh`
- `run_ui.bat` が `.venv` 不在時に setup を呼ぶ
- `models/`, `data/`, `ffmpeg` は project root/env/PATH 前提
- packaging はまだ dev oriented と既存 docs に記載

### Tauri

- dev: `npm --workspace apps/desktop run tauri dev`
- build: `tauri build`
- review: `npm.cmd run review:runtime`, `review:portable`, `review:zip`
- `scripts/prepare-review-runtime.ps1` が Python、backend、vendor、models、ffmpeg を `resources/review-runtime` に stage
- ABI mismatch 対策として vendor の `cp3XX` ABI から Python minor を選ぶ
- packaged runtime は app data directory に `runtime-data` を作る

実プロジェクト上の意味:

Tauri 版は review package まで現実に進んでいます。一方で、正式 installer/updater/uninstaller ではなく review runtime stage が中心です。Python ABI、vendor packages、ffmpeg exe、model integrity は既に事故履歴があり、計画上の P0 リスクとして扱う必要があります。

## 6. backend 呼び出し方式の違い

### PySide6

`MainWindow` が service object を直接呼びます。

例:

- `runtime.detection_service`
- `runtime.tracking_service`
- `runtime.mask_edit_service`
- `runtime.continuity_service`
- `runtime.project_store`
- `runtime.export_service`

### Tauri

React は `invoke("run_backend_command", { command, payload })` を呼び、Rust が Python を次で起動します。

```text
python -m auto_mosaic.api.cli_main <command>
stdin: JSON payload
stdout: JSON response only
stderr: logs/diagnostics
```

`cli_main.py` は Python stdout を guard し、漏れた stdout を stderr に逃がす実装を持ちます。command response は `ok`, `command`, `data`, `error`, `warnings` の共通形式です。

実プロジェクト上の意味:

PySide6 の service 呼び出しは Python object を返せますが、Tauri は JSON だけです。`Project`, `MaskTrack`, `Keyframe` の型差分、source 値、segment 値、error code、warning まで契約化しないと、UI と backend が簡単にズレます。

## 7. ファイルアクセス / asset access の違い

### PySide6

UI、OpenCV、ffmpeg が同じ local path を直接扱います。

### Tauri

表示用には `convertFileSrc(sourcePath)` で asset URL に変換します。一方で backend へ渡すのは raw local Windows path です。

Tauri 側の明示ルール:

- `asset.localhost` は display-only
- persisted project data と backend payload は raw Windows path
- `pathUtils.ts` が asset URL を backend に送ることを防ぐ
- backend `validate_raw_video_source_path()` も asset URL / http / file URL を拒否

実プロジェクト上の意味:

PySide6 で暗黙に成立した「表示 path = 処理 path」は Tauri では成立しません。保存形式に asset URL が混入すると export/detect/load が壊れるため、ここは移行の高リスク境界です。

## 8. 進捗表示 / 非同期処理 / ジョブ制御の違い

### PySide6

- `DetectionWorker(QThread)` と `ExportWorker(QThread)`
- `ProgressDialog`
- Qt signal で progress/failed/canceled/succeeded を通知
- cancel は worker 内 callback

### Tauri

- runtime jobs: `start-runtime-job`, `get-runtime-job-status`, `get-runtime-job-result`, `cancel-runtime-job`
- detect jobs: `start-detect-job`, `get-detect-status`, `get-detect-result`, `cancel-detect-job`, `cleanup-detect-jobs`
- export: `export-video` を非同期に呼び、`get-export-status`, `cancel-export` で polling
- job state は `apps/user-data/temp/...` または app data runtime-data 配下に JSON file として保存
- `JobPanel` が runtime/detect/export を共通表示へ正規化

実プロジェクト上の意味:

Tauri 側は job 化の方向は良いですが、runtime/detect/export で state vocabulary が完全には揃っていません。detect は `succeeded/failed/cancelled/interrupted`、runtime は `completed/failed/cancelled`、export は `phase=completed/cancelled/failed` です。UI 側 `jobProgress.ts` が吸収していますが、契約としてはまだ不均一です。

## 9. GPU / Python / ONNX / ffmpeg 依存の扱いの違い

### PySide6

- `requirements.txt` に `nudenet`, `opencv-python`, `imageio-ffmpeg`
- optional `onnxruntime-gpu`
- `DeviceManager`, `GpuConfig`, `DepChecker`, `runtime/environment.py`
- ffmpeg は env/PATH/imageio-ffmpeg などから解決

### Tauri

- backend `pyproject.toml` は `opencv-python`, optional `onnxruntime-gpu[cuda,cudnn]==1.24.4`, `onnxruntime==1.24.4`, `torch`
- `doctor.py` は ffmpeg/ffprobe、model integrity、ONNX Runtime、CUDA session test、writable runtime path を返す
- `fetch_models.py` と `model_catalog.py` が model integrity を扱う
- `start_detect_job.py` は worker 起動前に model preflight を行う
- `prepare-review-runtime.ps1` が Python ABI と vendor ABI を検査

実プロジェクト上の意味:

Tauri 側はモデル破損、GitHub HTML redirect、Python ABI mismatch という具体的な事故をすでに踏んで対策しています。これは移行計画では強みですが、同時に「runtime packaging は難しい」という証拠でもあります。

## 10. 開発速度の観点での差

PySide6 は同一 process のため実装速度が速いです。domain object を直接触り、preview と export を同じ Python service で処理できます。

Tauri は境界が多く、初期実装は遅くなります。Rust command、Python CLI、TypeScript 型、React state、job polling、review runtime を同時に維持する必要があります。

ただし長期的には、backend contract が固まれば UI 改修は React 側で進めやすくなります。現状は contract がまだ完全に固まっていないため、短期的には PySide6 より複雑です。

## 11. 保守性の観点での差

PySide6 側は `MainWindow` が大きく、保守性の上限があります。特に detection merge と edit/history の意味が GUI coordinator に集中しています。

Tauri 側は `apps/backend/domain/project.py`, `domain/mask_continuity.py`, `api/commands/*`, `apps/desktop/src/types.ts` で契約を分けています。ただし `App.tsx` もまだ大きく、selection/job/save/detect/export を抱えています。frontend helper が backend logic を mirror している箇所もあり、二重実装の保守リスクがあります。

## 12. Windows 配布の観点での差

PySide6 側は `.venv` と setup script をユーザー環境に作る前提が強いです。配布物というより開発/運用環境に近いです。

Tauri 側は review package と `review-runtime` により、第三者 Windows PC へ渡す現実的な導線ができています。`AutoMosaic-Review/` を reviewer に渡す設計、`Launch Auto Mosaic Review.cmd`、`review-runtime/python/backend/models/ffmpeg` がある点は大きな前進です。

ただし正式 installer/updater/uninstaller は未完成です。Python ABI と vendor packages の整合、ffmpeg exe の同梱、models の取得/検証、app data cleanup、GPU/CUDA optional handling はまだ製品配布リスクです。

## 13. ユーザー体験上の差

PySide6 は native desktop widget で、preview frame と mask 描画を Python 側で密接に管理できます。現行ユーザーの操作感はこの実装に依存しています。

Tauri は NLE 風 layout、HTML video、React overlay、Job Panel、DetectorSettingsModal を持ちます。UI は review 可能な shell まで進んでおり、project open/save/detect/edit/export の導線もあります。

ただし Tauri の `<video>` overlay 方式は、モザイク済み preview ではなく「元動画 + mask overlay」です。PySide6 の `RenderService` preview と視覚的意味が異なる箇所があります。ユーザーにとっては「この見た目で export される」と思いやすいため、preview/export の意味を明確にする必要があります。

## 14. 移行で再利用できるもの / できないもの

### 再利用できるもの

- PySide6 側の domain 知識
  - `Project`, `MaskTrack`, `Keyframe`, `ExportPreset`
  - `MaskEditService`, `TrackingService`, `ContinuityService`, `RenderService`, `ExportService`
- PySide6 側の実装済みテスト観点
  - tracking、mask edit、continuity、export、runtime、dependency check
- runtime/doctor の観点
  - ffmpeg/ffprobe、model、GPU、writable dirs
- setup で得たモデル構成
  - `320n.onnx`, optional `640m.onnx`, EraX, SAM2 tiny
- Tauri 側の既存契約
  - `cli_main.py` JSON guard
  - `run_backend_command`
  - job polling
  - raw path vs asset URL guard
  - model integrity preflight

### そのまま再利用しにくいもの

- PySide6 UI widget
  - `PreviewCanvas`, `TimelineWidget`, `PropertyPanel`, `TrackListPanel`
- `QThread` worker と Qt signal
- `MainWindow` の orchestration をそのまま React へ移すこと
- PySide6 の project JSON を Tauri `ProjectDocument` と同一視すること
- PySide6 export preset の resolution/bitrate/GPU codec 設定
- PySide6 の `SourceType` と Tauri の `source="detector"` / `source_detail` の体系

## 15. Tauri 化によって楽になる点

- UI を Web 技術で分割、テストしやすくなる
- `JobPanel` のような共通 progress surface を作りやすい
- `doctor`, `fetch-models`, `setup` を GUI と分離しやすい
- backend CLI 単体テストが可能
- review runtime で第三者 PC に渡す導線を作りやすい
- `stdout` JSON-only ルールで UI/backend 境界の事故を検出しやすい

## 16. Tauri 化によって逆に難しくなる点

- Python object ではなく JSON schema を維持する必要がある
- frontend と backend の型二重管理が起きる
- preview の映像と export の render の一致保証が難しい
- long-running job の status/result/cancel/recovery を設計しないといけない
- raw path と asset URL を混ぜてはいけない
- packaged runtime の Python ABI、vendor、models、ffmpeg、app data を管理する必要がある
- `MainWindow` にあった暗黙 merge/edit/history logic を契約化する必要がある

## 17. 見落としがちな差分

### 保存 schema が違う

PySide6 側は `project_version: int` を持つ `Project` です。Tauri 側は `version: str`, `schema_version: int`, `ProjectDocument`, `ProjectPaths`, `MaskSegment` を持ちます。互換 migration を設計せずに同じ JSON と扱うと壊れます。

### keyframe source が違う

PySide6 側:

- `auto`
- `manual`
- `interpolated`
- `predicted`
- `re-detected`
- `anchor_fallback`

Tauri 側:

- 主に `detector`
- `manual`
- `source_detail=detector_accepted/detector_anchored`
- segment state で `held/uncertain/interpolated/predicted/confirmed` など

これは同じ意味ではありません。移行計画では mapping が必要です。

### export の render 範囲が違う

PySide6 側は `MaskEditService.resolve_keyframe()` が範囲外 hold を返すため、export 側でどこまで適用するかは `RenderService.resolve_tracks()` と `frame_display_state()` の組み合わせです。

Tauri 側は `resolve_for_render()` が `track.frame_is_renderable(frame_idx)` を gate にし、renderable segment 外では None を返します。editing 用 `resolve_for_editing()` は segment gate を外します。

これは明示的で良い設計ですが、PySide6 の現在挙動を完全再現しているとは限りません。

### job state vocabulary が違う

PySide6 は Qt signal の状態語彙です。Tauri は runtime/detect/export ごとに state/phase が違います。UI helper で吸収していますが、backend contract としてはまだ統一が弱いです。

### detector label/category が違う

PySide6 側の label schema は NudeNet 由来 label と category grouping を持ちます。Tauri 側は product-facing category を `male_genitalia`, `female_genitalia`, `intercourse`, `male_face`, `female_face` に整理しています。仕様としてよい方向ですが、移行時に既存 project の label をどう読むかが未固定です。

### export 機能差

PySide6 側は container、resolution、bitrate、GPU toggle、ffmpeg rawvideo pipe、audio mux fallback、queue dialog を持ちます。Tauri 側の現在 export は mp4 save dialog、mosaic_strength、audio_mode、OpenCV writer、ffmpeg mux が中心です。機能 parity はまだ不足しています。

### setup/doctor の成熟方向が違う

PySide6 側は dependency dialog と setup script で修復します。Tauri 側は doctor/model integrity/review runtime ABI check が強いです。この差分は Tauri に寄せるべきですが、PySide6 側の `DepChecker` 観点を落としてはいけません。

## 移行コストが高い箇所

1. project schema migration
   - PySide6 `Project` と Tauri `ProjectDocument` の形が違うため。
2. mask/track/keyframe source mapping
   - `auto/re-detected/anchor_fallback/predicted` と `detector/source_detail/segments` の意味が違うため。
3. detection merge
   - PySide6 の `MainWindow.apply_range_detection_results()` と manual preservation は GUI 側に強くあるため。
4. preview/export consistency
   - HTML video overlay と backend rendered export の意味が違うため。
5. export parity
   - Tauri 側 export は現時点で PySide6 より機能が狭いため。
6. runtime packaging
   - Python ABI/vendor/ONNX/ffmpeg/models の組み合わせが壊れやすいため。

## 総合評価

Tauri 側は単なる scratch ではなく、すでに `subprocess + CLI + JSON I/O`、backend authoritative state、job polling、model integrity、review runtime まで進んだ実装です。方向性は正しいです。

ただし PySide6 側の現在仕様を完全に移し終えた状態ではありません。特に project schema、source/segment semantics、export parity、range detection merge、history/undo、runtime packaging の差分は重いです。

移行計画では、React UI の見た目を先に寄せるよりも、まず backend contract、schema migration、job state、render/edit resolver、runtime doctor を固定するべきです。
