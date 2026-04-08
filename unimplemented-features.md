# 未実装機能一覧

## 1. この文書の目的

本書は、現在の Auto Mosaic Tauri 版について、すでに動作している機能とまだ未実装または未完成の機能を切り分け、今後の実装優先順位を整理するための一覧である。

現状の Tauri 版は、動画を開く → 最低限編集 → 保存 → 書き出し までは成立している初期実用版であり、非開発者レビューに進む段階にある。一方で、仕様書上の完成形と比べると、編集体験の中核や製品版機能には未実装・未完成の項目が残っている。

## 2. 現在の前提整理

### 2.1 すでに実装済みの土台

現在の Tauri 版では、少なくとも以下は成立している。

- Tauri フロントエンド + Python バックエンド
- subprocess + CLI + JSON I/O 連携
- project save / load
- autosave / dirty guard / save status
- track / keyframe 選択同期
- inspector 編集
- canvas 直接編集
- ellipse 移動 / リサイズ
- polygon 頂点移動 / 全体移動 / 頂点追加 / 削除
- timeline 上の keyframe 移動
- undo / redo
- export / queue / cancel / progress polling
- review package 導線

### 2.2 本文書でいう「未実装」

本書では、以下をまとめて「未実装機能」と呼ぶ。

- 仕様書にはあるが、まだ Tauri 版に入っていない機能
- 一部はあるが、完成要件を満たしていない機能
- 編集ソフトとして成立するには不足している機能
- 今回のチャット群で「中心課題」と整理されたが、まだ解決していない機能

## 3. 最重要の未実装領域

### 3.1 Persistent Mask Track の完成

**概要**

現在もっとも重要な未完成領域は、マスクを断片ではなく、持続する track として編集できることである。

仕様上は、mask track は時間軸上に残り続け、検出が一時的に途切れても即消えず、ユーザーが同一トラックを育てるように編集できる必要がある。

**未実装項目**

- 検出区間外でも同一 track を継続編集できること
- detection span と editable span を切り離すこと
- 最終検出フレーム以降も shape を保持すること
- track の寿命を「最後に検出されたフレーム」で切らないこと
- 非検出フレームでも timeline 上に track を残すこと
- 一時的未検出で track を新規分断しないこと
- UI / 内部 / 書き出しで同じ存在期間ルールを使うこと

**補足**

この領域は、Persistent Editable Mask Track 要件仕様書で最優先フェーズとして定義されている。

### 3.2 検出区間外での manual 編集継続

**概要**

ユーザーが強く困っているのは、検出された区間でしかマスクを編集できないように見える問題である。
理想挙動は、「最後に有効だった shape を基準に、その後のフレームでも既存マスクを選択・編集でき、編集確定時にそのフレームへ manual keyframe が保存されること」である。

**未実装項目**

- 最終検出後フレームで既存マスクをクリック選択できること
- 最終検出後フレームで移動・拡縮・頂点編集を開始できること
- 現在フレームに detection がなくても hit-test できること
- 現在フレームに明示 keyframe がなくても handle を表示できること
- 最終 keyframe 以降でも shape を解決して編集開始できること
- 検出区間外フレームで manual keyframe を保存できること
- preview / timeline / inspector 間で編集可否が矛盾しないこと

**想定原因として未対処のもの**

- track の寿命が detection に縛られている
- shape 解決ロジックが区間外を返さない
- UI が detection / keyframe 前提で編集を許可している
- manual keyframe の保存ガードが強すぎる
- preview / timeline / inspector の state 同期不良

これらは今回の調査対象として明示されていたが、現状の進捗資料には解決済みとして含まれていない。

### 3.3 auto パス破綻時の採用戦略

**概要**

manual 保護があるだけでは不十分で、壊れた auto パスをそのまま採用しないための continuity 評価と fallback 設計が必要である、という整理になっている。
現在の主問題は「直したのに次ですぐ崩れる」ことであり、これは auto 採用戦略の未整備が原因とされている。

**未実装項目**

