param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$CodexPackagePath = "",
    [string]$OutputPath = "",
    [int]$PrerequisiteBudgetMs = 2000,
    [int]$CodexBudgetMs = 500,
    [switch]$ValidateOnly,
    [switch]$Simulate
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Path is required."
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Path not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-PythonExe {
    param([string]$LauncherDir)

    $candidates = @(
        (Join-Path $LauncherDir "python-runtime\python.exe"),
        (Join-Path $LauncherDir ".cache\python-runtime\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    throw "Python interpreter not found. Looked for bundled runtime and PATH python."
}

function Resolve-CodexPackagePath {
    param(
        [string]$Root,
        [string]$LauncherDir,
        [string]$RequestedPath
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        return Resolve-ExistingPath $RequestedPath
    }

    $manifestPath = Join-Path $Root "release-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "release-manifest.json not found: $manifestPath"
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $codexComponent = @($manifest.components | Where-Object {
        $component = $_
        $component.id -eq "codex-desktop"
    }) | Select-Object -First 1
    if (-not $codexComponent) {
        throw "release-manifest.json does not define codex-desktop"
    }

    $packageName = ""
    if ($codexComponent.urls -and $codexComponent.urls.Count -gt 0) {
        $packageName = [System.IO.Path]::GetFileName(([string]$codexComponent.urls[0]).Split("?")[0])
    }
    if ([string]::IsNullOrWhiteSpace($packageName)) {
        $packageName = "codex-0.142.3-win32-x64.tgz"
    }

    $candidates = @(
        (Join-Path $LauncherDir "redist\components\codex-desktop\$packageName"),
        (Join-Path $Root "artifacts\loom-rc\direct-agent-components-20260628\$packageName"),
        (Join-Path $Root "artifacts\task5-validate\$packageName")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $match = Get-ChildItem -LiteralPath (Join-Path $Root "artifacts") -Recurse -File -Filter $packageName -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($match) {
        return $match.FullName
    }

    throw "Unable to resolve a local Codex package. Provide -CodexPackagePath."
}

function ConvertTo-JsonText {
    param([object]$Value)

    return ($Value | ConvertTo-Json -Depth 12)
}

$resolvedRepoRoot = Resolve-ExistingPath $RepoRoot
$launcherDir = Resolve-ExistingPath (Join-Path $resolvedRepoRoot "openclaw_new_launcher")
$pythonExe = Resolve-PythonExe -LauncherDir $launcherDir
$resolvedCodexPackagePath = $null
$codexPackageArg = ""

if (-not $Simulate) {
    $resolvedCodexPackagePath = Resolve-CodexPackagePath -Root $resolvedRepoRoot -LauncherDir $launcherDir -RequestedPath $CodexPackagePath
    $codexPackageArg = $resolvedCodexPackagePath
}

$inlinePython = @'
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time

repo_root = os.path.abspath(sys.argv[1])
launcher_dir = os.path.join(repo_root, "openclaw_new_launcher")
codex_package_path = sys.argv[2]
prerequisite_budget_ms = int(sys.argv[3])
codex_budget_ms = int(sys.argv[4])
validate_only = sys.argv[5].lower() == "true"
simulate = sys.argv[6].lower() == "true"

python_dir = os.path.join(launcher_dir, "python")
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from core.component_installer import ComponentInstaller
from core.component_state import ComponentStateStore
from core.paths import AppPaths
from core.release_manifest import load_release_manifest_file
from services.process import OpenClawProcessService


def _result_template() -> dict:
    return {
        "mode": "simulate" if simulate else ("validate_only" if validate_only else "benchmark"),
        "launcherDir": launcher_dir,
        "codexPackagePath": codex_package_path or None,
        "prerequisiteMs": None,
        "codexDetectMs": None,
        "appxCalls": 0,
        "npmCalls": 0,
        "prerequisiteBudgetMs": prerequisite_budget_ms,
        "codexBudgetMs": codex_budget_ms,
        "prerequisiteBudgetPassed": None,
        "codexBudgetPassed": None,
        "onlineReadiness": {"verdict": "unknown", "detail": ""},
        "completeReadiness": {"verdict": "unknown", "detail": ""},
        "managedCodexVersion": None,
        "exitCode": 0,
        "failures": [],
    }


result = _result_template()
manifest = load_release_manifest_file(os.path.join(repo_root, "release-manifest.json"))
codex_component = next(component for component in manifest.components if component.component_id == "codex-desktop")

if simulate:
    result["prerequisiteMs"] = 0
    result["codexDetectMs"] = 0
    result["prerequisiteBudgetPassed"] = True
    result["codexBudgetPassed"] = True
    result["managedCodexVersion"] = codex_component.version
    result["onlineReadiness"] = {"verdict": "simulated", "detail": "Simulation mode skipped real prerequisite and Codex detection."}
    result["completeReadiness"] = {"verdict": "simulated", "detail": "Simulation mode skipped seed verification and release validation."}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if validate_only:
    result["onlineReadiness"] = {"verdict": "ready", "detail": "Performance harness inputs resolved without running benchmarks."}
    result["completeReadiness"] = {"verdict": "ready", "detail": "Codex package path resolved for release validation."}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="loom-installer-perf-") as temp_dir:
    process_service = OpenClawProcessService(
        AppPaths(temp_dir),
        append_log=lambda _text: None,
        ui_call=lambda *_args: None,
    )

    prerequisite_started = time.perf_counter()
    process_service.diagnose_prerequisites()
    prerequisite_ms = round((time.perf_counter() - prerequisite_started) * 1000)
    result["prerequisiteMs"] = prerequisite_ms
    result["prerequisiteBudgetPassed"] = prerequisite_ms <= prerequisite_budget_ms

    codex_base = os.path.join(temp_dir, "managed-codex")
    install_path = os.path.join(codex_base, codex_component.install_path)
    os.makedirs(install_path, exist_ok=True)
    with tarfile.open(codex_package_path, mode="r:gz") as archive:
        archive.extractall(install_path)

    runner_counts = {"appx": 0, "npm": 0}

    def counting_runner(command: list[str], cwd: str, timeout_ms: int) -> subprocess.CompletedProcess:
        lowered = " ".join(command).lower()
        if "get-appxpackage" in lowered or "appxpackage" in lowered:
            runner_counts["appx"] += 1
        if (
            "npm prefix -g" in lowered
            or "npm bin -g" in lowered
            or "npm root -g" in lowered
            or " npm " in f" {lowered} "
        ):
            runner_counts["npm"] += 1
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, int(timeout_ms / 1000)),
            check=False,
        )

    installer = ComponentInstaller(
        base_path=codex_base,
        state_store=ComponentStateStore(os.path.join(codex_base, "component-state.json")),
        installer_runner=counting_runner,
    )

    detect_started = time.perf_counter()
    state = installer.detect(codex_component, force_external_probe=False)
    codex_detect_ms = round((time.perf_counter() - detect_started) * 1000)

    result["codexDetectMs"] = codex_detect_ms
    result["codexBudgetPassed"] = codex_detect_ms <= codex_budget_ms
    result["appxCalls"] = runner_counts["appx"]
    result["npmCalls"] = runner_counts["npm"]
    result["managedCodexVersion"] = state.version
    result["onlineReadiness"] = {
        "verdict": "ready" if result["prerequisiteBudgetPassed"] else "blocked",
        "detail": f"Quick prerequisite check completed in {prerequisite_ms} ms.",
    }
    result["completeReadiness"] = {
        "verdict": "ready" if result["codexBudgetPassed"] and result["appxCalls"] == 0 and result["npmCalls"] == 0 else "blocked",
        "detail": (
            f"Managed Codex detect completed in {codex_detect_ms} ms with "
            f"{result['appxCalls']} Appx calls and {result['npmCalls']} npm calls."
        ),
    }

    if not result["prerequisiteBudgetPassed"]:
        result["failures"].append(f"prerequisiteMs>{prerequisite_budget_ms}")
    if not result["codexBudgetPassed"]:
        result["failures"].append(f"codexDetectMs>{codex_budget_ms}")
    if result["appxCalls"] != 0:
        result["failures"].append("appxCalls!=0")
    if result["npmCalls"] != 0:
        result["failures"].append("npmCalls!=0")

