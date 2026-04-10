# 人間向けドキュメント入口

このフォルダは、Auto Mosaic を使う人、レビューする人、仕様の全体像を先に理解したい人向けの入口です。
実装の細かい契約や内部設計ではなく、「何をするアプリか」「どう使うか」「今どこまでできるか」を先に読める形にしています。

## まず読むもの

| 目的 | ドキュメント |
|------|--------------|
| アプリの仕様をわかりやすく把握する | [product-spec.md](./product-spec.md) |
| 実際に動かして確認する | [../review/review-quickstart.md](../review/review-quickstart.md) |
| 一通りの動作確認をする | [../review/review-checklist.md](../review/review-checklist.md) |
| 実装済み/未実装を確認する | [../project/unimplemented-features.md](../project/unimplemented-features.md) |

## 読み方

- 仕様の説明は [product-spec.md](./product-spec.md) を起点にします。
- 開発者や AI エージェントが作業するときの正本は [../engineering/current-implementation.md](../engineering/current-implementation.md) です。
- 古い移行計画や過去の handoff は参考資料として残しますが、人間向けの判断材料にはしません。
