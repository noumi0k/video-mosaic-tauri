# P4 要件整理（EraX 改善ベース）

最終更新: 2026-04-11

## 0. 位置づけ

本ドキュメントは、EraX 改善ベースの P4-1 / P4-2 要件整理である。

前提として、現行本線は PySide6 で、P4-1 は「教師データ保存」、P4-2 は「ローカル自動再学習」であり、P4-1 と P4-2 には依存関係がある。

現状不足として、P4-1 では opt-in UI、保存先管理、件数 / 容量表示、プロジェクト単位削除、dataset manifest 生成が未実装である。P4-2 では training job、train / val split、学習ログ、モデル一覧、active model 切替、比較レポート、ロールバックが未実装である。

また、このソフトの土台は完全ローカル実行で、YOLO 系のカスタム検出モデルを ONNX 化前提で差し替え可能にしておく方針が元々ある。

## 1. 目的

本機能群の目的は次の3点である。

1. ユーザー PC 内で完結する教師データ蓄積
2. EraX をローカル再学習して、ユーザー専用モデルを生成利用可能にすること
3. 将来的に、教師データ本体を回収せず、学習済みモデルのみを回収評価再配布できる条件を整えること

## 2. 前提条件

### 2.1 セキュリティ前提

- 教師データには無修正フレームが含まれうるため、教師データ本体はアプリ外送信しない
- P4-1 / P4-2 初版では、ネットワーク送信機能を持たない
- 収集、保存、学習利用は、すべてユーザーのローカル PC 内で完結する

### 2.2 学習対象前提

- 初回の再学習対象は EraX のみ
- NudeNet 再学習、SAM2 再学習は今回スコープ外
- 学習対象は検出モデルであり、主教師データは bbox + class
- polygon は教師データの源泉として保持するが、学習投入時には bbox 化する

### 2.3 UX 前提

- 本ソフトは編集ソフトであり、価値の中心は人間が編集画面で修正した結果である
- プレビュー上の頂点編集、トラック編集、キーフレーム編集の結果を、教師データ生成に活用する
- 自動検出は補助であり、最終正解はユーザー編集結果とする設計を維持する。これは既存要件の「人間による最終確認前提」と整合する

## 3. スコープ

### 3.1 P4-1 のスコープ

- ローカル教師データ保存
- データ収集 ON / OFF
- 保存先管理
- 保存件数 / 容量表示
- プロジェクト単位削除
- accepted / rejected 管理
- dataset manifest 生成
- EraX 学習用 bbox ラベル出力

### 3.2 P4-2 のスコープ

- ローカル学習ジョブ実行
- train / val split
- 学習ログ表示
- val 指標表示
- 学習済みモデル一覧
- active model 切替
- ONNX export
- ロールバック

### 3.3 今回スコープ外

- 教師データのアップロード
- 学習済みモデルの自動送信
- 中央サーバーでの統合学習
- モデルマージ
- 集約評価の自動化
- SAM2 / contour 系再学習
- 複数検出モデルの同時学習

## 4. P4-1 要件: ローカル教師データ保存

### 4.1 目的

ユーザーが編集で確定させた結果を、EraX 再学習可能なローカルデータセットとして保存する。

### 4.2 保存対象

1サンプルは最低限、次を持つ。

#### 元データ

- source_video_path または内部 video_id
- frame_index
- frame_timestamp
- 元フレーム画像
- 初期検出 bbox
- 初期検出 class
- 初期検出 score
- track_id

#### 編集結果

- 最終 polygon
- polygon から導出した最終 bbox
- 編集後 class
- 修正種別
  - auto_accept
  - bbox_adjusted
  - polygon_refined
  - manual_added
  - false_positive_removed
- 採用状態
  - pending
  - accepted
  - rejected

#### 学習用派生データ

- YOLO label txt
- split 候補
  - unassigned
  - train
  - val
- サンプル fingerprint
- manifest entry

