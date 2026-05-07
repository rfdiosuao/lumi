param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"

$requiredFiles = @(
    "OpenClaw.exe",
    "node/node.exe",
    "node_modules/openclaw/openclaw.mjs",
    "start.js",
    "scripts/bot-plugin-helper.mjs",
    "_up_/python/bridge.py",
    "_up_/python-runtime/python.exe",
    "data/.openclaw/openclaw.json",
    "data/themes/default/theme.json",
    "data/themes/default/logo.png",
    "imgapi_config.json",
    "video_config.json",
    "node_modules/@larksuite/openclaw-lark/package.json",
    "node_modules/@tencent-weixin/openclaw-weixin/package.json"
)

$allowedTopLevelEntries = @(
    "OpenClaw.exe",
    "OpenClawFiles"
)

$forbiddenPatterns = @(
    "(?i)(^|/)data/license\.json$",
    "(?i)(^|/)data/install_id\.txt$",
    "(?i)(^|/)data/theme\.json$",
    "(?i)(^|/)__pycache__(/|$)",
    "(?i)\.pyc$",
    "(?i)(^|/)\.npm-cache-update(/|$)",
    "(?i)(^|/)(license\.db|private_key\.b64|admin_token\.txt)$",
    "(?i)(^|/)node_modules/\.cache(/|$)"
)

$contentScanSuffixes = @(
    "/.npmrc",
    "/README-离线包.txt",
    "/_up_/python/bridge.py",
    "/data/.openclaw/openclaw.json",
    "/imgapi_config.json",
    "/video_config.json",
    "/package.json",
    "/start.js"
)

$emptyJsonConfigSuffixes = @(
    "/imgapi_config.json",
    "/video_config.json"
)

$openClawRuntimeConfigSuffix = "/data/.openclaw/openclaw.json"

$sensitiveContentPattern = '(?i)\b(sk-[A-Za-z0-9_\-]{24,}|(?:OPENAI|DASHSCOPE|ANTHROPIC|GOOGLE|GITHUB|AZURE|COHERE)_API_KEY\s*[:=]\s*["'']?[A-Za-z0-9_\-]{16,})\b'

