# AI_HANDOFF.md

> 位置づけ: このファイルは直近作業の handoff log です。現行実装の正本は `docs/engineering/current-implementation.md`、実装済み / 未実装 backlog の正本は `docs/project/unimplemented-features.md` です。末尾の Next Logical Step は作成時点の履歴として扱い、現在の作業判断では正本を優先してください。

## Snapshot
- **Phase D 全 10 項目達成 (2026-04-17 3rd pass)**: M-C08 diff overlay も実装 (Shift+M で全 visible + export_enabled track の resolve_for_render 結果を canvas に半透明マゼンタで重ねる)。コード実装は Phase D 完了。次は Tauri ウィンドウでの目視レビュー。
- Phase D 完了 pass (2026-04-17 2nd): M-C06 の preview mode badge、M-C07 onion skin、M-C09 UI 言語切替を追加。
- Phase D 集中 pass (2026-04-17): M-C02 / M-C04 / M-C05 / M-C10 を追加実装し、M-C06 の legend を拡張、M-C08 の deferred 判定を再確認。
- Phase D 更新: 2026-04-16 に M-C01 (`polygon track 作成`) を実装。frontend で `Shift+N` と `+ 多角形` を追加し、backend の既存 `create-track(shape_type="polygon")` 契約へ接続した。
- Phase D 着手: 2026-04-17 に M-C03 (`export_enabled`) を実装。MaskTrack / export / update-track / TrackDetailPanel / TimelineView / MosaicPreviewCanvas に反映し、`visible` と独立して「書き出し対象外」を扱える。
- Minimum flow (open video → detect → mask edit → export) was manually verified in the Tauri window on April 16, 2026.
- Export now keeps preview/render semantics aligned for render span and segment gaps.
- Export auto encoder now retries with CPU (`libx264`) when a probed GPU encoder fails at runtime.
- Export modal state now rehydrates from parent settings on reopen.
- Frontend recovered shell is now back to a usable editor shape.
- `App.tsx` is a clean UTF-8 shell again and no longer carries the old mojibake damage.
- The shared Job Panel remains the common progress surface for runtime jobs, detect jobs, and export.
- Model download is now integrity-based: verify-before-promote, missing/broken/installed status, detect preflight guard.
- Current desktop build status on April 8, 2026: `npm.cmd run build` in `apps/desktop` passed.
- Current desktop mojibake check status on April 8, 2026: `npm.cmd run check:mojibake` in `apps/desktop` passed.
- Current desktop test status on April 8, 2026: `npm.cmd test` in `apps/desktop` passed with `21/21`.
- Current backend smoke status on April 8, 2026: `python -m pytest tests\\test_cli_smoke.py` in `apps/backend` passed with `62 passed`.
- Current backend integrity test status on April 9, 2026: `python -m pytest tests/test_model_integrity.py` passed with `25/25`.
- Current targeted backend status on April 16, 2026:
  - `python -m pytest tests/test_cli_smoke.py -k "auto_encoder_retries_with_cpu_after_gpu_runtime_failure"` passed
  - `python -m pytest tests/test_domain_track.py -k "held_segments_do_not_hide_detector_keyframe_span"` passed
  - `python -m pytest tests/test_mask_continuity.py -k "held_segment_does_not_hide_accepted_detector_keyframes"` passed
- Current desktop build status on April 16, 2026: `npm.cmd run build` in `apps/desktop` passed.

## What Was Added In This Pass (April 17, 2026 3rd — Phase D: M-C08 diff overlay → Phase D 全完)

### スコープ
`feature_list` 3-4 (差分オーバーレイ) を受けて deferred 判定を解除、M-C08 を実装。これで Phase D のコア編集 UX は 10/10 達成。

### Frontend
- `apps/desktop/src/App.tsx`
  - `diffOverlayEnabled` state、keydown の `Shift+M` トグル (小文字 `m` はモザイクプレビューのトグルにも追加)
  - `diffOverlayShapes` を useMemo で計算 (全 `track.visible && track.export_enabled` の track に対して `resolveForRender(track, currentFrame)` を適用)
  - CanvasStagePanel に新規 props `diffOverlayEnabled` / `diffOverlayShapes` を渡す
  - preview info bar に `差分 ON/OFF` トグルボタンを追加
- `apps/desktop/src/components/CanvasStagePanel.tsx`
  - 新規 helper `renderDiffShape(keyframe, trackId)` (ellipse/polygon 両対応、rotation 反映)
  - `.canvas-stage__diff-svg` オーバーレイ layer を onion skin layer の直後に配置 (z-index: 3)
