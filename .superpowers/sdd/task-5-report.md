# Task 5 Report: Windows Dual NSIS Seed Strategy

## Status

Implemented in `D:\Axiangmu\AUSTART` without running the full frontend/Tauri build.

## Scope

- Added `scripts/build-dual-nsis.ps1`
- Updated `openclaw_new_launcher/python/core/component_installer.py`
- Updated Task 5 contract coverage in:
  - `openclaw_new_launcher/python/tests/test_component_installer.py`
  - `openclaw_new_launcher/python/tests/test_release_scripts_contract.py`

## What Changed

- Added `build-dual-nsis.ps1 -CodexPackagePath <path> -OutputRoot <path> [-ValidateOnly]`.
- The script now:
  - validates launcher version consistency;
  - parses `release-manifest.json` for `codex-desktop`;
  - verifies the provided Codex package size and SHA-256;
  - plans distinct `-online-setup.exe` and `-complete-setup.exe` outputs;
  - builds the online variant before any seed injection;
  - injects the verified Codex seed only under `openclaw_new_launcher/redist/components/codex-desktop` for the complete variant;
  - cleans temporary seed state in `finally`;
  - preserves unrelated existing release artifacts.
- Added a manifest-parse fallback in the script because the current workspace `release-manifest.json` contains malformed description strings; this keeps `-ValidateOnly` usable without editing the manifest.
- Extended `ComponentInstaller` to look for verified local seeds before network download in:
  - `base/redist/components/<id>`
  - `base/_up_/redist/components/<id>`
  - `parent/redist/components/<id>`
- Bad local seeds now emit a warning and fall through to normal URL download.
- No account, token, or runtime-state writing was added.

## RED Evidence

Added failing Task 5 tests first:

- `test_dual_nsis_script_declares_validate_only_and_distinct_outputs`
- `test_dual_nsis_script_parses_manifest_and_validates_codex_seed`
- `test_dual_nsis_script_builds_online_before_seed_injection_and_cleans_up_in_finally`
- `test_dual_nsis_script_preserves_existing_release_outputs`
- `test_verified_seed_in_base_redist_avoids_fetcher`
- `test_verified_seed_in_parent_redist_avoids_fetcher`
- `test_invalid_local_seed_warns_and_falls_back_to_fetcher`

Initial focused RED runs failed because:

- `scripts/build-dual-nsis.ps1` did not exist
- `ComponentInstaller` did not yet search the local verified seed locations

## Verification

Ran only Task 5 related checks:

```powershell
python -m unittest openclaw_new_launcher.python.tests.test_component_installer -v
python -m unittest openclaw_new_launcher.python.tests.test_release_scripts_contract -v
python -m py_compile openclaw_new_launcher\python\core\component_installer.py openclaw_new_launcher\python\tests\test_component_installer.py openclaw_new_launcher\python\tests\test_release_scripts_contract.py
$errors = $null; $tokens = $null; [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'scripts\build-dual-nsis.ps1'), [ref]$tokens, [ref]$errors)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-dual-nsis.ps1 -CodexPackagePath D:\Axiangmu\AUSTART\artifacts\task5-validate\codex-0.142.3-win32-x64.tgz -OutputRoot D:\Axiangmu\AUSTART\artifacts\task5-validate\out -ValidateOnly
git diff --check
```

Results:

- `test_component_installer`: 65 tests passed
- `test_release_scripts_contract`: 15 tests passed
- Python compile check: passed
- PowerShell parser check: passed
- `-ValidateOnly`: passed
- `git diff --check`: passed (Git printed existing LF->CRLF working-tree warnings only)

## Notes

- I intentionally did **not** run `npm run build` or a full NSIS build per the latest instruction.
- For `-ValidateOnly`, I downloaded the verified package to:
  - `D:\Axiangmu\AUSTART\artifacts\task5-validate\codex-0.142.3-win32-x64.tgz`

---

## Task 5 Review Fixes Addendum (2026-07-10)

Addressed the follow-up review items in:

- `D:\Axiangmu\AUSTART\scripts\build-dual-nsis.ps1`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\tests\test_release_scripts_contract.py`

### Review Fixes

- Added contract coverage first for:
  - rejecting unsafe `OutputRoot` values;
  - failing clearly when the target online/complete installer path already exists;
  - keeping `-ValidateOnly` free of output directory creation.
- Updated `build-dual-nsis.ps1` so it now:
  - rejects `OutputRoot` when it resolves exactly to the repo root, `openclaw_new_launcher`, or `release`;
  - allows dedicated child output directories under those locations;
  - checks both planned output installer paths before build work starts;
  - fails with `Installer output already exists: <path>` instead of overwriting;
  - preserves existing release artifacts by removing forced overwrite behavior;
  - keeps `-ValidateOnly` read-only with respect to the output location.

### Verification For Review Fixes

Ran focused checks only:

```powershell
python -m unittest openclaw_new_launcher.python.tests.test_release_scripts_contract
$errors = $null; $tokens = $null; [void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'scripts\build-dual-nsis.ps1'), [ref]$tokens, [ref]$errors)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-dual-nsis.ps1 -CodexPackagePath D:\Axiangmu\AUSTART\artifacts\task5-validate\codex-0.142.3-win32-x64.tgz -OutputRoot D:\Axiangmu\AUSTART\artifacts\task5-validate\validate-only-<guid> -ValidateOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-dual-nsis.ps1 -CodexPackagePath D:\Axiangmu\AUSTART\artifacts\task5-validate\codex-0.142.3-win32-x64.tgz -OutputRoot D:\Axiangmu\AUSTART\artifacts\task5-validate\collision-<guid> -ValidateOnly
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-dual-nsis.ps1 -CodexPackagePath D:\Axiangmu\AUSTART\artifacts\task5-validate\codex-0.142.3-win32-x64.tgz -OutputRoot D:\Axiangmu\AUSTART -ValidateOnly
git diff --check -- scripts/build-dual-nsis.ps1 openclaw_new_launcher/python/tests/test_release_scripts_contract.py
```

Results:

- release script contract tests: passed (`18` tests)
- PowerShell parser check: passed
- `-ValidateOnly` happy-path check: passed and did not create the requested output directory
- existing-output collision check: failed as expected with `Installer output already exists`
- unsafe `OutputRoot` check: failed as expected with `Refusing unsafe OutputRoot`
- focused `git diff --check`: passed aside from existing LF/CRLF warnings
