# Build a "thin" portable package: the proven portable layout (OpenClaw.exe +
# OpenClawFiles/) MINUS the four heavy runtime layers, which the Rust bootstrap
# downloads + sha256-verifies into OpenClawFiles/ on first run. Result is <100MB
# and — unlike the NSIS installer — keeps the portable layout that all runtime
# path-resolution already expects, so it actually runs.
#
# The OpenClaw.exe you pass in MUST be built with the manifest URL baked in:
#   cd src-tauri
#   $env:OPENCLAW_DIST_MANIFEST_URL = "https://.../manifest.json"
#   cargo build --release        # -> target/release/app.exe
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/dist/build-thin-portable.ps1 `
#     -Source "release\OpenClaw-Portable-v2.0.6-...." `
#     -Exe    "src-tauri\target\release\app.exe" `
#     -Out    "release\OpenClaw-Online-v2.0.6.zip"

param(
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$Exe = "",
    [string]$Out = "",
    [string[]]$RemoveLayers = @(
        "OpenClawFiles\node",
        "OpenClawFiles\node_modules",
        "OpenClawFiles\_up_\python-runtime",
        "OpenClawFiles\agents\luminode-desktop"
    )
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath (Join-Path $Source "OpenClaw.exe"))) {
    throw "Source missing OpenClaw.exe: $Source"
}
if (-not (Test-Path -LiteralPath (Join-Path $Source "OpenClawFiles"))) {
    throw "Source missing OpenClawFiles: $Source"
}

$stage = Join-Path $env:TEMP ("openclaw-thin-" + [System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    # robocopy mirrors the tree but skips the heavy layer dirs (by full path, so
    # we never copy the ~1GB we're about to drop).
    $excludeDirs = $RemoveLayers | ForEach-Object { Join-Path $Source $_ }
    Write-Host "Copying (excluding heavy layers) -> $stage"
    & robocopy $Source $stage /E /XD @excludeDirs /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }
    $global:LASTEXITCODE = 0

    foreach ($rel in $RemoveLayers) {
        $p = Join-Path $stage $rel
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }

    if ($Exe -ne "") {
        if (-not (Test-Path -LiteralPath $Exe)) { throw "Baked exe not found: $Exe" }
        Copy-Item -LiteralPath $Exe -Destination (Join-Path $stage "OpenClaw.exe") -Force
        Write-Host "Swapped OpenClaw.exe with baked build: $Exe"
    } else {
        Write-Warning "No -Exe given; keeping the source OpenClaw.exe. It MUST already have the manifest URL baked in, or first-run download will not trigger."
    }

    # Pre-create the layer parent dirs so the bootstrap has somewhere to land.
    foreach ($rel in $RemoveLayers) {
        $parent = Split-Path (Join-Path $stage $rel) -Parent
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    if ($Out -eq "") {
        $Out = Join-Path (Split-Path $Source -Parent) ((Split-Path $Source -Leaf) + "-online.zip")
    }
    if (Test-Path -LiteralPath $Out) { Remove-Item -LiteralPath $Out -Force }
    Write-Host "Compressing -> $Out"
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $Out -CompressionLevel Optimal

    $sizeMB = [math]::Round((Get-Item -LiteralPath $Out).Length / 1MB, 1)
    Write-Host ("Done: {0}  ({1} MB)" -f $Out, $sizeMB)
    if ($sizeMB -ge 100) { Write-Warning "Package is >= 100MB ($sizeMB MB) — check that all four heavy layers were excluded." }
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