- `apps/desktop/src/components/ShortcutHelpModal.tsx`
  - 「プレビュー」カテゴリを新設: `M` モザイクトグル、`Shift+M` 差分オーバーレイトグル
- `apps/desktop/src/styles.css`: `.canvas-stage__diff-svg` と `.canvas-stage__diff-shape` (マゼンタ半透明 fill + 破線 stroke) を追加

### 検証
- `npm.cmd run build` → passed
- `npm.cmd run check:mojibake` → passed
- バックエンド変更なしのため backend テストは省略

### 次ステップ
- **Tauri ウィンドウでの目視レビュー**: Phase D の 10 項目すべてを実機で確認
  - polygon 作成 / ellipse 回転 / export_enabled / transport 速度 & Home/End / shortcut help / mode badge / onion skin / diff overlay / 言語切替 / inspector 折りたたみ
- 目視で問題が出たらフォローアップ、OK なら Phase A (recovery / review safety) へ進む

---

## What Was Added In This Pass (April 17, 2026 — Phase D: M-C06 full / M-C07 / M-C09)

### スコープ
Phase D の残り (M-C06 preview badge / M-C07 onion skin / M-C09 UI 言語切替) を追加し、Phase D のコア UX をひとまず完了させる。M-C08 は deferred 維持で変更なし。

### Frontend — M-C06 preview operation mode badge
- `apps/desktop/src/components/CanvasStagePanel.tsx`
  - 左上に `.canvas-stage__mode-badge` を新規配置し、再生状態 / モザイク ON/OFF / 選択トラック (label + `非表示` / `書き出し外` / `ロック` サブラベル) を表示
  - 新規 props `isVideoPlaying`, `mosaicPreviewEnabled`, `playbackRate`
- `apps/desktop/src/App.tsx`
  - `isVideoPlaying` state を追加、`<video>` の `onPlay` / `onPause` / `onEnded` に同期
  - CanvasStagePanel に新規 props を渡す
- `apps/desktop/src/styles.css`: `.canvas-stage__mode-badge` と `.canvas-stage__mode-chip--*` バリアントを追加

### Frontend — M-C07 onion skin
- `apps/desktop/src/components/CanvasStagePanel.tsx`
  - 新規 `renderOnionShape(keyframe, variant)` ヘルパーを追加 (ellipse/polygon 両対応、rotation 反映)
  - `.canvas-stage__onion-svg` レイヤーを backdrop 直後に追加
  - 新規 props `onionSkinEnabled`, `onionSkinPrev`, `onionSkinNext`
- `apps/desktop/src/App.tsx`
  - `onionSkinEnabled` state、`onionSkinKeyframes` (prev/next explicit keyframe) を useMemo で計算
  - preview info bar に `オニオン ON/OFF` トグルボタン
- `apps/desktop/src/styles.css`: `.canvas-stage__onion-svg` と `.canvas-stage__onion-shape--prev/next` を追加 (前=青破線 / 次=橙破線)

### Frontend — M-C09 UI 言語切替
- `apps/desktop/src/uiText.ts` を `UiText` 型 + `uiTextJa` + `uiTextEn` に再構成、`getUiText(lang)` ヘルパーを export (既存の `uiText` 定数も日本語辞書として互換維持)
- `apps/desktop/src/App.tsx`
  - `UiLanguage` state (初期値は `auto-mosaic:language` localStorage から) と永続化 effect
  - `uiText = useMemo(() => getUiText(language), [language])` で動的切替
  - header に日本語 / EN トグルボタンを追加
- `apps/desktop/src/styles.css`: `.nle-header__lang` コンテナクラス
- **クリーンアップ**: 古い `apps/desktop/src/uiText.js` (再エクスポートスタブ) を削除。rollup の拡張子解決で `.ts` より `.js` が優先されてしまい、新規 export `getUiText` が未発見になっていた

### 検証
- `npm.cmd run build` in `apps/desktop` → passed (M-C06 / M-C07 / M-C09 追加後の最終 build)
- `npm.cmd run check:mojibake` → passed
- バックエンドに触っていないので backend テストは省略

### 未検証 / 残り
- Tauri ウィンドウでの目視確認 (mode badge の色分け、onion skin の表示、言語切替時の UI 反映)
- `M-C08` diff overlay は deferred のまま (Phase D 完了後の次段階で再評価)
- onion skin は前後 1 frame ずつのみ。複数 frame 遡る / 透明度設定は未対応

---

