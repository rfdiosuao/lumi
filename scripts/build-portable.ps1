param(
    [string]$Version = "",
    [string]$PackageName = "",
    [string]$SeedPortableDir = "",
    [string]$BrandProfile = "lumi",
    [string]$PhoneAgentVerifiedVersion = "",
    [int]$PhoneAgentVerifiedVersionCode = 0,
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
$SmokeVerifyScript = Join-Path $PSScriptRoot "verify-portable-smoke.ps1"
$VerifySourceTextScript = Join-Path $PSScriptRoot "verify-source-text.ps1"

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

function Get-LauncherVersion {
    $packageJsonPath = Join-Path $LauncherDir "package.json"
    if (Test-Path -LiteralPath $packageJsonPath) {
        $packageJson = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
        if (-not [string]::IsNullOrWhiteSpace([string]$packageJson.version)) {
            return [string]$packageJson.version
        }
    }

    $tauriConfigPath = Join-Path $TauriDir "tauri.conf.json"
    if (Test-Path -LiteralPath $tauriConfigPath) {
        $tauriConfig = Get-Content -LiteralPath $tauriConfigPath -Raw | ConvertFrom-Json
        if (-not [string]::IsNullOrWhiteSpace([string]$tauriConfig.version)) {
            return [string]$tauriConfig.version
        }
    }

    throw "Unable to determine launcher version from package.json or tauri.conf.json."
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

    $candidateRoots = @(
        $Path,
        (Join-Path $Path "OpenClawFiles")
    )

    foreach ($rootPath in $candidateRoots) {
        $valid = $true
        foreach ($item in $required) {
            if (-not (Test-Path -LiteralPath (Join-Path $rootPath $item))) {
                $valid = $false
                break
            }
        }
        if ($valid) {
            return $true
        }
    }
    return $false
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
    if ($SkipBuild -and -not [string]::IsNullOrWhiteSpace($seedDir)) {
        $seedExe = Join-Path $seedDir "OpenClaw.exe"
        if (Test-Path -LiteralPath $seedExe) {
            return $seedExe
        }
    }

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

function Get-PhoneAgentVersionCodeFromVersion {
    param([string]$VersionName)

    if ($VersionName -match "^(\d+)\.(\d+)$") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -eq 6) {
            return 600 + ($minor * 10)
        }
    }

    return 0
}

function Resolve-PhoneAgentVersionInfo {
    $resolvedVersion = $PhoneAgentVerifiedVersion.Trim()
    $resolvedCode = $PhoneAgentVerifiedVersionCode
    $latestApk = Join-Path $LauncherDir "AgentPhone_latest.apk"

    if ([string]::IsNullOrWhiteSpace($resolvedVersion) -and (Test-Path -LiteralPath $latestApk)) {
        $latestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $latestApk).Hash
        $matchingVersionedApk = Get-ChildItem -LiteralPath $LauncherDir -File -Filter "AgentPhone_v*.apk" -ErrorAction SilentlyContinue |
            Where-Object { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash -eq $latestHash } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1

        if ($matchingVersionedApk -and $matchingVersionedApk.Name -match "AgentPhone_v(?<version>\d+\.\d+)_") {
            $resolvedVersion = $Matches["version"]
        }
    }

    if ([string]::IsNullOrWhiteSpace($resolvedVersion)) {
        Write-Warning "Unable to infer phone agent verified version. Pass -PhoneAgentVerifiedVersion during release packaging."
        $resolvedVersion = "unknown"
    }

    if ($resolvedCode -le 0 -and $resolvedVersion -ne "unknown") {
        $resolvedCode = Get-PhoneAgentVersionCodeFromVersion -VersionName $resolvedVersion
    }

    if ($resolvedCode -le 0) {
        Write-Warning "Unable to infer phone agent verified versionCode. Pass -PhoneAgentVerifiedVersionCode during release packaging."
        $resolvedCode = $null
    }

    return [pscustomobject]@{
        Version = $resolvedVersion
        VersionCode = $resolvedCode
    }
}

