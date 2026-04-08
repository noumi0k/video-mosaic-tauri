# レビュー用クイックスタート

## 最初に開く場所
レビュー担当者が最初に開く正本フォルダは `taurimozaic/AutoMosaic-Review/` です。

フォルダ内の主なファイル:

```text
./taurimozaic-desktop.exe
./Launch Auto Mosaic Review.cmd
./Create Desktop Shortcut.ps1
./Review Quickstart.md
./Review Checklist.md
./review-runtime/
```

最初に触るファイル:

- `./Launch Auto Mosaic Review.cmd`
- `./Review Quickstart.md`
- `./Review Checklist.md`

## 開始手順
1. `AutoMosaic-Review/` を開きます。
2. `Launch Auto Mosaic Review.cmd` をダブルクリックします。
3. 起動中は「起動準備中」画面が表示されます。
4. editor 画面が開いたら、上部または通知欄の起動チェックを確認します。

## 起動チェックの見方
- `レビュー準備完了`
  このまま動画を開いて、保存、軽い編集、書き出しまで進められます。
- `必要モデルが不足しています`
  画面内の `必要モデルを取得` または `使用モデルを一括取得` を押してください。
- `要確認`
  ffmpeg、runtime、保存先フォルダなどの確認が必要です。必要なら `サポート / 診断情報` を開いて詳細を確認します。

## レビューの基本導線
1. `動画を開く`
2. 中央プレビューに先頭フレームが表示されることを確認
3. プレビュー下の再生ボタン、1秒移動、1フレーム移動を試す
4. `AI検出開始` を押す
5. マスクが表示されたら、軽く編集する
6. project を保存する
7. `書き出し` を押して動画を書き出す

## モデル不足時
reviewer に手動でモデルを配置してもらう必要はありません。

不足モデルはアプリ内の次のボタンで取得します。

- `必要モデルを取得`
- `使用モデルを一括取得`

最低限の review に必要なモデルは `320n.onnx` です。既に存在するファイルは自動でスキップされます。

## 保存先と残るデータ
review build が使うデータは Tauri の app data directory 側に保存されます。終了後も次の情報は残ることがあります。

- project
- export
- temp
- log
- export preset
- export queue / recent results

実行中だった書き出しジョブがある状態でアプリを閉じた場合、そのジョブは次回起動時に `interrupted` として整理されます。

## 困ったとき
- 起動チェックの内容を確認する
- `必要モデルを取得` を押す
- `サポート / 診断情報` を開いて `doctor` を確認する
