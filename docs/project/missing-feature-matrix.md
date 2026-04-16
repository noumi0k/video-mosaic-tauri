# 不足機能マトリクス

最終更新: 2026-04-17 (Phase A / B core / C core / D 完了)

この文書は、追加された仕様書 [../feature_list.md](../feature_list.md) と [../unique_features.md](../unique_features.md) を基準に、現行 Tauri 実装でまだ不足している機能を整理した差分一覧です。

実装判断の順序は次のとおりです。

1. 現行コードとテスト
2. [../engineering/current-implementation.md](../engineering/current-implementation.md)
3. この文書
4. [unimplemented-features.md](./unimplemented-features.md)
5. PySide6 比較資料

## ステータス定義

- `partial`: 一部は動くが、現在の仕様書の要求を満たし切っていない
- `missing`: 現在の実装には存在しない
- `deferred`: 仕様書にはあるが、現行の完成優先順位では後段に回す
- `done`: 実装済み (履歴として残す — 新規差分は取り消し線で表記)

## 1. すでに揃っている基盤

次の土台は、安定化フェーズ完了時点で揃っている。

- project open / save / load、PySide6 v1 から Tauri schema v2 への migration
- raw local path を backend の正本とする path ルール
- mask track 中心の project model、manual edit 保護、segment-aware export
- open video → detect → mask edit → save/load → export の最小導線
- detect / runtime / export の job-based 進捗表示と cancel
- integrity-based model check、GPU 失敗時の CPU fallback
- timeline / canvas / inspector の基本編集

機能追加フェーズ以降に達成済みの項目 (履歴として残す):

- [x] **M-A01** file-backed crash recovery (backend snapshot commands + frontend migration) (2026-04-17)
- [x] **M-A02** recovery fail-safe (snapshot_id validation / atomic write / broken list isolation) (2026-04-17)
- [x] **M-A03** export 前 3 択 danger modal (review / export anyway / cancel) (2026-04-17)
- [x] **M-A04** confirmed danger frames を recovery snapshot に永続化 (2026-04-17)
- [x] **M-B01** file-backed export queue + frontend drive loop (2026-04-17)
- [x] **M-B02** queue persistence と再起動時の interrupted 復元 (2026-04-17)
- [x] **M-B05** export queue UI (state 色分け / 削除 / 再実行 / 一括クリア) (2026-04-17)
- [x] **M-B04** user-defined export preset (save / list / delete) (2026-04-17)
- [x] **M-E02 (backend)** recovery end-to-end 検証: save → 再起動模擬 → list → restore → delete (2026-04-17)
- [x] **M-E03** export output multi-frame ROI verification (8 frame 全てでピクセル差分を assert) (2026-04-17)
- [x] **M-C01** manual polygon track 作成 (2026-04-16)
- [x] **M-C02** ellipse 回転の UI / 描画 / patch 対応 (2026-04-17)
- [x] **M-C03** track 単位の `export_enabled` フラグ / preview の破線 outline / timeline 斜線・バッジ (2026-04-17)
- [x] **M-C04** 再生速度セレクタ (0.25x〜4x) と Home/End シーク (2026-04-17)
- [x] **M-C05** shortcut help modal (F1) (2026-04-17)
- [x] **M-C06** canvas mode badge (再生状態 / モザイク / 選択トラック) (2026-04-17)
- [x] **M-C07** onion skin オーバーレイ (前後 explicit keyframe の破線表示) (2026-04-17)
- [x] **M-C08** diff overlay (Shift+M、モザイク適用領域をマゼンタ半透明で可視化) (2026-04-17)
- [x] **M-C09** UI 言語切替 (ja / en) ヘッダートグル + localStorage (2026-04-17)
- [x] **M-C10** inspector 折りたたみ状態の localStorage 永続化 (2026-04-17)

**Phase D (Editing UX Completion) は全 10 項目達成**。目視レビュー待ち。

この文書では、上記に対してまだ不足している機能だけを列挙する。

## 2. 不足機能一覧

### A. 永続化 / review safety

