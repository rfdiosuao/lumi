param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"

function Resolve-PayloadRoot {
    param([string]$InputPath)

    $item = Get-Item -LiteralPath $InputPath
    if (-not $item.PSIsContainer) {
        throw "Smoke verification expects an extracted portable directory, not a zip: $InputPath"
    }

    $openClawFiles = Join-Path $item.FullName "OpenClawFiles"
    if (Test-Path -LiteralPath $openClawFiles) {
        return $openClawFiles
    }
    return $item.FullName
}

function Assert-File {
    param(
        [string]$Root,
        [string]$RelativePath
    )

    $full = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "Missing required file: $RelativePath"
    }
    return $full
}

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Script
    )

    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Script
    Write-Host "OK: $Label" -ForegroundColor Green
}

$payloadRoot = Resolve-PayloadRoot -InputPath $Path
Write-Host "Portable smoke target: $payloadRoot"

Invoke-Checked "Required file layout" {
    Assert-File -Root (Split-Path -Parent $payloadRoot) -RelativePath "OpenClaw.exe" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "node\node.exe" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "start.js" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "node_modules\openclaw\openclaw.mjs" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "_up_\python-runtime\python.exe" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "_up_\python\bridge.py" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "_up_\python\fastapi\__init__.py" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "_up_\python\uvicorn\__init__.py" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "scripts\openclaw-phone-agent.mjs" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "scripts\openclaw-context.mjs" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "data\.openclaw\workspace\AGENTS.md" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "data\.openclaw\workspace\SOUL.md" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "data\.openclaw\workspace\TOOLS.md" | Out-Null
    Assert-File -Root $payloadRoot -RelativePath "data\.openclaw\workspace\CAPABILITIES.md" | Out-Null
}

Invoke-Checked "Bundled Python imports" {
    $pythonExe = Assert-File -Root $payloadRoot -RelativePath "_up_\python-runtime\python.exe"
    $pythonPath = Join-Path $payloadRoot "_up_\python"
    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $pythonPath
        & $pythonExe -c "import fastapi, uvicorn; import bridge; print('python smoke ok')"
        if ($LASTEXITCODE -ne 0) {
            throw "Bundled Python import smoke failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

Invoke-Checked "Bundled Node CLI syntax" {
    $nodeExe = Assert-File -Root $payloadRoot -RelativePath "node\node.exe"
    foreach ($script in @(
        "scripts\openclaw-context.mjs",
        "scripts\openclaw-phone-agent.mjs",
        "scripts\openclaw-phone-secure.mjs",
        "scripts\openclaw-phone-vision.mjs",
        "scripts\openclaw-phone-game.mjs",
        "scripts\openclaw-phone-video.mjs",
        "scripts\openclaw-image-phone.mjs"
    )) {
        $scriptPath = Assert-File -Root $payloadRoot -RelativePath $script
        & $nodeExe --check $scriptPath
        if ($LASTEXITCODE -ne 0) {
            throw "Node syntax smoke failed: $script"
        }
    }
}

Invoke-Checked "Runtime context hard guard" {
    $contextPath = Assert-File -Root $payloadRoot -RelativePath "data\.openclaw\workspace\runtime-context.json"
    $context = Get-Content -LiteralPath $contextPath -Raw | ConvertFrom-Json
    if ($context.phone.baseUrl) {
        throw "runtime-context.json must not expose phone.baseUrl"
    }
    if ($context.phone.endpoint -ne "launcher-cli-wrapper") {
        throw "phone.endpoint must be launcher-cli-wrapper"
    }
    if ($context.capabilities.phoneAgent.controlPolicy -ne "wrapper-only") {
        throw "phoneAgent.controlPolicy must be wrapper-only"
    }
    if ($context.capabilities.phoneAgent.agentCli -ne "npm run phone:agent") {
        throw "phoneAgent.agentCli must be npm run phone:agent"
    }
}

Write-Host "Portable smoke verification passed." -ForegroundColor Green
