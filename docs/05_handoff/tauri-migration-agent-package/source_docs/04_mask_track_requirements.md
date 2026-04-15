# Mask Track Requirements

## 位置づけ

この文書は、マスク/トラック/キーフレーム周りの要求の正本です。  
次の2文書を統合した入口として扱います。

- 現行実装寄りの仕様: [02_mask-spec.md](../02_design/02_mask-spec.md)
- 目標挙動寄りの仕様: [persistent-mask-track-requirements.md](../99_archive/persistent-mask-track-requirements.md)

## 目標

- 1対象につき、できるだけ1本のマスクトラックを維持する
- 検出が一時的に途切れても即消えない
- ユーザーが任意フレームで manual keyframe を追加できる
- manual 編集は auto/predicted/re-detected に勝手に上書きされない
- UI と内部データと書き出しで同じ存在期間を共有する

## 要求の分離

### 製品要求

- ユーザーが編集対象として認識する単位は mask instance ではなく mask track
- 時間軸上での存在、欠落、補間、手修正の区別が見えること

### 現行設計要求

- `active / lost / inactive` のライフサイクルを持つ
- `auto / manual / interpolated / predicted / re-detected` の source を持つ
- 短命トラック除去、stitch、contour fallback が定義されている

### 今後の拡張要求

- `held / predicted / interpolated / uncertain` の区間可視化
- persistent track を前提にした UI 編集
- 欠落区間でも編集可能な一貫した保存モデル

## 正として扱う方針

- 実装済みの現在値と閾値は `docs/02_design/02_mask-spec.md` を優先
- 将来のあるべき体験と移行先の要求は `docs/99_archive/persistent-mask-track-requirements.md` を優先
- 新規実装では、両者が競合したら「ユーザーが同一トラックを継続編集できる」方を優先する

## 重要な禁止事項

- 検出が切れるたびに新規マスクを乱立させること
- manual keyframe を自動処理で上書きすること
- UI だけ表示して内部的には編集不能にすること
- 書き出しだけ別の存在期間判定を使うこと

## 関連文書

- 現行設計と UI: [01_architecture-and-ui.md](/h:/mosicprogect/mosic2/docs/02_design/01_architecture-and-ui.md)
- 旧詳細仕様: [02_mask-spec.md](../02_design/02_mask-spec.md), [persistent-mask-track-requirements.md](../99_archive/persistent-mask-track-requirements.md)