function Convert-ToPortablePath {
    param([string]$Value)
    return $Value.Replace("\", "/").TrimStart("/")
}

function Test-RequiredPath {
    param(
        [string[]]$AllPaths,
        [string]$RequiredPath
    )

    $needle = Convert-ToPortablePath $RequiredPath
    foreach ($item in $AllPaths) {
        $normalized = Convert-ToPortablePath $item
        if ($normalized -eq $needle -or $normalized.EndsWith("/$needle")) {
            return $true
        }
    }
    return $false
}

function Test-ForbiddenPath {
    param([string]$Value)

    $normalized = Convert-ToPortablePath $Value
    foreach ($pattern in $forbiddenPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }
    return $false
}

function Test-ContentScanTarget {
    param([string]$Value)

    foreach ($suffix in $contentScanSuffixes) {
        if ($Value.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-PayloadRelativePaths {
    param([string[]]$AllPaths)

    $normalized = @($AllPaths |
        ForEach-Object { Convert-ToPortablePath $_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

    if ($normalized.Count -eq 0) {
        return @()
    }

    $topSegments = @($normalized |
        ForEach-Object { ($_ -split "/")[0] } |
        Sort-Object -Unique)

    if (
        $topSegments.Count -eq 1 -and
        $topSegments[0] -ne "OpenClaw.exe" -and
        $topSegments[0] -ne "OpenClawFiles"
    ) {
        $prefix = "$($topSegments[0])/"
        $candidate = @($normalized |
            Where-Object { $_.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { $_.Substring($prefix.Length) } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

        $candidateTopSegments = @($candidate |
            ForEach-Object { ($_ -split "/")[0] } |
            Sort-Object -Unique)

        if ($candidateTopSegments -contains "OpenClaw.exe" -or $candidateTopSegments -contains "OpenClawFiles") {
            return $candidate
        }
    }

    return $normalized
}

function Add-ContentFindings {
    param(
        [string]$RelativePath,
        [string]$Content,
        [System.Collections.Generic.List[string]]$Errors,
        [System.Collections.Generic.List[string]]$Warnings
    )

    if ($Content -match $sensitiveContentPattern) {
        $Warnings.Add("Possible sensitive text found in: $RelativePath")
    }

    foreach ($suffix in $emptyJsonConfigSuffixes) {
        if (-not $RelativePath.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }

        try {
            $json = $Content | ConvertFrom-Json
            $props = @($json.PSObject.Properties)
            if ($props.Count -gt 0) {
                $Errors.Add("Runtime API config must be empty for delivery: $RelativePath")
            }
        }
        catch {
            $Errors.Add("Runtime API config is not valid JSON: $RelativePath")
        }
    }

    if ($RelativePath.EndsWith($openClawRuntimeConfigSuffix, [System.StringComparison]::OrdinalIgnoreCase)) {
        try {
            $json = $Content | ConvertFrom-Json
            $authMode = [string]$json.gateway.auth.mode
            $bind = [string]$json.gateway.bind

            if ($authMode -ne "none") {
                $Errors.Add("OpenClaw gateway auth mode must be none for launcher-managed local delivery: $RelativePath")
            }
            if ($bind -ne "loopback") {
                $Errors.Add("OpenClaw gateway bind must be loopback for local delivery: $RelativePath")
            }
        }
        catch {
            $Errors.Add("OpenClaw runtime config is not valid JSON: $RelativePath")
        }
    }
}

if (-not (Test-Path -LiteralPath $Path)) {
    throw "Release path does not exist: $Path"
}

$item = Get-Item -LiteralPath $Path
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$allPaths = @()

if ($item.PSIsContainer) {
    $root = $item.FullName
    $allFiles = Get-ChildItem -LiteralPath $root -Recurse -Force -File
    $allDirs = Get-ChildItem -LiteralPath $root -Recurse -Force -Directory
    $allPaths = @($allFiles + $allDirs | ForEach-Object {
            Convert-ToPortablePath ($_.FullName.Substring($root.Length).TrimStart("\", "/"))
        })

    foreach ($file in $allFiles) {
        $relative = Convert-ToPortablePath ($file.FullName.Substring($root.Length).TrimStart("\", "/"))
        if (Test-ForbiddenPath $relative) {
            $errors.Add("Forbidden file included: $relative")
        }
        if ((Test-ContentScanTarget $relative) -and $file.Length -le 2MB) {
            $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
            Add-ContentFindings -RelativePath $relative -Content $content -Errors $errors -Warnings $warnings
        }
    }

    foreach ($dir in $allDirs) {
        $relative = Convert-ToPortablePath ($dir.FullName.Substring($root.Length).TrimStart("\", "/"))
        if (Test-ForbiddenPath $relative) {
            $errors.Add("Forbidden directory included: $relative")
        }
    }
}
else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($item.FullName)
    try {
        $allPaths = @($zip.Entries | ForEach-Object { Convert-ToPortablePath $_.FullName })

        foreach ($entry in $zip.Entries) {
            $relative = Convert-ToPortablePath $entry.FullName
            if (Test-ForbiddenPath $relative) {
                $errors.Add("Forbidden entry included: $relative")
            }

            if ($entry.Length -gt 0 -and $entry.Length -le 2MB -and (Test-ContentScanTarget $relative)) {
                $reader = New-Object System.IO.StreamReader($entry.Open())
                try {
                    $content = $reader.ReadToEnd()
                }
                finally {
                    $reader.Dispose()
                }
                Add-ContentFindings -RelativePath $relative -Content $content -Errors $errors -Warnings $warnings
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}

$payloadPaths = @(Get-PayloadRelativePaths -AllPaths $allPaths)
$topLevelEntries = @($payloadPaths |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    ForEach-Object { ($_ -split "/")[0] } |
    Sort-Object -Unique)

foreach ($entry in $topLevelEntries) {
    if ($allowedTopLevelEntries -notcontains $entry) {
        $errors.Add("Unexpected top-level entry in portable package: $entry")
    }
}

foreach ($entry in $allowedTopLevelEntries) {
    if ($topLevelEntries -notcontains $entry) {
        $errors.Add("Required top-level entry missing: $entry")
    }
}

foreach ($required in $requiredFiles) {
    if (-not (Test-RequiredPath -AllPaths $payloadPaths -RequiredPath $required)) {
        $errors.Add("Required file missing: $required")
    }
}

Write-Host "Release verification target: $($item.FullName)"
Write-Host "Checked paths: $($allPaths.Count)"
Write-Host "Payload paths: $($payloadPaths.Count)"

if ($warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings:"
    foreach ($warning in $warnings) {
        Write-Host "  - $warning"
    }
}

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "Errors:"
    foreach ($errorItem in $errors) {
        Write-Host "  - $errorItem"
    }
    exit 1
}

Write-Host "Release package check passed."