function Write-CleanRuntimeConfig {
    param(
        [string]$PackageDir,
        [string]$ProfileName,
        [string]$ThemeId,
        [string]$Edition
    )

    $dataDir = Join-Path $PackageDir "data"
    $stateDir = Join-Path $dataDir ".openclaw"
    $agentDir = Join-Path $stateDir "agents\main\agent"
    $workspaceDir = Join-Path $stateDir "workspace"
    $storyboardAssets = Join-Path $dataDir "storyboards\assets"

    New-Item -ItemType Directory -Path $agentDir -Force | Out-Null
    New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null
    New-Item -ItemType Directory -Path $storyboardAssets -Force | Out-Null

    $openclawConfig = [ordered]@{
        gateway = [ordered]@{
            auth = [ordered]@{
                mode = "none"
            }
            bind = "loopback"
        }
        agents = [ordered]@{
            defaults = [ordered]@{
                workspace = "data/.openclaw/workspace"
                contextInjection = "always"
                bootstrapPromptTruncationWarning = "once"
            }
        }
    }
    $openclawConfig | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $stateDir "openclaw.json") -Encoding UTF8

    $brandProfile = [ordered]@{
        profile = $ProfileName
        themeId = $ThemeId
        edition = $Edition
    }
    $brandProfile | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $dataDir "brand_profile.json") -Encoding UTF8

    $launcherRuntime = [ordered]@{
        name = "OpenClaw Portable Launcher"
        version = $Version
        packageName = $PackageName
    }
    $launcherRuntime | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $dataDir "launcher_runtime.json") -Encoding UTF8

    "{}" | Set-Content -LiteralPath (Join-Path $PackageDir "imgapi_config.json") -Encoding UTF8
    "{}" | Set-Content -LiteralPath (Join-Path $PackageDir "video_config.json") -Encoding UTF8

    $phoneAgentVersionInfo = Resolve-PhoneAgentVersionInfo

    $runtimeContext = [ordered]@{
        schema = "openclaw.launcher.runtime-context.v1"
        updatedAt = $null
        launcher = [ordered]@{
            name = "OpenClaw Portable Launcher"
            version = $Version
            mode = "usb-portable"
            root = "."
        }
        workspace = [ordered]@{
            path = "data/.openclaw/workspace"
            bootstrapFiles = @("AGENTS.md", "SOUL.md", "TOOLS.md", "CAPABILITIES.md")
            skillsPath = "data/.openclaw/workspace/skills"
        }
        paths = [ordered]@{
            generatedImages = "data/generated-images"
            phoneVideos = "data/phone-videos"
            scripts = "scripts"
            imageToPhoneCli = "scripts/openclaw-image-phone.mjs"
            phoneAgentCli = "scripts/openclaw-phone-agent.mjs"
            phoneVideoCli = "scripts/openclaw-phone-video.mjs"
            phoneVisionCli = "scripts/openclaw-phone-vision.mjs"
            phoneGameCli = "scripts/openclaw-phone-game.mjs"
            phoneVerifier = "scripts/verify-phone-agent.ps1"
        }
        capabilities = [ordered]@{
            imageGeneration = [ordered]@{
                available = $true
                localOutputDir = "data/generated-images"
                cli = "npm run phone:image"
            }
            phoneAgent = [ordered]@{
                available = $true
                controlPolicy = "wrapper-only"
                agentCli = "npm run phone:agent"
                imageCli = "npm run phone:image"
                visionCli = "npm run phone:vision"
                videoDownloadDir = "data/phone-videos"
                videoCli = "npm run phone:video"
                gameModeCli = "npm run phone:game"
                defaultAlbum = "OpenClaw"
                galleryPath = "Pictures/OpenClaw"
                verifiedVersion = $phoneAgentVersionInfo.Version
                verifiedVersionCode = $phoneAgentVersionInfo.VersionCode
                maxRoundsPerTask = 60
                tokenSource = "data/.openclaw/launcher/phone-agent.json"
                tokenPolicy = "never expose token; use launcher CLI helpers only"
            }
            portableRuntime = [ordered]@{
                available = $true
                preferRelativePaths = $true
            }
        }
        phone = [ordered]@{
            configured = $false
            connected = $false
            endpoint = "launcher-cli-wrapper"
            baseUrl = $null
            tokenAvailable = $false
            configPath = "data/.openclaw/launcher/phone-agent.json"
            lastStatus = $null
        }
        policies = [ordered]@{
            autoSendGeneratedImagesToPhone = "enabled_when_phone_configured"
            autoUploadPersonalFiles = $false
            screenRecordingRequiresExplicitIntent = $true
            neverExposeSecrets = $true
        }
    }
    $runtimeContext | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $workspaceDir "runtime-context.json") -Encoding UTF8
}

