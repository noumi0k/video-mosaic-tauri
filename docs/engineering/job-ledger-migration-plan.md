# Job Ledger Migration Plan

Last updated: 2026-04-14

## 目的

検出ジョブの状態管理を、バックエンド所有の SQLite Job Ledger に移行する。

この計画は、`status.json`、`result.json`、worker PID、frontend polling がそれぞれ状態を推測している現状を止め、検出ジョブの成功・失敗・中断・結果取得を単一の台帳で確定させるための実装方針である。

## 参照した資料

- `docs/engineering/current-implementation.md`
- `docs/project/unimplemented-features.md`
- `docs/project/ai-handoff.md`
- `docs/05_handoff/README.md`
- `docs/05_handoff/tauri-migration-agent-package/AGENT_PROMPT.md`
- `docs/05_handoff/tauri-migration-agent-package/GAP_WARNING.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/09_remaining_tasks.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/15_known_limitations.md`
- `docs/05_handoff/tauri-migration-agent-package/source_docs/16_full_manual_test_procedure.md`

## PM 判断

SQLite Job Ledger を採用する。

初回スコープは検出ジョブだけに限定する。runtime jobs と export jobs は、この移行で触らない。

FastAPI、HTTP、常駐 Python worker、JSON-RPC 化は今回の解決策に含めない。現在のプロジェクトルールどおり、Tauri から Python への通信は `subprocess + CLI + JSON I/O` のまま維持する。

未決だった初期実装判断は次で固定する。

- Ledger 配置: `ensure_runtime_dirs().data_dir / "jobs" / "job-ledger.sqlite3"`
- SQLite journal mode: `WAL`
- SQLite lock 待ち: `PRAGMA busy_timeout = 5000`
- Heartbeat 書き込み: progress/status update と同じ write path で `heartbeat_at` を更新する
- Heartbeat timeout 初期値: 60 秒
- Schema version: `PRAGMA user_version` で管理し、forward-only migration helper を Phase 1 で用意する

Phase 1 の ledger 基盤だけは単独パッチでよい。ただし detect command へ接続し始める Phase 2-5 は、contract 混在を避けるため同一 PR / 同一実装スライスで閉じる。`start-detect-job` が ledger を書き、`get-detect-status` が `status.json` を読むような中途半端な状態を main line に残してはならない。

## 背景

現行の障害は IPC 方式の混在ではなく、ジョブ状態の split-brain が原因である。

現行の検出ジョブは主に次の情報源を持っている。

- `status.json`: 進捗、状態、worker PID を持つ。
- `result.json`: 検出結果を持つ。
- worker PID liveness: worker が生きているかを別系統で判定する。
- frontend polling: `interrupted` の猶予、`result_available` / `has_result` による結果存在推論を持つ。

これにより、次のような補正が増えている。

- `result.json` があれば `succeeded` に昇格する。
- worker が死んで見えた後に `result.json` を再確認する。
- terminal job でも追加 polling する。
- frontend 側で `interrupted` の grace period を持つ。
- frontend 側で `result_available` / `has_result` を見て成功扱いに寄せる。

これらは Windows の detached process とファイル可視化タイミングに対する短期対策としては妥当だったが、長期的には「誰がジョブの真実を決めるのか」が曖昧なままになる。

## 既存バグとの関係

`docs/project/ai-handoff.md` では、検出 worker の native crash や Python ABI mismatch が `Detection worker was no longer running and the job was marked interrupted.` として表面化した履歴がある。

この履歴から分かる問題は、worker crash そのものだけではない。worker が failed を書けずに死んだ時、status、result、PID、frontend がそれぞれ状態復旧を試みるため、ユーザーに見える結果が timing-dependent になる点が問題である。

また、`apps/desktop/src/App.tsx` には現在も `interrupted` の猶予と、`result_available` / `has_result` による結果存在推論が残っている。これはバックエンドが source of truth であるというルールと衝突している。

## ハンドオフ資料からの反映

PySide6 側のハンドオフ資料では、長時間処理は job-based で、progress、cancel、status、recovery を一貫して扱うことが前提になっている。

