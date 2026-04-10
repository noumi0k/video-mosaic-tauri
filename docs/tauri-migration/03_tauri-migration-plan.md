# Tauri 移行計画

この文書は、`mosic2/` の現行 PySide6 実装を基準に、Tauri 構成へ段階移行するための実行計画です。現行仕様の根拠は `01_current-architecture-pyside6.md`、構成差分は `02_pyside6-vs-tauri-architecture-comparison.md` に分離しています。

## 0. 計画の根拠と扱い

## 0.1 レビュー反映済み修正

`04_tauri-migration-plan-review.md` のレビューを受けて、この計画は次の点を修正済みとして扱う。

- 初回作業は UI 実装ではなく `Project / Track / Keyframe / Segment / Job / Runtime` の contract freeze に限定する。
- contract freeze は文書作成で止めず、次に Tauri backend へ追加する migration / guard test の fixture と acceptance criteria まで含める。
- Phase A では Project schema だけでなく、Rust command から Python backend を起動する runtime context、doctor、model / ffmpeg path も inventory 対象に含める。
- `Keyframe.source`、Tauri `source_detail`、`MaskSegment` state の対応は即決しない。未定項目は UI 移植へ進ませない gate とする。
- Tauri 側コードへ入る最初の変更は React UI ではなく backend migration test とする。
- export parity と runtime packaging は後半実装だが、Phase A の時点で「何を parity と呼ぶか」「doctor で何を release gate とするか」を固定する。
- この作業環境では `H:\mosicprogect\taurimozaic` が writable root 外であるため、承認なしで Tauri 側コード変更に進まない。承認前の初手は `docs/tauri-migration/` 配下に test-ready contract を残す。

### 確認済みの前提

- 移行元の正本は `mosic2/` の PySide6 実装である。
- PySide6 側は `app/main.py` から `app/bootstrap.py` を経由して `RuntimeServices` と `MainWindow` を組み立てる単一 Python GUI アプリである。
- PySide6 側の UI は `.ui` ファイルではなく `app/ui/*.py` による手書き PySide6 実装である。
- PySide6 側の保存形式は `app/domain/project.py` と `app/infra/storage/project_store.py` の `Project` JSON schema v1 を基準にしている。
- Tauri 側の主対象は、ユーザー指定構成と一致する `H:\mosicprogect\taurimozaic` である。
- Tauri 側は React frontend、Rust `run_backend_command`、Python backend CLI JSON I/O、runtime / review-runtime を持つ構成である。

### 未確認の前提

- Tauri 側の interactive UI フロー、GPU/CUDA 実行、実モデル download、実動画 export の現時点での成功可否は今回まだ再実行していない。
- `H:\mosicprogect\mosic2-tauri` は存在するが、ユーザー指定の `apps/backend` / `apps/desktop` 構成ではないため、主移行先としては扱わない。必要に応じて補助 POC として読む。
- PySide6 側 project v1 から Tauri 側 project v2 への完全変換ルールはまだ固定されていない。

## 1. 移行の目的

PySide6 ベースの Auto Mosaic を、Tauri ベースの desktop app と Python backend の構成へ移す。目的は UI 技術の置換だけではない。次を満たす必要がある。

- 現行 PySide6 の動画読込、project 保存/読込、AI 検出、manual edit、timeline、keyframe、render/export の既存挙動を説明可能な形で再現または明示的に再設計する。
- Tauri frontend、Rust command、Python backend の境界を contract として固定する。
- 保存形式、状態管理、ジョブ管理、model / ffmpeg / runtime / setup / doctor の扱いを曖昧にしない。
- Windows 配布時の Python / DLL / ONNX Runtime / CUDA / ffmpeg / model 配置を検証可能な単位へ分解する。

## 2. 移行対象のスコープ

### 対象に含める

- PySide6 `Project` schema v1 の意味を保った Tauri project schema / migration path。
- `MaskTrack`、`Keyframe`、manual protection、auto/re-detected/anchor fallback、interpolation/hold/resolver の扱い。
- 動画読込と metadata 取得。
- AI 検出導線、検出 job、進捗、cancel、結果 merge。
- timeline 表示、keyframe 選択、keyframe 移動、mask edit。
- export / render、progress、cancel、audio mux、ffmpeg fallback。
- model 管理、doctor、runtime path、review-runtime、setup。
- backend CLI JSON I/O、stdout purity、stderr log、Tauri command response。
- 最低限の parity test と smoke test。