result["exitCode"] = 1 if result["failures"] else 0
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(result["exitCode"])
'@

$pythonArgs = @(
    "-c",
    $inlinePython,
    $resolvedRepoRoot,
    $codexPackageArg,
    $PrerequisiteBudgetMs,
    $CodexBudgetMs,
    [string]$ValidateOnly.IsPresent,
    [string]$Simulate.IsPresent
)

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pythonExe
$psi.WorkingDirectory = $resolvedRepoRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
$psi.Arguments = ($pythonArgs | ForEach-Object {
    $text = [string]$_
    if ($text -match '\s|"') {
        '"' + ($text -replace '"', '\"') + '"'
    } else {
        $text
    }
}) -join ' '

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
[void]$process.Start()
$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()

if ($process.ExitCode -ne 0 -and [string]::IsNullOrWhiteSpace($stdout)) {
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        throw $stderr.Trim()
    }
    throw "measure-installer-performance helper failed with exit code $($process.ExitCode)"
}

if ([string]::IsNullOrWhiteSpace($stdout)) {
    throw "Performance harness returned no JSON output."
}

$result = $stdout | ConvertFrom-Json

if ($ValidateOnly) {
    $tempOutputRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("loom-task6-validate-" + [guid]::NewGuid().ToString("N"))
    try {
        $validationOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $resolvedRepoRoot "scripts\build-dual-nsis.ps1") `
            -CodexPackagePath $resolvedCodexPackagePath `
            -OutputRoot $tempOutputRoot `
            -ValidateOnly 2>&1
        if ($LASTEXITCODE -ne 0) {
            $result.onlineReadiness = [pscustomobject]@{
                verdict = "blocked"
                detail = (($validationOutput | Out-String).Trim())
            }
            $result.completeReadiness = [pscustomobject]@{
                verdict = "blocked"
                detail = (($validationOutput | Out-String).Trim())
            }
            $result.exitCode = 1
            $result.failures += "dual-nsis-validateonly-failed"
        } else {
            $detail = "build-dual-nsis.ps1 -ValidateOnly passed."
            $result.onlineReadiness = [pscustomobject]@{ verdict = "ready"; detail = $detail }
            $result.completeReadiness = [pscustomobject]@{ verdict = "ready"; detail = $detail }
        }
    } finally {
        if (Test-Path -LiteralPath $tempOutputRoot) {
            Remove-Item -LiteralPath $tempOutputRoot -Recurse -Force
        }
    }
}

$jsonText = ConvertTo-JsonText $result
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $outputParent = Split-Path -Parent $OutputPath
    if (-not [string]::IsNullOrWhiteSpace($outputParent)) {
        New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    }
    Set-Content -LiteralPath $OutputPath -Value $jsonText -Encoding UTF8
}

Write-Host $jsonText

if ($stderr -and -not $ValidateOnly -and -not $Simulate) {
    Write-Verbose $stderr
}

if (-not $Simulate -and $result.exitCode -ne 0) {
    exit ([int]$result.exitCode)
}
