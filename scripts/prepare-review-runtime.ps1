Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$desktopRoot = Join-Path $repoRoot "apps\desktop"
$resourceRoot = Join-Path $desktopRoot "src-tauri\resources\review-runtime"
$backendRoot = Join-Path $repoRoot "apps\backend"
$modelsRoot = Join-Path $repoRoot "models"
$ffmpegRoot = Join-Path $repoRoot "tools\ffmpeg\bin"

$pythonExe = & python -c "import sys; print(sys.executable)"
if (-not $pythonExe) {
  throw "Could not resolve python.exe from the current environment."
}

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
# python3.dll はスタブであり python3XX.dll (例: python314.dll) が python.exe の実体 DLL
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
  prepared_at    = (Get-Date).ToString("s")
  python_version = $pythonVersion
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $resourceRoot "manifest.json") -Encoding UTF8
@"
*
!.gitignore
!README.txt
"@ | Set-Content -Path (Join-Path $resourceRoot ".gitignore") -Encoding UTF8
"Review runtime staging output. Run review:runtime to repopulate this directory." | Set-Content -Path (Join-Path $resourceRoot "README.txt") -Encoding UTF8
Write-Host "Prepared review runtime at $resourceRoot"
