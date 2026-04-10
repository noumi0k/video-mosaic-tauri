# Tauri 移行計画レビュー

この文書は `03_tauri-migration-plan.md` の自己レビューです。目的は計画を正当化することではなく、このまま進めた場合にどこで事故るかを先に明示し、修正版方針へ落とすことです。

## 1. 総評

計画の大筋である「contract 先行、段階移行、UI 先行を避ける」は妥当です。ただし、そのままでは次の危険があります。

- contract 文書を作って満足し、Tauri backend の test / adapter 実装に接続されない。
- Project schema と resolver に集中しすぎて、export / runtime packaging の検証が後ろ倒しになる。
- PySide6 の再現と Tauri 側の既存再設計が混線し、どちらを正とするかが局所判断になる。
- `taurimozaic` が writable root 外である制約を理由に、実装着手が文書更新だけで止まる。

この計画は、次の修正を反映しないと「きれいだが動かない計画」になりやすい。

## 2. 抜け漏れ

### 問題

- 実 project JSON サンプルの採取方針が弱い。schema mapping を書いても、実データのサンプルがなければ migration test に落ちない。
- export parity の粒度がまだ粗い。PySide6 側は `ExportService` / `FFmpegExporter` / OpenCV fallback / audio mux を持つが、Tauri 側は単純化されている可能性がある。
- Tauri frontend 側の resolver mirror 実装と backend resolver の二重管理リスクへの対処がまだ弱い。
- job state の vocabulary を比較すると書いているが、UI 表示状態の最小 enum がまだ未定義。

### 修正

- `05_initial-contract-freeze.md` では単なる一覧ではなく、test fixture にできる JSON 形状と acceptance criteria まで書く。
- export は後半フェーズに置くが、Phase A で「何を parity と呼ぶか」を固定する。
- frontend resolver mirror は正本ではなく表示補助であると contract に明記し、backend parity test を必須にする。

## 3. スコープ過大

### 問題

計画は Project、job、runtime、UI、export、review package まで含んでおり、全体としては大きい。全部を一続きの「Phase 3 plan」として読むと、初手が曖昧になる。

### 修正

- 初手は `Project / Track / Keyframe / Segment / Job / Runtime` の contract freeze に限定する。
- その次の code task は Tauri backend の migration test だけにする。
- UI 作業は `open/save/load` と `job panel display` のような小さい接続単位に分ける。

## 4. 順序ミス

### 問題

`Runtime path / doctor contract` を Project contract の後に置いているが、Tauri command は runtime context 解決に依存する。backend migration test は CLI 単体で可能でも、desktop 経由の確認では runtime path が先に壊れる。

### 修正

- Phase A で project contract と runtime command context を同時に inventory する。
- code 実装順は「backend CLI test -> runtime doctor smoke -> frontend 接続」の順にする。

## 5. 楽観的すぎる見積もり

### 問題

`source` / `source_detail` / segment state の対応を表で解けば進むように見えるが、実際には render/edit resolver、manual lock、detector merge、history まで影響する。

### 修正

- mapping を即決しない。`未定` を許容し、未定の項目は UI 移植に進ませない gate にする。
- `auto`, `re-detected`, `anchor_fallback`, `manual`, `interpolated`, `predicted` はそれぞれ render/edit 上の意味をテスト候補へ落とす。

## 6. 前提の誤り

### 問題

Tauri 側に既に `ProjectDocument` や job infrastructure があるため、それを完成済みの移行先 contract と見なす誘惑がある。しかし現行仕様の判定は `mosic2/` が正であり、Tauri 側は比較対象に過ぎない。

### 修正

- Tauri 側の schema は「既存案」として扱い、PySide6 の仕様に対する適合状況を判定する。
- Tauri 側の都合で PySide6 仕様を変える場合は、必ず `再設計` として記録する。

## 7. 現行構成の理解不足

### 問題

`MainWindow` が大きいという指摘だけでは不十分で、どの UI 操作がどの service / state / history に触れるかを実装単位でさらに分解する必要がある。

### 修正

- 初回 contract freeze に、少なくとも次の操作単位を含める。
  - open video
  - save/load project
  - detect full/range/single
  - create/update/delete/move keyframe
  - export queue / cancel / status
  - GPU settings / doctor

## 8. テスト戦略不足

### 問題

「テストを書くべき箇所」は列挙されているが、最初にどのテストから書くかが弱い。ここを曖昧にすると、UI 作業へ逃げやすい。

### 修正

最初のテスト候補を次の順に絞る。

1. Tauri backend: PySide6 project v1 fixture を reject または migrate する CLI/domain test。
2. Tauri backend: `source` / `source_detail` / segment state 変換 test。
3. Tauri frontend: job status normalizer の enum test。
4. Tauri backend: raw path と display URL guard test。

## 9. 破壊的変更リスク

### 問題

