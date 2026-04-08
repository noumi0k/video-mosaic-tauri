Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$handoffRoot = Join-Path $repoRoot "AutoMosaic-Review"
$zipPath = Join-Path $repoRoot "AutoMosaic-Review-Windows.zip"
$tempZipPath = Join-Path $repoRoot "AutoMosaic-Review-Windows.tmp.zip"

if (-not (Test-Path $handoffRoot)) {
  throw "Review handoff folder was not found at $handoffRoot. Run review:portable first."
}

function Remove-WithRetry {
  param(
    [Parameter(Mandatory = $true)]
    [string] $PathToRemove
  )

  if (-not (Test-Path $PathToRemove)) {
    return
  }

  for ($attempt = 1; $attempt -le 10; $attempt += 1) {
    try {
      Remove-Item -LiteralPath $PathToRemove -Force
      return
    } catch {
      if ($attempt -eq 10) {
        throw "Could not replace $PathToRemove because it is still in use. Close Explorer preview or any app using the zip and retry."
      }
      Start-Sleep -Seconds 1
    }
  }
}

function Get-RelativeZipEntryPath {
  param(
    [Parameter(Mandatory = $true)]
    [string] $BaseDirectory,
    [Parameter(Mandatory = $true)]
    [string] $FilePath
  )

  $baseUri = [System.Uri]::new(($BaseDirectory.TrimEnd("\") + "\"))
  $fileUri = [System.Uri]::new($FilePath)
  $relativeUri = $baseUri.MakeRelativeUri($fileUri)
  return [System.Uri]::UnescapeDataString($relativeUri.ToString())
}

Remove-WithRetry -PathToRemove $tempZipPath

$zipFileStream = [System.IO.File]::Open($tempZipPath, [System.IO.FileMode]::CreateNew)
try {
  $zipArchive = [System.IO.Compression.ZipArchive]::new($zipFileStream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
  try {
    $handoffRootItem = Get-Item -LiteralPath $handoffRoot
    $files = Get-ChildItem -LiteralPath $handoffRoot -Recurse -File
    foreach ($file in $files) {
      $entryPath = Get-RelativeZipEntryPath -BaseDirectory $handoffRootItem.Parent.FullName -FilePath $file.FullName
      [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zipArchive,
        $file.FullName,
        $entryPath,
        [System.IO.Compression.CompressionLevel]::Optimal
      ) | Out-Null
    }
  } finally {
    $zipArchive.Dispose()
  }
} finally {
  $zipFileStream.Dispose()
}

Remove-WithRetry -PathToRemove $zipPath
Move-Item -LiteralPath $tempZipPath -Destination $zipPath

Write-Host "Prepared reviewer zip at $zipPath"
