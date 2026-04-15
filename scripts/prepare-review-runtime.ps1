Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$desktopRoot = Join-Path $repoRoot "apps\desktop"
$resourceRoot = Join-Path $desktopRoot "src-tauri\resources\review-runtime"
$backendRoot = Join-Path $repoRoot "apps\backend"
$modelsRoot = Join-Path $repoRoot "models"
$ffmpegRoot = Join-Path $repoRoot "tools\ffmpeg\bin"

# ---------------------------------------------------------------------------
# Python selection
#
# Priority order:
#   1. $env:AUTO_MOSAIC_REVIEW_PYTHON (explicit override — must point to
#      an existing python.exe)
#   2. py launcher (py -<target minor>)
#   3. Common Python install locations for the target minor version
#   4. Fallback: `python` on PATH
#
# The selected interpreter's minor version MUST match the ABI of the
# packages in apps/backend/vendor/.  If it does not, preparation aborts
# with a descriptive error.
# ---------------------------------------------------------------------------

function Test-PythonExe {
  param([string]$Path)
  if (-not $Path) { return $false }
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
  return $true
}

function Get-PythonMinor {
  param([string]$PythonExe)
  $versionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $versionText) {
    throw "Failed to query version from Python at: $PythonExe"
  }
  return $versionText.Trim()
}

function Get-VendorAbi {
  param([string]$VendorRoot)
  if (-not (Test-Path -LiteralPath $VendorRoot -PathType Container)) {
    return $null
  }
  # Look for *.cp3XX-win_amd64.pyd files (numpy, etc.) to detect the ABI
  # that the vendor was built against.
  $abis = @()
  $pydFiles = Get-ChildItem -LiteralPath $VendorRoot -Recurse -Filter "*.cp3*-win_amd64.pyd" -ErrorAction SilentlyContinue
  if ($pydFiles) {
    $abis = $pydFiles | ForEach-Object {
      if ($_.Name -match '\.cp(\d{3,})-win_amd64\.pyd$') {
        "cp$($matches[1])"
      }
    } | Where-Object { $_ } | Sort-Object -Unique
  }
  if (-not $abis) {
    return $null
  }
  $abiArray = @($abis)
  if ($abiArray.Count -gt 1) {
    throw "vendor/ contains mixed Python ABIs: $($abiArray -join ', '). Clean vendor/ and rebuild against a single Python version."
  }
  return $abiArray[0]
}

function Resolve-ReviewPython {
  param([string]$TargetMinor)

  # 1. Explicit override via env variable.
  $override = $env:AUTO_MOSAIC_REVIEW_PYTHON
  if ($override) {
    if (-not (Test-PythonExe -Path $override)) {
      throw "AUTO_MOSAIC_REVIEW_PYTHON points to a missing file: $override"
    }
    Write-Host "  Using AUTO_MOSAIC_REVIEW_PYTHON override: $override"
    return $override
  }

  # 2. py launcher with target minor.
  $pyCmd = Get-Command py.exe -ErrorAction SilentlyContinue
  if ($pyCmd) {
    $argList = @("-$TargetMinor", "-c", "import sys; print(sys.executable)")
    $launched = & py.exe @argList 2>$null
    if ($LASTEXITCODE -eq 0 -and $launched) {
      $candidate = $launched.Trim()
      if (Test-PythonExe -Path $candidate) {
        Write-Host "  Found Python $TargetMinor via py launcher: $candidate"
        return $candidate
      }
    }
  }

  # 3. Common install locations for the target minor version.
  $minorNoDot = $TargetMinor.Replace(".", "")
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$minorNoDot\python.exe"),
    (Join-Path $env:ProgramFiles "Python$minorNoDot\python.exe"),
    "C:\Python$minorNoDot\python.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-PythonExe -Path $candidate) {
      Write-Host "  Found Python $TargetMinor at standard location: $candidate"
      return $candidate
    }
  }

  # 4. Fallback: current `python` on PATH (warns if minor doesn't match).
  $fallback = & python -c "import sys; print(sys.executable)" 2>$null
  if ($LASTEXITCODE -eq 0 -and $fallback) {
    $fallbackExe = $fallback.Trim()
    if (Test-PythonExe -Path $fallbackExe) {
      Write-Host "  Falling back to 'python' on PATH: $fallbackExe"
      return $fallbackExe
    }
  }

  throw @"
Could not find a Python $TargetMinor interpreter.
Resolution attempted (in order):
  1. $($env:AUTO_MOSAIC_REVIEW_PYTHON) (AUTO_MOSAIC_REVIEW_PYTHON env)
  2. py.exe -$TargetMinor
  3. $($candidates -join ', ')
  4. python on PATH

