# 現行 PySide6 実装の構成理解

対象は `モザイク2` ディレクトリ、実体パスでは `mosic2/` 配下の現行 PySide6 実装です。Tauri 側に同名機能が存在していても、この文書では移行元仕様の判定に使っていません。

## 調査範囲と根拠

### 確認した優先資料

- `CLAUDE.md`
- `unimplemented-features.md`
- `README.md`
- `pyside6_remaining_tasks.md`
- `MASK_SPEC.md`
- `persistent_mask_track_requirements.md`
- `docs/00_overview/00_start-here.md`
- `docs/00_overview/01_document-map.md`
- `docs/01_requirements/01_core-product-requirements.md`
- `docs/01_requirements/02_mask-track-requirements.md`
- `docs/02_design/01_architecture-and-ui.md`
- `docs/99_archive/tauri_migration_backend_plan.md`
- `requirements.txt`
- `pyproject.toml`
- `app/` 配下の Python 実装
- `scripts/` 配下の setup/bootstrap 実装
- `tests/` 配下のテスト構成

### 確認できなかった資料

- `AGENTS.md` は `mosic2/` 直下に存在しませんでした。
- `AI_HANDOFF.md` は `mosic2/` 直下に存在しませんでした。
- `未実装機能一覧.md` は `mosic2/` 直下に存在しませんでした。

### 履歴資料として扱うもの

- `unimplemented-features.md` は先頭で `[廃止済み - 参照専用]` と明記されており、現在の PySide6 残タスクの正本ではありません。現在タスクは `pyside6_remaining_tasks.md` を優先します。
- `docs/99_archive/tauri_migration_backend_plan.md` は Tauri 移行の履歴資料として有用ですが、現行 PySide6 の仕様確定根拠としては扱いません。

## 1. システム全体像

現行アプリは Python 3.11 以上を前提にした PySide6 デスクトップアプリです。ユーザーは動画を読み込み、AI 検出結果を候補として使い、マスクトラック、タイムライン、キーフレーム、プロパティ編集で最終的なモザイク適用範囲を調整し、動画を書き出します。

確認済みの構成は次の通りです。

- GUI: `app/ui/` の PySide6 実装
- アプリ起動と runtime 組み立て: `app/main.py`, `app/bootstrap.py`, `app/application/runtime_services.py`
- domain model: `app/domain/models/`
- domain service: `app/domain/services/`
- AI / device / video / storage infra: `app/infra/`
- 設定と runtime パス: `app/config.py`, `app/gpu_config.py`, `app/runtime/paths.py`, `app/runtime/environment.py`
- setup / doctor: `setup.bat`, `setup.sh`, `run_ui.bat`, `scripts/setup_dev.py`, `scripts/install_deps.py`, `app/dep_checker.py`, `app/startup_checks.py`
- テスト: `tests/`

`docs/02_design/01_architecture-and-ui.md` は責務境界として、`ui` から `application/domain/infra/config/runtime` への依存は許容し、`application` から `ui` への依存は禁止、`infra` から `ui/application` への依存は禁止、`domain` から `ui/application` への依存は禁止としています。`tests/test_architecture_boundaries.py` がこの境界を検査します。

ただし同ドキュメント自体が、`domain/services` に一部 infra 実装への直接依存が残っていること、`MainWindow` が PySide6 中心の interaction を多く持つこと、packaging はまだ開発運用寄りであることを制約として挙げています。ここは移行時の重要な地雷です。

## 2. 主要ディレクトリ / 主要ファイルの役割

### ルート直下

- `README.md`
  - ユーザー向けセットアップ、実行方法、依存、モデル配置、export 機能の説明。
- `CLAUDE.md`
  - アーキテクチャ、開発コマンド、実装上の注意、現在の設計方針。
- `pyside6_remaining_tasks.md`
  - 現行 PySide6 実装の残タスクと実装済み範囲。現在の残作業把握ではこれを優先。
- `unimplemented-features.md`
  - 廃止済みの Tauri 移行メモ。参照専用。
- `MASK_SPEC.md`
  - マスク、トラッキング、輪郭、ラベルの仕様メモ。現在コードと数値差分がありうるため、実装値はコード優先。
