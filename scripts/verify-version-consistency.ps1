param(
    [string]$TagName = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "openclaw_new_launcher"
$TauriDir = Join-Path $LauncherDir "src-tauri"

function Read-JsonVersion {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file: $Path"
    }
    $text = Get-Content -LiteralPath $Path -Raw
    if ($text -match '"version"\s*:\s*"(?<version>[^"]+)"') {
        return $Matches["version"]
    }
    throw "Unable to read version from $Path"
}

function Read-PackageLockRootPackageVersion {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file: $Path"
    }
    $text = Get-Content -LiteralPath $Path -Raw
    $matches = [regex]::Matches($text, '"version"\s*:\s*"([^"]+)"')
    if ($matches.Count -lt 2) {
        throw "Unable to read root package version from $Path"
    }
    return $matches[1].Groups[1].Value
}

function Read-CargoPackageVersion {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing file: $Path"
    }

    $inPackage = $false
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\[package\]\s*$') {
            $inPackage = $true
            continue
        }
        if ($inPackage -and $line -match '^\[') {
            break
        }
        if ($inPackage -and $line -match '^version\s*=\s*"(?<version>[^"]+)"') {
            return $Matches["version"]
        }
    }

    throw "Unable to read [package] version from $Path"
}

$packageJsonVersion = Read-JsonVersion (Join-Path $LauncherDir "package.json")
$packageLockVersion = Read-JsonVersion (Join-Path $LauncherDir "package-lock.json")
$packageLockRootPackageVersion = Read-PackageLockRootPackageVersion (Join-Path $LauncherDir "package-lock.json")
$tauriConfigVersion = Read-JsonVersion (Join-Path $TauriDir "tauri.conf.json")
$cargoVersion = Read-CargoPackageVersion (Join-Path $TauriDir "Cargo.toml")

$versions = [ordered]@{
    "package.json" = [string]$packageJsonVersion
    "package-lock.json" = [string]$packageLockVersion
    "package-lock.json packages root" = [string]$packageLockRootPackageVersion
    "tauri.conf.json" = [string]$tauriConfigVersion
    "Cargo.toml" = [string]$cargoVersion
}

$expected = $versions["package.json"]
$mismatches = @()
foreach ($entry in $versions.GetEnumerator()) {
    if ([string]::IsNullOrWhiteSpace($entry.Value)) {
        $mismatches += "$($entry.Key) is empty"
    } elseif ($entry.Value -ne $expected) {
        $mismatches += "$($entry.Key)=$($entry.Value), expected $expected"
    }
}

if (-not [string]::IsNullOrWhiteSpace($TagName)) {
    $tagVersion = $TagName -replace '^v', ''
    if ($tagVersion -ne $expected) {
        $mismatches += "tag=$TagName, expected v$expected"
    }
}

if ($mismatches.Count -gt 0) {
    throw "Launcher version mismatch:`n$($mismatches -join "`n")"
}

Write-Host "Version consistency check passed: $expected" -ForegroundColor Green
