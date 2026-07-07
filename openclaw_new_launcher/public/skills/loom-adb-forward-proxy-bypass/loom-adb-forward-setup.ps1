param(
    [string]$BasePath = "",
    [string]$DeviceSerial = "",
    [string]$LoomDeviceId = "",
    [int]$LocalPort = 18790,
    [int]$PhonePort = 9527,
    [string]$ConfigPath = "",
    [string]$AdbPath = "",
    [string]$PythonPath = "",
    [string]$CliPath = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Say($message, $color = "Gray") {
    Write-Host $message -ForegroundColor $color
}

function FirstExistingFile([string[]]$paths) {
    foreach ($item in $paths) {
        if ($item -and (Test-Path -LiteralPath $item -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $item).Path
        }
    }
    return ""
}

function FirstExistingDir([string[]]$paths) {
    foreach ($item in $paths) {
        if ($item -and (Test-Path -LiteralPath $item -PathType Container)) {
            return (Resolve-Path -LiteralPath $item).Path
        }
    }
    return ""
}

function FindOnPath($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    return ""
}

function Join-IfBase($base, $child) {
    if (-not $base) { return "" }
    return Join-Path $base $child
}

function Test-TcpPort($hostName, $port) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $task = $client.ConnectAsync($hostName, $port)
        if (-not $task.Wait(2000)) {
            $client.Dispose()
            return $false
        }
        $client.Dispose()
        return $true
    } catch {
        return $false
    }
}

function Read-JsonFile($path) {
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Cannot read or parse config: $path; $($_.Exception.Message)"
    }
}

function Write-JsonFile($path, $value) {
    $json = $value | ConvertTo-Json -Depth 20
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, $utf8NoBom)
}

function Get-AuthorizedDevices($adb) {
    $lines = & $adb devices 2>&1
    $devices = @()
    foreach ($line in $lines) {
        $text = [string]$line
        if ($text -match "^(\S+)\s+device$") {
            $devices += $Matches[1]
        }
    }
    return $devices
}

function Pick-Device($devices, $requestedSerial) {
    if ($requestedSerial) {
        if ($devices -contains $requestedSerial) { return $requestedSerial }
        throw "Authorized ADB device not found: $requestedSerial. Approve USB debugging and retry."
    }
    if ($devices.Count -eq 1) { return $devices[0] }
    if ($devices.Count -eq 0) { throw "No authorized ADB device. Connect USB, enable USB debugging, and approve the phone dialog." }
    throw "Multiple ADB devices found: $($devices -join ', '). Use -DeviceSerial to choose one."
}

function Update-PhoneConfig($path, $newBaseUrl, $loomDeviceId, $dryRun) {
    $cfg = Read-JsonFile $path
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$path.bak.$timestamp"

    if ($cfg.PSObject.Properties.Name -contains "devices") {
        $devices = @($cfg.devices)
        if ($devices.Count -eq 0) {
            throw "phone-agents.json has no devices. Save one phone in LOOM first."
        }

        $target = $null
        if ($loomDeviceId) {
            $target = $devices | Where-Object { "$($_.id)" -eq $loomDeviceId } | Select-Object -First 1
            if (-not $target) { throw "LoomDeviceId=$loomDeviceId not found. Available: $(( $devices | ForEach-Object { $_.id }) -join ', ')" }
        } elseif ($devices.Count -eq 1) {
            $target = $devices[0]
        } else {
            throw "LOOM config has multiple phones. Use -LoomDeviceId to choose the target device."
        }

        $old = "$($target.baseUrl)"
        if (-not $dryRun) {
            Copy-Item -LiteralPath $path -Destination $backup -Force
            $target.baseUrl = $newBaseUrl
            Write-JsonFile $path $cfg
        }
        return [pscustomobject]@{ OldBaseUrl = $old; NewBaseUrl = $newBaseUrl; Backup = $backup }
    }

    if ($cfg.PSObject.Properties.Name -contains "baseUrl") {
        $old = "$($cfg.baseUrl)"
        if (-not $dryRun) {
            Copy-Item -LiteralPath $path -Destination $backup -Force
            $cfg.baseUrl = $newBaseUrl
            Write-JsonFile $path $cfg
        }
        return [pscustomobject]@{ OldBaseUrl = $old; NewBaseUrl = $newBaseUrl; Backup = $backup }
    }

    throw "Unknown LOOM phone-agent config shape: $path"
}

Say "=== LOOM USB ADB fallback connection repair ===" Cyan