- `persistent_mask_track_requirements.md`
  - 永続マスクトラックの要求メモ。現行思想の把握に有用だが、現在挙動の確定はコードで確認する必要があります。
- `requirements.txt`, `pyproject.toml`
  - Python 依存定義。PySide6、OpenCV、numpy、imageio-ffmpeg、NudeNet、pytest が主依存。GPU は optional dependency として `onnxruntime-gpu`。
- `setup.bat`, `setup.sh`, `run_ui.bat`
  - ユーザー向けセットアップと起動導線。

### `app/`

- `app/main.py`
  - `app.bootstrap.run()` を呼ぶ薄い entry point。ユーザー向け実行は `python -m app.main` または `run_ui.bat`。
- `app/bootstrap.py`
  - `AppConfig` 読み込み、logging 初期化、`QApplication` 作成、theme 適用、依存チェック、runtime services 構築、`MainWindow` 作成、Qt event loop 開始。
- `app/application/runtime_services.py`
  - `RuntimeServices` を組み立てる composition root。device、project store、ffprobe、detector、detection、contour、tracking、mask edit、continuity、project edit、render、export、history を束ねる。
- `app/config.py`
  - `AppConfig`。モデルパス、ffmpeg/ffprobe パス、data/temp/export/log/config ディレクトリ、GPU 設定などを解決。
- `app/gpu_config.py`
  - GPU / detector / contour / label category / batch / resolution 設定。`data/config/gpu_config.json` を主設定として扱い、legacy の `data/gpu_config.json` も読む。
- `app/cli.py`
  - `run-ui`, `check-env`, `paths` の CLI。Tauri 向けの汎用 backend command API ではまだありません。

### `app/domain/models/`

- `project.py`
  - `Project` と `ExportPreset`。保存形式の中心。`project_version=1`、`source_video_path`、`video_meta`、`mask_tracks`、`export_preset` を持つ。
- `mask_track.py`
  - `MaskTrack`、`MaskStyle`、track state/source、frame display state。`active/lost/inactive`、`auto/user-adjusted/re-detected`、`visible`、`user_locked`、`motion_history`、`association_history` を持つ。
- `keyframe.py`
  - `Keyframe`。ellipse/polygon、bbox、points、contour_points、confidence、source、rotation、opacity、expand_px、feather を持つ。source は `auto/manual/interpolated/predicted/re-detected/anchor_fallback`。
- `export_job.py`
  - export queue 用の `ExportJob` と status。`Project.snapshot()` を保持する。
- `detection.py`
  - `Detection` と `DetectionResult`。
- `video_meta.py`
  - 動画メタ情報。
- `label_schema.py`
  - ラベル正規化、label category、default enabled category。

### `app/domain/services/`

- `detection_service.py`
  - detector と `CvVideoReader` を使い、サンプルフレーム検出と単一フレーム検出を実行。
- `tracking_service.py`
  - detection を永続 track に変換し、active/lost/inactive、predicted keyframe、fragment stitching、短命 track filter を処理。
- `mask_edit_service.py`
  - キーフレーム解決、補間、追加、複製、削除、移動、vertex 編集、polygon 整形。手動 keyframe 保護もここ。
- `continuity_service.py`
  - manual anchor と自動検出結果の連続性検証。危険な自動結果を `anchor_fallback` へ置換する。
- `project_edit_service.py`
  - 手動 track 作成、削除、複製、分割、表示切替。
- `render_service.py`
  - frame index に対して track を resolve し、frame にモザイクを適用。
- `export_service.py`
  - export preset と project snapshot から動画を書き出す。ffmpeg があれば rawvideo pipe と audio mux、なければ OpenCV writer へ fallback。
- `history_service.py`
  - undo/redo 用の project snapshot 管理。
- `contour_service.py`
  - bbox から輪郭候補を作る。mode は `none/fast/balanced/quality` 系で、SAM2 tiny adapter 連携も考慮。

### `app/infra/`

