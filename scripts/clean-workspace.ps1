param(
    [switch]$RemoveBuildOutputs,
    [switch]$RemoveOldReleaseZips,
    [int]$KeepReleaseZips = 1
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "openclaw_new_launcher"
$ReleaseDir = Join-Path $Root "release"

function Resolve-ExistingPath {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Assert-InWorkspace {
    param([string]$ResolvedPath)

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    if (-not $ResolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside workspace: $ResolvedPath"
    }
}

function Remove-WorkspacePath {
    param([string]$Path)

    $resolved = Resolve-ExistingPath $Path
    if (-not $resolved) {
        return
    }

    Assert-InWorkspace $resolved
    Write-Host "Removing $resolved"
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

Write-Host "Cleaning workspace caches..."

$defaultTargets = @(
    (Join-Path $Root ".cache"),
    (Join-Path $Root "build"),
    (Join-Path $Root "dist"),
    (Join-Path $Root "__pycache__"),
    (Join-Path $LauncherDir "dist"),
    (Join-Path $LauncherDir "python\__pycache__"),
    (Join-Path $LauncherDir "python\core\__pycache__"),
    (Join-Path $LauncherDir "python\services\__pycache__")
)

foreach ($target in $defaultTargets) {
    Remove-WorkspacePath $target
}

$pycRoots = @(
    (Join-Path $LauncherDir "python"),
    (Join-Path $LauncherDir "src-tauri\target\debug\_up_\python"),
    (Join-Path $LauncherDir "src-tauri\target\release\_up_\python")
)

foreach ($pycRoot in $pycRoots) {
    if (-not (Test-Path -LiteralPath $pycRoot)) {
        continue
    }

    foreach ($pyc in Get-ChildItem -LiteralPath $pycRoot -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue) {
        Assert-InWorkspace $pyc.FullName
        Write-Host "Removing $($pyc.FullName)"
        Remove-Item -LiteralPath $pyc.FullName -Force
    }
}

if ($RemoveBuildOutputs) {
    Remove-WorkspacePath (Join-Path $LauncherDir "src-tauri\target")
}

if ($RemoveOldReleaseZips -and (Test-Path -LiteralPath $ReleaseDir)) {
    $keep = [Math]::Max(0, $KeepReleaseZips)
    $zips = Get-ChildItem -LiteralPath $ReleaseDir -Filter "*.zip" -File |
        Sort-Object LastWriteTime -Descending

    $oldZips = @($zips | Select-Object -Skip $keep)
    foreach ($zip in $oldZips) {
        Assert-InWorkspace $zip.FullName
        Write-Host "Removing old release zip $($zip.FullName)"
        Remove-Item -LiteralPath $zip.FullName -Force
    }
}

Write-Host "Workspace cleanup complete."