- auto 採用 / fallback / reject の分岐設計
- continuity 評価に基づく採用判定
- 面積差・重心移動・bbox 変化・アスペクト比変化などの破綻判定
- fallback の内部由来追跡
- source_detail 相当の補助状態
- fallback_from_frame_id 相当の参照元記録
- auto bbox が怪しい場合の多段 fallback
- 完全 reject 時の処理方針
- 必要な fallback 優先順位

**仕様としては、少なくとも以下が必要と整理されている。**

- **auto bbox が妥当**
  - anchor shape + auto の位置 / スケール
- **anchor shape + auto の位置 / スケール**
  - auto bbox まで怪しい場合の候補
- **さらに怪しい**
  - 前回安定キーフレームの位置 / スケール
- **最後の手段**
  - 前回安定形状をそのまま維持

### 3.4 manual anchor の前方継承

**概要**

ユーザーが望んでいるのは、前回きれいに直した感じが次にも残ることであり、shape blending を最初から入れることではない。
そのため、まず必要なのは conservative な manual 前方継承である。

**未実装項目**

- manual anchor の影響範囲の明文化
- 直近 manual anchor を優先する前方継承
- auto から位置 / スケール / 重心だけ借りる保守的継承
- 次の manual で anchor を切り替えるルール
- frame gap に応じた影響減衰の余地を残す構造
- manual 修正が補間区間へ強く効く設計

**今は避けるべきだが、将来候補のもの**

- manual polygon と auto polygon の単純 blend
- bbox ベースの雑な shape 再配置
- 頂点対応が曖昧なままの shape blending

## 4. タイムライン体験の未実装項目

**概要**

タイムライン自体は存在するが、編集ソフトとして必要な細かい時間操作はまだ不足している。
このチャットでも、タイムラインズームは重要だが、マスク破綻より優先度は下と整理されている。

**未実装項目**

- タイムラインズーム
  - _zoom_level 管理
  - _scroll_offset 管理
  - _frame_to_x() / _x_to_frame() のズーム対応
  - Ctrl + ホイールでのズーム
  - 横スクロール操作
  - 再生ヘッドを見失わない追従
  - ズームスライダー
  - 小さい区間を見やすくする表示
- predicted / interpolated / uncertain の区別表示
- manual / auto / predicted / interpolated の視覚区別

**将来的に必要なもの**

- keyframe のコピー / ペースト
- 前後補間プレビュー
- 再トラッキング範囲指定

これらは persistent track / keyframe 中心モデルの UI 要件としても挙げられている。

## 5. Progress UX の未実装項目

**概要**

export の進捗表示や cancel はあるが、自動検出・1フレーム検出・トラック生成・書き出しに共通で使える progress UX はまだ完成していない。
仕様上は長時間処理は job 化され、進捗・フェーズ・キャンセル・artifact 導線を一貫して扱うべきである。

**未実装項目**

- 自動検出用 progress UI
- 1フレーム自動検出用 busy / progress UI
- トラック生成用 progress UI
- 各処理に共通で使える progress overlay / panel / dialog
- 進捗率が取れない処理の indeterminate 表示
- ステップ名表示
- エラー時に progress UI が残りっぱなしにならない保証
- 処理ごとの多重起動防止
- 実行中ジョブを見落としにくい表示

**求められている粒度**

- 検出: 準備中 / フレーム解析中 / トラック生成中 / 結果反映中
- 1フレーム検出: フレーム取得中 / 検出中 / 結果反映中
- 書き出し: レンダリング中 / エンコード中 / 音声結合中 / 完了処理中

## 6. UI / UX の未完成項目

**概要**

現在の Tauri 版は editor-first 化が進んでいるが、まだPremiere / EDIUS ライクな完成度には達していない。
最近の方針では、中央プレビューを主役とし、下タイムラインを強く見せ、左トラック / 右インスペクタ / 最小限の上部操作を持つ固定レイアウトが求められている。

**未実装 / 未完成項目**

