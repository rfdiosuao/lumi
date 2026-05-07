# Bridge Migration Guard

> Purpose: keep the current Python Bridge behavior stable before replacing the
> `http.server` implementation with FastAPI.

## Why This Exists

The launcher is already close to delivery, so the FastAPI migration should not
start by rewriting `python/bridge.py` directly. First we need a small behavior
contract and a repeatable smoke check. After those pass, each endpoint can be
moved to FastAPI without guessing what the old bridge used to return.

Current call chain:

```text
React UI -> Tauri invoke(proxy_request) -> Rust -> HTTP -> Python Bridge
```

Target call chain after migration:

```text
React UI -> Tauri/Rust security gate -> FastAPI Bridge
```

## Migration Rule

Do not change the public response shape of an endpoint during the framework
migration. If a response shape needs to change, do it in a separate product
change after the FastAPI migration is already stable.

## Current Protected Endpoints

These endpoints require a valid local license before Rust/Python should allow
the action:

| Endpoint | Feature |
| --- | --- |
| `POST /api/process/start` | `openclaw` |
| `POST /api/image/generate` | `image` |
| `POST /api/video/generate` | `video` |

The smoke script intentionally does not call these endpoints because it must not
start OpenClaw, spend API credits, or require a customer license.

## Read-Only Smoke Contract

The local smoke script verifies the bridge can start, accepts its runtime token,
rejects missing tokens, and returns valid JSON from low-risk read-only endpoints.

Run it from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-bridge.ps1
```

Checked endpoints:

| Endpoint | Method | Expected shape |
| --- | --- | --- |
| `/api/system/info` | `GET` | `node_path`, `base_path`, `openclaw_version` |
| `/api/process/status` | `GET` | `running`, `pid` |
| `/api/log/get` | `GET` | `log` |
| `/api/license/current` | `GET` | `license` |
| `/api/license/authorized` | `POST` | `authorized` |
| `/api/theme/current` | `GET` | `theme` |
| `/api/skills/list` | `GET` | `skills`, `directories`, `sites` |
| `/api/skills/paths` | `GET` | `directories`, `sites` |

## FastAPI Migration Phases

1. Contract phase
   - Keep `bridge.py` unchanged except for bug fixes.
   - Keep this document and `scripts/smoke-bridge.ps1` passing.

2. Skeleton phase
   - Add `python/api/` routers and Pydantic models.
   - Add FastAPI dependencies, but do not switch the launcher entrypoint yet.

3. Shadow phase
   - Run the old bridge and FastAPI bridge behind a development flag.
   - Compare smoke responses for read-only endpoints.

4. Switch phase
   - Replace the entrypoint only after smoke checks pass.
   - Keep Rust license checks in place for protected endpoints.

5. Cleanup phase
   - Delete the old route chain from `bridge.py`.
   - Update API docs and remove migration-only flags.

## Stop Conditions

Pause the migration if any of these happen:

- Activation cannot complete.
- OpenClaw service startup becomes less reliable.
- Feishu or Weixin binding regresses.
- Packaged Windows portable verification fails.
- The root package layout is no longer `OpenClaw.exe + OpenClawFiles/`.

The goal is not to make the architecture prettier first. The goal is to make it
safe to improve the architecture without breaking delivery.
