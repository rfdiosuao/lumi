param(
    [string]$Owner = "rfdiosuao",
    [string]$Repo = "lumi",
    [string]$TagName = "",
    [string]$Name = "",
    [string]$Body = "",
    [string[]]$Assets = @(),
    [string]$Token = $env:GITEE_ACCESS_TOKEN
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = $env:GITEE_TOKEN
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    throw "Missing Gitee token. Set GITEE_ACCESS_TOKEN or GITEE_TOKEN first."
}

if ([string]::IsNullOrWhiteSpace($TagName)) {
    $TagName = (git describe --tags --exact-match 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($TagName)) {
        throw "TagName was not provided and current commit is not exactly tagged."
    }
}

if ([string]::IsNullOrWhiteSpace($Name)) {
    $Name = $TagName
}

if ([string]::IsNullOrWhiteSpace($Body)) {
    $Body = @"
OpenClaw Launcher release $TagName

Build commit: $(git rev-parse --short HEAD)
"@
}

function Invoke-GiteeApi {
    param(
        [string]$Method,
        [string]$Path,
        [hashtable]$Body = $null
    )

    $uri = "https://gitee.com/api/v5$Path"
    if ($Method -eq "GET" -or $Method -eq "DELETE") {
        $separator = if ($uri.Contains("?")) { "&" } else { "?" }
        $uri = "$uri${separator}access_token=$Token"
        return Invoke-RestMethod -Method $Method -Uri $uri
    }

    $payload = @{}
    if ($Body) {
        foreach ($key in $Body.Keys) {
            $payload[$key] = $Body[$key]
        }
    }
    $payload["access_token"] = $Token
    return Invoke-RestMethod -Method $Method -Uri $uri -Body $payload
}

function Get-ReleaseByTag {
    param([string]$Tag)

    try {
        return Invoke-GiteeApi -Method "GET" -Path "/repos/$Owner/$Repo/releases/tags/$Tag"
    } catch {
        return $null
    }
}

function Publish-Asset {
    param(
        [int]$ReleaseId,
        [string]$AssetPath
    )

    if (-not (Test-Path -LiteralPath $AssetPath)) {
        throw "Asset not found: $AssetPath"
    }

    $resolved = (Resolve-Path -LiteralPath $AssetPath).Path
    $fileName = Split-Path -Leaf $resolved
    $existing = @()

    try {
        $existing = @(Invoke-GiteeApi -Method "GET" -Path "/repos/$Owner/$Repo/releases/$ReleaseId/attach_files")
    } catch {
        $existing = @()
    }

    foreach ($item in $existing) {
        if ($item.name -eq $fileName -or $item.filename -eq $fileName) {
            Invoke-GiteeApi -Method "DELETE" -Path "/repos/$Owner/$Repo/releases/$ReleaseId/attach_files/$($item.id)" | Out-Null
        }
    }

    $url = "https://gitee.com/api/v5/repos/$Owner/$Repo/releases/$ReleaseId/attach_files"
    $curlArgs = @(
        "-sS",
        "-X", "POST",
        "-F", "access_token=$Token",
        "-F", "file=@$resolved",
        $url
    )
    $result = & curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload asset: $fileName"
    }
    Write-Host "Uploaded asset: $fileName"
}

$release = Get-ReleaseByTag -Tag $TagName

if ($release) {
    Write-Host "Updating existing Gitee release: $TagName"
    $release = Invoke-GiteeApi -Method "PATCH" -Path "/repos/$Owner/$Repo/releases/$($release.id)" -Body @{
        name = $Name
        body = $Body
        prerelease = "false"
    }
} else {
    Write-Host "Creating Gitee release: $TagName"
    $release = Invoke-GiteeApi -Method "POST" -Path "/repos/$Owner/$Repo/releases" -Body @{
        tag_name = $TagName
        name = $Name
        body = $Body
        target_commitish = "master"
        prerelease = "false"
    }
}

foreach ($asset in $Assets) {
    Publish-Asset -ReleaseId ([int]$release.id) -AssetPath $asset
}

Write-Host "Gitee release ready: $TagName"
