param(
    [string]$Version = "2.0.1",
    [string]$PackageName = "",
    [string]$SeedPortableDir = "",
    [switch]$SkipBuild,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "openclaw_new_launcher"
$TauriDir = Join-Path $LauncherDir "src-tauri"
$ReleaseDir = Join-Path $Root "release"
$CleanScript = Join-Path $PSScriptRoot "clean-workspace.ps1"
$VerifyScript = Join-Path $PSScriptRoot "verify-release.ps1"

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

function Get-ResolvedPathOrNull {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Assert-InWorkspace {
    param([string]$ResolvedPath)

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    if (-not $ResolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside workspace: $ResolvedPath"
    }
}

function Remove-SafePath {
    param([string]$Path)

    $resolved = Get-ResolvedPathOrNull $Path
    if (-not $resolved) {
        return
    }

    Assert-InWorkspace $resolved
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Copy-Directory {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Directory not found: $Source"
    }

    $destinationParent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null

    $args = @(
        $Source,
        $Destination,
        "/MIR",
        "/R:2",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )
    if ($ExcludeDirs.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFiles
    }

    & robocopy @args | Out-Host
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        throw "robocopy failed with exit code $code from $Source to $Destination"
    }
    $global:LASTEXITCODE = 0
}

function Test-SeedPortableDir {
    param([string]$Path)

    $required = @(
        "node\node.exe",
        "node_modules\openclaw\openclaw.mjs",
        "_up_\python-runtime\python.exe",
        "start.js",
        "package.json",
        "package-lock.json"
    )

    foreach ($item in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $item))) {
            return $false
        }
    }
    return $true
}

function Find-SeedPortableDir {
    $targetPortableDir = Join-Path $ReleaseDir $PackageName

    if (-not [string]::IsNullOrWhiteSpace($SeedPortableDir)) {
        $resolved = Get-ResolvedPathOrNull $SeedPortableDir
        if (-not $resolved -or -not (Test-SeedPortableDir $resolved)) {
            throw "Seed portable directory is invalid: $SeedPortableDir"
        }
        if ($resolved.Equals($targetPortableDir, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Seed portable directory cannot be the same as output directory: $resolved"
        }
        return $resolved
    }

    if (-not (Test-Path -LiteralPath $ReleaseDir)) {
        throw "Release directory not found: $ReleaseDir"
    }

    $candidates = Get-ChildItem -LiteralPath $ReleaseDir -Directory |
        Where-Object {
            -not $_.FullName.Equals($targetPortableDir, [System.StringComparison]::OrdinalIgnoreCase) -and
            (Test-SeedPortableDir $_.FullName)
        } |
        Sort-Object LastWriteTime -Descending

    $seed = $candidates | Select-Object -First 1
    if (-not $seed) {
        throw "No usable seed portable directory found under $ReleaseDir"
    }

    return $seed.FullName
}

function Find-TauriExe {
    $candidatePaths = @(
        (Join-Path $TauriDir "target\release\app.exe"),
        (Join-Path $TauriDir "target\release\OpenClaw.exe")
    )

    $candidateExe = $candidatePaths |
        Where-Object { Test-Path -LiteralPath $_ } |
        ForEach-Object { Get-Item -LiteralPath $_ } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($candidateExe) {
        return $candidateExe.FullName
    }

    $exe = Get-ChildItem -LiteralPath (Join-Path $TauriDir "target\release") -Filter "*.exe" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -eq (Join-Path $TauriDir "target\release") } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $exe) {
        throw "Could not find built Tauri exe under src-tauri\target\release"
    }

    return $exe.FullName
}

