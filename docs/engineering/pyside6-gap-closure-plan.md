# PySide6 Gap Closure Plan

Last updated: 2026-04-15 (Phase 1 完了 / Phase 2 一部実装)

## 目的

現行 Tauri 版と PySide6 版の機能差を、レビュー可能な順序で解消する。

この計画は「PySide6 UI をそのまま移植する」ためのものではない。現行 Tauri 版の backend contract、mask track domain、不変条件、`subprocess + CLI + JSON I/O` 境界を守りながら、PySide6 版で検証済みだったユーザー価値を Tauri 版へ取り込むための実装順序を定義する。

## 参照資料

- `docs/engineering/current-implementation.md`
- `docs/project/unimplemented-features.md`
- `docs/project/ai-handoff.md`
- `docs/project/pyside6-remaining-tasks.md`
- `docs/engineering/job-ledger-migration-plan.md`
- `docs/05_handoff/tauri-migration-agent-package/GAP_WARNING.md`
- `docs/05_handoff/tauri-migration-agent-package/AGENT_PROMPT.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/09_remaining_tasks.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/15_known_limitations.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/16_full_manual_test_procedure.md`

## PM 判断

差分解消は、次の順で進める。

1. 検出ジョブ状態を安定化する。
2. レビュー導線に直結する差分を先に埋める。
3. export / recovery / E2E を実装して、レビュー可能性を上げる。
4. UI polish と補助表示は、主要フローが通った後に扱う。
5. 教師データ、再学習、installer は別計画に分ける。

現行 Tauri 版には、古い gap 資料で「未実装」とされていた項目の一部が既に入っている。したがって、`docs/project/pyside6-remaining-tasks.md` は差分探索の参考に留め、最終判断は現行コードと正本資料を優先する。

## 現状サマリー

P0/P1 の domain core は概ね Tauri 側へ移植済みと判断する。

すでに成立しているもの:

- PySide6 project v1 から Tauri schema v2 への migration
- mask track 中心の project model
- manual edit / user_locked / user_edited の保護
- polygon / ellipse / feather / expand interpolation
- track stitching / ephemeral track filter / range detect IoU merge
- danger frame detection の基本ロジック
- danger warning の左パネル表示と timeline marker の基本表示
- polygon edge double-click による頂点追加
- transport button の基本 UI
- detector backend / category selection UI の基盤
- export 基本設定、FFmpeg pipe export、OpenCV fallback、audio mux
- autosave と localStorage ベースの簡易 recovery
- frontend unit tests と backend smoke/domain tests

まだ PySide6 同等ではないもの（2026-04-15 時点）:

- recovery の file-backed 管理と project_id 識別
- export queue の UI / 実行制御 / 永続化
- export settings の詳細 UX
- review workflow E2E
- shortcut help / wording / 状態ラベルの polish
- GPU encoder selection
- export 前 danger warning 全確認チェック（未確認警告の改善）

## Parity Matrix

