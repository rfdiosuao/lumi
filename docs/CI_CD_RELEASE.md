# CI/CD Release Notes

This repository uses Gitee Go for cloud CI and release artifacts.

## What Gitee Go Builds

The Gitee Go cloud runner validates the repository, installs an isolated Node.js 20 runtime, builds the React/Tauri frontend, compiles Python files, and publishes `ci_artifacts` as Gitee artifacts.

The cloud artifact is not the full customer-facing Windows portable package. The full offline package contains a Windows Tauri executable, bundled Node.js, OpenClaw, and an embedded Python runtime. That package must be produced on a Windows builder or on the local packaging machine.

## Automatic Triggers

The pipeline runs on:

- Pushes to `master`
- Tags matching `v*`

## Full Gitee Release Upload

To publish the locally built Windows portable zip to Gitee Releases, create a personal access token in Gitee and set it as an environment variable:

```powershell
$env:GITEE_ACCESS_TOKEN = "your-token"
```

Then run:

```powershell
.\scripts\publish-gitee-release.ps1 `
  -TagName "v2.0.1-storyboard-2026.05.06" `
  -Name "OpenClaw Portable v2.0.1" `
  -Assets @(
    "D:\Axiangmu\AUSTART\release\OpenClaw-Portable-v2.0.1-2026.05.06.zip",
    "D:\Axiangmu\AUSTART\release\OpenClaw-Portable-v2.0.1-2026.05.06.zip.sha256.txt"
  )
```

Do not commit tokens, generated release packages, license databases, private keys, or runtime state files.
