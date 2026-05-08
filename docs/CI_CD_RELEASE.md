# CI/CD Release Notes

This repository supports GitHub Actions for CI and GitHub Releases. Gitee Go can
still be used for domestic mirroring, but GitHub is the primary cloud CI/CD path
for this checkout.

## GitHub Actions

Workflows:

- `.github/workflows/ci.yml`: runs on pushes and pull requests to `master`.
- `.github/workflows/release.yml`: runs on tags matching `v*` or manual dispatch.

The release workflow validates source text, installs Node.js 20, builds the React
frontend, checks Rust, builds Tauri bundles, uploads CI artifacts, and publishes a
GitHub Release for the tag.

The cloud artifact is not the full customer-facing Windows portable package. The
full offline package contains a Windows Tauri executable, bundled Node.js,
OpenClaw, bundled bot plugins, and an embedded Python runtime. That package must
be produced on a Windows builder or on the local packaging machine with an
existing seed package.

## Automatic GitHub Triggers

CI runs on:

- Pushes to `master`
- Pull requests to `master`

Release publishing runs on:

- Tags matching `v*`
- Manual `workflow_dispatch` with a tag name

## Local Full Portable Release

Build the full portable zip locally:

```powershell
cd D:\Axiangmu\AUSTART
powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1 `
  -Version 2.0.1 `
  -PackageName OpenClaw-Portable-v2.0.1-YYYY.MM.DD
```

Verify the zip:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1 `
  -Path release\OpenClaw-Portable-v2.0.1-YYYY.MM.DD.zip
```

Create or update a GitHub Release with local portable assets:

```powershell
gh release create v2.0.1-YYYY.MM.DD `
  release\OpenClaw-Portable-v2.0.1-YYYY.MM.DD.zip `
  release\OpenClaw-Portable-v2.0.1-YYYY.MM.DD.zip.sha256.txt `
  --repo rfdiosuao/lumi `
  --title "Lumi / OpenClaw v2.0.1 YYYY.MM.DD" `
  --generate-notes
```

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