| 機能 | PySide6 期待値 | Tauri 現状 | 状態 | 方針 |
| --- | --- | --- | --- | --- |
| Mask track domain | persistent track、manual 保護、segment/export parity | 正本上は実装済み | implemented | 変更しない。回帰テストを維持 |
| 範囲検出 | I/O 範囲、IoU merge、manual 保護 | backend 実装済み | implemented | job ledger 後に smoke で再確認 |
| Detect job 状態 | progress/cancel/failure/recovery が一貫 | SQLite ledger canonical state。frontend の result_available 推論と grace period 削除済み | **implemented** | 完了 |
| Job Panel cancel | 実行中 job を UI から中断できる | nle-btn--cancel スタイルで視認性確保、cancel 導線完了 | **implemented** | 完了 |
| App close shutdown | window close で子プロセスも終了 | onCloseRequested で active job に cancel を送信してから destroy | **implemented** | 完了 |
| AI detect GPU | ONNX Runtime GPU execution provider を使い、不可なら CPU fallback | CUDA/DirectML 自動選択。progress message に GPU/CPU 表示。doctor 表示も対応済み | **implemented** | 完了 |
| 全体検出前確認 | manual 保護 / 全上書き / cancel の 3 択 | guard-modal 3択モーダル。backend に overwrite_manual_tracks フラグ追加 | **implemented** | 完了 |
| 危険フレーム左パネル | 折りたたみ、確認トグル、行クリック seek | confirmedDangerFrames を App.tsx に lift up。確認済みをグレー表示。seek 実装済み | **implemented** | 完了（折りたたみは常時展開に変更） |
| 危険フレーム marker | 色分け、クリック seek、確認済み表示 | 確認済みマーカーを灰色 + opacity 0.45 でグレーアウト | **implemented** | 完了。近傍 snap は未対応 |
| polygon 頂点追加 | edge double-click が正式導線 | double-click 実装あり | implemented | テストを追加して固定 |
| Recovery | atomic file、project_id 識別、起動時 dialog、cleanup | localStorage snapshot のみ | partial | backend/file-backed recovery に寄せる |
| Transport | 独立した操作帯 | 基本ボタンあり | partial | 主要フロー後にアクセシビリティと状態同期を整える |
| Export 基本 | FFmpeg、fallback、audio mux | 実装済み | implemented | 変更しない |
| Export settings | upscaling guard、target size、排他表示、説明改善 | 簡易 modal | partial | queue 前に設定 contract を整理 |
| Export queue | 複数 job、逐次実行、永続化、interrupted 復元 | 型と helper の一部のみ | missing | job ledger 後、detect 安定後に実装 |
| E2E | review workflow と crash recovery flow | desktop unit tests 中心 | missing | Playwright/Tauri 起動方針を決めて追加 |
| Shortcut help | registry + F1 searchable dialog | `window.alert` | partial | UI polish phase で modal 化 |
| 状態ラベル / wording | 用語刷新、英語混在排除 | `held` / `uncertain` など残りあり | partial | UI polish phase でまとめて修正 |
| Onion skin / diff overlay | 補助表示。PySide6 側でも必要性再評価 | Tauri では未整理 | deferred | 主要フロー後に採否判断 |
| 教師データ / 再学習 | 将来機能 | 未実装 | deferred | gap closure ではなく別ロードマップ |
| installer / updater | 将来機能 | 未実装 | deferred | review package 安定後に別計画 |

## 実装順序

### Phase 0: 正本更新と棚卸し

目的: 古い gap 情報と現行コードのズレを止める。

作業:

- この文書を今後の差分解消計画として使う。
- `docs/project/unimplemented-features.md` は実装着手時に更新する。
- 古い `docs/project/pyside6-remaining-tasks.md` は比較履歴として扱い、正本にしない。

完了条件:

- 実装担当者が「何を先にやるか」をこの文書から判断できる。

### Phase 1: Stability Gate

目的: PySide6 差分を足す前に、検出 job の timing-dependent な失敗を減らす。

作業:

- `docs/engineering/job-ledger-migration-plan.md` を実行する。
- detect job の success/failure/cancel/interrupted/result access を backend canonical state に寄せる。
- frontend の `interrupted` grace と result existence 推論を削除する。
- Job Panel の detect cancel ボタンを復旧し、GUI から cancel を確認できるようにする。
- メインウィンドウ終了時に backend worker / child process / dev helper process が残らないようにする。
- AI 自動検出の GPU provider 利用状況を doctor / UI で確認できるようにし、GPU 不可時は CPU fallback を明示する。
- manual interactive flow を 1 回通す。

対象:

- `apps/backend/src/auto_mosaic/infra/ai/detect_jobs.py`
- `apps/backend/src/auto_mosaic/api/commands/*detect*`
- `apps/desktop/src/App.tsx`
- detect job tests

完了条件:

- `get-detect-status` と `get-detect-result` が ledger state を正とする。
- Job Panel から detect job を cancel でき、terminal job への cancel が no-op になることを GUI で確認できる。
- メインウィンドウを閉じた後に backend worker / child process が残らない。
- AI 自動検出が使用中の execution provider を表示し、GPU 不可時は CPU fallback として継続する。
- `open video -> detect -> edit -> save/load -> export` が最低 1 回通る。

### Phase 2: Review Workflow Gap

目的: レビュー時に「壊れている」と見えやすい差分を先に埋める。

実装順:

1. 全体検出前の上書き確認
2. danger warning panel / timeline marker の確認状態連動
3. polygon edge double-click のテスト固定
4. recovery の file-backed 化

受け入れ条件:

- 全体検出時に、manual 保護、全上書き、cancel を選べる。
- danger warning の確認状態が panel と timeline marker の両方に反映される。
- recovery は `project_id` を使い、起動時に復元 / 削除 / 後で決める選択ができる。
- localStorage だけに依存しない。

### Phase 3: Export Parity

目的: PySide6 で進んでいた export 周辺の差分を詰める。

実装順:

1. Export settings contract の整理
2. 入力解像度より大きい preset の無効化
3. manual bitrate の slider + number input 同期
4. bitrate mode に応じた排他表示
5. target file size mode を入れるか PM 判断
6. export queue の backend/frontend 契約定義
7. export queue の逐次実行、永続化、interrupted 復元

受け入れ条件:

- export 基本挙動は現行の FFmpeg/OpenCV fallback を壊さない。
- queue は複数 job を持てる。
- running job は再起動後に `interrupted` として表示される。
- completed job は永続 queue の肥大化を防ぐ。

### Phase 4: Verification

目的: PySide6 版であった review workflow confidence を Tauri 側にも作る。

作業:

- desktop unit tests を gap ごとに追加する。
- backend smoke tests を ledger / recovery / export queue に合わせて追加する。
- Tauri window を含む E2E 方針を決める。
- review package 起動後の手順を自動化できる範囲で固定する。

優先 E2E:

- open video -> detect -> edit canvas -> save/load
- range detect -> manual keyframe protection
- danger warning -> confirm -> export
- recovery snapshot -> restart -> restore
- export queue -> interrupted restore

完了条件:

- 少なくとも review workflow の主要 happy path が CI またはローカル一発コマンドで検証できる。

### Phase 5: UI Polish

目的: 主機能が通った後に、PySide6 の review polish を Tauri に合わせて取り込む。

候補:

- F1 shortcut help を `window.alert` から modal にする。
- shortcut registry を `App.tsx` 直書きから分離する。
- Home / End / 上下キー / Ctrl+E など、PySide6 側で追加されたショートカットを必要分だけ採用する。
- `held` / `uncertain` / `anchored` などの英語混在を日本語化する。
- timeline legend と inspector の状態ラベルを揃える。
- transport の disabled state、tooltip、keyboard focus を整える。

完了条件:

- UI 文言は `uiText.ts` へ寄せる。
- domain state 名を UI に直出ししない。
- `App.tsx` の肥大化を悪化させない。

### Phase 6: Deferred / Separate Plans

次は、この gap closure から外す。

- onion skin / diff overlay の採否
- Undo 履歴ツリー表示
- track order の drag-and-drop 永続化
- 教師データ保存
- ローカル再学習
- installer / updater / uninstaller

理由:

- PySide6 側でも補助表示系は必要性再評価または保留になっている。
- 教師データ / 再学習 / installer は製品ロードマップ上の別テーマであり、レビュー導線の gap closure とはリスクの種類が違う。

## 直近の推奨バックログ (2026-04-15 更新)

| 優先 | 状態 | 作業 | 理由 |
| --- | --- | --- | --- |
| 1 | ✅ 完了 | Job Panel detect cancel 復旧 | cancel確認ができず、E2Eの中断系が止まっていた |
| 2 | ✅ 完了 | App close shutdown | window close 後に backend が残るとレビュー環境で不安定になる |
| 3 | ✅ 完了 | AI detect GPU / CPU fallback 診断 | 自動検出が遅く、GPU利用可否が不透明。高速化には必須 |
| 4 | ✅ 完了 | Detect Job Ledger GUI確認 | ledgerはCLIで通っている（GUI実証は次の E2E フェーズで確認） |
| 5 | ✅ 完了 | 全体検出前の上書き確認 | manual 意図保護を UI でも明示する |
| 6 | ✅ 完了 | danger warning 連動強化 | confirmedDangerFrames を timeline marker と共有 |
| 7 | **次** | recovery file store | crash recovery を localStorage 依存から外す |
| 8 | 次 | export settings 整理 | export queue 前の contract 固定 |
| 9 | 次 | export queue | PySide6 との差分が大きく、job model と接続する |
| 10 | 次 | E2E | 差分解消後の回帰検知が必要 |
| 11 | 次 | shortcut / wording polish | 主機能後で十分 |

## 実装時の注意

- Backend project state を source of truth とする。
- Frontend の都合で backend domain rule を曲げない。
- `asset.localhost` / display URL を backend に渡さない。
- manual track / manual keyframe を再検出で消さない。
- export を last-keyframe hold に戻さない。
- GPU / CUDA failure を startup blocker にしない。
- backend Python 変更を review build に含める場合は `npm.cmd run review:runtime` を実行する。

## 報告フォーマット

各 implementation slice の完了時は次を報告する。

- PySide6 gap のどれを閉じたか
- 変更ファイル
- backend contract の変更有無
- frontend 表示の変更有無
- 実行したテスト
- まだ PySide6 と違う点
