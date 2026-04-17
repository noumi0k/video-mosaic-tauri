# Project ドキュメント入口

このフォルダは、Auto Mosaic の開発状態、仕様差分、実装順序、PySide6 比較資料を扱います。

安定化フェーズは完了扱いになったため、今後は「PySide6 比較を主軸にする」のではなく、「現行仕様との差分」と「実装順序」を主軸に読む構成へ切り替えます。

## 中核ドキュメント

| 役割 | ドキュメント | 読み方 |
| --- | --- | --- |
| 現行実装の不変条件 | [../engineering/current-implementation.md](../engineering/current-implementation.md) | backend/frontend 境界、project state、job model などの正本 |
| 仕様との差分一覧 | [missing-feature-matrix.md](./missing-feature-matrix.md) | `feature_list.md` / `unique_features.md` に対して何が足りないかを確認する |
| 実装順序と受け入れ条件 | [unimplemented-features.md](./unimplemented-features.md) | phase 単位で次に何を作るかを決める |
| PySide6 比較の補助資料 | [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md) | 旧 checklist と比較ログを参照する |
| UI 観察資料 | [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) | PySide6 UI の配置や導線を参考にする |

## 読む順番

1. [../engineering/current-implementation.md](../engineering/current-implementation.md)
2. [../feature_list.md](../feature_list.md)
3. [../unique_features.md](../unique_features.md)
4. [missing-feature-matrix.md](./missing-feature-matrix.md)
5. [unimplemented-features.md](./unimplemented-features.md)
6. 必要に応じて [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md) / [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) / [ai-handoff.md](./ai-handoff.md)

## ドキュメントの役割

| ファイル | 役割 | 更新タイミング |
| --- | --- | --- |
| [missing-feature-matrix.md](./missing-feature-matrix.md) | 現行仕様との差分一覧 | 新しい仕様書を追加したとき、実装状況の見立てを変えたとき |
| [unimplemented-features.md](./unimplemented-features.md) | 実装ロードマップ | phase、優先順位、受け入れ条件を変えたとき |
| [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md) | PySide6 比較の checklist / 旧フェーズ票 | 比較ログを追加したとき |
| [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) | PySide6 UI の観察記録 | 参照すべき UI 情報を追加で確認したとき |
| [ai-handoff.md](./ai-handoff.md) | 直近作業の handoff log | 大きな作業完了時。履歴として更新 |
| [pyside6-remaining-tasks.md](./pyside6-remaining-tasks.md) | PySide6 比較の過去資料 | 基本的に更新しない |
| [未実装機能一覧.md](./未実装機能一覧.md) | 日本語名の入口 | `unimplemented-features.md` への誘導用 |

## 判断優先順位

実装判断で資料が衝突した場合は、次の順で優先する。

1. 現行コードとテスト
2. [../engineering/current-implementation.md](../engineering/current-implementation.md)
3. [missing-feature-matrix.md](./missing-feature-matrix.md)
4. [unimplemented-features.md](./unimplemented-features.md)
5. PySide6 比較資料
6. `ai-handoff.md` や移行アーカイブなどの履歴資料

## AI エージェントへの依頼単位

AI エージェントへ依頼するときは、phase と gap ID をセットで切る。

```text
Phase B の M-B01 / M-B02 を実装してください。
達成条件:
- export queue に複数 job を積める
- queue は逐次実行される
- 再起動後に running job は interrupted として復元される
- 関連テストを追加する
```

避ける依頼:

```text
PySide6 と同じ UI にしてください。
```

理由:

- PySide6 版 UI は参照資料であり、そのままの再現仕様ではない
- Tauri 版では Web UI としての情報設計と操作導線を優先する
- backend contract、project schema、job state、manual edit 保護を先に守る必要がある

## 更新ルール

- 新しい仕様差分が見つかったら [missing-feature-matrix.md](./missing-feature-matrix.md) を更新する
- 実装順序を変えたら [unimplemented-features.md](./unimplemented-features.md) を更新する
- backend/domain の不変条件が変わる場合は [../engineering/current-implementation.md](../engineering/current-implementation.md) を更新する
- PySide6 観察事項を増やす場合だけ比較資料を更新する
- speculative な思いつきは正本に入れず、必要なら別の検討メモへ分離する