- `app/infra/ai/`
  - `detector_factory.py`, `nudenet_adapter.py`, `erax_adapter.py`, `sam2_tiny_adapter.py`, `onnxruntime_utils.py`, `model_runner.py`, `label_mapper.py`, `mobile_sam_adapter.py`。
- `app/infra/device/`
  - `device_manager.py`, `device_info.py`。GPU/CPU 実行判断。
- `app/infra/video/`
  - `ffprobe_reader.py`, `ffmpeg_exporter.py`, `cv_video_reader.py`, `cv_video_writer.py`。
- `app/infra/storage/`
  - `project_store.py`。JSON 保存/読込。

### `app/ui/`

- `main_window.py`
  - 現行 GUI の中心。動画読込、検出、range 検出、単一フレーム検出、保存/読込、export queue、history、preview/timeline/property/track list 同期を大量に抱える。
- `preview_canvas.py`
  - `QGraphicsView` ベースのプレビュー、mask shape 描画、hit testing、handle/vertex 編集、context menu、onion skin。
- `timeline_widget.py`
  - timeline 表示、zoom/scroll、in/out frame、keyframe marker、track 行描画。
- `track_list_panel.py`
  - track group/list、選択、表示切替、onion/vertex/overlay 操作。
- `property_panel.py`
  - 選択 track の style、keyframe、形状編集パラメータ。
- `detection_worker.py`, `export_worker.py`
  - `QThread` と signal で長時間処理を GUI に返す PySide6 固有の非同期境界。
- `export_queue_dialog.py`, `export_settings_dialog.py`
  - export 設定と in-memory queue。
- `gpu_settings_dialog.py`, `dep_install_dialog.py`, `progress_dialog.py`
  - GPU 設定、依存修復、進捗表示。

UI は `.ui`, `.qml`, `.qrc` ファイルではなく、Python コードでプログラム的に構築されています。

## 3. UI から backend までの主要フロー

### 起動

1. `app/main.py` が `app.bootstrap.run()` を呼ぶ。
2. `bootstrap.run()` が `AppConfig.load()` を実行。
3. `AppConfig.load()` が `AppPaths.resolve()`、環境変数、GPU 設定を解決。
4. logging と Qt application を初期化。
5. `startup_checks` と dependency dialog を通す。
6. `build_runtime_services(config)` で domain/infra service を組み立てる。
7. `MainWindow(runtime)` を作成して表示する。

### 動画読込

1. `MainWindow.open_video()` が `QFileDialog` で動画を選択。
2. `_load_video(video_path)` が `FFProbeReader` で `VideoMeta` を取得。
3. `CvVideoReader` で先頭フレームを読む。
4. `Project.create(source_video_path, video_meta)` で新規 project を作成。
5. timeline、track list、property panel、preview、history を初期化。

### プロジェクト保存/読込

保存:

1. `MainWindow.save_project()` が保存先を決める。
2. `ProjectStore.save(project, path)` が `Project.to_dict()` を UTF-8 JSON として保存。
3. `HistoryService` は clean mark を更新。

読込:

1. `MainWindow.load_project()` が `ProjectStore.load(path)` を呼ぶ。
2. `Project.from_dict()` で domain model を復元。
3. `source_video_path` が存在すれば `CvVideoReader` を開いて先頭フレームを表示。
4. track/timeline/property/preview/history を同期。

確認した範囲では、動画ファイルが移動していた場合の再リンク UI は明確ではありません。これは Tauri 化時に保存形式互換と user data file access の地雷になります。

### AI 検出

全体検出:

1. `MainWindow.detect_masks()` が既存 track の有無を確認し、manual track 保護/上書き/キャンセルを選ばせる。
2. `run_full_detection()` が `DetectionWorker` を起動。
3. `DetectionWorker` は `DetectionService.detect_sampled_frames()` を実行。
4. detection result を `TrackingService.build_tracks()` に渡して mask track を構築。
5. `MainWindow.apply_full_detection_results()` が `ContinuityService` で検証し、project tracks へ反映。
6. UI 同期と history commit を行う。

範囲検出:

1. `TimelineWidget` の in/out frame を使って `run_range_detection(start, end)`。
2. 検出後、`apply_range_detection_results()` が既存 track と新規 track を label と IoU で対応づける。
3. 範囲外 keyframe を保持し、manual keyframe は preserve 設定に応じて保護。
4. unmatched track は追加。
5. continuity 検証、UI 同期、history commit。

単一フレーム検出:

1. 現在フレームで `DetectionService.detect_single_frame()`。
2. `TrackingService.build_tracks()` で一時 track 化。
3. `_apply_single_frame_detected_tracks()` が既存 track と label/IoU で統合、または新規 track として追加。

ここで注意すべき点は、AI 検出が単に detection list を返すだけではなく、GUI 側の既存 track 統合、manual 保護、continuity fallback、history commit と強く絡んでいることです。

### マスク編集

1. `PreviewCanvas` の hit testing と context menu が track/keyframe/vertex 操作 signal を出す。
2. `MainWindow` が編集可否を確認する。再生中は編集をロックする。
3. `MaskEditService` または `ProjectEditService` が domain model を更新。
4. `MainWindow._commit_history_state()` で undo/redo snapshot を積む。
5. `EditorDisplayService` を経由して timeline、track list、property panel、preview を同期。

編集ロジックは domain service に寄せられていますが、ユーザー操作の解釈、選択状態、現在フレーム、history commit の粒度は `MainWindow` に集中しています。

### export / render

1. `MainWindow.export_video()` が `ExportSettingsDialog` で preset と出力先を選ばせる。
2. `ExportQueueDialog.add_job_with_settings()` が `ExportJob.create()` で project snapshot を持つ job を作成。
3. `ExportWorker(QThread)` が `ExportService.export_project()` を呼ぶ。
4. `ExportService` は各 frame で `RenderService.resolve_tracks()` と `RenderService.render_frame()` を呼ぶ。
5. `FFmpegExporter` が使える場合は silent video を作り、音声 mux を行う。ffmpeg がなければ OpenCV writer へ fallback し、音声なしになる。
6. 進捗、成功、失敗、キャンセルは Qt signal で UI に返る。

export queue は in-memory で、`pyside6_remaining_tasks.md` でも queue persistence は未実装タスクです。

## 4. データフロー

代表的なデータの流れは次の通りです。

```text
動画ファイル
  -> FFProbeReader / CvVideoReader
  -> VideoMeta / frame
  -> DetectionService
  -> DetectionResult / Detection
  -> TrackingService
  -> MaskTrack / Keyframe
  -> MainWindow / EditorDisplayService
  -> PreviewCanvas / TimelineWidget / TrackListPanel / PropertyPanel
  -> ProjectStore JSON
  -> ExportService / RenderService
  -> 出力動画
```

保存形式の中心は `Project.to_dict()` / `Project.from_dict()` です。`ProjectStore` は JSON を保存/読込します。現時点で確認した範囲では、versioned migration layer は薄く、`project_version=1` を持つものの、将来 schema 変更に対する明示的 migration は十分ではありません。

export job は `ExportJob.create(project, ...)` で `Project.snapshot()` を持ちます。これは UI 編集中に export 対象が変化しないようにする重要な仕様です。Tauri 移行でも job 開始時 snapshot の意味を維持する必要があります。

## 5. 状態管理の流れ

中心状態は `MainWindow` にあります。

- `current_project`
- `current_project_file`
- `video_reader`
- `current_frame`
- `current_frame_index`
- `selected_track_id`
- `show_mosaic_preview`
- onion skin 関連 state
- track list 表示 mode
- overlay/vertex 表示 state
- detection worker / progress dialog
- export queue dialog
- playback timer
- history service

domain 側にも状態はあります。

- `MaskTrack.state`: `active/lost/inactive`
- `MaskTrack.source`: `auto/user-adjusted/re-detected`
- `MaskTrack.user_locked`
- `MaskTrack.motion_history`
- `MaskTrack.association_history`
- `Keyframe.source`
- `ExportJob.status`: `queued/running/completed/canceled/error`

表示用状態は `EditorDisplayService` で `ResolvedTrack` / presentation へ変換されます。`RenderService.resolve_tracks()` も export/render 用に frame index で track を resolve します。つまり、「編集表示」と「export render」が別ルートで同じ domain service を使う構造です。ここがずれると、UI では正しく見えて export では違う、またはその逆になります。

