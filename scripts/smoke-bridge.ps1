param(
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LauncherDir = Join-Path $Root "openclaw_new_launcher"
$BridgePath = Join-Path $LauncherDir "python\bridge.py"

if (-not (Test-Path -LiteralPath $BridgePath)) {
    throw "Bridge script not found: $BridgePath"
}

function Invoke-BridgeJson {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][hashtable]$Headers,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = $Headers
        TimeoutSec = 8
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
    }
    return Invoke-RestMethod @params
}

function Assert-Property {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Context
    )

    if (-not ($Object.PSObject.Properties.Name -contains $Name)) {
        throw "$Context missing property: $Name"
    }
}

function Get-FileText {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) "openclaw-bridge-smoke-$timestamp.out"
$stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) "openclaw-bridge-smoke-$timestamp.err"
$process = $null
$previousUtf8 = $env:PYTHONUTF8
$previousIoEncoding = $env:PYTHONIOENCODING
$previousDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE

try {
    Write-Host "Starting Python bridge smoke test..."
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList "`"$BridgePath`"" `
        -WorkingDirectory $LauncherDir `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru `
        -WindowStyle Hidden

    $port = $null
    $token = $null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)

    while ([DateTime]::UtcNow -lt $deadline -and (-not $port -or -not $token)) {
        if ($process.HasExited) {
            $stderrText = Get-FileText -Path $stderrPath
            throw "Bridge exited before becoming ready. $stderrText"
        }

        $stdoutText = Get-FileText -Path $stdoutPath
        foreach ($line in ($stdoutText -split "`r?`n")) {
            if (-not $port -and $line -match "^BRIDGE_PORT=(\d+)$") {
                $port = [int]$Matches[1]
                Write-Host "Bridge port: $port"
            }
            if (-not $token -and $line -match "^BRIDGE_TOKEN=(.+)$") {
                $token = $Matches[1]
                Write-Host "Bridge token received."
            }
        }

        if (-not $port -or -not $token) {
            Start-Sleep -Milliseconds 100
        }
    }

    if (-not $port -or -not $token) {
        $stderrText = Get-FileText -Path $stderrPath
        $stdoutText = Get-FileText -Path $stdoutPath
        throw "Bridge did not become ready within ${TimeoutSeconds}s.`nSTDOUT:`n$stdoutText`nSTDERR:`n$stderrText"
    }

    $baseUrl = "http://127.0.0.1:$port"
    $headers = @{ "X-Bridge-Token" = $token }

    Write-Host "Checking token rejection..."
    try {
        Invoke-RestMethod -Uri "$baseUrl/api/system/info" -Method GET -TimeoutSec 8 | Out-Null
        throw "Bridge accepted a request without X-Bridge-Token."
    } catch {
        $response = $_.Exception.Response
        if ($null -eq $response) {
            throw
        }
        $statusCode = [int]$response.StatusCode
        if ($statusCode -ne 401) {
            throw "Expected HTTP 401 without token, got $statusCode"
        }
    }

    $checks = @(
        @{ Name = "system info"; Path = "/api/system/info"; Method = "GET"; Props = @("node_path", "base_path", "openclaw_version") },
        @{ Name = "process status"; Path = "/api/process/status"; Method = "GET"; Props = @("running", "pid") },
        @{ Name = "log get"; Path = "/api/log/get"; Method = "GET"; Props = @("log") },
        @{ Name = "license current"; Path = "/api/license/current"; Method = "GET"; Props = @("license") },
        @{ Name = "license authorized"; Path = "/api/license/authorized"; Method = "POST"; Body = @{ feature = "openclaw" }; Props = @("authorized") },
        @{ Name = "theme current"; Path = "/api/theme/current"; Method = "GET"; Props = @("theme") },
        @{ Name = "skills list"; Path = "/api/skills/list"; Method = "GET"; Props = @("skills", "directories", "sites") },
        @{ Name = "skills paths"; Path = "/api/skills/paths"; Method = "GET"; Props = @("directories", "sites") }
    )

    foreach ($check in $checks) {
        Write-Host "Checking $($check.Name)..."
        $response = Invoke-BridgeJson -Url "$baseUrl$($check.Path)" -Headers $headers -Method $check.Method -Body $check.Body
        foreach ($prop in $check.Props) {
            Assert-Property -Object $response -Name $prop -Context $check.Name
        }
    }

    Write-Host "Bridge smoke check passed." -ForegroundColor Green
} finally {
    $env:PYTHONUTF8 = $previousUtf8
    $env:PYTHONIOENCODING = $previousIoEncoding
    $env:PYTHONDONTWRITEBYTECODE = $previousDontWriteBytecode

    if ($process -and -not $process.HasExited) {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            $process.WaitForExit(5000) | Out-Null
        } catch {
            Write-Warning "Failed to stop bridge process $($process.Id): $_"
        }
    }

    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
}