## What Was Added In This Pass (April 17, 2026 — Phase D: M-C02 / M-C04 / M-C05 / M-C10 + M-C06 partial / M-C08 re-eval)

### スコープ
Phase D (Editing UX Completion) を一気に進めるパス。既存 domain と補間を活かして UI 導線を補い、永続化と help modal を整備。

### Backend
- `apps/backend/src/auto_mosaic/api/commands/update_keyframe.py`
  - patch で `rotation` を受け入れ (degrees、±180 正規化)。`track.mark_user_edited` の対象にも追加
- `apps/backend/src/auto_mosaic/infra/video/export.py`
  - `_build_shape_mask` 内の `cv2.ellipse` に `keyframe.rotation` を渡し、ellipse の回転を出力に反映
- `apps/backend/tests/test_cli_smoke.py`
  - `test_update_keyframe_rotation_roundtrip_and_normalisation` を追加 (45° 保存、270° → -90° への wrap、非数値で `INVALID_KEYFRAME_PATCH`)

### Frontend
- `apps/desktop/src/types.ts`: `UpdateKeyframePayload.patch` に `rotation` を追加
- `apps/desktop/src/keyframeInspector.ts`
  - `KeyframeInspectorState` / `InspectorPayload` に `rotationText` / `rotation` を追加、parse 時に ±180 正規化
- `apps/desktop/src/components/KeyframeDetailPanel.tsx`
  - ellipse のときのみ表示される回転スライダー + 数値入力、`onSaveKeyframe` の patch に `rotation` を含める
- `apps/desktop/src/components/CanvasStagePanel.tsx`: ellipse div に `transform: rotate(${rotation}deg)` を反映
- `apps/desktop/src/components/MosaicPreviewCanvas.tsx`
  - モザイク描画と outline 描画の両方で `ctx.ellipse` に rotation を反映 (degrees → radians 変換)
- `apps/desktop/src/components/ShortcutHelpModal.tsx` 新規: F1 の `window.alert` を置き換えるカテゴリ別テーブル、Escape / overlay クリック / × ボタンで閉じる
- `apps/desktop/src/App.tsx`
  - F1 を modal 起動に置換、`shortcutModalOpen` state、`ShortcutHelpModal` を render
  - transport bar に `0.25x〜4x` の `<select className="nle-transport__speed">` を追加
  - `playbackRate` state と、`videoRef` に反映する `useEffect`
  - keydown handler に `Home` / `End` を追加
  - `inspectorEnvironment / detect / export / trackDetail / keyframeDetail` の 5 箇所に `usePersistedDetails` を適用し、`<details>` の `open` 状態を localStorage 永続化
- `apps/desktop/src/hooks/usePersistedDetails.ts` 新規: `auto-mosaic:inspector-open:${id}` key で `<details>` 開閉を永続化する hook
- `apps/desktop/src/components/TimelineView.tsx`: legend に `非表示` / `再生範囲外` / `書き出し外` 3 項目を並べた
- `apps/desktop/src/styles.css`: `.nle-transport__speed` / `.nle-shortcut-table*` / legend 追加項目のスタイルを追加

### 検証
- `py -3.12 -m pytest tests/test_cli_smoke.py -k "rotation" -q` → 1 passed
- `npm.cmd run build` in `apps/desktop` → passed (3 回、各 feature 追加後)
- 既存の failure (`test_export_video_mux_if_possible_reports_video_only_when_source_has_no_audio`, `test_list_detect_jobs_*`) は変更前から存在し本パスの変更とは無関係

### 未検証 / 残り
- Tauri ウィンドウでの目視確認 (各 Phase D 項目)
- ellipse 回転ハンドルの canvas 側ドラッグ操作 (今回は数値入力とスライダーのみ)
- `M-C06` preview operation mode badge (legend は拡張、badge は未着手)
- `M-C07` onion skin / `M-C09` UI 言語切替 (いずれも未着手、別 pass で扱う)

---

## What Was Added In This Pass (April 16, 2026 — Phase D: M-C01 polygon track creation)

### スコープ
Phase D の編集機能追加として、manual polygon track を frontend から正式に作成できるようにした。
既存 backend の `create-track(shape_type)` 契約を利用し、UI 導線不足だけを補完した。

### Backend
- `apps/backend/tests/test_cli_smoke.py`
  - `create_track.run()` の ellipse default と polygon payload を確認する smoke test を追加
  - backend command 自体の挙動変更はなし

### Frontend
- `apps/desktop/src/manualTrackFactory.ts`
  - manual track 作成 payload の小さな helper を追加
  - polygon は初期矩形を points 化して backend へ渡す