特に `source_docs/09_remaining_tasks.md` では、export queue の永続化において次の考え方が成立していた。

- running job は再起動時に `interrupted` として復元する。
- atomic write を使う。
- corrupted file を安全に読み込む。
- 起動時に queued / interrupted をユーザーへ明示する。

ただし、これは PySide6 export queue の設計であり、Tauri 検出ジョブへそのまま横滑りさせるものではない。今回取り込むのは、「job の永続状態はバックエンドの単一ストアで扱う」という原則である。

## 対象範囲

対象にする。

- `apps/backend/src/auto_mosaic/infra/ai/detect_jobs.py`
- `apps/backend/src/auto_mosaic/api/commands/start_detect_job.py`
- `apps/backend/src/auto_mosaic/api/commands/run_detect_job.py`
- `apps/backend/src/auto_mosaic/api/commands/get_detect_status.py`
- `apps/backend/src/auto_mosaic/api/commands/get_detect_result.py`
- `apps/backend/src/auto_mosaic/api/commands/cancel_detect_job.py`
- `apps/backend/src/auto_mosaic/api/commands/list_detect_jobs.py`
- `apps/backend/src/auto_mosaic/api/commands/cleanup_detect_jobs.py`
- 検出ジョブの backend tests
- 検出ジョブ安定後の `apps/desktop/src/App.tsx` の detect polling cleanup

初回では対象にしない。

- runtime jobs
- export jobs
- export queue
- Rust/Tauri IPC
- CLI command 名の変更
- response envelope の変更
- UI redesign
- FastAPI / HTTP / OpenAPI / 常駐 worker

## 保持する契約

CLI command 名は変更しない。

- `start-detect-job`
- `run-detect-job`
- `get-detect-status`
- `get-detect-result`
- `cancel-detect-job`
- `list-detect-jobs`
- `cleanup-detect-jobs`

response envelope は変更しない。

- `ok`
- `command`
- `data`
- `error`
- `warnings`

`stdout` は machine-readable JSON 専用のまま維持する。logs、diagnostics、traceback、native library 出力は `stderr` に送る。

## 目標アーキテクチャ

バックエンドに SQLite job ledger を追加する。Python 標準ライブラリの `sqlite3` を使い、外部 DB 依存は追加しない。

Ledger file は次へ固定する。

```text
ensure_runtime_dirs().data_dir / "jobs" / "job-ledger.sqlite3"
```

検出ジョブ履歴はアプリ再起動後の recovery 判断に使うため、`temp_dir` 配下には置かない。一時領域の cleanup や Windows Defender 等による一時ファイル削除の影響を避ける。

SQLite connection 初期化では次を明示する。

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

`start-detect-job` の親プロセスと `run-detect-job` の子プロセスが同時に ledger を書くため、WAL と busy timeout は必須とする。

重要なのは、`status.json` / `result.json` / PID / frontend の複数推論をやめ、SQLite の row を canonical state にすることである。

## Ledger Schema 方針

初期 schema は過剰に一般化しない。detect job に必要な最小限から始める。

Schema version は `PRAGMA user_version` で管理する。Phase 1 では version 1 の作成と、将来の forward-only migration helper の骨だけを入れる。rollback migration は不要。

推奨テーブル: `jobs`

| field | purpose |
| --- | --- |
| `job_id` | primary key |
| `job_kind` | 初期値は `detect` |
| `state` | `queued` / `running` / `cancelling` / `succeeded` / `failed` / `cancelled` / `interrupted` |
| `stage` | UI 表示用 stage |
| `progress_percent` | 0.0-100.0 |
| `message` | UI 表示用 message |
| `current` | 進捗 current |
| `total` | 進捗 total |
| `error_json` | failure details |
| `result_json` | succeeded result |
| `worker_pid` | worker liveness 補助情報。canonical state ではない |
| `cancel_requested` | cancel flag の canonical 値 |
| `heartbeat_at` | worker が最後に進捗を書いた時刻 |
| `created_at` | 作成時刻 |
| `updated_at` | 更新時刻 |
| `finished_at` | terminal state 到達時刻 |

