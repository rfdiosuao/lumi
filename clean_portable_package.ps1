param(
    [string]$PackageDir = "$PSScriptRoot\release\OpenClaw-Portable"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PackageDir)) {
    throw "Package directory not found: $PackageDir"
}

$PackageRoot = (Resolve-Path -LiteralPath $PackageDir).Path.TrimEnd('\')
$removed = 0

function Get-DirSizeBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($null -eq $sum) { return 0 }
    return [int64]$sum
}

function Resolve-InPackage([string]$RelativePath) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $PackageRoot $RelativePath))
    $prefix = $PackageRoot + [System.IO.Path]::DirectorySeparatorChar
    if ($target -ne $PackageRoot -and -not $target.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to touch path outside package: $target"
    }
    return $target
}

function Remove-PackagePath([string]$RelativePath) {
    $target = Resolve-InPackage $RelativePath
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
        $script:removed += 1
    }
}

$before = Get-DirSizeBytes $PackageRoot

# Per-customer state must not ship with the package.
Remove-PackagePath "data\install_id.txt"
Remove-PackagePath "data\license.json"
Remove-PackagePath "data\.openclaw"
Remove-PackagePath "data\storyboards"

# Root files that are useful during development but not required at runtime.
Remove-PackagePath "package-lock.json"
Remove-PackagePath "node_modules\.package-lock.json"
Remove-PackagePath "logo_square.ico"
Get-ChildItem -LiteralPath $PackageRoot -File -Filter "*OpenClaw.bat" -Force -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force
        $script:removed += 1
    }

# Node helper files not used by the launcher runtime.
Remove-PackagePath "node\README.md"
Remove-PackagePath "node\CHANGELOG.md"
Remove-PackagePath "node\install_tools.bat"
Remove-PackagePath "node\nodevars.bat"
Remove-PackagePath "node\corepack"
Remove-PackagePath "node\corepack.cmd"
Remove-PackagePath "node\pnpx"
Remove-PackagePath "node\pnpx.cmd"
Remove-PackagePath "node\pnpx.ps1"

# Large docs/examples that are not needed for running OpenClaw from the USB package.
@(
    "node_modules\openclaw\docs",
    "node_modules\@mariozechner\pi-coding-agent\docs",
    "node_modules\@mariozechner\pi-coding-agent\examples",
    "node\node_modules\npm\docs",
    "node_modules\@modelcontextprotocol\sdk\dist\cjs\examples",
    "node_modules\@modelcontextprotocol\sdk\dist\esm\examples",
    "node_modules\@mistralai\mistralai\examples",
    "node_modules\@mistralai\mistralai\tests"
) | ForEach-Object { Remove-PackagePath $_ }

# Keep only the Windows x64 koffi native binding; this package already ships Windows x64 Node.
$koffiDir = Resolve-InPackage "node_modules\koffi\build\koffi"
if (Test-Path -LiteralPath $koffiDir) {
    Get-ChildItem -LiteralPath $koffiDir -Directory -Force |
        Where-Object { $_.Name -ne "win32_x64" } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
            $script:removed += 1
        }
}

# Source maps and debug symbols are safe to remove from the retail package.
Get-ChildItem -LiteralPath $PackageRoot -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".map", ".pdb" -or $_.Name -in "package-lock.json", ".package-lock.json" } |
    ForEach-Object {
        $prefix = $PackageRoot + [System.IO.Path]::DirectorySeparatorChar
        if (-not $_.FullName.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to touch path outside package: $($_.FullName)"
        }
        Remove-Item -LiteralPath $_.FullName -Force
        $script:removed += 1
    }

$after = Get-DirSizeBytes $PackageRoot
$saved = [math]::Round(($before - $after) / 1MB, 2)
$size = [math]::Round($after / 1MB, 2)

Write-Host "Cleaned package: $PackageRoot"
Write-Host "Removed entries: $removed"
Write-Host "Saved: $saved MB"
Write-Host "Current size: $size MB"
