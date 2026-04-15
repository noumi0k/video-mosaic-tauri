# PySide6同等編集体験チェックリスト

最終更新: 2026-04-15

この文書は、Tauri版Auto MosaicでユーザーがPySide6版と同等の編集体験を得るための実装指針です。
PySide6版のUIをそのまま移植するための文書ではありません。Tauri版では、既存の設計方針である「backend project stateをsource of truthにする」「mask trackを中心に扱う」「manual editを保護する」「長時間処理をjob化する」を優先します。

安定化フェーズ完了後は、この文書を今後の開発ロードマップの中核として扱います。新規開発は、原則としてこの文書のチェックリストIDと開発フェーズに紐づけて進めます。

## 参照元

- Tauri現状: `docs/engineering/current-implementation.md`
- Tauri未実装一覧: `docs/project/unimplemented-features.md`
- 直近handoff: `docs/project/ai-handoff.md`
- PySide6実装参照元: `H:\mosicprogect\mosic2`
- PySide6側は読み取り専用で扱う。Tauri側の計画やチェックリストはこのリポジトリ内にのみ作成する。
- UIはPySide6版の再現を目標にせず、PySide6版を機能要件と編集フローの参照元として扱い、Tauri版ではWeb UIとして最適な情報設計・操作導線を優先する。
- PySide6版のUI構成、ボタン配置、メニュー構成は [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) を参照する。

## 判断ルール

PySide6版にある機能をTauri版へ入れるかは、次の基準で判断する。

| 区分 | 判断基準 | 扱い |
| --- | --- | --- |
| 必須 | ないと「動画を開く、検出、手直し、保存、書き出し」の実用フローが止まる | 最優先で実装 |
| 安全性 | ユーザー編集の喪失、誤書き出し、クラッシュ後の復旧不能を防ぐ | 必須に準じる |
| 編集効率 | 編集時間を大きく減らすが、なくても完了できる | 安定化後に実装 |
| 品質向上 | 表示、ショートカット、説明文、操作感の改善 | 主フロー確定後に実装 |
| 保留 | PySide6版でも実験扱い、使用頻度が低い、Tauri版設計に直接合わない | 別計画に分離 |
| 移植しない | PySide6固有UI、Qt thread設計、Tauri版のdomain ruleを歪める実装 | 採用しない |

## 完了判定の共通条件

各機能は、単にUIが見えるだけでは完了としない。最低限、次を満たすこと。

- backend domain ruleが明示されている。
- frontendはbackend stateの投影であり、独自に不変条件を再定義しない。
- raw local pathとdisplay URLを混在させない。
- `stdout`はJSON専用、ログや診断は`stderr`へ出す。
- manual track、manual keyframe、user edited stateを自動処理で消さない。
- CPU fallbackを壊さない。
- jobのprogress、cancel、failed、interrupted、completedの扱いが定義されている。
- 最小限のbackend testまたはfrontend testがある。
- review buildへ含めるbackend変更では`npm.cmd run review:runtime`の要否を報告する。

## ユーザー体験ゴール

Tauri版で達成したい編集体験は次の通り。

1. ユーザーが動画を開く。
2. モデル状態、GPU/CPU状態、検出条件が分かる。
3. 全体検出、範囲検出、現在フレーム検出を選べる。
4. 検出結果がtrackとして残り、消えた対象も不自然に消えない。
5. ユーザーがcanvasとtimelineでmask trackを直接修正できる。
6. 手動修正したtrackやkeyframeは再検出で勝手に壊れない。
7. 危険フレームを見つけ、確認済みとして管理できる。
8. 保存、再読込、クラッシュ復旧で編集状態を失わない。
9. 書き出し設定、進捗、キャンセル、失敗時fallbackが分かる。
10. 書き出した動画に、意図したframe範囲とtrackだけモザイクが入る。

## 機能チェックリスト