function Resolve-BrandProfile {
    param([string]$Profile)

    $normalized = if ([string]::IsNullOrWhiteSpace($Profile)) { "lumi" } else { $Profile.Trim() }
    switch -Regex ($normalized.ToLowerInvariant()) {
        "^(lumi|personal|private)$" {
            return [pscustomobject]@{ Profile = "lumi"; ThemeId = "lumi"; Edition = "personal" }
        }
        "^(customer|delivery|yonghao|yonghao_tech)$" {
            return [pscustomobject]@{ Profile = "customer"; ThemeId = "yonghao_tech"; Edition = "delivery" }
        }
        default {
            return [pscustomobject]@{ Profile = $normalized; ThemeId = $normalized; Edition = "custom" }
        }
    }
}

function Copy-ThemeBundle {
    param(
        [string]$PackageDir,
        [string]$ThemeId
    )

    $themeRoot = Join-Path $LauncherDir "data\themes"
    $normalizedThemeId = if ([string]::IsNullOrWhiteSpace($ThemeId)) { "default" } else { $ThemeId.Trim() }
    $themeIds = New-Object System.Collections.Generic.List[string]
    $themeIds.Add("default")
    if ($normalizedThemeId -ne "default") {
        $themeIds.Add($normalizedThemeId)
    }

    $destinations = @(
        (Join-Path $PackageDir "data\themes"),
        (Join-Path $PackageDir "_up_\data\themes")
    )

    foreach ($destinationRoot in $destinations) {
        New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null
        foreach ($themeId in $themeIds) {
            $sourceTheme = Join-Path $themeRoot $themeId
            if (-not (Test-Path -LiteralPath $sourceTheme)) {
                throw "Theme not found: $sourceTheme"
            }
            Copy-Directory -Source $sourceTheme -Destination (Join-Path $destinationRoot $themeId)
        }
    }
}

function Remove-PythonCacheFiles {
    param([string]$PackageDir)

    Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $PackageDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force
}