- `apps/desktop/src/App.tsx`
  - `handleCreateTrack(shapeType)` に変更
  - `Shift+N` で polygon、`N` で ellipse を作成
  - ヘッダーに `+ 楕円` / `+ 多角形` ボタンを追加
  - F1 の shortcut 文言に `Shift+N` を追加
- `apps/desktop/tests/manualTrackFactory.test.ts`
  - ellipse / polygon payload の生成を確認する unit test を追加

### 検証
- `node --test --experimental-strip-types tests/manualTrackFactory.test.ts` passed
- `npm.cmd run build` in `apps/desktop` passed
- workspace 固定パスでの `create-track` roundtrip を確認:
  - ellipse: default bbox `[0.3, 0.3, 0.2, 0.2]`
  - polygon: 指定 points がそのまま保存される

### 未実施 / 残り
- Tauri ウィンドウでの manual polygon track 作成と、その後の vertex 編集の目視確認
- `M-C05` shortcut help modal 本体は未着手。今回は shortcut 導線追加のみ
- `tests/test_cli_smoke.py` はこの sandbox では `tempfile` 配下への書き込み制約で未実行

## What Was Added In This Pass (April 17, 2026 — Phase D: M-C03 export_enabled)

### スコープ
Phase D (Editing UX Completion) の最初の項目として、`MaskTrack.export_enabled` フラグを導入。
`visible` (UI 表示の on/off) とは独立した責務で、「書き出し対象外」を明示的に扱う。

### Backend
- `apps/backend/src/auto_mosaic/domain/project.py`
  - `MaskTrack` dataclass に `export_enabled: bool = True` を追加
  - `_normalize_track_payload` / `_migrate_pyside6_track_payload` / `MaskTrack.from_payload` / `build_read_model` に反映
  - schema_version は v2 のまま (default=True の後方互換で旧 payload を補完)
- `apps/backend/src/auto_mosaic/infra/video/export.py`
  - FFmpeg pipe export と OpenCV fallback の両方で `visible` チェック直後に `export_enabled` ガードを追加
- `apps/backend/src/auto_mosaic/api/commands/update_track.py`
  - patch で `export_enabled` を受け入れる

### Frontend
- `apps/desktop/src/types.ts`: `MaskTrack` / `TrackSummary` / `EditableTrack` / `UpdateTrackPayload` に追加
- `apps/desktop/src/editorSelection.ts`: `writeTracks` マッピングに追加
- `apps/desktop/src/components/TrackDetailPanel.tsx`: meta 行とトグルボタンを追加
- `apps/desktop/src/App.tsx`: `handleToggleTrackExportEnabled` を追加
- `apps/desktop/src/components/TimelineView.tsx`: `nle-tl-row--export-disabled` と右側バッジ、legend に項目追加
- `apps/desktop/src/components/MosaicPreviewCanvas.tsx`: `export_enabled=false` の track は破線 outline のみ描画 (モザイク非適用)
- `apps/desktop/src/styles.css`: 斜線パターン / 赤バッジ / legend 色を追加

### テスト
- `apps/backend/tests/test_domain_track.py`: `TestExportEnabledFlag` クラス (default, legacy payload, false payload, asdict roundtrip, visible との独立性) を追加
- `apps/backend/tests/test_cli_smoke.py`:
  - `test_export_video_skips_tracks_with_export_enabled_false` (ellipse ROI が source と一致、polygon は従来どおりモザイクされる)
  - `test_update_track_roundtrip_toggles_export_enabled` (patch で往復切替)

### 検証
- `py -3.12 -m pytest tests/test_domain_track.py -q` → 35 passed
- `py -3.12 -m pytest tests/test_cli_smoke.py -k "export_enabled_false or toggles_export_enabled" -q` → 2 passed
- `npm.cmd run build` in `apps/desktop` → passed
- `npm.cmd run check:mojibake` in `apps/desktop` → passed
- 既存の failure (`test_export_video_mux_if_possible_reports_video_only_when_source_has_no_audio`, `test_list_detect_jobs_*`, `npm test` の maskShapeResolver parity) は変更前から存在し本パスの変更とは無関係であることを `git stash` 比較で確認

### 未検証 / 残り
- Tauri ウィンドウでの目視確認 (トグル操作、preview の破線 outline、timeline の斜線パターン)
- `npm.cmd run review:runtime` の再同期 (review build に反映する場合)

---