### 対象外にする

- いきなりの全面 UI 作り直し。
- PySide6 側と Tauri 側を同時に大規模 refactor する作業。
- 現行仕様の根拠がない状態での domain schema 変更。
- final installer / code signing / auto update の完成。ただし review-runtime と配布前提は計画から外さない。
- 高度な GPU 最適化や新 detector 追加。まず現行相当の contract を固定する。

## 3. 成功条件

### 最低成功条件

- PySide6 の保存済み project の主要データを Tauri 側が破壊せず読み取れる、または migration 不可の理由を明示して拒否できる。
- Tauri 側で動画読込、project 作成/保存/読込、detect job 開始/進捗/結果反映、manual edit、timeline 選択、export job 開始/進捗/完了/失敗表示が contract 上つながる。
- backend command の request/response、job status、error shape、path policy が文書とテストで固定される。
- runtime doctor が model / ffmpeg / ffprobe / ONNX Runtime / CUDA / writable path の状態を UI へ説明可能な形で返す。
- 主要な PySide6 暗黙仕様を「再現する」「Tauri では変える」「未対応として拒否する」のどれかに分類できる。

### 完了と呼ばない条件

- Tauri UI 上でボタンが表示されるだけ。
- PySide6 の保存形式を実データで検証していない。
- export の見た目だけ通り、audio / cancel / failure / fallback が未検証。
- GPU / model / ffmpeg / review-runtime を後回しにしたまま「移行完了」と言う。

## 4. 前提条件

- Python backend は当面継続する。検出、OpenCV、ONNX Runtime、ffmpeg 連携を Rust に即移植しない。
- Tauri frontend は backend を直接 import せず、Rust command 経由で CLI JSON I/O を呼ぶ。
- backend は stdout に machine-readable JSON だけを出す。ログ、native stdout 汚染、警告は stderr または response warning に分離する。
- Windows raw path は backend 用、`asset.localhost` URL は frontend 表示用として分離する。
- PySide6 側の `MainWindow` の挙動はそのまま React に移植せず、command / domain / UI state へ分解する。

## 5. 現時点の blockers

- PySide6 project v1 と Tauri project v2 の完全な migration rule が未固定。
- PySide6 の `Keyframe.source` と Tauri の `source` / `source_detail` / `MaskSegment` の対応が未固定。
- PySide6 の `RenderService.resolve_tracks` と Tauri の `resolve_for_render` / frontend resolver の parity が未証明。
- PySide6 の in-memory `ExportQueueDialog` と Tauri の file-based export job の user-facing state 対応が未固定。
- Tauri 側の現行 interactive UI / GPU / model download / export の実機検証を今回まだ行っていない。
- この作業環境では `H:\mosicprogect\taurimozaic` が writable root ではないため、Tauri 側コード変更には別途承認が必要になる可能性がある。

## 6. リスク一覧

| リスク | 事故り方 | 重大度 |
| --- | --- | --- |
| 保存形式差分 | v1 project を v2 として読んで manual keyframe や source を壊す | 高 |
| resolver 差分 | 編集時は見えるが export で消える、または hold されすぎる | 高 |
| job 状態差分 | UI が完了/失敗/cancel を誤表示し、処理中断できない | 高 |
| stdout 汚染 | Tauri command が JSON parse に失敗し、UI では backend failure になる | 高 |
| Windows path 混線 | 表示 URL を backend に渡す、raw path を WebView に出す | 高 |
| runtime packaging | review-runtime の Python ABI / DLL / model / ffmpeg 不一致で配布物が起動しない | 高 |
| export parity | 音声 mux、codec、resolution、cancel、fallback が PySide6 とズレる | 高 |
| UI 先行 | 見た目の移植後に backend 契約が合わず大きく戻る | 高 |
| Tauri 既存実装の過信 | 同名機能を移植済みと誤認し、PySide6 の暗黙仕様を落とす | 中 |
| ドキュメント肥大化 | 計画だけ増え、検証可能な contract/test に落ちない | 中 |

## 7. リスク軽減策

- 最初に project / keyframe / track / job / runtime command の contract を固定する。
- PySide6 の実 project JSON サンプルを用意し、Tauri backend の load/migrate テストに使う。
- resolver は backend で正本を持ち、frontend の mirror 実装は snapshot / parity test を置く。
- detect/export/runtime job は共通 UI 表示モデルへ normalize する。ただし backend の domain state と UI 表示 state を混同しない。
- path は `raw_path` と `display_url` を型・命名で分ける。
- runtime doctor は setup の代替ではなく、配布物の検証ゲートとして扱う。
- export は最初から happy path だけでなく cancel / ffmpeg missing / audio fallback / failure を test plan に入れる。