必要なら将来 `job_events` を追加する。初回から event sourcing へ広げない。

## 状態遷移ルール

SQLite row の `state` を canonical state とする。

`result_json` の存在だけで `succeeded` に昇格してはならない。

`state=succeeded` と `result_json` は同一 SQLite transaction で書く。

`get-detect-result` は、ledger state が `succeeded` かつ `result_json` が存在する場合だけ結果を返す。

`heartbeat_at` を active job の stale 判定の第一情報とする。worker PID は死活確認の hint として保存してよいが、canonical 判定ではない。

`worker_pid` が死んで見えるだけでは成功・失敗を確定しない。ledger が active state のまま `heartbeat_at` から 60 秒を超えた場合に、バックエンドが `interrupted` へ遷移させる。PID はその時の補助 diagnostics として使う。

`heartbeat_at` は独立タイマーで書かない。progress/status update と同じ update で `updated_at` と合わせて更新する。native hang の検出はこの計画では heartbeat timeout のみで扱い、それ以上の watchdog は別課題とする。

cancel は request-based とする。terminal state の job を `cancelling` に戻してはならない。

## Frontend 方針

frontend は backend canonical state を表示するだけに戻す。

Ledger 移行が backend tests で安定するまで、frontend cleanup は後回しにする。

backend 移行後に削除するもの。

- `apps/desktop/src/App.tsx` の `interruptedGraceRef`
- `interrupted` を frontend 側で猶予する処理
- `result_available` / `has_result` による detect 成功推論
- terminal job への過剰な再 polling

frontend に残してよいもの。

- backend から返った canonical state の表示
- cancel button の UI
- Job Panel の共通表示
- terminal job の dismiss

## 実装フェーズ

| Phase | 目的 | 作業 | 完了条件 |
| --- | --- | --- | --- |
| 0 | 方針固定 | この文書を正本化し、FastAPI を範囲外に置く | `docs/engineering/job-ledger-migration-plan.md` が存在する |
| 1 | Ledger 基盤 | `sqlite3` ベースの ledger module を追加する | create/read/update/heartbeat/finish/cancel の unit tests が通る |
| 2 | Detect start 移行 | `start-detect-job` で ledger row を作成し、worker PID を保存する | start 成功・start 失敗・model preflight 失敗が ledger に反映される |
| 3 | Detect worker 移行 | `run-detect-job` の progress/result/failure/cancel を ledger に書く | success は `state=succeeded` と `result_json` を同一 transaction で保存する |
| 4 | Status/result 移行 | `get-detect-status` / `get-detect-result` を ledger 読み取りにする | result file existence による成功推論が消える |
| 5 | Recovery 移行 | `list-detect-jobs` / `cleanup-detect-jobs` を ledger 基準にする | active stale job が heartbeat timeout で `interrupted` になる |
| 6 | Backend tests | race-focused tests を追加する | success、failure、cancel、worker death、heartbeat timeout、result access が通る |
| 7 | Frontend cleanup | detect polling の猶予・推論を削除する | UI が backend canonical state だけを表示する |
| 8 | 展開判断 | runtime/export へ拡張するか決める | detect job 安定後に別文書または追記で判断する |

## 推奨する初回パッチ

初回パッチは backend ledger 基盤だけにする。

作業内容:

1. `apps/backend/src/auto_mosaic/infra/jobs/job_ledger.py` を追加する。
2. `sqlite3` 初期化、schema version、transaction helper を実装する。
3. detect job 用に必要な create/read/update/progress/finish/cancel/heartbeat API を用意する。
4. `apps/backend/tests/test_job_ledger.py` を追加する。
5. `App.tsx`、Rust、export/runtime job には触らない。

この順序にする理由は、状態の source of truth を先に backend 内で確立しないまま frontend cleanup を行うと、既存バグの見え方だけが変わり、根本原因が残るためである。

次のパッチで detect command に接続する場合は、Phase 2-5 を同じ実装スライスで完了させる。混在状態を避けるため、`start-detect-job`、`run-detect-job`、`get-detect-status`、`get-detect-result`、`cancel-detect-job`、`list-detect-jobs`、`cleanup-detect-jobs` のうち一部だけを ledger 化した状態で止めない。

