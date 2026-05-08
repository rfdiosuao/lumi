# Lumi / OpenClaw Portable Launcher

Lumi is a merchant-facing portable desktop launcher for OpenClaw. It packages the launcher UI, Python bridge, offline OpenClaw runtime, license activation, AI image/video tools, ad storyboard workflow, and bot binding utilities into a customer-ready desktop experience.

Main version: `v2.0.1`

## Repository Layout

```text
.
├─ openclaw_new_launcher/      # Main Tauri + React + Python Bridge launcher
├─ license_server/             # Online license server
├─ scripts/                    # Repo-level verification, packaging, release scripts
├─ docs/                       # Repo-level branding, CI/CD, packaging docs
├─ data/                       # Local runtime state; state files are ignored
└─ release/                    # Local build outputs, not committed
```

Canonical repository root: `D:\Axiangmu\AUSTART`.

Do not use `D:\Axiangmu\U盘启动器` as the source workspace; it is only suitable for temporary package testing or historical portable-build output. See `openclaw_new_launcher/docs/PROJECT_STRUCTURE.md` for the current directory map.

## Development

Recommended environment:

- Windows 10/11
- Node.js 20+
- Rust stable
- Python 3.11+

```powershell
cd openclaw_new_launcher
npm ci
npm run build
npm run tauri dev
```

Run local checks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1
```

## Windows Portable Package

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1 -Version 2.0.1 -PackageName OpenClaw-Portable-v2.0.1-YYYY.MM.DD
```

The final customer package should contain only:

- `OpenClaw.exe`
- `OpenClawFiles/`

It must not include license files, install IDs, API keys, user bot bindings, build caches, or historical release artifacts.

## macOS Migration

Read these documents before building on macOS:

- `openclaw_new_launcher/docs/MAC_BUILD_NOTES.md`
- `openclaw_new_launcher/docs/MAC_MIGRATION_CHECKLIST.md`
- `openclaw_new_launcher/docs/RUNTIME_PATHS.md`

Basic macOS workflow:

```bash
cd openclaw_new_launcher
npm ci
npm run build
npm run tauri dev
npm run tauri build -- --bundles app,dmg
```

Do not reuse Windows `node_modules`, `src-tauri/target`, Windows Node runtime, or `.exe` files on macOS.

## Security Rules

Never commit or ship:

- License server private keys, backend tokens, database files
- `data/license.json`
- `data/install_id.txt`
- Customer API keys
- Customer WeChat/Feishu bot cache
- `node_modules/`
- `dist/`
- `src-tauri/target/`
- `release/`