## 6. AI 検出モデルジョブ管理の流れ

### モデルと detector

`DetectorFactory.create(config.gpu.detector_backend)` が detector を生成します。NudeNet、EraX、SAM2 tiny などの adapter が `app/infra/ai/` にあります。必須モデルとして `models/320n.onnx`、任意モデルとして `640m.onnx`、EraX、SAM2 tiny encoder/decoder が README と setup 系に記載されています。

`GpuConfig` は `device`, `detector_backend`, `sample_every`, `max_samples`, `inference_resolution`, `batch_size`, `confidence_threshold`, `contour_mode`, `precise_face_contour`, `enabled_label_categories`, `vram_saving_mode` などを持ちます。

### 検出ジョブ

検出の実行単位は PySide6 の `QThread` である `DetectionWorker` です。進捗は Qt signal で `ProgressDialog` と `MainWindow` に返ります。キャンセルは worker 側の cancel flag と callback で処理されます。

Tauri ではこのまま移植できません。Tauri command は短時間 command と長時間 job を分け、progress event、job id、cancel command、stdout/stderr purity のルールを作る必要があります。

### track 化

`TrackingService.build_tracks()` が detection を persistent track にします。コード上の現在値では、`max_frame_gap=60`, `lost_grace_frames=120`, `inactive_reactivation_max_frame_gap=600`, `stitch_max_frame_gap=180` などの設定があります。`MASK_SPEC.md` の古い数値と差分があるため、移行時はコード値を優先して仕様化する必要があります。

`TrackingService` は次を行います。

- label group ごとの candidate matching
- active/lost/inactive の state 遷移
- missing gap で predicted keyframe を生成
- inactive track の reactivation
- fragmented track stitching
- 短命 auto track の filter
- contour mode に応じた keyframe shape 作成

## 7. マスク編集、タイムライン、キーフレームの構造

### MaskTrack

`MaskTrack` は `track_id`, `label`, `start_frame`, `end_frame`, `visible`, `style`, `keyframes`, `state`, `source`, `last_detected_frame`, `last_tracked_frame`, `missing_frame_count`, `confidence`, `user_locked`, `motion_history`, `association_history` を持ちます。

`frame_display_state()` は frame と resolved keyframe source から `active/interpolated/predicted/inactive/ended` を返します。export と UI 表示の整合に関わるため、Tauri 側で別解釈してはいけません。

### Keyframe

`Keyframe` は frame index 単位の shape です。ellipse/polygon を扱い、`bbox`, `points`, `contour_points`, `source`, `confidence`, `rotation`, `opacity`, `expand_px`, `feather` を持ちます。

source の意味は移行で重要です。

- `auto`: AI 検出由来
- `manual`: ユーザー編集由来
- `interpolated`: 補間
- `predicted`: tracking の予測 tail
- `re-detected`: 再検出
- `anchor_fallback`: manual anchor を使った continuity fallback

### MaskEditService

`resolve_keyframe(track, frame_index)` は exact keyframe がない場合に、前後 keyframe から補間します。範囲外でも nearest keyframe を `interpolated` として返す実装があります。これは「検出外 frame の表示/編集がどう見えるか」に直結する暗黙仕様です。

`upsert_keyframe(..., protect_manual=True)` は manual keyframe を非 manual で上書きしない保護を持ちます。manual keyframe を追加すると track は `user-adjusted` になり、`user_locked=True` になります。

### TimelineWidget

`TimelineWidget` は zoom/scroll、in/out frame、keyframe marker、track 行を扱います。keyframe marker は source に応じて色分けされています。範囲検出は timeline の in/out frame に依存します。

### PreviewCanvas

`PreviewCanvas` は `QGraphicsView` ベースです。resolved track を受け取り、shape、handle、vertex、onion skin、context menu を描きます。hit testing と編集 signal が UI 側にあります。Tauri では Canvas/SVG/DOM のどれで再現するかを決める必要があり、単純なコンポーネント置換では済みません。

