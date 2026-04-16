# 実装ロードマップ

最終更新: 2026-04-17 (Phase D 完了 pass)

この文書は、[missing-feature-matrix.md](./missing-feature-matrix.md) を実装順に並べ替えたロードマップです。
機能差分の正本は `missing-feature-matrix.md`、不変条件の正本は [../engineering/current-implementation.md](../engineering/current-implementation.md) を参照してください。

## 1. 現在の判断

- Tauri 安定化フェーズは完了扱いとする
- 最小導線 `open video -> detect -> mask edit -> save/load -> export` は手動確認済み
- これ以降の作業は「安定化の続き」ではなく「製品機能の完成」と「回帰防止」のフェーズに入る
- PySide6 比較資料は補助資料であり、今後の正本は `feature_list.md` / `unique_features.md` / `missing-feature-matrix.md` / この文書の 4 点に寄せる

### Phase 進捗サマリ (2026-04-17 時点)

| Phase | 目的 | 状態 |
| --- | --- | --- |
| A | Persistent workflow completion (recovery / review safety) | 完了 (M-A01〜M-A04) |
| B | Export workflow completion (queue / preset) | 未着手 |
| C | Regression & verification (Tauri E2E / output verify) | 未着手 |
| **D** | **Editing UX completion (M-C01〜M-C10)** | **コード実装完了、目視レビュー待ち** |
| E | AI / data / distribution | 未着手 |

### 達成済みチェックリスト

機能追加フェーズで完了した ID を、達成順に履歴として残す。詳細は
[missing-feature-matrix.md](./missing-feature-matrix.md) と
[ai-handoff.md](./ai-handoff.md) を参照。

- [x] **M-C01** polygon track 作成 (Phase D / 2026-04-16)
  - `Shift+N` / ヘッダーの `+ 多角形` / 初期矩形 polygon payload
- [x] **M-C02** ellipse 回転 UI (Phase D / 2026-04-17)
  - backend: `update-keyframe` で `rotation` patch 対応 (±180 正規化)、export の `cv2.ellipse` に angle を渡す
  - frontend: KeyframeDetailPanel に回転スライダー、MosaicPreviewCanvas と CanvasStagePanel の ellipse に rotation を反映
- [x] **M-C03** `export_enabled` フラグ (Phase D / 2026-04-17)
  - backend: domain / export skip / `update-track` patch
  - frontend: TrackDetailPanel toggle、TimelineView の斜線+バッジ、MosaicPreviewCanvas の破線 outline
- [x] **M-C04** 再生速度 / transport jump (Phase D / 2026-04-17)
  - transport bar に `0.25x〜4x` セレクタ、`Home` / `End` キーバインド
- [x] **M-C05** shortcut help modal (Phase D / 2026-04-17)
  - `ShortcutHelpModal` コンポーネントで F1 alert を置き換え、カテゴリ別テーブル
- [x] **M-C06** preview operation mode badge (Phase D / 2026-04-17, 追加)
  - canvas 左上に再生状態 / モザイク / 選択トラック (非表示・書き出し外・ロックのサブラベル) を表示
- [x] **M-C07** onion skin (Phase D / 2026-04-17, 追加)
  - 前後 explicit keyframe を canvas に SVG で破線表示 (前=青、次=橙)、preview バーの `オニオン ON/OFF` トグル
- [x] **M-C09** UI 言語切替 (Phase D / 2026-04-17, 追加)
  - `uiText.ts` に `UiText` 型と `getUiText(lang)` を追加、英訳辞書を整備。header に `日本語 / EN` トグル、`auto-mosaic:language` localStorage で保持
- [x] **M-C08** diff overlay (Phase D / 2026-04-17, 追加)
  - `Shift+M` で全 visible && export_enabled track の resolve_for_render 結果を canvas に半透明マゼンタで重ね、モザイク適用領域を可視化
- [x] **M-C10** inspector 折りたたみ永続化 (Phase D / 2026-04-17)
  - `usePersistedDetails` hook で `<details>` 開閉状態を localStorage に保存

**Phase D (Editing UX Completion) は全 10 項目達成**。コード実装は完了しており、次は Tauri ウィンドウでの目視レビュー。

## 2. Phase A: Persistent Workflow Completion

目的:
- recovery と review safety を frontend 一時 state から外し、再起動に耐える実装へ移す

完了条件:
- recovery snapshot を backend/file-backed で保持できる
- 起動時 recovery dialog が backend 側の snapshot を読む
- danger warning が `review / export anyway / cancel` の 3 択で動く
- warning 確認済み状態の保存先を明文化し、再起動時の扱いが決まっている