### 4.3 保存ルール

- デフォルトは OFF
- ユーザーが明示的に ON にした場合のみ保存
- 保存先はユーザー指定可能
- 保存済みデータはユーザーが削除可能
- 保存の有無は UI 上で明確に分かること

これは既存の将来拡張要件とも一致する。

### 4.4 正解データの定義

- 学習上の正解は編集完了後の最終 bbox
- bbox は最終 polygon の外接矩形から生成する
- polygon 自体も保存するが、P4-2 の EraX 学習には直接使わない
- false positive の削除も教師情報として扱う

### 4.5 保存トリガー

以下のいずれかでサンプル確定候補に入る。

- ユーザーが manual 修正を保存したとき
- トラック確定操作を行ったとき
- プロジェクト保存時に「教師データへ反映」が有効なとき
- 書き出し前チェック通過済みサンプルを accepted にするとき

### 4.6 UI 要件

設定または専用パネルに次を追加する。

- 教師データ保存 ON / OFF
- 保存先 browse
- 保存件数
- 総容量
- accepted 件数 / rejected 件数 / pending 件数
- プロジェクト単位削除
- 全削除
- manifest 再生成
- 学習用に含める / 含めない の切替

### 4.7 フォルダ構成

```text
data/training/erax/
  manifest.json
  dataset.yaml
  classes.txt
  images/
    pending/
    train/
    val/
  labels/
    pending/
    train/
    val/
  metadata/
    samples/
  review/
    accepted.json
    rejected.json
```

### 4.8 非機能要件

- atomic write
- 途中中断で壊れにくいこと
- 同一サンプル二重保存を避けること
- 容量肥大を可視化すること
- ネットワーク不要で動作すること。既存要件の「完全ローカル利用可能」と一致する

## 5. P4-2 要件: ローカル再学習

### 5.1 目的

P4-1 で蓄積した accepted サンプルを使って、ユーザー専用の EraX 派生モデルを生成し、アプリ内で利用可能にする。

### 5.2 学習前提

入力データは P4-1 が生成した dataset とする。学習前に以下をチェックする。

- 最小サンプル数
- train / val 両方に最低件数があるか
- GPU 利用可否
- 必要ディスク空き容量
- 出力先書き込み可否

条件未達なら学習開始不可とする。

### 5.3 学習ジョブ

学習ジョブは最低限、次の状態を持つ。

- queued
- preparing
- training
- validating
- exporting
- completed
- failed
- cancelled

### 5.4 学習フロー

1. accepted サンプル収集
2. train / val split 実施
3. dataset.yaml 生成
4. base EraX から fine-tune
5. best checkpoint 保存
6. validation 実行
7. ONNX export
8. モデル登録
9. active model 切替可能状態にする

### 5.5 学習ログ

UI 上で次を表示する。

- 現在ステージ
- epoch
- 経過時間
- loss
- val 指標
- 出力パス
- エラー内容
- cancel 可否

### 5.6 モデル管理

学習済みモデル一覧には次を表示する。

- model_name
- created_at
- base_model_id
- base_model_hash
- sample_count
- train_count
- val_count
- val_metrics
- export_format
- app_version
- status
- active / inactive

### 5.7 モデル切替

- base EraX と user-tuned EraX を区別表示する
- active model は1つだけ
- active 切替は validation / export 成功済みモデルのみ許可
- 切替後の推論では、そのモデル名を UI に表示する
- いつでも base EraX に戻せる

### 5.8 ロールバック

- 直前 active model を履歴として保持
- 切替失敗時は自動ロールバック
- ユーザーが任意に旧モデルへ戻せる

### 5.9 出力形式

- 学習中間成果物は PyTorch checkpoint で保持してよい
- アプリ実運用で使う採用形式は ONNX
- これは既存方針の「推論モデルは可能な限り ONNX 化して利用」と一致する

## 6. 将来のモデル回収に備えた互換条件

### 6.1 今回入れておくべき metadata

