param(
    [switch]$SkipFrontend,
    [switch]$SkipRust,
    [switch]$SkipPython,
    [switch]$SkipLicenseServer
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "openclaw_new_launcher"
$TauriDir = Join-Path $LauncherDir "src-tauri"
$LicenseServerDir = Join-Path $Root "license_server"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Script
    )
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Script
    Write-Host "OK: $Name" -ForegroundColor Green
}

if (-not $SkipFrontend) {
    Invoke-Step "Frontend build" {
        Push-Location $LauncherDir
        try {
            if (Test-Path -LiteralPath "package-lock.json") {
                npm ci
            } else {
                npm install
            }
            npm run build
        } finally {
            Pop-Location
        }
    }
}

if (-not $SkipRust) {
    Invoke-Step "Rust cargo check" {
        Push-Location $TauriDir
        try {
            cargo check
        } finally {
            Pop-Location
        }
    }
}

if (-not $SkipPython) {
    Invoke-Step "Python launcher compile" {
        Push-Location $LauncherDir
        try {
            $files = @("python/bridge.py")
            $files += Get-ChildItem -LiteralPath "python/core" -Filter "*.py" | ForEach-Object { $_.FullName }
            $files += Get-ChildItem -LiteralPath "python/services" -Filter "*.py" | ForEach-Object { $_.FullName }
            python -m py_compile @files
        } finally {
            Pop-Location
        }
    }
}

if (-not $SkipLicenseServer -and (Test-Path -LiteralPath (Join-Path $LicenseServerDir "server.py"))) {
    Invoke-Step "Python license server compile" {
        Push-Location $LicenseServerDir
        try {
            python -m py_compile server.py
        } finally {
            Pop-Location
        }
    }
}

Write-Host ""
Write-Host "All CI checks passed." -ForegroundColor Green