## What Was Fixed In This Pass (April 16, 2026 — minimum flow verification follow-up)

### Review findings addressed
- Export `encoder="auto"` could still fail hard when FFmpeg exposed a GPU encoder but runtime initialization failed. This now retries with CPU (`libx264`) instead of aborting the export.
- Mosaic preview used editing semantics rather than render semantics, so it could show masks after the last renderable frame or inside segment gaps. The preview now mirrors export-side render gating.
- Export settings modal state persisted across reopen, which could show stale encoder / bitrate settings after parent-state changes. The modal now reloads from current app state when reopened.

### Files changed in this pass
- `apps/backend/src/auto_mosaic/infra/video/export.py`
- `apps/backend/tests/test_cli_smoke.py`
- `apps/desktop/src/maskShapeResolver.ts`
- `apps/desktop/src/components/MosaicPreviewCanvas.tsx`
- `apps/desktop/src/components/ExportSettingsModal.tsx`
- `apps/desktop/tests/maskShapeResolver.test.ts`
- `docs/engineering/current-implementation.md`
- `docs/project/unimplemented-features.md`
- `docs/project/ai-handoff.md`

### Verification in this pass
- Manual Tauri flow: open video → detect → mask edit → export: confirmed by human
- `npm.cmd run build` in `apps/desktop`: passed
- `python -m pytest tests/test_cli_smoke.py -k "auto_encoder_retries_with_cpu_after_gpu_runtime_failure"`: passed
- `python -m pytest tests/test_domain_track.py -k "held_segments_do_not_hide_detector_keyframe_span"`: passed
- `python -m pytest tests/test_mask_continuity.py -k "held_segment_does_not_hide_accepted_detector_keyframes"`: passed

### Not fully verified in this pass
- Desktop Node test runner is still blocked in this sandbox with `spawn EPERM`, so the frontend test suite was not re-run end-to-end here.
- Preview fidelity for `expand_px` / `feather` is still not guaranteed to match backend export pixel-for-pixel. The verified manual flow did not expose a blocking issue, but the preview remains an approximation.

## What Was Fixed In This Pass (April 9, 2026 — Python ABI mismatch in review-runtime)

### 症状
model integrity 修正 (コミット `fa4c4e3`) 適用後にも関わらず、review package で detect を実行すると再び `Detection worker was no longer running and the job was marked interrupted.` が発生。

### 真因
model 破損でも同期不良でもなく、**review-runtime の Python と vendor packages の ABI mismatch**:

- `review-runtime/python/` に Python **3.14** がコピーされていた
- `review-runtime/backend/vendor/` は numpy 2.4.4 / onnxruntime-gpu 1.24.4 が **cp312 ABI** (Python 3.12 専用)
- detect worker が `bootstrap_backend_environment()` → `import numpy` の時点で `ImportError`
- worker プロセスが failed status を書き出す前に即死
- `reconcile_job_state()` が worker PID dead を検出し "interrupted" 判定

### 発生経緯
- `prepare-review-runtime.ps1` は `python -c "sys.executable"` でシステム Python を使っていた
- 開発機のシステム Python が 3.12 → 3.14 にアップグレードされた際、script は黙って 3.14 をコピーした
- vendor (cp312) と Python (3.14) が矛盾したまま review-runtime が生成された
- vendor ABI 整合性の検証機構が無かったため、silent failure として発覚が遅れた

### 恒久対策 — `scripts/prepare-review-runtime.ps1`

#### 1. ABI-driven Python selection
vendor 内の `*.cp3XX-win_amd64.pyd` ファイル名から ABI (`cp312` など) を検出し、それに合致する Python minor バージョン (`3.12`) を自動選択。

#### 2. Python 解決優先順位
1. `$env:AUTO_MOSAIC_REVIEW_PYTHON` (明示的 override)
2. `py.exe -<target minor>` (py launcher)
3. 標準インストール先 (`%LOCALAPPDATA%\Programs\Python\Python3XX\python.exe` など)
4. PATH の `python`

#### 3. ABI 整合性検証 (fail-fast)
選択された Python の `sys.version_info.minor` と vendor ABI が一致しない場合、`throw` で**ディレクトリを削除する前に** preparation を中止。既存 review-runtime は保護される。

#### 4. manifest 拡張
`manifest.json` に次を追加:
- `python_minor` — `"3.12"` など
- `python_source` — 選択された python.exe の絶対パス
- `vendor_abi` — `"cp312"` など
- `abi_check_passed` — 常に `true` (失敗時は manifest が書き換えられない)