Install Python $TargetMinor, or set AUTO_MOSAIC_REVIEW_PYTHON to point at a compatible interpreter.
"@
}

# ---------------------------------------------------------------------------
# Detect the ABI the vendor was built against, then select a matching Python.
# ---------------------------------------------------------------------------

$vendorRoot = Join-Path $backendRoot "vendor"
$vendorAbi = Get-VendorAbi -VendorRoot $vendorRoot
if (-not $vendorAbi) {
  throw "Could not detect the ABI of apps/backend/vendor/ — no cp3XX-win_amd64.pyd files found. vendor/ may be missing or incomplete."
}
Write-Host "Detected vendor ABI: $vendorAbi"

# Derive the expected Python minor version from the ABI ("cp312" -> "3.12").
if ($vendorAbi -notmatch '^cp(\d)(\d+)$') {
  throw "Unexpected vendor ABI format: $vendorAbi"
}
$targetMinor = "$($matches[1]).$($matches[2])"
Write-Host "Target Python minor version: $targetMinor"

$pythonExe = Resolve-ReviewPython -TargetMinor $targetMinor
if (-not (Test-PythonExe -Path $pythonExe)) {
  throw "Could not resolve python.exe from the current environment."
}

# Validate that the selected Python matches the vendor ABI.
$selectedMinor = Get-PythonMinor -PythonExe $pythonExe
$expectedMinor = $targetMinor
if ($selectedMinor -ne $expectedMinor) {
  throw @"
Python ABI mismatch.
Selected Python : $pythonExe (Python $selectedMinor)
Vendor ABI       : $vendorAbi (requires Python $expectedMinor)

Either:
  - Install Python $expectedMinor and set AUTO_MOSAIC_REVIEW_PYTHON, or
  - Rebuild apps/backend/vendor/ against Python $selectedMinor.

Silent ABI mismatches caused review-runtime workers to die at import time
(observed 2026-04-09). This preparation step aborts rather than ship a
broken runtime.
"@
}
Write-Host "Python ABI check passed: selected Python $selectedMinor matches vendor $vendorAbi"

$pythonRoot = Split-Path -Parent $pythonExe
$pythonTarget = Join-Path $resourceRoot "python"
$backendTarget = Join-Path $resourceRoot "backend"
$modelsTarget = Join-Path $resourceRoot "models"
$ffmpegTarget = Join-Path $resourceRoot "ffmpeg\bin"

if (Test-Path $resourceRoot) {
  Remove-Item -LiteralPath $resourceRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $pythonTarget | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backendTarget "src") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $backendTarget "vendor") | Out-Null
New-Item -ItemType Directory -Force -Path $modelsTarget | Out-Null
New-Item -ItemType Directory -Force -Path $ffmpegTarget | Out-Null

$pythonFiles = @(
  "python.exe",
  "pythonw.exe",
  "python3.dll",
  "vcruntime140.dll",
  "vcruntime140_1.dll"
)

foreach ($name in $pythonFiles) {
  $source = Join-Path $pythonRoot $name
  if (Test-Path $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $pythonTarget $name) -Force
  }
}

# バージョン付き DLL (python3XX.dll) を動的に検出してコピー
# python3.dll はスタブであり python3XX.dll (例: python312.dll) が python.exe の実体 DLL
# 旧コードは python312.dll をハードコードしており、3.12 以外の環境で DLL が欠落していた
Get-ChildItem -LiteralPath $pythonRoot -Filter "python3??.dll" | ForEach-Object {
  if ($_.Name -ne "python3.dll") {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $pythonTarget $_.Name) -Force
    Write-Host "  Copied versioned Python DLL: $($_.Name)"
  }
}

# DLLs はそのままコピー
$source = Join-Path $pythonRoot "DLLs"
if (Test-Path $source) {
  Copy-Item -LiteralPath $source -Destination (Join-Path $pythonTarget "DLLs") -Recurse -Force
}

# Lib: テストスイート・開発ツール・キャッシュを除外してコピー
$libSource = Join-Path $pythonRoot "Lib"
if (Test-Path $libSource) {
  $libTarget = Join-Path $pythonTarget "Lib"
  $null = & robocopy $libSource $libTarget /E /NFL /NDL /NJH /NJS /NP `
    /XD test idlelib ensurepip tkinter turtle turtledemo __pycache__ `
    /XF "*.pyc" "*.pyo"
  $robocopyExitCode = $LASTEXITCODE
  if ($robocopyExitCode -gt 7) {
    throw "Lib copy failed with robocopy exit code $robocopyExitCode"
  }
}