## 受け入れ条件

backend:

- `status.json` の存在なしで detect job status を返せる。
- `result.json` の存在なしで detect result を返せる。
- `state=succeeded` と `result_json` が同一 transaction で保存される。
- worker crash 時に active job が timeout 後 `interrupted` へ遷移する。
- stale 判定は `heartbeat_at` を第一情報とし、`worker_pid` は補助 diagnostics に留める。
- cancel request が ledger に保存される。
- terminal state の job は cancel によって `cancelling` へ戻らない。
- `stdout` に logs / traceback が出ない。

frontend:

- detect job の成功判定を `has_result` / `result_available` から推論しない。
- `interrupted` の frontend grace period を追加・維持しない。
- Job Panel は backend state をそのまま表示する。

verification:

- backend ledger unit tests が通る。
- detect job smoke tests が通る。
- frontend cleanup 後に desktop build が通る。
- review-runtime に backend Python 変更を含める必要がある場合は `npm.cmd run review:runtime` を実行する。

## リスク

SQLite file lock は Windows で失敗しうる。実装では短い transaction、接続の明示 close、`PRAGMA journal_mode = WAL`、`PRAGMA busy_timeout = 5000` を使う。

worker が native crash した場合、最後の状態更新は残らない。そのため heartbeat timeout と worker PID は補助として必要である。ただし canonical success/failure の判定は ledger transaction で行う。PID は hint、`heartbeat_at` は stale 判定の第一情報として扱う。

既存 `status.json` / `result.json` ベースの tests は一時的に失敗する可能性がある。Phase 2-5 で ledger 契約に合わせて更新する。

worker death の race-focused test は Windows で実装難度が高い。Phase 6 ではサブプロセスを起動して強制終了する fixture が必要になる可能性がある。Windows では `taskkill /F /PID` 相当、POSIX では signal kill 相当を使う前提で設計する。Phase 1 ではこの fixture まで作らなくてよい。

runtime/export jobs に同じ仕組みを広げる誘惑があるが、detect job が安定するまで拡張しない。PM判断として、初回の価値は「検出ジョブの split-brain を断つこと」に限定する。

## 実装担当者への指示

```text
Implement the SQLite Job Ledger migration for detect jobs only.

Rules:
- Do not introduce FastAPI or HTTP.
- Do not change the Rust/Tauri IPC boundary.
- Do not change public CLI command names.
- Preserve the response envelope: ok, command, data, error, warnings.
- Keep stdout machine-readable JSON only.
- Do not touch runtime/export jobs in the first pass.
- Store the ledger at ensure_runtime_dirs().data_dir / "jobs" / "job-ledger.sqlite3".
- Configure SQLite with WAL journal mode and busy_timeout=5000.
- Manage schema version with PRAGMA user_version and forward-only migration helpers.
- Update heartbeat_at on normal progress/status writes; do not add a separate heartbeat timer in the first pass.
- Use heartbeat_at as the primary stale-job signal and worker_pid only as a diagnostic hint.
- Do not add frontend grace-period logic.
- Do not infer success from result.json existence.
- Commit detect job success by writing state=succeeded and result_json in one SQLite transaction.
- Make get-detect-status read canonical ledger state only.
- Make get-detect-result return data only for canonical succeeded state.
- Add focused backend tests before frontend cleanup.
- After the standalone ledger-base patch, migrate the detect command contract as one slice; do not leave start/status/result split between ledger and JSON files.

Suggested first patch:
1. Add apps/backend/src/auto_mosaic/infra/jobs/job_ledger.py.
2. Add apps/backend/tests/test_job_ledger.py.
3. Test create/read/update/heartbeat/finish/read-result/cancel/schema-version behavior.
4. Do not edit App.tsx, Rust, runtime jobs, or export jobs in this first patch.
```

## 非ゴール

- FastAPI HTTP migration
- OpenAPI generation
- Persistent Python worker
- JSON-RPC rewrite
- Runtime/export job migration in the first patch
- UI redesign
- Model management redesign
- Export queue redesign