## 8. 移行方針

### 採用方針: 段階移行

一括移行は採用しない。理由は、PySide6 側の `MainWindow` が UI / application flow / worker 起動 / merge / history / preview sync を広く抱えており、これを見た目単位で React に置換すると保存形式と job 契約の破壊を見逃すためである。

### どこから着手すべきか

最初に固定する順序は次の通り。

1. Project / MaskTrack / Keyframe / MaskSegment の保存・表示・編集 contract。
2. Detect / Export / Runtime job の status contract。
3. Runtime path / model / ffmpeg / doctor contract。
4. PySide6 v1 project から Tauri v2 project への migration / rejection rule。
5. UI の操作単位ごとの command 接続。
6. export parity と配布 runtime 検証。

### 何を先に固定すべきか

- `ProjectDocument` の互換境界。
- `Keyframe.source` / `source_detail` / segment state の対応。
- 編集時 resolver と render 時 resolver の違い。
- job status の terminal / active / cancellable 判定。
- raw path と display URL の境界。
- doctor result の UI 表示 contract。

## 9. フェーズ分割

### Phase A: Contract inventory と現行仕様固定

目的: PySide6 の現行仕様と Tauri の既存 schema / command の差分を、実装対象の contract に落とす。

完了条件:
- Project / Track / Keyframe / Segment / Job / Runtime の対応表がある。
- PySide6 由来の source / state / resolver の扱いが「再現」「変換」「拒否」「未定」に分類されている。
- Tauri 側で先に壊してはいけない command response shape が明記されている。

成果物:
- `docs/tauri-migration/05_initial-contract-freeze.md` または同等の contract 文書。
- 後続で Tauri repo に移す test case 候補。

壊してはいけないもの:
- PySide6 の `Project` v1 の意味。
- Tauri backend の stdout JSON-only 原則。
- raw path / display URL の分離。

### Phase B: Backend schema migration と parity test

目的: PySide6 v1 project を Tauri backend で安全に扱う。

完了条件:
- v1 project sample を load/migrate するテストがある。
- source/state の変換または拒否が明示されている。
- manual keyframe と user lock を落とさない。
- invalid path / display URL 混入時の failure が構造化されている。

成果物:
- Tauri backend の migration adapter または loader guard。
- backend smoke / domain test。

壊してはいけないもの:
- Tauri project v2 の既存保存データ。
- manual / user-edited track の保護。

### Phase C: Job contract 統一

目的: detect / export / runtime job を UI が安全に表示・cancel できる状態にする。

完了条件:
- active / terminal / cancellable / failed / canceled の分類が job 種別横断で揃う。
- UI normalizer が backend 状態を誤って完了扱いしない。
- stale / interrupted job の扱いが文書化・テスト化される。

成果物:
- frontend job normalization test。
- backend job status fixture。

壊してはいけないもの:
- 既存の file-based job status。
- cancel flag と result file の扱い。

### Phase D: UI operation migration

目的: UI 見た目ではなく、操作単位で command と state update を接続する。

完了条件:
- open video、save/load project、create/update/delete/move keyframe、detect job、export job が contract に従って動く。
- frontend state と backend read model の source of truth が混線しない。
- editing resolver と render resolver の差分が UI 上で説明できる。

成果物:
- React component / hooks の小変更。
- frontend unit test と必要な smoke 手順。

壊してはいけないもの:
- unsaved changes guard。
- path guard。
- backend response error shape。

### Phase E: Export parity と runtime packaging

目的: 実用上の失敗が多い export と配布 runtime を移行完了条件へ入れる。

完了条件:
- export の progress / cancel / failure / audio mux / ffmpeg missing fallback が検証される。
- review-runtime の Python ABI、backend import、model integrity、ffmpeg / ffprobe、writable path が doctor で検証される。
- Windows 実行環境の依存が docs と script で一致する。

成果物:
- export smoke / runtime review 手順。
- review-runtime 検証結果。

壊してはいけないもの:
- stdout purity。
- vendor ABI 選択。
- model checksum / required model 判定。

### Phase F: 非技術者レビュー可能な build

目的: reviewer が GUI から主要フローを確認できる単位にする。

