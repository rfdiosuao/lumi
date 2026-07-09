param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$SmokeRoot,
    [Parameter(Mandatory = $true)]
    [string[]]$InstallPaths,
    [string]$ProductName = "Luming AI Matrix Acquisition Workbench",
    [string]$SecretScanScript = (Join-Path $PSScriptRoot "verify-release-secrets.ps1")
)

$ErrorActionPreference = "Stop"

function Resolve-NormalizedPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
}

function Assert-ChildPath {
    param(
        [string]$Parent,
        [string]$Child,
        [string]$Label
    )
    $parentPath = Resolve-NormalizedPath $Parent
    $childPath = Resolve-NormalizedPath $Child
    $prefix = $parentPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $childPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay inside $parentPath"
    }
    return $childPath
}

function Invoke-ProcessAndWait {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$StandardOutputPath = "",
        [string]$StandardErrorPath = ""
    )
    $startParameters = @{
        FilePath = $FilePath
        ArgumentList = $Arguments
        PassThru = $true
        Wait = $true
        WindowStyle = "Hidden"
    }
    if (-not [string]::IsNullOrWhiteSpace($StandardOutputPath)) {
        $startParameters["RedirectStandardOutput"] = $StandardOutputPath
    }
    if (-not [string]::IsNullOrWhiteSpace($StandardErrorPath)) {
        $startParameters["RedirectStandardError"] = $StandardErrorPath
    }
    $process = Start-Process @startParameters
    if ($process.ExitCode -ne 0) {
        $details = @()
        foreach ($logPath in @($StandardOutputPath, $StandardErrorPath)) {
            if (-not [string]::IsNullOrWhiteSpace($logPath) -and (Test-Path -LiteralPath $logPath)) {
                $logContent = Get-Content -LiteralPath $logPath -Raw -Encoding UTF8
                if ($null -ne $logContent) {
                    $details += ([string]$logContent).Trim()
                }
            }
        }
        $detailText = ($details | Where-Object { $_ }) -join [Environment]::NewLine
        throw "Process failed with exit code $($process.ExitCode): $FilePath$([Environment]::NewLine)$detailText"
    }
}

function Stop-OwnedProcess {
    param(
        [int]$ProcessId,
        [string]$ExpectedRoot
    )
    if ($ProcessId -le 0) {
        return
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo) {
        return
    }
    $executablePath = [string]$processInfo.ExecutablePath
    if ([string]::IsNullOrWhiteSpace($executablePath)) {
        throw "Refusing to stop process $ProcessId without an executable path"
    }
    [void](Assert-ChildPath -Parent $ExpectedRoot -Child $executablePath -Label "Owned process")
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
}