### A. プロジェクト、保存、復旧

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| A-01 | 動画を開く | 実装済み | backendへ渡すのはraw local path。display URLをprojectに保存しない。動画metadataをread modelに反映する。 |
| A-02 | project save/load/save as | 実装済み | schema v2を保存し、PySide6 project v1を安全にmigrationできる。manual source、segments、export presetを失わない。 |
| A-03 | dirty guard | 実装済み | 未保存変更がある状態でnew/open/open video/closeを実行すると確認を出す。保存成功後はdirtyを解除する。 |
| A-04 | autosave | 一部実装済み | 保存済みprojectに対して定期保存する。未保存projectでは勝手に不明な場所へ保存しない。 |
| A-05 | file-backed recovery | 未完了 | `localStorage`依存からbackend/file-backedへ移す。project_id単位でrecoveryを識別し、起動時に復元、破棄、後で確認を選べる。 |
| A-06 | atomic write | 要確認 | project保存、recovery保存、queue保存は一時ファイルへ書いてからreplaceする。破損ファイルはアプリ起動を止めず、復旧候補として扱う。 |

PySide6参照:

- `app/infra/storage/project_store.py`
- `app/infra/storage/recovery_store.py`
- `app/ui/recovery_dialog.py`

### B. 検出、モデル、GPU/CPU

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| B-01 | 全体検出 | 実装済み | replaceable detector trackだけを置換する。manual/user edited/user locked trackは既定で保護する。 |
| B-02 | 全体検出前の上書き確認 | 実装済み | manual保護、全上書き、キャンセルの3択を出す。backendにも`overwrite_manual_tracks`相当の明示フラグを渡す。 |
| B-03 | 範囲検出 | 実装済み | I/O markerまたは指定範囲だけ検出し、範囲外keyframeを保持する。manual keyframeを既定で保護する。 |
| B-04 | 現在フレーム検出 | 一部実装済み | 現在フレームだけ検出できる。既存trackへのmergeか新規track作成かのルールをbackend側で決める。 |
| B-05 | 未検出ゾーンから検出 | 未完了 | timeline上の空白または危険区間から範囲検出を開始できる。これは便利機能扱いで、B-01からB-04の後に実装する。 |
| B-06 | detector backend選択 | 一部実装済み | NudeNet 320n、NudeNet 640m、EraX、複合backendの可用性をモデル状態から判定する。カテゴリ非対応backendは選択時に説明する。 |
| B-07 | category選択 | 一部実装済み | backendが対応するカテゴリだけを選べる。未対応カテゴリはUIだけでなくbackend payloadでも無効化する。 |
| B-08 | model integrity | 実装済み | existenceだけでinstalled扱いにしない。HTML、LFS pointer、tiny file、ONNX magic、size、hashを確認する。 |
| B-09 | EraX setup | 一部実装済み | `.pt`取得、ONNX変換、ultralytics未導入時のエラー、変換jobのprogress/cancelを扱う。 |
| B-10 | GPU provider選択 | 実装済み | CUDA、DirectML、CPU fallbackの実利用状態をprogressやdoctorに出す。GPU不可でもstartupを止めない。 |
| B-11 | VRAM saving/batch tuning | 後回し | PySide6の`vram_saving_mode`相当は便利機能。まず検出が安定してから、inference resolutionとbatch sizeの自動調整を入れる。 |

PySide6参照:

- `app/domain/services/detection_service.py`
- `app/domain/services/tracking_service.py`
- `app/gpu_config.py`
- `app/domain/engine_registry.py`
- `app/domain/model_presets.py`
- `app/ui/gpu_settings_dialog.py`
- `app/ui/model_management_dialog.py`

### C. Track continuity、merge、manual保護

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| C-01 | persistent mask track | 実装済み | 検出結果は孤立keyframeではなくtrackとして扱う。track_id、source、state、segmentsを持つ。 |
| C-02 | track stitching | 実装済み | 一時的に途切れた同一対象を一定gap内で結合する。誤結合を避けるためlabel group、空間距離、面積、aspectを評価する。 |
| C-03 | ephemeral track filter | 実装済み | 短すぎる自動trackを除外する。ただしmanual/user locked trackは除外しない。 |
| C-04 | predicted/held/interpolated state | 実装済み | UI表示用とexport用の解決を分ける。exportではrenderable segment外を描画しない。 |
| C-05 | manual anchor fallback | 実装済み | manual keyframe後の自動検出が破綻した場合、anchor shapeを使って補正する。manual keyframe自体は変更しない。 |
| C-06 | 範囲検出merge | 実装済み | 範囲内のみIoU mergeし、範囲外keyframeを保持する。完全交差やID swapの既知リスクをテストで文書化する。 |
| C-07 | inactive reactivation | 要検討 | 長時間見失ったtrackを再検出で復活させるかは誤結合リスクがある。PySide6の挙動をそのまま移植せず、review後に判断する。 |

