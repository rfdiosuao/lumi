# Launcher Documentation Index

This page is the recommended entry point for launcher documentation. Removed
historical rewrite drafts and obsolete API snapshots should not be recreated as
source-of-truth documents; prefer the current code and the docs listed here.

## Current Operational Docs

| Document | Use for |
| --- | --- |
| `PROJECT_STRUCTURE.md` | Canonical workspace, current directory map, and cleanup rules |
| `BRIDGE_MIGRATION_GUARD.md` | Bridge smoke checks and FastAPI migration guardrails |
| `SESSION_HANDOFF.md` | Current handoff notes for the next Codex/GPT session |
| `task.md` | Current executable task list and remaining product gaps |
| `RUNTIME_PATHS.md` | Windows and Mac runtime path rules |
| `RELEASE_CHECKLIST.md` | Manual release verification |
| `CUSTOMER_GUIDE.md` | Customer-facing quick guide |
| `SUPPORT_TROUBLESHOOTING.md` | Support and troubleshooting |
| `DELIVERY_ACCEPTANCE.md` | Delivery acceptance checklist |
| `广告视频使用文档.md` | Customer-facing guide for the AI ad video workflow |
| `MAC_BUILD_NOTES.md` | Mac build notes |
| `MAC_MIGRATION_CHECKLIST.md` | Mac migration acceptance checklist |

## Product And Extension Docs

| Document | Use for |
| --- | --- |
| `PRODUCT_ROADMAP.md` | Product planning and priorities |
| `LUMI_AGENT_PLATFORM_ROADMAP.md` | Long-term Agent platform roadmap |
| `APKCLAW_PHONE_CONTROL_ROADMAP.md` | Phone-side APKClaw integration, AI cursor, and multimodal control roadmap |
| `PHONE_CONNECTOR_API_CONTRACT.md` | MVP API contract for Lumi to connect APKClaw |
| `MODULE_EXTENSION_GUIDE.md` | Adding launcher modules and pages |
| `UI_CUSTOMIZATION_DESIGN.md` | Brand and UI customization design |
| `LUMI_PERSONAL_UI_DESIGN.md` | Personal Lumi edition UI direction and acceptance notes |
| `MODULE_BOUNDARIES.md` | Module responsibility boundaries |

## Repo And CI Notes

| Document | Status |
| --- | --- |
| `GITEE_SETUP.md` | Gitee setup notes |
| `GIT_CICD_PLAN.md` | CI/CD planning notes |

## Bridge Migration Rule

For FastAPI migration work, start here:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-bridge.ps1
```

Then read `BRIDGE_MIGRATION_GUARD.md`. Do not replace `python/bridge.py` until
the smoke contract is passing and the migration has a clear rollback path.
