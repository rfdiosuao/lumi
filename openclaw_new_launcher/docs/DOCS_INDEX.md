# Launcher Documentation Index

This page is the recommended entry point for launcher documentation. Some older
documents are kept for historical context, but they should not be treated as the
source of truth when they conflict with code or the current guard documents.

## Current Operational Docs

| Document | Use for |
| --- | --- |
| `BRIDGE_MIGRATION_GUARD.md` | Bridge smoke checks and FastAPI migration guardrails |
| `RUNTIME_PATHS.md` | Windows and Mac runtime path rules |
| `RELEASE_CHECKLIST.md` | Manual release verification |
| `CUSTOMER_GUIDE.md` | Customer-facing quick guide |
| `SUPPORT_TROUBLESHOOTING.md` | Support and troubleshooting |
| `DELIVERY_ACCEPTANCE.md` | Delivery acceptance checklist |
| `AD_VIDEO_WORKBENCH_GUIDE.md` | Customer-facing guide for the AI ad video workflow |
| `MAC_BUILD_NOTES.md` | Mac build notes |
| `MAC_MIGRATION_CHECKLIST.md` | Mac migration acceptance checklist |

## Product And Extension Docs

| Document | Use for |
| --- | --- |
| `PRODUCT_ROADMAP.md` | Product planning and priorities |
| `MODULE_EXTENSION_GUIDE.md` | Adding launcher modules and pages |
| `UI_CUSTOMIZATION_DESIGN.md` | Brand and UI customization design |
| `MODULE_BOUNDARIES.md` | Module responsibility boundaries |

## Historical Or Planning Docs

These documents are useful for background, but can be stale. Prefer current code
and the operational docs above when making implementation decisions.

| Document | Status |
| --- | --- |
| `API_SPEC.md` | Historical full API planning spec |
| `api-reference.md` | Historical API reference from an earlier code snapshot |
| `ARCHITECTURE.md` | Historical architecture overview |
| `ARCHITECTURE_REVIEW_2026-05-05.md` | Review notes from the May 2026 stabilization period |
| `AGENT_TASKS.md` | Agent orchestration notes |
| `GITEE_SETUP.md` | Gitee setup notes |
| `GIT_CICD_PLAN.md` | CI/CD planning notes |

## Bridge Migration Rule

For FastAPI migration work, start here:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-bridge.ps1
```

Then read `BRIDGE_MIGRATION_GUARD.md`. Do not replace `python/bridge.py` until
the smoke contract is passing and the migration has a clear rollback path.