Tauri project schema v2 に migration ルールを足すと、既存 Tauri project を壊す可能性がある。逆に v2 を温存しすぎると PySide6 v1 由来の情報を落とす。

### 修正

- loader に direct rewrite ではなく adapter / migration layer を追加する。
- 既存 v2 fixture と v1 fixture を両方テストする。
- migration できない field は黙って捨てず warnings に出す。

## 10. packaging / runtime / setup 軽視

### 問題

計画では runtime packaging を後半に置いている。これは UI 作業の順序としては妥当だが、配布成否リスクとしては早めに smoke すべきである。

### 修正

- Phase A または B の時点で `doctor` response contract と review-runtime smoke 手順を固定する。
- model integrity / ffmpeg / ffprobe / Python ABI / writable dirs を `移行後半の配布問題` ではなく `初期 gate` として扱う。

## 11. UI 側だけ見て backend を軽視していないか

### 判定

計画上は backend contract 先行なので軽視はしていない。ただし、初回実装が docs のみだと実質的には backend が進まない。

### 修正

- `05_initial-contract-freeze.md` の次は必ず Tauri backend test に進む。
- writable root 制約で即時コード変更できない場合でも、次の code diff と test command を文書に固定する。

## 12. Windows 実行環境依存を過小評価していないか

### 判定

過小評価の危険がある。Tauri は Rust shell から Python を起動するため、PySide6 開発環境で暗黙に通っていた PATH、DLL、model path、ffmpeg path がそのままでは通らない。

### 修正

- Rust `run_backend_command` の env 注入、review-runtime の Python ABI、model dir、data dir、ffmpeg bin の contract を Phase A に含める。
- doctor を単なる表示ではなく release gate として扱う。

## 13. モデル管理 / GPU / ffmpeg 周りを甘く見ていないか

### 判定

まだ甘い。モデルファイル名、required 判定、CUDA session test、ONNX Runtime provider、ffmpeg audio mux は failure mode が多い。

### 修正

- model registry / integrity / provider / ffmpeg availability を migration contract に含める。
- GPU は高速化ではなく「使えない場合の説明と CPU fallback」をまず固定する。

## 14. この順だと失敗しやすい箇所

- Contract freeze が長引き、実 project fixture がないまま抽象表だけ増える。
- Tauri 側の既存 UI があるため、先に見た目を直したくなり、schema / resolver gate を飛ばす。
- export を「後半」と言いすぎて、最後に audio / ffmpeg / cancel の仕様差分が露出する。
- runtime packaging を review package 前まで放置し、Python ABI / model path / ffmpeg path で詰まる。

## 15. 代替案

### 代替案 A: UI から移す

却下。`MainWindow` の責務が広すぎ、保存形式と job contract を後から合わせる負債が大きい。

### 代替案 B: Tauri backend schema を正として PySide6 を合わせる

却下。ユーザー指定では現行仕様の根拠は `mosic2/` であり、Tauri 側都合で現行仕様を上書きできない。

### 代替案 C: PySide6 v1 project を完全互換 migration してから UI を触る

部分採用。ただし完全互換に時間を使いすぎると前進が止まる。初期は「migrate / reject / warning」の分類を固定し、未定は gate として残す。

### 代替案 D: runtime / doctor を最初に完成させる

部分採用。runtime は重要だが、Project contract なしでは実フロー検証に進めない。Phase A で並行 inventory し、Phase B 以降の smoke gate にする。

## 16. 最終的に採用する修正版方針

採用方針は次の通り修正する。

1. 初手は `05_initial-contract-freeze.md` を作る。ただし文書目的ではなく、次の backend test に直結する fixture / acceptance criteria を含める。
2. Phase A で Project contract と runtime command context を同時に inventory する。
3. `source` / `source_detail` / segment state は即決せず、未定項目を gate として列挙する。
4. Tauri code に入る最初の変更は UI ではなく backend migration test にする。
5. writable root の制約で Tauri code を触れない場合は、それを blocker と明記し、次に入れるべき test file / test command / expected failure を contract 文書へ残す。
6. export parity と runtime packaging は後半実装だが、Phase A で parity 項目と doctor gate を定義する。
7. 計画レビュー後の `03_tauri-migration-plan.md` には、この修正版方針を反映する。

## 17. 批判的結論

この計画は、契約固定から始める限り実務的です。ただし、contract freeze を成果物扱いして止めると失敗します。次の一手は「見た目を直す」ではなく、「PySide6 由来 project / source / job / runtime の contract を test fixture 化できる粒度まで固定する」ことです。

また、Tauri 側は既に多くの実装があるため、逆に危険です。空の移行先なら不足が明白ですが、既存機能がある移行先では、似た名前の機能が現行仕様と一致していないことに気づきにくい。ここを甘く見ると、移行の後半で保存データや export の挙動差分として表面化します。