- 空状態でも編集ソフトの骨格が見えること
- プレビュー主役のレイアウト完成
- タイムライン主役のレイアウト完成
- 左トラックパネルの整理
- 右インスペクタのセクション型整理
- 書き出し領域の脇役化
- debug / raw 情報の既定非表示
- 非開発者が迷わない主導線の polish
- 操作感の最終調整
- 情報密度の最適化

**現状評価**

進捗報告でも、UI は「十分使えるがまだ初期実用版」であり、細かく触っても快適な段階までは未到達と整理されている。

## 7. 製品版機能として未実装のもの

### 7.1 教師データ保存の本実装

詳細仕様では、教師データ保存は正式機能として定義されているが、進捗報告ではまだ本格実装前と整理されている。

**未実装項目**

- opt-in UI
- 保存先表示
- 件数 / 容量表示
- project 単位 / dataset 単位削除
- export 完了時の確定区間抽出
- crop / 初期予測 / 最終結果 / metadata 一式保存
- dataset manifest 生成

### 7.2 ローカル自動再学習の本実装

これも仕様書上は正式要件だが、現状は未着手または未完成である。

**未実装項目**

- training dataset validator
- train / val split
- retraining job
- 学習ログ表示
- 学習済みモデル一覧
- active model 切替
- 比較レポート
- ロールバック
- VRAM / ディスク / サンプル数事前チェック

### 7.3 最終インストーラ / アンインストーラ / updater

現在は review package 段階であり、製品配布の最終形ではない。

**未実装項目**

- Windows 向け正式 installer
- updater
- 標準 / 拡張 / 完全削除を持つアンインストーラ
- インストール後の初回 bootstrap 完成
- 必須同梱物と任意追加モデルの整理
- 完全な配布運用導線

## 8. 品質・保守面で未完成の項目

進捗報告では、基盤と backend のハードニングは進んでいる一方で、製品レベルの品質整備はまだ残っている。

**未実装 / 未完成項目**

- frontend の厚い E2E / UI テスト
- canvas drag など実操作ベースのテスト
- review package 起動後の一連フローテスト
- crash recovery
- 高度な queue 永続化
- 高度な export profile
- GPU 最適化の仕上げ
- recovery / retry / interrupted 表示の改善

## 9. 優先順位整理

### P0: 最優先

- 検出区間外でも同一マスクを継続編集できること
- Persistent Mask Track の完成
- auto 破綻判定 + fallback
- manual anchor の保守的前方継承

### P1: 高優先

- タイムラインズーム
- source / segment の視覚区別
- 共通 Progress UX
- editor-first UI の polish

### P2: 中優先

- 教師データ保存
- ローカル再学習
- 高度な export / queue / recovery
- frontend E2E 強化

### P3: 後優先

- 最終 installer / updater / uninstall の完成
- 製品版としての最終 polish
- 高度な品質向上機能

## 10. 現時点のまとめ

現在の Tauri 版は、基盤・最低限編集・保存・書き出しまでは成立している。
しかし、仕様書と今回の課題整理に照らすと、まだ未実装の中心は以下である。

**マスク継続編集の完成**
- persistent track
- 検出外編集
- hold / predict / interpolate
- manual anchor 継承
- auto 破綻時 fallback

**編集ソフトとしての体験完成**
- timeline zoom
- source / segment 可視化
- 共通 progress UX
- editor-first UI polish

**製品版機能の完成**
- 教師データ保存
- ローカル再学習
- 最終 installer / uninstall
- 高度なテスト / recovery / export

要するに、
> 今の Tauri 版は MVP の芯はあるが、編集体験の本丸と製品版機能はまだ未完成である。

## 11. 参照資料

- Persistent Editable Mask Track 実装 要件仕様書
- Auto Mosaic Tauri 完全新規実装 指示書（AIエージェント向け）
- Auto Mosaic Tauri完全新規構築 詳細要件仕様書 v2.1
- 進捗報告書 / 現在の開発状況整理
- このチャットで整理された編集体験・マスク継続編集・progress UX・UI再設計方針
