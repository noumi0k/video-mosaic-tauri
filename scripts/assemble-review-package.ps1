Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$desktopRoot = Join-Path $repoRoot "apps\desktop"
$tauriRoot = Join-Path $desktopRoot "src-tauri"
$releaseExe = Join-Path $tauriRoot "target\release\taurimozaic-desktop.exe"
$runtimeRoot = Join-Path $tauriRoot "resources\review-runtime"
$packageRoot = Join-Path $desktopRoot "review-package"
$packageRuntime = Join-Path $packageRoot "review-runtime"
$handoffRoot = Join-Path $repoRoot "AutoMosaic-Review"
$quickstartSource = Join-Path $repoRoot "docs\review-quickstart.md"
$quickstartTarget = Join-Path $packageRoot "Review Quickstart.md"
$checklistSource = Join-Path $repoRoot "docs\review-checklist.md"
$checklistTarget = Join-Path $packageRoot "Review Checklist.md"
$launcherPath = Join-Path $packageRoot "Launch Auto Mosaic Review.cmd"
$shortcutScriptPath = Join-Path $packageRoot "Create Desktop Shortcut.ps1"
$gitignorePath = Join-Path $packageRoot ".gitignore"
$handoffGitignorePath = Join-Path $handoffRoot ".gitignore"

if (-not (Test-Path $releaseExe)) {
  throw "Review package assembly requires a release desktop executable at $releaseExe"
}

if (-not (Test-Path $runtimeRoot)) {
  throw "Review package assembly requires a staged review runtime at $runtimeRoot"
}

if (Test-Path $packageRoot) {
  Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path $handoffRoot) {
  Remove-Item -LiteralPath $handoffRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $packageRuntime | Out-Null

Copy-Item -LiteralPath $releaseExe -Destination (Join-Path $packageRoot "taurimozaic-desktop.exe") -Force
$null = & robocopy $runtimeRoot $packageRuntime /E /NFL /NDL /NJH /NJS /NP /XF .gitignore *.pyc *.pyo /XD __pycache__
$robocopyExitCode = $LASTEXITCODE
if ($robocopyExitCode -gt 7) {
  throw "Review runtime copy failed with robocopy exit code $robocopyExitCode"
}

if (Test-Path $quickstartSource) {
  Copy-Item -LiteralPath $quickstartSource -Destination $quickstartTarget -Force
}
if (Test-Path $checklistSource) {
  Copy-Item -LiteralPath $checklistSource -Destination $checklistTarget -Force
}

$launcherContent = @'
@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "APP_EXE=%SCRIPT_DIR%taurimozaic-desktop.exe"

if not exist "%APP_EXE%" (
  echo Auto Mosaic review app was not found next to this launcher.
  echo Please keep this file in the same folder as taurimozaic-desktop.exe.
  pause
  exit /b 1
)

if not exist "%SCRIPT_DIR%review-runtime\backend\src" (
  echo The review runtime folder is missing or incomplete.
  echo Expected: review-runtime\backend\src
  echo Rebuild the review package or ask for a fresh review bundle.
  pause
  exit /b 1
)

pushd "%SCRIPT_DIR%"
start "" "%APP_EXE%"
if errorlevel 1 (
  echo Auto Mosaic could not be started.
  echo Try reading Review Quickstart.md and confirm the review-runtime folder is still beside the app.
  pause
  popd
  exit /b 1
)
popd
exit /b 0
'@
Set-Content -Path $launcherPath -Value $launcherContent -Encoding ASCII

$shortcutScriptContent = @'
param(
  [string]$DesktopPath = [Environment]::GetFolderPath("Desktop")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcherPath = Join-Path $scriptDir "Launch Auto Mosaic Review.cmd"
$shortcutPath = Join-Path $DesktopPath "Auto Mosaic Review.lnk"

if (-not (Test-Path $launcherPath)) {
  throw "Launcher not found at $launcherPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $scriptDir
$shortcut.IconLocation = "$launcherPath,0"
$shortcut.Description = "Launch the Auto Mosaic review build"
$shortcut.Save()

Write-Host "Created shortcut at $shortcutPath"
'@
Set-Content -Path $shortcutScriptPath -Value $shortcutScriptContent -Encoding UTF8
@"
*
!.gitignore
"@ | Set-Content -Path $gitignorePath -Encoding ASCII

New-Item -ItemType Directory -Force -Path $handoffRoot | Out-Null
Get-ChildItem -LiteralPath $packageRoot -Force | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $handoffRoot -Recurse -Force
}
@"
*
!.gitignore
"@ | Set-Content -Path $handoffGitignorePath -Encoding ASCII

Write-Host "Prepared portable review package at $packageRoot"
Write-Host "Prepared reviewer handoff folder at $handoffRoot"