各学習済みモデルに次を持たせる。

- model_id
- parent_model_id
- parent_model_hash
- class_schema_version
- training_recipe_version
- augmentation_recipe_version
- export_recipe_version
- app_version
- train_count
- val_count
- val_metrics
- created_at
- local_dataset_fingerprint
- local_only = true
- exportable = true

### 6.2 目的

これにより将来、次へ進める条件を整えられる。

- ユーザーから学習済みモデルを受領
- 何をベースに学習したか検証
- 中央側で比較評価
- 採用候補を選定
- 再配布

### 6.3 今回やらないこと

- モデルアップロード UI
- 利用規約同意画面
- サーバー送信
- 自動回収
- 自動マージ

## 7. データモデル拡張要件

### 7.1 Project への追加

```json
{
  "dataset_capture": {
    "enabled": false,
    "root_dir": "C:/...",
    "accepted_count": 0,
    "rejected_count": 0,
    "pending_count": 0,
    "total_bytes": 0
  },
  "training": {
    "active_model_id": "base_erax",
    "user_models": []
  }
}
```

### 7.2 Sample metadata

```json
{
  "sample_id": "uuid",
  "video_id": "uuid",
  "frame_index": 1234,
  "track_id": "uuid",
  "class_name": "penis",
  "initial_bbox": [120, 80, 240, 180],
  "final_bbox": [118, 76, 248, 186],
  "polygon_points": [[118, 76], [366, 82], [358, 262]],
  "edit_type": "polygon_refined",
  "review_status": "accepted"
}
```

### 7.3 User model metadata

```json
{
  "model_id": "erax_user_20260411_001",
  "parent_model_id": "erax_base_v1",
  "parent_model_hash": "sha256:...",
  "class_schema_version": 1,
  "training_recipe_version": 1,
  "sample_count": 482,
  "train_count": 386,
  "val_count": 96,
  "val_metrics": {
    "map50": 0.91,
    "map50_95": 0.63
  },
  "artifact_paths": {
    "best_pt": "C:/...",
    "onnx": "C:/..."
  },
  "active": false
}
```

## 8. 受け入れ条件

### 8.1 P4-1 完了条件

- 教師データ保存はデフォルト OFF
- 保存はローカルのみ
- 保存先指定可能
- accepted / rejected 管理可能
- manifest 生成可能
- polygon から bbox を生成できる
- 件数 / 容量表示がある
- プロジェクト単位削除ができる

### 8.2 P4-2 完了条件

- accepted データから学習ジョブを開始できる
- train / val split できる
- ログが確認できる
- ONNX export できる
- モデル一覧が表示される
- active model を切り替えられる
- base EraX へ戻せる

### 8.3 将来互換条件

- 学習済みモデルに provenance metadata が付く
- base model hash が記録される
- class schema が固定される
- export 形式が統一される
- 将来の回収対象を「モデル」に限定できる

## 9. 実装順

### Phase A: P4-1 基盤

- dataset_capture 設計
- sample metadata
- 保存先管理
- accepted / rejected 管理
- manifest 生成

### Phase B: P4-1 UI

- ON / OFF
- browse
- 件数 / 容量表示
- 削除導線
- review 状態切替

### Phase C: P4-2 学習ジョブ

- 前提チェック
- train / val split
- training / validation / export
- ログ表示

### Phase D: P4-2 モデル運用

- モデル一覧
- active 切替
- ロールバック
- UI 表示

### Phase E: 将来互換

- metadata 固定
- model artifact manifest
- exportable package 定義

## 10. 実装時の注意

- 教師データ本体を外へ出す導線は作らない
- 最初から自動回収まで入れない
- polygon を直接 EraX 学習へ入れようとしない
- active model 切替を後回しにしない
- 既存の編集 UX を壊さない。現行本線はすでに preview / timeline / detection / export / settings まで成立しているため、P4 はその上に追加する形で入れるべきである
