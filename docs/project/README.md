# Projectドキュメント入口

このフォルダは、Auto Mosaicの開発状態、今後の開発方針、PySide6版との比較資料を扱います。

## 位置づけ

安定化フェーズ中は、現行実装の不変条件と未実装一覧を優先します。

安定化フェーズ完了後は、今回作成した次の2資料を今後の開発の中核として扱います。

| 役割 | ドキュメント | 読み方 |
| --- | --- | --- |
| 今後の開発ロードマップ | [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md) | PySide6同等の編集体験へ近づけるための機能チェックリストと開発フェーズ票 |
| UI参照資料 | [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) | PySide6版のUI構成、ボタン配置、メニュー構成の観察記録。Tauri版UIの再現仕様ではない |

## 読む順番

### 安定化フェーズ中

1. [../engineering/current-implementation.md](../engineering/current-implementation.md)
2. [unimplemented-features.md](./unimplemented-features.md)
3. [ai-handoff.md](./ai-handoff.md)
4. [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md)
5. [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md)

安定化フェーズ中は、backend state、job、detect、export、manual edit保護などの不変条件を壊さないことを最優先にします。

### 安定化フェーズ完了後

1. [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md)
2. [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md)
3. [unimplemented-features.md](./unimplemented-features.md)
4. [../engineering/current-implementation.md](../engineering/current-implementation.md)
5. [ai-handoff.md](./ai-handoff.md)

安定化フェーズ完了後は、`pyside6-editing-experience-parity-checklist.md`のIDとフェーズを開発単位にします。

## ドキュメントの役割

| ファイル | 役割 | 更新タイミング |
| --- | --- | --- |
| [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md) | 今後の主ロードマップ。機能一覧、達成条件、開発フェーズ票 | 新機能の方針、優先順位、完了条件を変えるとき |
| [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md) | PySide6版UIの観察記録。Tauri版UIを設計するための参考 | PySide6版UIから参照すべき操作や配置を追加で調べたとき |
| [unimplemented-features.md](./unimplemented-features.md) | 実装済み/未実装の状態管理 | 実装完了、優先度変更、残課題整理のたび |
| [ai-handoff.md](./ai-handoff.md) | 直近作業の時系列handoff log | 大きな作業完了時。正本ではなく履歴 |
| [pyside6-remaining-tasks.md](./pyside6-remaining-tasks.md) | PySide6比較の過去資料 | 履歴参照用。通常は更新しない |
| [pyside6-source-handoff-prompt.md](./pyside6-source-handoff-prompt.md) | PySide6ソース調査用のhandoff prompt | 調査手順を変えるときだけ |
| [未実装機能一覧.md](./未実装機能一覧.md) | 日本語名の入口 | `unimplemented-features.md`への誘導用 |

## 判断優先順位

実装判断で資料が衝突した場合は、次の順で優先します。

1. 現行コードとテスト
2. [../engineering/current-implementation.md](../engineering/current-implementation.md)
3. [unimplemented-features.md](./unimplemented-features.md)
4. [pyside6-editing-experience-parity-checklist.md](./pyside6-editing-experience-parity-checklist.md)
5. [pyside6-ui-structure-reference.md](./pyside6-ui-structure-reference.md)
6. `ai-handoff.md`や移行アーカイブなどの履歴資料

ただし、安定化フェーズ完了後の新規機能計画では、`pyside6-editing-experience-parity-checklist.md`を最初に参照します。

## AIエージェントへの依頼単位

AIエージェントへ作業を依頼するときは、原則として次の形にします。

```text
pyside6-editing-experience-parity-checklist.md の H-05 を実装してください。
達成条件:
- 未確認danger warningが残る場合、export前に警告する
- 全確認済みなら警告せずexportへ進む
- timeline markerとpanelの確認状態を一致させる
- 関連テストを追加する
```

避ける依頼:

```text
PySide6と同じUIにしてください。
```

理由:

- PySide6版UIは参照資料であり、Tauri版の再現仕様ではない。
- Tauri版ではWeb UIとしての情報設計と操作導線を優先する。
- backend contract、project schema、job state、manual edit保護を先に守る必要がある。

## 更新ルール

- 新規機能を追加したら、該当するチェックリストIDを更新する。
- 実装済み/未実装の状態は`unimplemented-features.md`へ反映する。
- backend/domainの不変条件が変わる場合は`../engineering/current-implementation.md`を更新する。
- UI方針やPySide6版からの観察事項を追加する場合は`pyside6-ui-structure-reference.md`へ反映する。
- speculativeな思いつきは正本へ入れず、必要なら別の検討メモとして分ける。
- PySide6版のUI配置をそのまま移植する方針は採用しない。