function Get-HttpStatus {
    param(
        [string]$Uri,
        [hashtable]$Headers
    )
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers $Headers -Method Get -TimeoutSec 10
        return [int]$response.StatusCode
    }
    catch {
        if ($null -ne $_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Wait-BridgeSession {
    param(
        [string]$SessionPath,
        [int]$TimeoutSeconds = 35
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $SessionPath) {
            try {
                $session = Get-Content -LiteralPath $SessionPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($session.port -and $session.token -and $session.pid) {
                    return $session
                }
            }
            catch {
                # The bridge writes through a temporary file; retry a partial read.
            }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Packaged bridge did not become ready within $TimeoutSeconds seconds"
}

function Test-InstalledRuntime {
    param(
        [string]$InstallPath,
        [string]$CaseName,
        [string]$CaseDataRoot,
        [string]$SecretScanPath
    )

    $loomExe = Join-Path $InstallPath "LOOM.exe"
    $uninstaller = Join-Path $InstallPath "uninstall.exe"
    $pythonExe = Join-Path $InstallPath "_up_\python-runtime\python.exe"
    $bridgeFile = Join-Path $InstallPath "_up_\python\bridge.py"
    foreach ($required in @($loomExe, $uninstaller, $pythonExe, $bridgeFile)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Installed payload is missing: $required"
        }
    }

    $forbiddenExecutables = Get-ChildItem -LiteralPath $InstallPath -Recurse -File -ErrorAction Stop |
        Where-Object { $_.Name -match '^(codex|claude|opencode|hermes)(\.exe|\.cmd|\.bat)?$' }
    if ($forbiddenExecutables) {
        throw "Installer bundled a third-party Agent executable: $($forbiddenExecutables[0].FullName)"
    }

    New-Item -ItemType Directory -Path $CaseDataRoot -Force | Out-Null
    $secretScanOutput = Join-Path $CaseDataRoot "secret-scan.stdout.log"
    $secretScanError = Join-Path $CaseDataRoot "secret-scan.stderr.log"
    Invoke-ProcessAndWait -FilePath "powershell.exe" -Arguments @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $SecretScanPath,
        "-Path",
        $InstallPath
    ) -StandardOutputPath $secretScanOutput -StandardErrorPath $secretScanError

    $sessionDir = Join-Path $CaseDataRoot "bridge-session"
    New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
    $sessionPath = Join-Path $sessionDir "bridge-session.json"
    if (Test-Path -LiteralPath $sessionPath -PathType Leaf) {
        Remove-Item -LiteralPath $sessionPath -Force
    }

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $loomExe
    $startInfo.WorkingDirectory = $InstallPath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.EnvironmentVariables["LOCALAPPDATA"] = $CaseDataRoot
    $startInfo.EnvironmentVariables["LOOM_BRIDGE_SESSION_DIR"] = $sessionDir

    $appProcess = $null
    $bridgePid = 0
    try {
        $appProcess = [System.Diagnostics.Process]::Start($startInfo)
        $session = Wait-BridgeSession -SessionPath $sessionPath
        $bridgePid = [int]$session.pid
        if ([string]$session.impl -ne "fastapi") {
            throw "Packaged bridge did not start with FastAPI: $($session.impl)"
        }

        $bridgeProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$bridgePid" -ErrorAction Stop
        $bridgeExecutable = Resolve-NormalizedPath ([string]$bridgeProcess.ExecutablePath)
        $expectedPython = Resolve-NormalizedPath $pythonExe
        if (-not $bridgeExecutable.Equals($expectedPython, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Bridge used an unexpected Python runtime: $bridgeExecutable"
        }

        $headers = @{ "X-Bridge-Token" = [string]$session.token }
        $licenseStatus = Get-HttpStatus -Uri "$($session.url)/api/license/current" -Headers $headers
        $matrixStatus = Get-HttpStatus -Uri "$($session.url)/api/matrix/status" -Headers $headers
        $acquisitionStatus = Get-HttpStatus -Uri "$($session.url)/api/matrix/acquisition" -Headers $headers
        if ($licenseStatus -ne 200) {
            throw "Public license endpoint returned $licenseStatus"
        }
        if ($matrixStatus -ne 403 -or $acquisitionStatus -ne 403) {
            throw "Protected endpoints were not denied for an unlicensed install: matrix=$matrixStatus acquisition=$acquisitionStatus"
        }

        return [pscustomobject]@{
            case = $CaseName
            installPath = $InstallPath
            bridge = "fastapi"
            pythonRuntime = "packaged"
            licenseEndpoint = $licenseStatus
            matrixEndpoint = $matrixStatus
            acquisitionEndpoint = $acquisitionStatus
        }
    }
    finally {
        if ($null -ne $appProcess -and -not $appProcess.HasExited) {
            Stop-OwnedProcess -ProcessId $appProcess.Id -ExpectedRoot $InstallPath
        }
        Start-Sleep -Milliseconds 500
        if ($bridgePid -gt 0) {
            Stop-OwnedProcess -ProcessId $bridgePid -ExpectedRoot $InstallPath
        }
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$allowedArtifactsRoot = Resolve-NormalizedPath (Join-Path $repoRoot "artifacts")
$resolvedSmokeRoot = Assert-ChildPath -Parent $allowedArtifactsRoot -Child $SmokeRoot -Label "Smoke root"
$resolvedInstaller = (Resolve-Path -LiteralPath $Installer).Path
$resolvedSecretScanScript = (Resolve-Path -LiteralPath $SecretScanScript).Path
if ([System.IO.Path]::GetExtension($resolvedInstaller) -ine ".exe") {
    throw "Installer must be an executable"
}

New-Item -ItemType Directory -Path $resolvedSmokeRoot -Force | Out-Null
$resolvedInstallPaths = @()
foreach ($installPath in $InstallPaths) {
    $resolvedPath = Assert-ChildPath -Parent $resolvedSmokeRoot -Child $installPath -Label "Install path"
    if (Test-Path -LiteralPath $resolvedPath) {
        throw "Install path must not already exist: $resolvedPath"
    }
    $resolvedInstallPaths += $resolvedPath
}

$runningLoom = Get-CimInstance Win32_Process -Filter "Name='LOOM.exe'" -ErrorAction SilentlyContinue
if ($runningLoom) {
    throw "Close all existing LOOM processes before running the installer smoke test"
}

$uninstallRoot = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
$productKey = Join-Path $uninstallRoot $ProductName
$backupName = "$ProductName.__codex_release_smoke_$PID"
$backupKey = Join-Path $uninstallRoot $backupName
if (Test-Path -LiteralPath $backupKey) {
    throw "Temporary uninstall backup key already exists: $backupKey"
}

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$ProductName.lnk"
$programsShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "$ProductName.lnk"
$shortcutPaths = @($desktopShortcut, $programsShortcut)
$shortcutBackupRoot = Join-Path $resolvedSmokeRoot "shortcut-backup"
$shortcutBackups = [System.Collections.Generic.List[object]]::new()
$renamedProductKey = $false
$results = [System.Collections.Generic.List[object]]::new()

try {
    New-Item -ItemType Directory -Path $shortcutBackupRoot -Force | Out-Null
    $shortcutIndex = 0
    foreach ($shortcutPath in $shortcutPaths) {
        if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
            $backupPath = Join-Path $shortcutBackupRoot "$shortcutIndex.lnk"
            Copy-Item -LiteralPath $shortcutPath -Destination $backupPath -Force
            $shortcutBackups.Add([pscustomobject]@{ Original = $shortcutPath; Backup = $backupPath })
        }
        $shortcutIndex += 1
    }

    if (Test-Path -LiteralPath $productKey) {
        Rename-Item -LiteralPath $productKey -NewName $backupName
        $renamedProductKey = $true
    }

    $caseIndex = 0
    foreach ($installPath in $resolvedInstallPaths) {
        $caseName = "case-$caseIndex"
        Invoke-ProcessAndWait -FilePath $resolvedInstaller -Arguments @("/S", "/D=$installPath")
        try {
            $caseDataRoot = Join-Path $resolvedSmokeRoot "$caseName-data"
            $result = Test-InstalledRuntime -InstallPath $installPath -CaseName $caseName -CaseDataRoot $caseDataRoot -SecretScanPath $resolvedSecretScanScript
            $results.Add($result)
        }
        finally {
            $uninstaller = Join-Path $installPath "uninstall.exe"
            if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
                Invoke-ProcessAndWait -FilePath $uninstaller -Arguments @("/S")
                Start-Sleep -Seconds 2
            }
            if (Test-Path -LiteralPath $installPath) {
                $verifiedTarget = Assert-ChildPath -Parent $resolvedSmokeRoot -Child $installPath -Label "Cleanup path"
                Remove-Item -LiteralPath $verifiedTarget -Recurse -Force
            }
        }
        $caseIndex += 1
    }
}
finally {
    foreach ($shortcutPath in $shortcutPaths) {
        if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
            Remove-Item -LiteralPath $shortcutPath -Force
        }
    }
    foreach ($shortcutBackup in $shortcutBackups) {
        Copy-Item -LiteralPath $shortcutBackup.Backup -Destination $shortcutBackup.Original -Force
    }

    if (Test-Path -LiteralPath $productKey) {
        $testInstallLocation = [string](Get-ItemProperty -LiteralPath $productKey -ErrorAction SilentlyContinue).InstallLocation
        if (-not [string]::IsNullOrWhiteSpace($testInstallLocation)) {
            $trimmedLocation = $testInstallLocation.Trim('"')
            [void](Assert-ChildPath -Parent $resolvedSmokeRoot -Child $trimmedLocation -Label "Temporary uninstall key")
        }
        Remove-Item -LiteralPath $productKey -Recurse -Force
    }
    if ($renamedProductKey -and (Test-Path -LiteralPath $backupKey)) {
        Rename-Item -LiteralPath $backupKey -NewName $ProductName
    }
}

$results | ConvertTo-Json -Depth 4
