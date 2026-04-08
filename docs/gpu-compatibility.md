# GPU 互換ベースライン

この project では、場当たり的に複数の組み合わせを試すのではなく、Windows 上で確認したベースラインを固定しています。

## 採用しているベースライン

| 層 | 採用ベースライン |
| --- | --- |
| OS | Windows 10/11 x64 |
| Python | 3.12.x |
| NVIDIA driver | `nvidia-smi` が使える RTX driver |
| driver が報告する CUDA capability | 13.x でも可。CUDA 12.x user-mode runtime と後方互換で扱う |
| ONNX Runtime GPU | `onnxruntime-gpu[cuda,cudnn]==1.24.4` |
| CUDA user-mode runtime | ORT extra が入れる CUDA 12.9 runtime |
| cuDNN | ORT extra が入れる cuDNN 9.20 |
| Torch | 任意。runtime inference 診断には必須ではない |

## 補足

- runtime path 上では、ONNX Runtime の flavor は 1 つだけ有効にする前提です
- この project では `apps/backend/vendor/` を優先し、global Python 環境へ依存しない方針です
- `onnxruntime-gpu` の確認は 2 段階で行います
  1. provider discovery
  2. CUDA を要求した最小 `InferenceSession` 作成
- `CUDAExecutionProvider` が見えるだけでは十分ではありません。session 作成成功まで確認します

## 現在の診断コードが返す主な状態

- `cpu-ort-only`: CPU 版 `onnxruntime` だけが有効
- `provider-unavailable`: GPU package は見えているが、まだ利用できない
- `cuda-dll-missing`: GPU package はあるが、CUDA/cuDNN DLL 解決が不完全
- `ready`: CUDA session 作成成功