### 検証
- `vendor_abi = cp312` を自動検出
- py launcher 経由で `C:\Users\bbbtg\AppData\Local\Programs\Python\Python312\python.exe` を選択
- ABI 整合性チェック通過
- bootstrap → numpy/onnxruntime import → doctor 整合性チェック → 320n.onnx の InferenceSession 作成まで完全動作
- `AUTO_MOSAIC_REVIEW_PYTHON` を Python 3.14 に強制指定したテスト: ディレクトリを消さずに `throw` で停止することを確認

### Files changed
- `scripts/prepare-review-runtime.ps1`
- `apps/desktop/src-tauri/resources/review-runtime/` (regenerated with Python 3.12)
- `AutoMosaic-Review/review-runtime/` (robocopy mirror of staging)

---

## What Was Fixed In This Pass (April 9, 2026 — model integrity spec fixed)

### 結論
detect failure の直接原因は UI や Phase 4 continuity 実装ではなく、
**破損した `320n.onnx` による detect worker の native crash** だった。

### 発生メカニズム
1. GitHub Release の取得で `browser_download_url` 側を使った結果、HTML リダイレクト内容が返るケースがあった
2. ダウンロード処理に Content-Type / header / hash 検証がなく、HTML が `.onnx` として保存された
3. doctor はファイル存在のみで取得済み扱いしていた
4. detect worker が破損 ONNX を onnxruntime で開こうとして native crash
5. worker は failed を書かずに死亡し、polling 側で `interrupted` として回収された

### 恒久対策

#### 1. catalog 正本化 (`model_catalog.py`)
`ONNX_MAGIC_BYTES` を追加・公開。`ModelSpec` に以下フィールドを追加:
- `model_id` — ファイル名と無関係な安定識別子
- `source_type` — `"github_release_asset"` / `"huggingface"` / `"derived"` / `"none"`
- `valid_magic_bytes` — `ONNX_MAGIC_BYTES` を設定（`.pt` など形式不定のモデルは `None` でスキップ）
- `browser_download_url` の生文字列は正本にしない。常に `api.github.com/repos/…/assets/<ID>` を使う。

#### 2. 2-stage download (`fetch_models.py`)
モデル取得は必ず以下で行う:
- `.download` 一時ファイルへ保存
- `_verify_downloaded_file()` で全チェック（サイズ → HTML → magic bytes → expected_size → sha256）
- 通過時のみ `rename()` で正式配置（失敗時は一時ファイルを削除、ターゲット未更新）
- skip-if-exists は `_verify_downloaded_file` 通過時のみ適用。失敗時は再ダウンロード。

#### 3. integrity-based doctor (`doctor.py`)
モデル判定は existence base ではなく integrity base に変更:
- `"missing"` — ファイルなし
- `"broken"` — ファイルあり、整合性チェック失敗
- `"installed"` — ファイルあり、全チェック通過

`exists=true` でも整合性が崩れていれば `broken` 扱い。レスポンスに `"status"` フィールドを追加（`"exists"` / `"valid"` は後方互換で保持）。

#### 4. detect preflight guard (`start_detect_job.py`)
detect 実行前に required model の整合性を確認:
- `broken` → `MODEL_BROKEN` で即 failure、worker 未起動
- `missing` → `MODEL_MISSING` で即 failure、worker 未起動

### Files changed
- `apps/backend/src/auto_mosaic/infra/ai/model_catalog.py`
- `apps/backend/src/auto_mosaic/api/commands/doctor.py`
- `apps/backend/src/auto_mosaic/api/commands/fetch_models.py`
- `apps/backend/src/auto_mosaic/api/commands/start_detect_job.py`
- `apps/backend/tests/test_model_integrity.py` (新規、25テスト)
- `apps/backend/tests/test_cli_smoke.py` (既存テスト2件を valid ONNX バイトに更新)

### 残課題
- `apps/desktop/src-tauri/resources/review-runtime/` が未同期（`npm.cmd run review:runtime` 要実行）
- 以下のモデルは `expected_size` / `expected_sha256` 固定が未完:
  - `640m.onnx`
  - `erax_nsfw_yolo11s.pt`
  - `erax_nsfw_yolo11s.onnx`（変換生成物のため固定不可）
  - `sam2_tiny_encoder.onnx` / `sam2_tiny_decoder.onnx`

---

## What Was Fixed In This Pass (April 8, 2026 — ONNX validity + size/hash check)