Get-ChildItem -LiteralPath (Join-Path $backendRoot "src") -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $backendTarget "src") -Recurse -Force
}
if (Test-Path (Join-Path $backendRoot "vendor")) {
  Get-ChildItem -LiteralPath (Join-Path $backendRoot "vendor") -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $backendTarget "vendor") -Recurse -Force
  }
}

# ---------------------------------------------------------------------------
# EraX PT -> ONNX 事前変換 (A 案 / 2026-04-11)
#
# bundled review-runtime には ultralytics を恒常的に同梱しないため、
# .pt から .onnx を生成するための ultralytics 実行は prep 時に 1 度だけ行う。
# workspace の models/ に .onnx が生成されたあとは models コピーで bundled
# 配下にも自動的に入る。.onnx が既にあればスキップする (idempotent)。
#
# ※ 将来 EraX ONNX をホスト経由で配布する案 (model_catalog 化) に切り替わる
#    場合、このブロックごと削除可能。
# ---------------------------------------------------------------------------
$eraxPt = Join-Path $modelsRoot "erax_nsfw_yolo11s.pt"
$eraxOnnx = Join-Path $modelsRoot "erax_nsfw_yolo11s.onnx"
$eraxLabels = Join-Path $modelsRoot "erax_nsfw_yolo11s.labels.json"
if ((Test-Path -LiteralPath $eraxPt) -and -not (Test-Path -LiteralPath $eraxOnnx)) {
  Write-Host "EraX: pre-converting .pt -> .onnx (one-time, ~30s)..."
  $bundledPython = Join-Path $pythonTarget "python.exe"
  if (-not (Test-Path -LiteralPath $bundledPython)) {
    throw "EraX pre-conversion needs the bundled python at $bundledPython, which was not produced by the earlier copy step."
  }

  & $bundledPython -m pip install --quiet ultralytics
  if ($LASTEXITCODE -ne 0) {
    throw "EraX pre-conversion: pip install ultralytics failed (exit $LASTEXITCODE)."
  }

  $convertCode = @"
from pathlib import Path
from ultralytics import YOLO
pt = Path(r'$eraxPt')
model = YOLO(str(pt))
exported = model.export(format='onnx', imgsz=640)
exported_path = Path(str(exported))
if not exported_path.exists():
    raise SystemExit(f'export reported success but {exported_path} is missing')
print(f'EraX: wrote {exported_path} ({exported_path.stat().st_size} bytes)')
names = getattr(model, 'names', None) or getattr(model.model, 'names', None) or {}
import json
labels_target = Path(r'$eraxLabels')
labels_target.write_text(json.dumps({'labels': [names[i] for i in sorted(names)]}, indent=2), encoding='utf-8')
print(f'EraX: wrote labels sidecar to {labels_target}')
"@
  & $bundledPython -c $convertCode
  if ($LASTEXITCODE -ne 0) {
    throw "EraX pre-conversion: ultralytics ONNX export failed (exit $LASTEXITCODE)."
  }
  if (-not (Test-Path -LiteralPath $eraxOnnx)) {
    throw "EraX pre-conversion: $eraxOnnx not present after export."
  }
  Write-Host "  EraX ONNX ready at $eraxOnnx"
}
elseif (Test-Path -LiteralPath $eraxOnnx) {
  Write-Host "EraX: .onnx already present, skipping pre-conversion."
}
else {
  Write-Host "EraX: .pt not found at $eraxPt, skipping pre-conversion."
}

Get-ChildItem -LiteralPath $modelsRoot -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $modelsTarget -Recurse -Force
}
# ffmpeg: 開発用シム (.cmd/.bat) を除外して実体 (.exe) のみコピー
Get-ChildItem -LiteralPath $ffmpegRoot -File | Where-Object {
  $_.Extension -notin @(".cmd", ".bat")
} | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ffmpegTarget $_.Name) -Force
}

$pythonVersion = (& $pythonExe -c "import sys; print(sys.version.split()[0])" 2>$null)
$manifest = @{
  prepared_at          = (Get-Date).ToString("s")
  python_version       = $pythonVersion
  python_minor         = $selectedMinor
  python_source        = $pythonExe
  vendor_abi           = $vendorAbi
  abi_check_passed     = $true
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $resourceRoot "manifest.json") -Encoding UTF8
@"
*
!.gitignore
!README.txt
"@ | Set-Content -Path (Join-Path $resourceRoot ".gitignore") -Encoding UTF8
"Review runtime staging output. Run review:runtime to repopulate this directory." | Set-Content -Path (Join-Path $resourceRoot "README.txt") -Encoding UTF8
Write-Host "Prepared review runtime at $resourceRoot"
Write-Host "  Python: $pythonExe ($pythonVersion, $vendorAbi)"