PySide6参照:

- `app/domain/services/tracking_service.py`
- `app/domain/services/continuity_service.py`
- `app/domain/services/mask_edit_service.py`

### D. Canvas編集

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| D-01 | ellipse移動 | 実装済み | dragで現在frameのmanual keyframeを作成または更新する。既存manual keyframeを意図せず消さない。 |
| D-02 | ellipse resize | 実装済み | corner handleでbboxを変更する。aspect固定の有無を明確にする。frameごとのmanual keyframeとして保存する。 |
| D-03 | polygon頂点移動 | 実装済み | 頂点dragでpointsとbboxを更新する。self-intersectionや点数不足の警告を出せる。 |
| D-04 | polygon頂点追加 | 一部実装済み | context menuに加え、PySide6相当のedge double-click追加を実装する。追加位置は最寄りedge上、中心部clickでは追加しない。 |
| D-05 | polygon頂点削除 | 一部実装済み | context menuまたはAlt+clickで削除する。3点未満になる削除は拒否する。 |
| D-06 | polygon smooth | 未完了 | 選択頂点または全頂点に平滑化を適用する。manual keyframeとして保存し、Undo対象にする。 |
| D-07 | polygon decimate | 未完了 | 近接頂点を間引く。3点未満、極端な形状崩壊、self-intersectionを避ける。 |
| D-08 | contour follow | 後回し | PySide6の`ContourFollowService`相当。編集効率機能なので、主フロー安定後に扱う。 |
| D-09 | onion skin | 後回し | 前後keyframe shapeの半透明表示。PySide6側でも必要性再評価の扱いがあるため、必須にしない。 |
| D-10 | diff overlay | 後回し | 変更差分表示。実験機能として扱い、初期の同等体験条件から外す。 |

PySide6参照:

- `app/ui/preview_canvas.py`
- `app/domain/services/mask_edit_service.py`
- `app/domain/services/contour_follow_service.py`

### E. Timeline、track list、navigation

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| E-01 | timeline track表示 | 実装済み | trackごとのbar、keyframe marker、segment state、playhead、zoomを表示する。 |
| E-02 | timeline縦スクロール | 実装済み相当 | track数が増えても全行にアクセスできる。selected trackでlayoutがずれない。 |
| E-03 | keyframe source marker | 実装済み | manual、detector、interpolated、predicted、anchor fallbackを視覚的に区別する。 |
| E-04 | danger marker | 一部実装済み | dangerous frame markerをtimelineに表示し、クリックまたは近接snapで該当frameへ移動できる。確認済みmarkerは弱く表示する。 |
| E-05 | I/O marker | 実装済み | Iで開始、Oで終了。範囲検出とtimeline表示で同じ範囲を使う。 |
| E-06 | track visibility | 実装済み | 表示/非表示はpreviewとtimeline表示に効く。export対象とは独立させる。 |
| E-07 | track export enabled | 一部実装済み | export対象から除外できる。非表示とは別状態としてUIで明確に区別する。 |
| E-08 | track context menu | 一部実装済み | keyframe追加、複製、split、表示切替、export対象切替、削除を提供する。 |
| E-09 | track split | 未完了または要確認 | 指定frameでtrackを左右に分割し、split frameをmanual keyframeとして両側に持たせる。 |
| E-10 | track ordering DnD | 後回し | PySide6でも保留扱い。必要になるまで実装しない。 |
| E-11 | transport UI | 一部実装済み | HTML video controlsだけに依存せず、skip/step/play/pauseを編集UI上で一貫して操作できる。 |