### Root cause
After the previous pass (URL repair + HTML guard), a corrupted `.onnx` file could still pass
`_check_model_file` if it happened to be large enough and not start with HTML bytes (e.g. a
partially downloaded binary, or a file from a wrong URL that returns valid non-HTML binary).

### Fixes applied

**P1 — ONNX protobuf magic bytes check (`doctor.py`)**
- Added `_ONNX_PROTO_FIRST_BYTES` frozenset: all valid field tags for the ONNX ModelProto
  protobuf first byte (0x08 ir_version, 0x12 producer_name, 0x3a graph, 0x42 opset_import, etc.).
- `_check_model_file` now rejects any `.onnx` file whose first byte is not in this set.

**P2 — size + SHA-256 metadata in catalog (`model_catalog.py`, `doctor.py`)**
- Added `expected_size: int | None` and `expected_sha256: str | None` to `ModelSpec`.
- `320n.onnx` now has known values: size=12150158, sha256=c15d8273…
- `_check_model_file(path, spec)` now takes the spec and applies (in order, cheapest first):
  1. Minimum size (existing)
  2. Exact expected_size match (new — fast, avoids reading the file)
  3. HTML signature bytes (existing)
  4. ONNX protobuf first byte (new)
  5. SHA-256 hash (new — only when expected_sha256 is set)
- All other models leave expected_size/expected_sha256 as None (values unknown).

### Files changed
- `apps/backend/src/auto_mosaic/infra/ai/model_catalog.py`
- `apps/backend/src/auto_mosaic/api/commands/doctor.py`
- `apps/desktop/src-tauri/resources/review-runtime/…` (re-synced via `review:runtime`)

## What Was Fixed In The Pass Before That (April 8, 2026 — 不足モデル取得ボタン修正)

### Root cause
The "不足モデルを取得" button's call chain was intact end-to-end, but the download
destination was silently corrupted:

- The GitHub `browser_download_url` for NudeNet release assets now redirects to
  `github.com/login` (HTML, 44 KB) instead of the binary file.
- `_download_to_path` had no Content-Type guard, so the HTML page was written as
  the `.onnx` file. The job reported success, doctor saw "file exists", and the UI
  showed the model as available — even though the file was invalid.

### Fixes applied

**P0 — URL repair + download headers (`model_catalog.py`, `fetch_models.py`)**
- Replaced GitHub `browser_download_url` with GitHub API asset URLs:
  - `320n.onnx` → `https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176831997`
  - `640m.onnx` → `https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/176832019`
- Added `request_headers` field to `ModelSpec` (frozen dataclass).
  NudeNet API URLs need `Accept: application/octet-stream` to return binary.
- `_download_to_path` now builds a `urllib.request.Request` with per-spec headers
  instead of calling `urlopen(url)` directly.
- Added Content-Type guard: raises `ValueError` immediately when server returns
  `text/html`, preventing any HTML page from being saved as a model file.
- Hugging Face URLs (`erax_v1_1.pt`, SAM2) confirmed working; no URL change needed.

**P1 — model validity in doctor (`doctor.py`)**
- Added `_check_model_file(path)` helper: returns `(exists, valid)`.
  A file is invalid if it is < 1 KB or begins with HTML signature bytes.
- `doctor` now reports `"exists": exists and valid` and includes a `"valid"` field.
  An HTML-corrupted model file is now reported as missing, not available.

**P2 — doctor refresh on fetch failure (`App.tsx`)**
- When a `fetch_models` job ends in a terminal failure state, `runDoctor()` is now
  called so the UI reflects whatever partial progress occurred.

