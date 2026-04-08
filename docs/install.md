# インストール方針

Phase 1 は開発者向け運用と reviewer handoff を優先しています。現時点では Windows review bundle と handoff folder 配布を扱います。

## ffmpeg / ffprobe

最小構成では次を前提にしています。

- Windows review runtime に `ffmpeg.exe` と `ffprobe.exe` を stage する
- release build では bundle 内の runtime から解決する
- 開発中の PATH fallback は補助用途に留める

開発中の標準配置:

```text
taurimozaic/tools/ffmpeg/bin/
```

## review package と handoff folder

開発用の portable review package は次に生成されます。

```text
taurimozaic/apps/desktop/review-package/
```

reviewer に渡す handoff 正本は次です。

```text
taurimozaic/AutoMosaic-Review/
```

役割の違いは次のとおりです。

- `apps/desktop/review-package/`
  開発用の生成元です。desktop app 側の assemble 出力先です。
- `taurimozaic/AutoMosaic-Review/`
  reviewer に渡す handoff 正本です。必要ならこのフォルダをそのまま zip 化して配布します。

重要:

- `apps/desktop/review-package/` と `AutoMosaic-Review/` は生成物で、Git 追跡しません
- reviewer は Git clone ではなく、配布された `AutoMosaic-Review/` を開いて開始します
- 開発者は `review:portable` で handoff 正本を再生成します

## Windows review bundle の生成

bundled runtime を stage します。

```powershell
cd apps/desktop
npm.cmd run review:runtime
```

review bundle を作ります。

```powershell
cd apps/desktop
npm.cmd run review:bundle
```

portable review package と handoff folder をまとめて作る場合は次です。

```powershell
cd apps/desktop
npm.cmd run review:portable
```

reviewer には、生成された `AutoMosaic-Review/` をそのまま渡します。配布時に zip が必要なら、開発者または配布担当がこのフォルダを外側で zip 化してください。
reviewer は `AutoMosaic-Review/Launch Auto Mosaic Review.cmd` をダブルクリックして開始します。
必須モデルが不足していても、reviewer に手動配置は要求しません。起動後の画面上部に出る `必要モデルを取得` または `使用モデルを一括取得` を使って取得します。

## review runtime の内容

review package / handoff folder では、`review-runtime/` に次が stage されている前提です。

- `python/`
- `backend/`
- `models/`
- `ffmpeg/bin/`

desktop shell は `doctor` を実行し、startup checklist で次を確認します。

- backend runtime が使える
- `ffmpeg` / `ffprobe` が見つかる
- 必須 model が揃っている
- runtime data folder が書き込める

checklist が ready であれば、最低限次の review flow が成立する前提です。

- 動画を開く
- project を保存 / 読込する
- 小さな編集を行う
- export する

## アンインストールと残るデータ

- review 後はアプリ本体のフォルダを削除できます
- ただし user data は Tauri app data directory に残ることがあります
- 残る可能性があるもの:
  projects, exports, temp files, logs, saved export presets
- 最小永続化された export queue state と recent export results も残ることがあります
- 前回 running だった export は、次回起動時に `interrupted` として整理されます

例:

```text
%APPDATA%\com.tauri.dev\taurimozaic\runtime-data\projects\
%APPDATA%\com.tauri.dev\taurimozaic\runtime-data\exports\
%APPDATA%\com.tauri.dev\taurimozaic\runtime-data\temp\
```
