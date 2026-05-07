# Bridge Migration Guard

> Purpose: keep the current Python Bridge behavior stable before replacing the
> `http.server` implementation with FastAPI.

## Why This Exists

The launcher is already close to delivery, so the FastAPI migration should not
start by rewriting `python/bridge.py` directly. First we need a small behavior
contract and a repeatable smoke check. After those pass, each endpoint can be
moved to FastAPI without guessing what the old bridge used to return.

Current call chain after phase 1:

```text
React UI -> Tauri invoke(proxy_request) -> Rust -> HTTP -> FastAPI Bridge
```

The FastAPI service currently delegates endpoint behavior to the legacy route
logic so the response contract stays stable during the migration.

The first low-risk endpoints have been moved to native FastAPI routes:

| Endpoint | Status |
| --- | --- |
| `/api/system/info` | FastAPI native |
| `/api/process/status` | FastAPI native |
| `/api/log/get` | FastAPI native |
| `/api/log/clear` | FastAPI native |
| `/api/license/current` | FastAPI native |
| `/api/license/authorized` | FastAPI native |
| `/api/theme/current` | FastAPI native |
| `/api/theme/by_merchant` | FastAPI native |
| `/api/theme/list` | FastAPI native |
| `/api/config/read` | FastAPI native |
| `/api/config/write` | FastAPI native |
| `/api/auth/profiles` | FastAPI native |
| `/api/diagnostics/run` | FastAPI native |
| `/api/skills/list` | FastAPI native |
| `/api/skills/paths` | FastAPI native |

All other endpoints still go through the legacy catch-all route until they are
migrated and verified one group at a time.

Target call chain after the full migration:

```text
React UI -> Tauri/Rust security gate -> FastAPI routers
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

To force the FastAPI implementation during local migration testing, run:

```powershell
python -m pip install -r openclaw_new_launcher\python\requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\smoke-bridge.ps1 -RequireFastApi
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
   - Add FastAPI dependencies.
   - Switch the HTTP service layer to FastAPI.
   - Keep endpoint behavior delegated to the legacy route logic.

3. Shadow phase
   - Add `python/api/` routers and Pydantic models.
   - Move read-only endpoints first.
   - Compare smoke responses before and after each endpoint move.

4. Switch phase
   - Move protected and write endpoints only after read-only routes are stable.
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
