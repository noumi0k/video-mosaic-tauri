# Core Product Requirements

## 位置づけ

この文書は、現時点での製品要求の正本です。  
主な出典は以下です。

- [requirements-spec-v1.md](../99_archive/requirements-spec-v1.md)
- [README.md](/h:/mosicprogect/mosic2/README.md)

## プロダクトの目的

- ローカル動画に対して自動でマスク候補を生成する
- ユーザーがプレビュー上とタイムライン上でそのマスクを編集できる
- 編集結果をモザイク付き動画として書き出せる
- プロジェクト保存と再編集ができる

## 基本原則

- 完全ローカル実行
- オフライン利用前提
- AI は候補生成の補助であり、最終品質はユーザー確認を前提とする
- 漏れ防止を優先し、必要なら保守的な広めマスクを許容する
- 編集体験はフレーム断片ではなくマスクトラック中心で設計する

## 必須機能

- 動画読み込み
- 自動検出
- マスク表示
- タイムライン上のトラック確認
- キーフレーム編集
- プレビュー上の直接編集
- モザイクプレビュー
- 書き出し
- プロジェクト保存/再読込

## 非機能要件

- Windows を主対象としつつ、他 OS でも動作可能な構成
- GPU が使えない環境では CPU にフォールバック
- 長尺動画でも破綻しにくい保存/書き出し導線
- モデル差し替えが可能な構造

## 対象外

- クラウド処理
- モバイル対応
- 共同編集
- 自動再学習の本実装
- 教師データ保存の本実装

## 現行で重視すること

- 編集作業が成立すること
- 断片マスクの乱立を避けること
- 1テーマ1文書に近づけること

## 関連文書

- 完成像としての要件定義書（実装非依存・上位文書）: [00_product-vision.md](/h:/mosicprogect/mosic2/docs/01_requirements/00_product-vision.md)
- マスク/トラック要求: [02_mask-track-requirements.md](/h:/mosicprogect/mosic2/docs/01_requirements/02_mask-track-requirements.md)
- 設計/現行構成: [01_architecture-and-ui.md](/h:/mosicprogect/mosic2/docs/02_design/01_architecture-and-ui.md)
