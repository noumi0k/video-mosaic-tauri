# セットアップ

## Backend

1. `cd apps/backend`
2. `python -m pip install -e .`

### CPU ベースライン

- 現在の Python 環境をそのまま使います
- editor 作業、JSON contract test、CPU fallback 確認に向いています

### GPU 診断ベースライン

GPU runtime は、project-local の vendor directory にインストールします。

```powershell
python -m pip install --upgrade --target .\vendor "onnxruntime-gpu[cuda,cudnn]==1.24.4"
```

backend CLI は `apps/backend/vendor/` を自動検出し、ONNX Runtime import より先に追加します。

任意:

- `python -m pip install "torch>=2.8,<2.9"`

### ffmpeg / ffprobe

開発中は、次の場所にバイナリを置きます。

```text
taurimozaic/tools/ffmpeg/bin/
  ffmpeg.exe or ffmpeg.cmd
  ffprobe.exe or ffprobe.cmd
```

Windows での軽量な開発運用例:

- `%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe` を指す wrapper を置く
- `%LOCALAPPDATA%\Microsoft\WinGet\Links\ffprobe.exe` を指す wrapper を置く
- 実バイナリ本体は repository の外に置く

## Desktop

1. `cd apps/desktop`
2. `npm.cmd install`
3. `npm.cmd run tauri dev`

## Windows review runtime staging

bundle 前に、非開発者レビュー用 runtime を stage する場合は次を実行します。

```powershell
cd apps/desktop
npm.cmd run review:runtime
```

これにより、現在の Python runtime、backend source、任意の backend vendor runtime、models、`ffmpeg` tools が `src-tauri/resources/review-runtime/` にコピーされます。

stage 後に bundle を作る場合:

```powershell
cd apps/desktop
npm.cmd run review:bundle
```

ダブルクリック起動用の portable review folder を作る場合:

```powershell
cd apps/desktop
npm.cmd run review:portable
```

## ffmpeg / ffprobe 方針

- 開発時:
  - `AUTO_MOSAIC_FFMPEG_PATH` を許可
  - `AUTO_MOSAIC_FFPROBE_PATH` を許可
  - `taurimozaic/tools/ffmpeg/bin` を優先
  - 最後に system `PATH` を許可
- Release:
  - 両方のバイナリを app runtime に同梱し、同梱パスを優先