対象:
- `M-A01` file-backed recovery
- `M-A02` recovery fail-safe / interrupted restore policy
- `M-A03` export 前 danger warning dialog 化
- `M-A04` confirmed warning state の保存方針固定

検証:
- dirty project を作成して snapshot 保存
- 再起動後に復元 / 破棄の両方を確認
- danger warning が残っている状態で export を開き、review/export/cancel の 3 導線を確認

## 3. Phase B: Export Workflow Completion

目的:
- 現在の単発 export を、仕様書どおりの queue ベース workflow に拡張する

完了条件:
- 複数 export job を queue に積める
- queue は逐次実行される
- 再起動後に `running` job は `interrupted` へ復元される
- export 設定 UI が、現在の仕様書で必須とする項目を扱える

対象:
- `M-B01` multi-job export queue
- `M-B02` queue persistence / interrupted restore
- `M-B03` export settings breadth の拡張
- `M-B04` user-defined export preset
- `M-B05` queue UI / recent results

検証:
- queue に 2 件以上追加して順次実行
- 実行中にアプリを閉じ、再起動後の interrupted 復元を確認
- queue 経由でも cancel / completed / failed が崩れないことを確認

## 4. Phase C: Regression And Verification

目的:
- ここまでの persistent workflow と export workflow を、人手だけに依存せず守れる状態にする

完了条件:
- Tauri 実ウィンドウを使った代表フローの E2E がある
- recovery と export queue の再起動系を自動または半自動で検証できる
- export 出力の最低限の自動検証がある

対象:
- `M-E01` Tauri E2E
- `M-E02` crash recovery E2E
- `M-E03` export output verification

検証:
- `open -> detect -> edit -> save/load -> export` の代表フロー
- recovery / interrupted export queue の復元フロー
- 既知の ROI にモザイクが入ることの自動確認

## 5. Phase D: Editing UX Completion

目的:
- コア workflow を壊さない前提で、仕様書にある編集体験の不足分を埋める

完了条件:
- polygon track 作成、ellipse 回転、`export_enabled` が揃う
- transport / shortcut / help が現在の仕様書に近づく
- preview / timeline の状態表示が整理される
- 後回し機能は `deferred` のまま採否を明文化する

対象:
- [x] `M-C01` polygon track 作成 (2026-04-16 達成)
- [x] `M-C02` ellipse 回転 UI (2026-04-17 達成)
- [x] `M-C03` `export_enabled` (2026-04-17 達成)
- [x] `M-C04` playback speed / transport jump (2026-04-17 達成)
- [x] `M-C05` shortcut help modal (2026-04-17 達成)
- [x] `M-C06` mode badge / legend / state visualization (2026-04-17 達成)
- [x] `M-C07` onion skin (2026-04-17 達成)
- [x] `M-C08` diff overlay (2026-04-17 達成)
- [x] `M-C09` UI 言語切替 (2026-04-17 達成)
- [x] `M-C10` inspector 折りたたみ (2026-04-17 達成)

検証:
- canvas / timeline / inspector の一連操作
- shortcut 一覧と実際の割り当てが一致すること
- `export_enabled` off の track が preview と export で期待どおり分離されること

## 6. Phase E: AI / Data / Distribution

目的:
- 製品完成後の差別化機能と配布整備を進める

完了条件:
- detect 速度最適化方針が決まり、実装または判断保留の理由が残る
- model management / contour follow / detector breadth の扱いが整理される
- teacher dataset / retraining / installer の入口ができる

対象:
- `M-D01` AI detect performance tuning
- `M-D02` contour follow
- `M-D03` installed model management
- `M-D04` detector engine breadth の再判断
- `M-D05` detect settings persistence
- `M-E04` teacher dataset
- `M-E05` local retraining
- `M-E06` installer / updater

検証:
- GPU/CPU の実測比較
- contour follow の停止条件と manual 保護
- installer / updater は別途配布手順書とあわせて確認

## 7. すぐに実装対象へ落とすときの単位

実装依頼は、この文書の phase と `missing-feature-matrix.md` の ID をセットで切る。

例:

```text
Phase B の M-B01 / M-B02 を実装してください。
完了条件:
- 複数 export job を queue に積める
- queue は逐次実行される
- 再起動後に running job は interrupted として復元される
- 関連テストを追加する
```

## 8. 補助資料

- PySide6 比較の機能 ID と観察ログ: [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md)
- PySide6 UI 観察記録: [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md)
- 直近の時系列 handoff: [ai-handoff.md](./ai-handoff.md)