PySide6参照:

- `app/ui/timeline_widget.py`
- `app/ui/track_list_panel.py`
- `app/ui/display_state.py`

### F. Inspector、style、keyframe詳細

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| F-01 | track detail | 実装済み | label、state、source、visible、export enabled、keyframe count、rangeを表示する。 |
| F-02 | keyframe detail | 実装済み | shape_type、bbox、points、confidence、source、rotation、opacity、expand_px、featherを確認、編集できる。 |
| F-03 | style interpolation | 実装済み | expand_px、feather、rotation、opacityをkeyframe間で補間できる。 |
| F-04 | validation message | 一部実装済み | polygon点数不足、self-intersection、bbox不正、範囲外値をユーザーに分かる文言で示す。 |
| F-05 | terminology polish | 未完了 | `held`、`uncertain`、`predicted`などdomain語をUI向け日本語に変換する。domain名をそのまま露出しない。 |

PySide6参照:

- `app/ui/property_panel.py`
- `app/ui/i18n.py`
- `app/domain/services/mask_edit_service.py`

### G. Undo、Redo、history

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| G-01 | Undo/Redo | 実装済み | project mutation前後のsnapshotを正しく持つ。検出結果適用、canvas drag、inspector編集、track削除もUndo対象にする。 |
| G-02 | Undo/Redo件数表示 | 実装済み相当 | UIから戻せる状態が分かる。ボタンdisabled stateが正しい。 |
| G-03 | 操作名表示 | 後回し | 「頂点移動」「キーフレーム追加」など直近操作名を表示する。便利機能扱い。 |
| G-04 | history tree | 保留 | PySide6側でも保留。Tauri版初期同等体験には含めない。 |

PySide6参照:

- `app/domain/services/history_service.py`

### H. Danger warning、review workflow

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| H-01 | dangerous frame detection | 実装済み | long gap、area jump、predicted sectionなどを検出する。検出ロジックはfrontendだけでなくbackend移行も検討する。 |
| H-02 | danger panel | 一部実装済み | 左またはreview panelに常時表示し、確認済み、未確認、解除を管理できる。 |
| H-03 | row click seek | 一部実装済み | warning行クリックで該当frameへ移動する。確認済みでも移動できる。 |
| H-04 | timeline marker連動 | 一部実装済み | panel確認状態とtimeline marker表示が同期する。確認済みはグレーまたは低opacityにする。 |
| H-05 | export前未確認チェック | 未完了 | 未確認dangerが残る場合、export前に警告する。全確認済みなら通常exportへ進む。 |
| H-06 | 確認状態の永続化 | 要検討 | `confirmedDangerFrames`をproject documentに保存するか、review session stateにするかを決める。保存する場合はbackend schemaに入れる。 |

PySide6参照:

- `app/domain/services/danger_detector.py`
- `app/ui/danger_warnings_section.py`
- `app/ui/dangerous_frames_dialog.py`

### I. Export、queue、進捗

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| I-01 | FFmpeg pipe export | 実装済み | frameごとにrendered maskを適用してpipeへ渡す。失敗時はOpenCV fallbackを使う。 |
| I-02 | segment-aware render | 実装済み | renderable segment/stateに基づいて出力する。単純なlast-keyframe holdへ戻さない。 |
| I-03 | resolution preset | 実装済み | source、720p、1080p、4Kを選べる。入力より大きいupscaleを許可しないか、明示警告する。 |
| I-04 | bitrate mode | 一部実装済み | auto、manual、target file sizeの扱いを整理する。Tauri版の初期必須はauto/manualまででよい。 |
| I-05 | audio mode | 実装済み | mux_if_possible/video_onlyを扱う。PySide6のre-encode相当は後回しでよい。 |
| I-06 | GPU encoder selection | 未完了 | h264_nvenc、h264_qsv、h264_amfの検出と選択を行う。失敗時はCPU encoderへfallbackし、warningに残す。 |
| I-07 | export progress | 実装済み | preparing、rendering、encoding、muxing、completed、failed、cancelledを表示する。 |
| I-08 | export cancel | 実装済み | cancel flagをworkerが見て停止し、一時ファイルを片付ける。terminal jobをcancellingへ戻さない。 |
| I-09 | export queue | 未完了 | 複数jobを追加し、順次実行する。queued/running/completed/canceled/error/interruptedを扱う。 |
| I-10 | export queue永続化 | 未完了 | completedを永続化しない。runningは起動時にinterruptedへ変換する。壊れたqueue fileで起動を止めない。 |
| I-11 | export preset保存 | 後回し | PySide6のuser preset保存/削除相当。まずqueueと安全なexportを優先する。 |