## 8. setup / bootstrap / packaging / runtime の仕組み

### ユーザー向け導線

- Windows:
  - 初回: `setup.bat`
  - 起動: `run_ui.bat`
- macOS/Linux:
  - 初回: `setup.sh`
  - 起動: `python -m app.main`

`run_ui.bat` は `.venv` がなければ `setup.bat` を呼びます。`setup.bat` は `.venv` 作成、pip bootstrap、data/models directory 作成、`scripts/setup_dev.py` 実行を行います。`CLAUDE.md` は `.bat` は ASCII only と明記しています。

### runtime path

`AppPaths.resolve()` は次を解決します。

- project root: `AUTO_MOSAIC_PROJECT_ROOT` または `app/runtime/paths.py` から見た project root
- data dir: `AUTO_MOSAIC_DATA_DIR` または `project_root/data`
- model dir: `AUTO_MOSAIC_MODEL_DIR` / `MODEL_DIR` または `project_root/models`
- config/cache/temp/export/log dir
- ffmpeg/ffprobe: `AUTO_MOSAIC_FFMPEG_PATH` / `FFMPEG_PATH`, `AUTO_MOSAIC_FFPROBE_PATH` / `FFPROBE_PATH`

Tauri 化では app data dir、resource dir、sidecar/backend path、asset access が変わります。今の project root 相対前提をそのまま持ち込むと、packaged app で破綻する可能性が高いです。

### dependency check / doctor

`app/dep_checker.py` と `app/runtime/environment.py` が依存、model、ffmpeg/ffprobe、GPU、path の状態を検査します。`app/cli.py check-env --json` と `paths --json` は Tauri 側の doctor/bootstrap へ利用できる可能性がありますが、現状の CLI は migration 用 command contract ではありません。

### packaging

確認した範囲では、現行は開発環境 bootstrap が中心です。`docs/02_design/01_architecture-and-ui.md` でも packaging は dev oriented で、最終 packaging/installer は未完了領域として扱われています。Windows 配布、DLL、Python runtime、ffmpeg、ONNX Runtime、GPU/CUDA の同梱方針は移行計画で先送りしすぎると事故ります。

## 9. 現行構成の強み

- domain model と service が存在し、すべてが UI に埋まっているわけではありません。
- `RuntimeServices` に composition root があり、Tauri backend 側の service 組み立てに再利用できる見込みがあります。
- `Project.to_dict()` / `from_dict()` と `ProjectStore` があり、保存形式の入口は比較的明確です。
- `MaskEditService`, `TrackingService`, `ContinuityService`, `RenderService`, `ExportService` など、移行単位に分けやすい service が存在します。
- `tests/` が広く存在し、architecture boundary、tracking、mask edit、continuity、export、runtime、dependency check などをカバーしています。
- `check-env --json`, `paths --json` は Tauri 側 doctor の土台にできる可能性があります。
- export job が project snapshot を持つ設計は、Tauri の非同期 job 化にも合います。

## 10. 現行構成の弱み

- `MainWindow` が非常に大きく、動画読込、検出統合、range merge、single-frame merge、保存/読込、export queue、history、UI 同期の多くを持ちます。
- 長時間処理の境界が `QThread` と Qt signal に依存しています。Tauri では job id、event、cancel command に分解が必要です。
- `PreviewCanvas` と `TimelineWidget` は PySide6/QPainter/QGraphicsView 的な前提を持ちます。React へ直接置換しにくいです。
- 保存形式は JSON として存在するものの、schema version migration が薄いです。
- runtime path が project root 相対、`data/` 相対、`.venv` 前提を含み、packaged Tauri app の resource/app data の考え方とズレます。
- dependency/model/bootstrap は現行 dev setup に寄っており、配布 runtime として未整理です。
- export queue persistence は未実装です。
- 動画ファイル移動時の再リンク、user data 管理、権限境界は未確認です。

## 11. 移行時に壊れやすい箇所

- manual keyframe 保護
  - `MaskEditService.upsert_keyframe()`、range detection merge、single frame detection の replace 挙動が絡みます。
