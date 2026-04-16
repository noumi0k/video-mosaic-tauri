Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$backendRoot = Join-Path $repoRoot "apps\backend"
$desktopRoot = Join-Path $repoRoot "apps\desktop"
$modelRoot = Join-Path $repoRoot "models"

function Test-PythonExe {
  param([string]$Path)
  if (-not $Path) { return $false }
  return Test-Path -LiteralPath $Path -PathType Leaf
}

function Resolve-DevPython {
  if ($env:AUTO_MOSAIC_PYTHON) {
    if (-not (Test-PythonExe -Path $env:AUTO_MOSAIC_PYTHON)) {
      throw "AUTO_MOSAIC_PYTHON points to a missing file: $($env:AUTO_MOSAIC_PYTHON)"
    }
    return $env:AUTO_MOSAIC_PYTHON
  }

  $standard = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
  if (Test-PythonExe -Path $standard) {
    return $standard
  }

  $fallback = & python -c "import sys; print(sys.executable)" 2>$null
  if ($LASTEXITCODE -eq 0 -and $fallback -and (Test-PythonExe -Path $fallback.Trim())) {
    return $fallback.Trim()
  }

  throw "Could not resolve a development Python. Set AUTO_MOSAIC_PYTHON to Python 3.12."
}

$pythonExe = Resolve-DevPython
$env:AUTO_MOSAIC_BACKEND_ROOT = $backendRoot
$env:AUTO_MOSAIC_PYTHON = $pythonExe
$env:AUTO_MOSAIC_MODEL_DIR = $modelRoot
$env:PYTHONPATH = Join-Path $backendRoot "src"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Checking development CUDA runtime..."
Write-Host "  Python : $pythonExe"
Write-Host "  Backend: $backendRoot"
Write-Host "  Models : $modelRoot"

$doctorJson = "{}" | & $pythonExe -m auto_mosaic.api.cli_main doctor
if ($LASTEXITCODE -ne 0 -or -not $doctorJson) {
  throw "Backend doctor failed before development launch."
}

$doctor = $doctorJson | ConvertFrom-Json
if (-not $doctor.ok) {
  $message = $doctor.error.message
  throw "Backend doctor returned failure: $message"
}

$onnx = $doctor.data.onnxruntime
$providers = @($onnx.providers)
$cudaSessionOk = $onnx.cuda_session_ok -eq $true
if ($providers -notcontains "CUDAExecutionProvider" -or -not $cudaSessionOk) {
  throw @"
Development CUDA check failed.
providers       : $($providers -join ', ')
cuda_session_ok : $($onnx.cuda_session_ok)
python          : $pythonExe

The app would run detection on CPU. Rebuild apps/backend/vendor with
onnxruntime-gpu[cuda,cudnn], or run npm.cmd run review:runtime and use the
bundled review-runtime path.
"@
}

Write-Host "CUDA development check passed."
Write-Host "  Providers: $($providers -join ', ')"
Write-Host "  CUDA session: ok"

Push-Location $desktopRoot
try {
  npm.cmd run tauri -- dev
} finally {
  Pop-Location
}