$baseCandidates = @(
    $BasePath,
    $env:LOOM_HOME,
    "D:\LOOM",
    "C:\LOOM",
    "$env:LOCALAPPDATA\LOOM",
    (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)
$resolvedBase = FirstExistingDir $baseCandidates

if (-not $AdbPath) {
    $AdbPath = FirstExistingFile @(
        $env:LOOM_ADB,
        $env:ADB,
        (Join-IfBase $resolvedBase "LOOMFiles\platform-tools\adb.exe"),
        (Join-IfBase $resolvedBase "platform-tools\adb.exe"),
        (Join-IfBase $resolvedBase "_up_\platform-tools\adb.exe"),
        (Join-IfBase $resolvedBase "LOOMFiles\_up_\platform-tools\adb.exe"),
        (FindOnPath "adb.exe"),
        (FindOnPath "adb")
    )
}
if (-not $AdbPath) { throw "adb.exe not found. Install/bundle Android platform-tools, or pass -AdbPath." }

if (-not $ConfigPath) {
    $ConfigPath = FirstExistingFile @(
        $env:LOOM_PHONE_CONFIG,
        (Join-IfBase $resolvedBase "LOOMFiles\data\.openclaw\launcher\phone-agents.json"),
        (Join-IfBase $resolvedBase "data\.openclaw\launcher\phone-agents.json"),
        (Join-IfBase $resolvedBase "LOOMFiles\data\.openclaw\launcher\phone-agent.json"),
        (Join-IfBase $resolvedBase "data\.openclaw\launcher\phone-agent.json")
    )
}
if (-not $ConfigPath) { throw "LOOM phone config not found. Save a device in LOOM first, or pass -ConfigPath." }

if (-not $CliPath) {
    $CliPath = FirstExistingFile @(
        $env:LOOM_CLI,
        (Join-IfBase $resolvedBase "_up_\python\loom_cli.py"),
        (Join-IfBase $resolvedBase "LOOMFiles\_up_\python\loom_cli.py"),
        (Join-IfBase $resolvedBase "python\loom_cli.py")
    )
}

if (-not $PythonPath) {
    $PythonPath = FirstExistingFile @(
        $env:LOOM_PYTHON,
        (Join-IfBase $resolvedBase "LOOMFiles\_up_\python-runtime\python.exe"),
        (Join-IfBase $resolvedBase "_up_\python-runtime\python.exe"),
        (FindOnPath "python.exe"),
        (FindOnPath "python")
    )
}

Say "[1/5] Check ADB device..." Yellow
$devices = Get-AuthorizedDevices $AdbPath
$serial = Pick-Device $devices $DeviceSerial
Say "      device: $serial" Green

Say "[2/5] Create USB forward 127.0.0.1:$LocalPort -> phone:$PhonePort..." Yellow
if (-not $DryRun) {
    & $AdbPath -s $serial forward --remove "tcp:$LocalPort" 2>$null | Out-Null
    & $AdbPath -s $serial forward "tcp:$LocalPort" "tcp:$PhonePort" | Out-Null
}
if (-not $DryRun -and -not (Test-TcpPort "127.0.0.1" $LocalPort)) {
    throw "ADB forward was created, but 127.0.0.1:$LocalPort is still unreachable. Make sure APKClaw is running on the phone."
}
Say "      forward ready" Green

Say "[3/5] Try to start APKClaw..." Yellow
if (-not $DryRun) {
    $proc = & $AdbPath -s $serial shell ps -A 2>&1 | Select-String "com.apk.claw.android"
    if (-not $proc) {
        & $AdbPath -s $serial shell am start -n "com.apk.claw.android/.ui.splash.SplashActivity" 2>&1 | Out-Null
        Start-Sleep -Seconds 3
    }
}
Say "      start attempted; if accessibility is off, open APKClaw on the phone and authorize it." Green

Say "[4/5] Update LOOM phone config..." Yellow
$newUrl = "http://127.0.0.1:$LocalPort"
$updated = Update-PhoneConfig $ConfigPath $newUrl $LoomDeviceId $DryRun
Say "      $($updated.OldBaseUrl) -> $($updated.NewBaseUrl)" Green
if (-not $DryRun) { Say "      backup: $($updated.Backup)" DarkGray }

Say "[5/5] Verify LOOM phone status..." Yellow
if ($CliPath -and $PythonPath -and -not $DryRun) {
    try {
        $first = & $PythonPath -B $CliPath phone status --json 2>&1 | Select-Object -First 1
        Say "      status job submitted: $first" Green
    } catch {
        Say "      forward completed, but CLI verification failed: $($_.Exception.Message)" Yellow
    }
} else {
    Say "      skip CLI verification. Python/CLI not found or DryRun=true." Yellow
}

Say ""
Say "Done. Current phone channel: USB ADB forward -> $newUrl" Cyan
Say "If USB is replugged or ADB restarts, rerun this script." DarkGray