PySide6参照:

- `app/domain/services/export_service.py`
- `app/domain/models/export_job.py`
- `app/infra/storage/export_queue_store.py`
- `app/ui/export_settings_dialog.py`
- `app/ui/export_queue_dialog.py`

### J. Shortcut、ヘルプ、表示文言

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| J-01 | 編集ショートカット | 実装済み | Ctrl+S、Ctrl+Z、Ctrl+Shift+Z、Space、Arrow、K、Shift+K、I、O、H、N、Deleteを維持する。 |
| J-02 | 追加ショートカット | 一部実装 | Ctrl+Shift+D、Ctrl+Shift+R、Ctrl+M、Ctrl+E、Home、End、Shift+Home、Shift+Endの採用を検討する。 |
| J-03 | F1 help | 未完了 | `window.alert`ではなく検索可能なmodalにする。shortcut registryを単一情報源にする。 |
| J-04 | 日本語UI統一 | 未完了 | ユーザー向け文言は`uiText`へ集約する。英語ラベル、domain語、開発者向け説明をUIへ残さない。 |
| J-05 | layout安定性 | 継続 | 状態変化、hover、marker、警告件数で主要panelやtimeline rowが跳ねない。 |

PySide6参照:

- `app/ui/shortcuts.py`
- `app/ui/shortcut_help_dialog.py`
- `app/ui/i18n.py`

### K. 検証、レビュー、配布前確認

| ID | 機能 | Tauri現状 | 達成条件 |
| --- | --- | --- | --- |
| K-01 | backend smoke | 実装済み | CLI JSON contract、project mutation、detect、exportを最小fixtureで確認する。 |
| K-02 | frontend unit | 実装済み | selection、shape resolver、danger、job progress、save workflowを確認する。 |
| K-03 | Tauri E2E | 未完了 | 実ウィンドウまたはreview package相当でopen video、detect、edit、save/load、exportを通す。 |
| K-04 | crash recovery E2E | 未完了 | dirty projectのrecovery snapshot作成、起動時復元、破棄、保存後cleanupを確認する。 |
| K-05 | export output検証 | 一部実装済み | 出力動画の対象frame/対象ROIだけモザイクが入っていることをpixel差分で確認する。 |
| K-06 | model missing/broken | 実装済み | missing、broken、installedをUIとbackendで一致させる。broken modelでworkerを起動しない。 |

PySide6参照:

- `tests/e2e/`
- `tests/test_export_service.py`
- `tests/test_recovery_store.py`
- `tests/test_model_management_dialog.py`

## 初期同等体験の必須スコープ

最初の「PySide6同等編集体験」として必須にするのは次の範囲。

- 動画open、project save/load、autosave、dirty guard
- 全体検出、範囲検出、現在フレーム検出
- detector backend選択、カテゴリ選択、model integrity
- track表示、選択、表示切替、export対象切替
- ellipse/polygonの直接編集
- keyframe追加、削除、複製、移動
- Undo/Redo
- danger warning表示、確認、timeline marker、export前未確認警告
- FFmpeg export、cancel、progress、audio mux、CPU fallback
- file-backed recovery
- 最小E2E

初期同等体験から外すもの。

- onion skin
- diff overlay
- history tree
- track order drag-and-drop
- local retraining
- teacher dataset保存
- installer/updater
- PySide6のQt UI構造そのもの

## 今後の開発フェーズ票