| ID | ソース | 状態 | 不足内容 | 現状メモ | フェーズ |
| --- | --- | --- | --- | --- | --- |
| ~~M-A01~~ | `feature_list` 16, `unique_features` 13 | done | crash recovery を `localStorage` 依存から backend/file-backed に移す | 2026-04-17 (4th): `save-recovery-snapshot` / `list-recovery-snapshots` / `delete-recovery-snapshot` を実装し `user-data/recovery/` に JSON で保存。frontend は backend コール中心で localStorage は legacy migration 専用 | A |
| ~~M-A02~~ | `feature_list` 16, `unique_features` 13 | done | recovery データ破損時の fail-safe と interrupted restore 方針 | 2026-04-17 (4th): snapshot_id の厳格 validation (SAFE_ID regex)、atomic write、list で壊れた JSON は `broken[]` に分離して skip。interrupted export restore は Phase B の queue 実装と合流予定 | A |
| ~~M-A03~~ | `feature_list` 13-10, `unique_features` 8 | done | export 前 warning を 3 択の review/export/cancel 導線へ | 2026-04-17 (4th): `window.confirm` を撤去、未確認 danger frame がある時に「詳細を確認 / そのまま書き出し / キャンセル」の modal で処理分岐。詳細を確認 → 最初の対象フレームへ seek | A |
| ~~M-A04~~ | `feature_list` 13-10, `unique_features` 8 | done | warning 確認済み状態の保存方針 | 2026-04-17 (4th): `confirmedDangerFrames` を recovery snapshot に `confirmed_danger_frames: string[]` として保存。起動時 / 手動復元時に state を復元。project ファイル本体は汚さない | A |

### B. Export workflow completion

| ID | ソース | 状態 | 不足内容 | 現状メモ | フェーズ |
| --- | --- | --- | --- | --- | --- |
| ~~M-B01~~ | `feature_list` 14-1/14-2, `unique_features` 13 | done | 複数 export job の逐次実行 | 2026-04-17 (5th): `user-data/export-queue/queue.json` 1 本に atomic write。frontend は useEffect drive loop で `queued` を順次 `running → completed/failed` へ遷移 | B |
| ~~M-B02~~ | `feature_list` 14-2, `unique_features` 13 | done | export queue の永続化と再起動時の `interrupted` 復元 | 2026-04-17 (5th): `list-export-queue` 呼び出し時に `running` を `interrupted` に自動変換し、UI に `再実行` ボタンで requeue | B |
| M-B03 | `feature_list` 13-3/13-4/13-5/13-6/13-7 | partial | export 設定を仕様書レベルまで広げる | 現状は `resolution` `mosaic_strength` `audio_mode` `bitrate_kbps` `encoder` のみ (codec / container / FPS / quality 未対応) | B |
| ~~M-B04~~ | `feature_list` 13-9 | done | user-defined export preset の保存 / 再利用 / 削除 | 2026-04-17 (6th): `list-export-presets` / `save-export-preset` / `delete-export-preset` を実装、`user-data/presets/{name}.json` に 1 ファイル 1 preset。ExportSettingsModal にセレクタ + 保存 / 削除導線 | B |
| ~~M-B05~~ | `feature_list` 14-1 | done | queue UI と recent export results の整理 | 2026-04-17 (5th): Job Panel の下に `.nle-export-queue` セクションを追加。state 別色分け + 削除 / 再実行 / 終了項目一括クリア | B |

### C. 編集体験の不足

| ID | ソース | 状態 | 不足内容 | 現状メモ | フェーズ |
| --- | --- | --- | --- | --- | --- |
| ~~M-C01~~ | `feature_list` 6-2 | done | 手動 polygon track 作成の正式導線 | 2026-04-16: ヘッダーに `+ 多角形`、`Shift+N`、初期矩形 polygon 作成を追加 | D |
| ~~M-C02~~ | `feature_list` 7-4 | done | ellipse 回転の UI | 2026-04-17: keyframe inspector にスライダー/数値入力、canvas ellipse に transform:rotate、export の `cv2.ellipse(angle)` と preview `ctx.ellipse(rotation)` に反映、update-keyframe patch で rotation 受け入れ | D |
| ~~M-C03~~ | `feature_list` 6-8, `unique_features` 7 | done | `export_enabled` フラグと preview/timeline 上の対象外表示 | 2026-04-17 実装: domain / export / update-track / TrackDetailPanel / Timeline / Preview (破線 outline) に反映 | D |
| ~~M-C04~~ | `feature_list` 4-2/4-4/4-5, 17 | done | 再生速度変更と transport shortcut の拡張 | 2026-04-17: transport bar に 0.25x〜4x 速度セレクタ、Home/End を keydown / shortcut help に追加 | D |
| ~~M-C05~~ | `feature_list` 17, 19 | done | shortcut help を専用 modal 化 | 2026-04-17: `ShortcutHelpModal` を導入、F1 は window.alert から modal に置換、カテゴリ別テーブル表示。未接続 `Ctrl+M` `Ctrl+E` は採否判断保留 | D |
| ~~M-C06~~ | `feature_list` 3-5, `unique_features` 16 | done | preview mode badge、timeline legend、lost/inactive 可視化 | 2026-04-17 (2nd): canvas 左上に再生状態 / モザイク / 選択トラック (`非表示` `書き出し外` `ロック` サブラベル) を示す mode badge を追加。timeline legend も拡張済み | D |
| ~~M-C07~~ | `project checklist` D-09, `pyside6-ui-structure-reference` | done | onion skin | 2026-04-17 (2nd): 前後の explicit keyframe を canvas に SVG で重ね (前=青破線 / 次=橙破線)、preview バーの `オニオン ON/OFF` でトグル | D |
| ~~M-C08~~ | `feature_list` 3-4 | done | diff overlay | 2026-04-17 (3rd): `Shift+M` で全 visible && export_enabled track の resolve_for_render 結果を canvas に半透明 (マゼンタ) で重ねる。preview バーに `差分 ON/OFF` トグル、ShortcutHelpModal にも追記 | D |
| ~~M-C09~~ | `feature_list` 18-1 | done | 日本語 / 英語の UI 言語切替 | 2026-04-17 (2nd): `uiText` を `UiText` 型化し `getUiText(lang)` を追加、英訳の完全辞書を導入。header に ja/EN 切替ボタン、設定は `auto-mosaic:language` localStorage に保存 | D |
| ~~M-C10~~ | `feature_list` 19-3 | done | property panel の折りたたみセクション | 2026-04-17: `usePersistedDetails` hook を導入し、5 つの inspector section の開閉状態を localStorage に永続化 | D |