完了条件:
- review quickstart に沿って起動できる。
- doctor で不足が説明される。
- open video -> detect -> manual edit -> save/load -> export の最小シナリオが確認できる。

成果物:
- review package。
- known issues /未対応リスト。

壊してはいけないもの:
- fallback 表示。
- error message。
- project 保存データ。

## 10. 先にテストを書くべき箇所

- PySide6 v1 project sample の load / migrate / reject。
- `Keyframe.source` と Tauri `source_detail` の変換。
- manual keyframe / user_locked / user-edited track の保護。
- render resolver と editing resolver の差分。
- detect job / export job / runtime job の normalizer。
- raw path と `asset.localhost` display URL の混入防止。
- doctor response の不足項目表示。
- stdout JSON-only guard。

## 11. 後回しにしてよい箇所

- UI の装飾や細部の見た目合わせ。
- 最終 installer / code signing / auto update。
- detector の新規追加。
- GPU 最適化。ただし GPU 状態の検出と CPU fallback 表示は後回しにしない。
- export の高度な preset。基本 export parity と failure handling が先。

## 12. 依存関係順

1. Project / domain contract。
2. Runtime path / doctor contract。
3. Job status contract。
4. Backend migration / loader / guards。
5. Frontend state mapping。
6. UI 操作接続。
7. Export parity。
8. Review runtime / packaging。
9. 非技術者レビュー build。

## 13. クリティカルパス

最短のクリティカルパスは次である。

1. PySide6 v1 project の意味を contract 化する。
2. Tauri v2 schema との差分を migration / rejection rule にする。
3. job status と runtime doctor を UI 表示 contract にする。
4. open video / detect / edit / save / export の command を小さく接続する。
5. review-runtime で同じ flow を通す。

この順序を崩して UI を先に作ると、後から schema と job state を合わせるために UI state を大きく戻す可能性が高い。

## 14. ロールバックしやすい進め方

- Contract 文書と test fixture を先に追加し、既存挙動を変える実装は小さな PR / commit に分ける。
- Tauri backend の migration は既存 loader を直接書き換えるより、adapter / guard として追加する。
- frontend UI は component 単位で差し替えず、command response 取り込み箇所から小さく変更する。
- export / runtime packaging は feature flag または review-only script の範囲で検証してから本線化する。
- PySide6 側の実装は正本調査対象として残し、互換確認が終わるまで不用意に改変しない。

## 15. 非技術者レビューに回せる区切り

- 区切り 1: doctor が不足項目を正しく表示し、動画を開ける。
- 区切り 2: sample project の save/load と manual edit が破壊されない。
- 区切り 3: detect job が進捗表示され、結果が timeline / canvas に反映される。
- 区切り 4: export job が進捗表示され、cancel / failure が説明される。
- 区切り 5: review package で同じ流れが再現できる。

## 16. 直近で着手すべき最小タスク列

1. `docs/tauri-migration/05_initial-contract-freeze.md` を作り、Project / Track / Keyframe / Segment / Job / Runtime の初期 contract を固定する。
2. PySide6 `Project` v1 と Tauri `ProjectDocument` v2 の field mapping を明記する。
3. `Keyframe.source` / `source_detail` / segment state の未決定箇所を `未定` として列挙する。
4. detect / export / runtime job の status vocabulary を比較し、UI 表示用 normalized status を定義する。
5. Tauri repo へ移すべき最初の test 候補を列挙する。
6. Tauri repo の書き込み承認が得られた時点で、backend schema migration test から着手する。

## 17. 採用しない初手

- `MainWindow` 相当の React 移植から始める。
- export 実装を UI から直接叩く形に寄せる。
- PySide6 project v1 を無検証で Tauri v2 と同一視する。
- 既存 Tauri schema を正として PySide6 の暗黙仕様を落とす。
- runtime / packaging / doctor を最後まで放置する。

## 18. 初期判断

最初の安全な実装は、Tauri UI の大規模変更ではなく contract freeze である。理由は、現時点の最大リスクが「描画できないこと」ではなく「保存形式、resolver、job state、runtime 境界が合っていないまま移植済み扱いになること」だからである。

Tauri 側コードへ入る最初の実装候補は backend migration test だが、この作業環境では `H:\mosicprogect\taurimozaic` が writable root ではない。承認なしに無理に触るより、まず `docs/tauri-migration/` 配下に contract freeze を残し、その後に Tauri repo で test / adapter 実装へ移す。
