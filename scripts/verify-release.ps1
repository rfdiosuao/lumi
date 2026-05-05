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
    "_up_/python/bridge.py",
    "_up_/python-runtime/python.exe",
    "data/.openclaw/openclaw.json"
)

$forbiddenPatterns = @(
    "(?i)(^|/)data/license\.json$",
    "(?i)(^|/)data/install_id\.txt$",
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
    "/package.json",
    "/start.js"
)

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
            if ($content -match $sensitiveContentPattern) {
                $warnings.Add("Possible sensitive text found in: $relative")
            }
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
                if ($content -match $sensitiveContentPattern) {
                    $warnings.Add("Possible sensitive text found in: $relative")
                }
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}

foreach ($required in $requiredFiles) {
    if (-not (Test-RequiredPath -AllPaths $allPaths -RequiredPath $required)) {
        $errors.Add("Required file missing: $required")
    }
}

Write-Host "Release verification target: $($item.FullName)"
Write-Host "Checked paths: $($allPaths.Count)"

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