| Phase | 名前 | 目的 | 主な作業 | 完了条件 |
| --- | --- | --- | --- | --- |
| 0 | 現状固定 | 実装済み範囲と差分を固定する | この文書を作業基準にする。古いPySide6比較資料は参考扱いにする。 | 次にやる機能をこの文書のIDで説明できる。 |
| 1 | 実操作フロー検証 | 追加実装前に主フローの破綻を見つける | Tauri windowでopen video、detect、canvas edit、save/load、exportを実行する。 | 人間またはE2Eで一連の流れが1回通る。止まった箇所はbugとして記録する。 |
| 2 | Review安全性 | 誤書き出しと編集喪失を防ぐ | H-02からH-06、A-05、A-06を実装する。 | 未確認dangerがexport前に止まる。crash後に復旧候補が出る。 |
| 3 | Export運用 | 書き出しを実用レベルにする | I-04、I-06、I-09、I-10を実装する。 | 複数exportをqueueでき、再起動後にinterrupted jobが分かる。GPU失敗でCPU fallbackする。 |
| 4 | 編集効率 | PySide6で便利だった編集操作を補う | D-04、D-05、D-06、D-07、E-08、E-09、J-02を実装する。 | polygon編集、track操作、ショートカットで通常編集が速くなる。Undo対象になる。 |
| 5 | E2Eと回帰防止 | 同等体験を壊さない状態にする | K-03からK-05を実装する。review package起動後の主要flowをテストする。 | open/detect/edit/save/export/recoveryの代表flowが自動または半自動で検証できる。 |
| 6 | UI polish | 使いにくさと文言の粗さを取る | J-03、J-04、J-05、transport UI、status label整理を行う。 | 主要UIに英語/内部用語が残らず、状態変化でlayoutが崩れない。 |
| 7 | 保留機能再評価 | 必要な便利機能だけ採用する | onion skin、diff overlay、history tree、track order DnDを再評価する。 | 採用/不採用/別計画を明文化する。 |
| 8 | 別計画 | 製品配布、学習系、大規模機能を扱う | teacher dataset、local retraining、installer/updaterを別docsで計画する。 | 編集体験改善とは別のロードマップに分離されている。 |

## 直近の推奨順序

1. Phase 1の実操作フロー検証を実施する。
2. 見つかったblockerを先に直す。
3. `H-05 export前未確認チェック`を完了する。
4. `A-05 file-backed recovery`を実装する。
5. `I-09/I-10 export queue`を実装する。
6. `K-03 Tauri E2E`を追加する。
7. その後にpolygon編集効率、shortcut help、GPU encoderを進める。

## AIエージェントへ依頼するときの単位

AIエージェントには、機能名だけでなくこの文書のIDと完了条件を渡す。

良い依頼例:

```text
H-05を実装してください。
要件:
- confirmedDangerFramesにないdanger warningが残る場合、export前に警告する。
- 全て確認済みなら警告せずexportへ進む。
- danger warningの確認状態はpanelとtimeline markerで一致させる。
- frontend testを追加する。
```

避ける依頼例:

```text
PySide6と同じdanger warningを移植してください。
```

理由:

- PySide6のUI構造をそのまま移すとTauri版の責務分離が崩れる。
- Tauri版ではbackend contract、project schema、job stateを先に決める必要がある。
- 「同じ見た目」より「同じ編集結果、安全性、復旧性」を優先する。

## 実装時の報告フォーマット

各slice完了時は次を報告する。

- 閉じたチェックリストID
- 変更したファイル
- backend contract変更の有無
- project schema変更の有無
- 実行したテスト
- PySide6版とまだ違う点
- 残るリスク

## 採用しない方針

- PySide6版のQt widget構成をTauriへ写経しない。
- UI都合でbackend domain ruleを曲げない。
- `asset.localhost`やdisplay URLをbackend stateへ保存しない。
- 全体再検出でmanual keyframeを黙って消さない。
- exportを単純なlast-keyframe holdへ戻さない。
- GPU/CUDA失敗をstartup blockerにしない。
- 実験扱いのonion skin/diff overlayを必須機能として扱わない。