function Write-CleanRuntimeConfig {
    param([string]$PackageDir)

    $dataDir = Join-Path $PackageDir "data"
    $stateDir = Join-Path $dataDir ".openclaw"
    $agentDir = Join-Path $stateDir "agents\main\agent"
    $storyboardAssets = Join-Path $dataDir "storyboards\assets"

    New-Item -ItemType Directory -Path $agentDir -Force | Out-Null
    New-Item -ItemType Directory -Path $storyboardAssets -Force | Out-Null

    $openclawConfig = [ordered]@{
        gateway = [ordered]@{
            auth = [ordered]@{
                mode = "none"
            }
            bind = "loopback"
        }
    }
    $openclawConfig | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $stateDir "openclaw.json") -Encoding UTF8

    "{}" | Set-Content -LiteralPath (Join-Path $PackageDir "imgapi_config.json") -Encoding UTF8
    "{}" | Set-Content -LiteralPath (Join-Path $PackageDir "video_config.json") -Encoding UTF8
}

function Remove-PythonCacheFiles {
    param([string]$PackageDir)

    Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $PackageDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force
}

function Write-PortableReadme {
    param(
        [string]$PackageDir,
        [string]$NodeVersion,
        [string]$OpenClawVersion
    )

    $content = @"
OpenClaw offline portable package

1. Copy this whole folder to a USB drive or local disk.
2. Run OpenClaw.exe.
3. Activate with a valid license code on first use.
4. Configure API settings in the launcher before using image/video features.

Bundled Node.js: $NodeVersion
Bundled OpenClaw: $OpenClawVersion
"@

    Set-Content -LiteralPath (Join-Path $PackageDir "README-PORTABLE.txt") -Value $content -Encoding UTF8
}

function Get-NodeVersion {
    param([string]$PackageDir)

    $nodeExe = Join-Path $PackageDir "node\node.exe"
    if (Test-Path -LiteralPath $nodeExe) {
        return (& $nodeExe --version).Trim()
    }
    return "unknown"
}

function Get-OpenClawVersion {
    param([string]$PackageDir)

    $pkgPath = Join-Path $PackageDir "node_modules\openclaw\package.json"
    if (Test-Path -LiteralPath $pkgPath) {
        try {
            $pkg = Get-Content -LiteralPath $pkgPath -Raw | ConvertFrom-Json
            if ($pkg.version) {
                return [string]$pkg.version
            }
        } catch {
            return "unknown"
        }
    }
    return "unknown"
}

function Set-JsonProperty {
    param(
        [object]$Object,
        [string]$Name,
        [object]$Value
    )

    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    } else {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
}

function Install-BundledBotPlugins {
    param([string]$PackageDir)

    $nodeDir = Join-Path $PackageDir "node"
    $npmCmd = Join-Path $nodeDir "npm.cmd"
    $pkgJsonPath = Join-Path $PackageDir "package.json"
    $openclawVersion = Get-OpenClawVersion -PackageDir $PackageDir

    if (-not (Test-Path -LiteralPath $npmCmd)) {
        throw "Bundled npm not found: $npmCmd"
    }
    if ($openclawVersion -eq "unknown") {
        throw "Cannot read bundled OpenClaw version before installing bot plugins."
    }

    $pkg = Get-Content -LiteralPath $pkgJsonPath -Raw | ConvertFrom-Json
    if (-not $pkg.dependencies) {
        Set-JsonProperty -Object $pkg -Name "dependencies" -Value ([pscustomobject]@{})
    }
    Set-JsonProperty -Object $pkg.dependencies -Name "openclaw" -Value $openclawVersion
    $pkg | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $pkgJsonPath -Encoding UTF8

    $oldPath = $env:Path
    Push-Location $PackageDir
    try {
        $env:Path = "$nodeDir;$oldPath"
        & $npmCmd install --omit=dev --ignore-scripts --no-audit --no-fund --save-exact "@larksuite/openclaw-lark@latest" "@tencent-weixin/openclaw-weixin@latest"
        if ($LASTEXITCODE -ne 0) {
            throw "npm install bot plugins failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
        $env:Path = $oldPath
    }

    $required = @(
        "node_modules\@larksuite\openclaw-lark\package.json",
        "node_modules\@tencent-weixin\openclaw-weixin\package.json"
    )
    foreach ($item in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageDir $item))) {
            throw "Bundled bot plugin missing after install: $item"
        }
    }
}