- range detection merge
  - 既存 track と新規 track の label/IoU 対応、範囲外 keyframe 保持、manual preserve が GUI 側にあります。
- `Keyframe.source` の意味
  - `auto/manual/interpolated/predicted/re-detected/anchor_fallback` を UI 表示、export、history、tracking がそれぞれ参照します。
- `resolve_keyframe()` の範囲外 hold/interpolation
  - UI と export が一致しないと実害が出ます。
- `frame_display_state()`
  - active/interpolated/predicted/inactive/ended の解釈を Tauri UI が独自実装するとズレます。
- export snapshot
  - job 開始後の編集が export に影響しない設計を維持する必要があります。
- ffmpeg fallback
  - ffmpeg がない場合は OpenCV writer へ fallback し、音声 mux ができません。この差分を Tauri UI が説明できないと UX 事故になります。
- GPU fallback
  - GPU 失敗時の CPU fallback、VRAM saving、ONNX Runtime GPU の状態表示を UI だけで単純化するとサポート不能になります。
- runtime path
  - `project_root/data` と packaged app data/resource の差分。
- dependency repair
  - PySide6 dialog 前提の `DepInstallDialog` を Tauri でどう置き換えるか。

## 12. 技術的負債 / 暗黙依存 / 危険な前提

### 技術的負債

- `MainWindow` の責務過多。
- PySide6 signal/slot を backend contract の代わりに使っている。
- `DetectionWorker` / `ExportWorker` に UI 用の進捗語彙が埋まっている。
- 保存 schema の migration 方針が弱い。
- project root と `data/` 相対の runtime 前提。
- setup と runtime doctor と packaging が完全には分離していない。

### 暗黙依存

- `Project.source_video_path` はローカル path 文字列で、移動時の扱いが弱い。
- `Project.snapshot()` が export job の不変入力として使われる。
- `MaskEditService.resolve_keyframe()` の補間/hold 結果を UI と export が共有する。
- `TrackingService` の現行 default 値はドキュメントよりコードが正しい。
- `MainWindow._commit_history_state()` の呼び忘れが undo/redo 欠落に直結する。
- 再生中は編集を止めるという UI 側 lock が編集整合性を支えている。
- `data/config/gpu_config.json` と legacy `data/gpu_config.json` の両方が存在しうる。

### 危険な前提

- Tauri 化を UI 移植だけとみなすこと。
- Python backend をそのまま subprocess 化すれば同等になるとみなすこと。
- `QThread` signal の progress/cancel 仕様をそのまま Tauri command に持ち込めるとみなすこと。
- 開発環境の `models/`, `data/`, `.venv`, `ffmpeg` 解決が packaged app でも成立するとみなすこと。
- `unimplemented-features.md` を現在仕様の正本として扱うこと。

## 13. まだ把握しきれていない点

- Tauri 側コードベースの現状。これは次フェーズで別途調査します。
- packaged Windows 配布で Python runtime、ONNX Runtime、CUDA、ffmpeg、モデルをどう同梱するかの確定方針。
- project schema の将来 migration 方針。
- 動画ファイル移動時の再リンク UX と保存形式上の扱い。
- export queue persistence の設計。
- crash recovery の設計。
- installer/updater/uninstaller の設計。
- 実運用でどの detector backend、GPU 構成、モデル配置が主流か。
- `tests/` の全件実行結果。現時点では調査のみで、テスト実行はまだ行っていません。

## 批判的所見

現行実装は、domain service があるため移行の足場はあります。ただし実際のユーザー操作の一貫性は `MainWindow` と PySide6 worker/signal にかなり依存しています。Tauri 化で React UI を作るだけでは、manual 保護、range detection merge、history、progress/cancel、export snapshot、runtime doctor のどれかが高確率で欠落します。

最初に固定すべきなのは画面見た目ではなく、保存 schema、job state、progress event、cancel、file path、runtime doctor、モデル/ffmpeg/GPU の境界です。特に Windows 配布前提では、Python backend をどう起動し、どこにモデルを置き、stdout をどう扱い、ffmpeg/ONNX Runtime の失敗をどう UI に返すかを早期に契約化しないと、後半で作り直しになります。