function Install-PythonBridgeDependencies {
    param([string]$PackageDir)

    $requirements = Join-Path $LauncherDir "python\requirements.txt"
    $target = Join-Path $PackageDir "_up_\python"

    if (-not (Test-Path -LiteralPath $requirements)) {
        return
    }
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Python bridge target not found: $target"
    }

    & python -m pip install `
        --disable-pip-version-check `
        --no-warn-script-location `
        --upgrade `
        --target $target `
        -r $requirements
    if ($LASTEXITCODE -ne 0) {
        throw "pip install Python bridge dependencies failed with exit code $LASTEXITCODE"
    }
}

function Copy-PhoneAgentApks {
    param([string]$PackageDir)

    $latestApk = Join-Path $LauncherDir "AgentPhone_latest.apk"
    if (-not (Test-Path -LiteralPath $latestApk)) {
        Write-Warning "AgentPhone_latest.apk not found; portable package will not include phone agent APK."
        return
    }

    $targetDir = Join-Path $PackageDir "releases\agent-phone"
    Remove-SafePath $targetDir
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

    Copy-Item -LiteralPath $latestApk -Destination (Join-Path $targetDir "AgentPhone_latest.apk") -Force

    $latestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $latestApk).Hash
    Get-ChildItem -LiteralPath $LauncherDir -File -Filter "AgentPhone_v*.apk" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $candidateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
            if ($candidateHash -eq $latestHash) {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $targetDir $_.Name) -Force
            }
        }
}

function Copy-WebView2Redist {
    param([string]$PackageDir)

    $source = Join-Path $LauncherDir "redist\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    if (-not (Test-Path -LiteralPath $source)) {
        throw "WebView2 offline installer is missing: $source. Run scripts\download-webview2-runtime.ps1 before packaging."
    }

    $targetDir = Join-Path $PackageDir "redist"
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $targetDir "MicrosoftEdgeWebView2RuntimeInstallerX64.exe") -Force
}

function Expand-PortablePayloadForBuild {
    param([string]$PackageDir)

    $payloadDir = Join-Path $PackageDir "OpenClawFiles"
    if (-not (Test-Path -LiteralPath $payloadDir)) {
        return
    }
    if (Test-Path -LiteralPath (Join-Path $PackageDir "node\node.exe")) {
        return
    }

    Get-ChildItem -LiteralPath $payloadDir -Force |
        ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination $PackageDir -Force
        }
    Remove-SafePath $payloadDir
}

function Remove-LegacyNestedLaunchers {
    param([string]$PackageDir)

    Get-ChildItem -LiteralPath $PackageDir -Directory -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -notin @("data", "_up_", "node", "node_modules", "scripts", "releases") -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "app.exe")) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "data")) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "_up_"))
        } |
        ForEach-Object {
            Write-Host "Removing legacy nested launcher payload: $($_.FullName)" -ForegroundColor Yellow
            Remove-SafePath $_.FullName
        }
}

function Move-PortablePayload {
    param([string]$PackageDir)

    $payloadDir = Join-Path $PackageDir "OpenClawFiles"
    Remove-SafePath $payloadDir
    New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null

    Get-ChildItem -LiteralPath $PackageDir -Force |
        Where-Object { $_.Name -ne "OpenClaw.exe" -and $_.Name -ne "OpenClawFiles" } |
        ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination $payloadDir -Force
        }
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
5. Install the bundled phone agent from OpenClawFiles\releases\agent-phone\AgentPhone_latest.apk when phone control is needed.

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

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Get-LauncherVersion
}

if ([string]::IsNullOrWhiteSpace($PackageName)) {
    $date = Get-Date -Format "yyyy.MM.dd"
    $PackageName = "OpenClaw-Portable-v$Version-$date"
}

New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

$seedDir = Find-SeedPortableDir
$brand = Resolve-BrandProfile -Profile $BrandProfile
$brandThemeDir = Join-Path $LauncherDir "data\themes\$($brand.ThemeId)"
if (-not (Test-Path -LiteralPath (Join-Path $brandThemeDir "theme.json"))) {
    throw "Brand profile theme not found: $($brand.ThemeId) ($brandThemeDir)"
}
$packageDir = Join-Path $ReleaseDir $PackageName
$zipPath = Join-Path $ReleaseDir "$PackageName.zip"
$hashPath = Join-Path $ReleaseDir "$PackageName.zip.sha256.txt"

Write-Host "Package name: $PackageName"
Write-Host "Seed portable dir: $seedDir"
Write-Host "Brand profile: $($brand.Profile) -> theme $($brand.ThemeId) [$($brand.Edition)]"

Invoke-Step "Clean source workspace" {
    & powershell -ExecutionPolicy Bypass -File $CleanScript
}

Invoke-Step "Verify source text" {
    & powershell -ExecutionPolicy Bypass -File $VerifySourceTextScript
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
    Expand-PortablePayloadForBuild -PackageDir $packageDir
    Remove-LegacyNestedLaunchers -PackageDir $packageDir
    Copy-Item -LiteralPath $tauriExe -Destination (Join-Path $packageDir "OpenClaw.exe") -Force

    Remove-SafePath (Join-Path $packageDir "data")
    Remove-SafePath (Join-Path $packageDir "_up_\python")
    Remove-SafePath (Join-Path $packageDir "_up_\data")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "python") `
        -Destination (Join-Path $packageDir "_up_\python") `
        -ExcludeDirs @("__pycache__") `
        -ExcludeFiles @("*.pyc", "*.pyo")

    Install-PythonBridgeDependencies -PackageDir $packageDir

    Copy-ThemeBundle -PackageDir $packageDir -ThemeId $brand.ThemeId

    Copy-Directory `
        -Source (Join-Path $LauncherDir "openclaw-workspace") `
        -Destination (Join-Path $packageDir "data\.openclaw\workspace")

    Copy-Directory `
        -Source (Join-Path $LauncherDir "scripts") `
        -Destination (Join-Path $packageDir "scripts")

    Copy-PhoneAgentApks -PackageDir $packageDir
    Copy-WebView2Redist -PackageDir $packageDir

    Install-BundledBotPlugins -PackageDir $packageDir

    Write-CleanRuntimeConfig -PackageDir $packageDir -ProfileName $brand.Profile -ThemeId $brand.ThemeId -Edition $brand.Edition

    $nodeVersion = Get-NodeVersion -PackageDir $packageDir
    $openclawVersion = Get-OpenClawVersion -PackageDir $packageDir
    Write-PortableReadme -PackageDir $packageDir -NodeVersion $nodeVersion -OpenClawVersion $openclawVersion

    Get-ChildItem -LiteralPath $packageDir -File -Filter "README-*.txt" |
        Where-Object { $_.Name -ne "README-PORTABLE.txt" } |
        Remove-Item -Force

    Remove-PythonCacheFiles -PackageDir $packageDir
    Move-PortablePayload -PackageDir $packageDir
}

Invoke-Step "Verify portable directory" {
    & powershell -ExecutionPolicy Bypass -File $VerifyScript -Path $packageDir
}

Invoke-Step "Smoke verify portable runtime" {
    & powershell -ExecutionPolicy Bypass -File $SmokeVerifyScript -Path $packageDir
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
