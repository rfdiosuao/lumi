param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$InstallRoot,
    [Parameter(Mandatory = $true)][string]$AppExe,
    [Parameter(Mandatory = $true)][string]$RecoveryRoot,
    [Parameter(Mandatory = $true)][string]$MarkerPath,
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$TestMode
)

$ErrorActionPreference = "Stop"
$backupData = Join-Path $RecoveryRoot "data"
$logPath = Join-Path $RecoveryRoot "update-handoff.log"
New-Item -ItemType Directory -Force -Path $RecoveryRoot | Out-Null

function Write-UpdateLog([string]$Message) {
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value ((Get-Date -Format o) + " " + $Message)
}

function Copy-DataTree([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & "$env:WINDIR\System32\robocopy.exe" $Source $Destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed: exit=$LASTEXITCODE source=$Source destination=$Destination"
    }
}

try {
    while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 200
    }

    $sourceData = Join-Path $InstallRoot "data"
    Copy-DataTree -Source $sourceData -Destination $backupData
    [pscustomobject]@{
        version = $Version
        installRoot = $InstallRoot
        backup = $backupData
        state = "installing"
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $MarkerPath -Encoding UTF8
    Write-UpdateLog "backup complete; starting installer"

    & $Installer "/S" "/D=$InstallRoot"
    $setupExit = $LASTEXITCODE
    if ($null -eq $setupExit) {
        $setupExit = 0
    }
    if ($setupExit -ne 0) {
        throw "installer failed: exit=$setupExit"
    }

    Copy-DataTree -Source $backupData -Destination (Join-Path $InstallRoot "data")
    Remove-Item -LiteralPath $MarkerPath -Force -ErrorAction SilentlyContinue
    Write-UpdateLog "update complete; launching LOOM"
    if (-not $TestMode) {
        Start-Process -FilePath $AppExe -WorkingDirectory $InstallRoot
    }
}
catch {
    Write-UpdateLog ("update failed: " + $_.Exception.Message)
    Copy-DataTree -Source $backupData -Destination (Join-Path $InstallRoot "data")
    [pscustomobject]@{
        version = $Version
        installRoot = $InstallRoot
        backup = $backupData
        state = "failed"
        error = $_.Exception.Message
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $MarkerPath -Encoding UTF8
    exit 1
}