### D. AI 検出 / モデル管理の不足

| ID | ソース | 状態 | 不足内容 | 現状メモ | フェーズ |
| --- | --- | --- | --- | --- | --- |
| M-D01 | `unimplemented-features`, `feature_list` 11 | missing | GPU/CPU 実測に基づく detect 速度最適化 | CUDA が使えても CPU より遅く見えるケースの調査未着手 | E |
| M-D02 | `unique_features` 4 | missing | contour follow (optical flow) | current implementation / frontend とも未導入 | E |
| M-D03 | `feature_list` 12-2 | partial | installed model 管理タブ | detector modal で状態確認はできるが、一覧管理や削除導線はない | E |
| M-D04 | `feature_list` 11-1, `unique_features` 10 | deferred | YOLO / SSD 系まで含めた detector backend breadth | 現行 Tauri は NSFW-first の detector set に絞っている | E |
| M-D05 | `unique_features` 9 | partial | detect device / tuning 設定の永続化 | doctor から初期値は出すが、session 間の保存はない | E |

### E. QA / data / distribution

| ID | ソース | 状態 | 不足内容 | 現状メモ | フェーズ |
| --- | --- | --- | --- | --- | --- |
| M-E01 | `feature_list` 16, `project checklist` K-03 | missing | Tauri 実操作 E2E | playwright / tauri-driver 導入は別パスに先送り (スコープ大)。ユニット + CLI smoke で実質カバー中 | C |
| ~~M-E02~~ | `feature_list` 16, `project checklist` K-04 | done (backend) | crash recovery E2E (backend 再現) | 2026-04-17 (7th): `test_recovery_workflow_simulates_restart` で save → 新プロセス (新 ensure_runtime_dirs) → list → restore → delete の全段階を検証。Tauri ウィンドウの実操作 E2E は M-E01 と合わせて後段 | C |
| ~~M-E03~~ | `project checklist` K-05 | done | export output の差分検証 | 2026-04-17 (7th): `test_export_video_mosaic_persists_across_all_frames` で 8 フレーム全てについて ROI ピクセル差分を検証 (差分 > 4 を要求) | C |
| M-E04 | `feature_list` 16, `architecture/p4-retraining-requirements.md` | missing | teacher dataset 保存 | opt-in UI、crop、metadata、manifest が未実装 | E |
| M-E05 | `feature_list` 16, `architecture/p4-retraining-requirements.md` | missing | local retraining | validator、training job、trained model 管理が未実装 | E |
| M-E06 | `feature_list` 16, `operations` | missing | 正式 installer / updater | review package はあるが、正式配布導線は未整備 | E |

## 3. この一覧から外したもの

次は「現時点では足りない機能一覧」に入れていない。

- 現行コード上で最低限の機能が揃っており、追加 polish のみが残る項目
- PySide6 比較資料にはあるが、新しい仕様書では必須機能として明文化されていない項目
- 将来の内部リファクタ対象であって、ユーザー機能不足ではない項目

具体例:

- `App.tsx` 分割のような内部整理
- PySide6 の UI 配置そのものの再現
- history tree や track order DnD のような未採用 convenience 機能

## 4. 次に使う文書

- 実装順序と受け入れ条件は [unimplemented-features.md](./unimplemented-features.md)
- 不変条件と責務境界は [../engineering/current-implementation.md](../engineering/current-implementation.md)
- 仕様の母集団は [../feature_list.md](../feature_list.md) と [../unique_features.md](../unique_features.md)