### Files changed
- `apps/backend/src/auto_mosaic/infra/ai/model_catalog.py`
- `apps/backend/src/auto_mosaic/api/commands/fetch_models.py`
- `apps/backend/src/auto_mosaic/api/commands/doctor.py`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src-tauri/resources/review-runtime/…` (re-synced via `review:runtime`)

## What Was Fixed In The Previous Pass
- Reintegrated the remaining editor surfaces into the recovered shell:
  - `apps/desktop/src/components/CanvasStagePanel.tsx`
  - `apps/desktop/src/components/KeyframeDetailPanel.tsx`
- Rebuilt `apps/desktop/src/App.tsx` as clean UTF-8 source after partial patching hit Windows command-length limits.
- Restored timeline, canvas, track detail, and keyframe detail to a shared selection model.
- Kept job responsibilities split out of `App.tsx`.
- Fixed a backend runtime-job cancellation race so stale `cancelling` jobs do not block progress forever.

## Current Frontend Shape
- `App.tsx` is a shell responsible for:
  - project open/save/new
  - preview source setup
  - selection coordination
  - shared job launch and polling
  - high-level activity/error status
- The four editor faces are now present together again:
  - timeline: `TimelineView.tsx`
  - canvas: `CanvasStagePanel.tsx`
  - track detail: `TrackDetailPanel.tsx`
  - keyframe detail: `KeyframeDetailPanel.tsx`

## Current Job UX Behavior
- The Job Panel is still the common progress surface.
- Runtime jobs, detect jobs, and export all appear in the same panel.
- Cancel is request-based.
- Runtime-job cancel avoids overwriting already-terminal states.
- `fetch_models` failure now also triggers `runDoctor()` so the model panel refreshes.

## Verified
- `npm.cmd run build` in `apps/desktop`: passed (April 8 2026)
- `npm.cmd run check:mojibake` in `apps/desktop`: passed
- `npm.cmd test` in `apps/desktop`: passed (`21/21`)
- `python -m pytest tests\\test_cli_smoke.py` in `apps/backend`: passed (`62 passed`)
- `cargo check` in `apps/desktop/src-tauri`: passed
- `npm.cmd run review:runtime`: synced all Python changes to resources review-runtime
- `_check_model_file` unit tests (HTML/tiny/real/missing): all 4 cases pass
- GitHub API URLs for 320n.onnx and 640m.onnx confirmed reachable and returning
  `application/octet-stream` (12 MB and 103 MB respectively)
- Hugging Face URLs for erax, SAM2 confirmed reachable
- ONNX protobuf first-byte set manually verified against ModelProto field encoding rules
- 320n.onnx size (12150158) and SHA-256 verified from prior download

## Not Fully Verified
- GPU/CUDA path in the review-runtime was not exercised.
- Actual end-to-end model download (320n.onnx via new API URL, through Tauri → Python worker) has not been driven in a Tauri window session.
- Frontend Node test runner remains sandbox-sensitive (`spawn EPERM`) in this environment, so `npm.cmd test` was not re-run in this pass.

## Known Risks
- GitHub API asset IDs (176831997, 176832019) are stable for existing releases but
  will break if NudeNet publishes a new release and deprecates v3.4-weights. When
  that happens, update `model_catalog.py` with new asset IDs and the new expected_size/expected_sha256.
- `check:mojibake` is still a heuristic guard, not a full encoding validator.
- The review-runtime prepare step must be re-run whenever backend Python files change.
- `MosaicPreviewCanvas` now matches render span semantics, but it is still a frontend approximation and does not guarantee byte-for-byte parity with backend export for blurred / dilated masks.
- SAM2, erax, and 640m.onnx have no expected_size/expected_sha256 in the catalog (values
  were not available to hash locally). Doctor will still catch HTML/size/ONNX-magic corruption
  for those files, but will not catch a byte-flipped binary of the correct size.
- SHA-256 check reads the entire file on every `doctor` invocation. For 320n.onnx this is
  ~12 MB — acceptable. If larger models gain hash entries in the future, consider caching
  the validated state to avoid repeated reads.

## Do Not Do
- Do not restore the old corrupted `App.tsx`.
- Do not reintroduce Japanese UI literals directly into giant JSX blocks.
- Do not send `asset.localhost` URLs to the backend.
- Do not put logs on backend `stdout`.
- Do not bypass the shared job helpers for new long-running work.
- Do not regress runtime-job cancel back into a state where terminal jobs can be overwritten to `cancelling`.
- Do not ship a review build without re-running `npm.cmd run review:runtime` after any backend Python change.
- Do not judge a model as installed by file existence alone — always use `_check_model_file` (integrity-based).
- Do not promote a temp download file to its final name before `_verify_downloaded_file` passes.
- Do not use `browser_download_url` as the download URL — always use `api.github.com/repos/…/assets/<ID>`.
- Do not let `prepare-review-runtime.ps1` silently pick a Python whose minor version differs from the vendor ABI. The ABI check must remain fail-fast.
- Do not hand-edit `review-runtime/python/` to swap interpreters without re-running the ABI check.

## Next Logical Step
1. Continue moving editor-specific orchestration out of `App.tsx` into small hooks or controller modules before adding more editing features.
2. Implement remaining P2 items from `docs/project/unimplemented-features.md`: onion skin, AI detect performance work, export queue, and E2E tests.
3. If backend Python changes are intended for review builds, re-run `npm.cmd run review:runtime`.
4. (Backlog) Add `expected_size` + `expected_sha256` for `640m.onnx`, SAM2, erax once those files are available to hash locally.