if ([string]::IsNullOrWhiteSpace($PackageName)) {
    $date = Get-Date -Format "yyyy.MM.dd"
    $PackageName = "OpenClaw-Portable-v$Version-$date"
}

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

$seedDir = Find-SeedPortableDir
$packageDir = Join-Path $ReleaseDir $PackageName
$zipPath = Join-Path $ReleaseDir "$PackageName.zip"
$hashPath = Join-Path $ReleaseDir "$PackageName.zip.sha256.txt"

Write-Host "Package name: $PackageName"
Write-Host "Seed portable dir: $seedDir"

Invoke-Step "Clean source workspace" {
    & powershell -ExecutionPolicy Bypass -File $CleanScript
}

if (-not $SkipBuild) {
    Invoke-Step "Install frontend dependencies" {
        Push-Location $LauncherDir
        try {
            npm ci
        } finally {
            Pop-Location
        }
    }

    Invoke-Step "Clean Tauri target for icon resources" {
        Push-Location $TauriDir
        try {
            cargo clean
        } finally {
            Pop-Location
        }
    }

    Invoke-Step "Build Tauri application" {
        Push-Location $LauncherDir
        try {
            npm run tauri -- build
        } finally {
            Pop-Location
        }
    }
}

$tauriExe = Find-TauriExe

Invoke-Step "Create portable directory" {
    Remove-SafePath $packageDir
    Remove-SafePath $zipPath
    Remove-SafePath $hashPath

    Copy-Directory -Source $seedDir -Destination $packageDir
    Copy-Item -LiteralPath $tauriExe -Destination (Join-Path $packageDir "OpenClaw.exe") -Force

    Remove-SafePath (Join-Path $packageDir "data")
    Remove-SafePath (Join-Path $packageDir "_up_\python")
    Remove-SafePath (Join-Path $packageDir "_up_\data")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "python") `
        -Destination (Join-Path $packageDir "_up_\python") `
        -ExcludeDirs @("__pycache__") `
        -ExcludeFiles @("*.pyc", "*.pyo")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "data\themes") `
        -Destination (Join-Path $packageDir "data\themes")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "data\themes") `
        -Destination (Join-Path $packageDir "_up_\data\themes")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "scripts") `
        -Destination (Join-Path $packageDir "scripts")

    Install-BundledBotPlugins -PackageDir $packageDir

    Write-CleanRuntimeConfig -PackageDir $packageDir

    $nodeVersion = Get-NodeVersion -PackageDir $packageDir
    $openclawVersion = Get-OpenClawVersion -PackageDir $packageDir
    Write-PortableReadme -PackageDir $packageDir -NodeVersion $nodeVersion -OpenClawVersion $openclawVersion

    Get-ChildItem -LiteralPath $packageDir -File -Filter "README-*.txt" |
        Where-Object { $_.Name -ne "README-PORTABLE.txt" } |
        Remove-Item -Force

    Remove-PythonCacheFiles -PackageDir $packageDir
}

Invoke-Step "Verify portable directory" {
    & powershell -ExecutionPolicy Bypass -File $VerifyScript -Path $packageDir
}

if (-not $NoZip) {
    Invoke-Step "Create zip package" {
        Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -CompressionLevel Optimal
    }

    Invoke-Step "Verify zip package" {
        & powershell -ExecutionPolicy Bypass -File $VerifyScript -Path $zipPath
    }

    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath
    "$($hash.Hash)  $(Split-Path -Leaf $zipPath)" | Set-Content -LiteralPath $hashPath -Encoding ASCII

    Write-Host ""
    Write-Host "Package: $zipPath" -ForegroundColor Green
    Write-Host "SHA256:  $($hash.Hash)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Package directory: $packageDir" -ForegroundColor Green
}
