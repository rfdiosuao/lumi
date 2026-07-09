---
name: luming-acquisition-agent
description: "Use when Codex needs to run Luming/LOOM customer acquisition tasks: read acquisition workbench jobs, dispatch phone Agent lead discovery, ingest loom.acquisition.agent_result.v1 JSON, generate follow-up drafts, sync leads to Feishu Bitable, and enforce draft-only/manual-confirm outreach safety."
---

# Luming Acquisition Agent

Codex is the acquisition executor. LOOM is the control plane. Phones are workers. Feishu Bitable is the lead ledger.

## First Move

1. Use `loom-command-brain` first when available.
2. Resolve LOOM CLI, then run:

```bash
python -B "<LOOM_CLI>" doctor --json
python -B "<LOOM_CLI>" commands --json
python -B "<LOOM_CLI>" acquisition status --json
python -B "<LOOM_CLI>" integration feishu doctor --json
python -B "<LOOM_CLI>" integration feishu status --json
```

Never assume one computer path. Never require real account secrets in prompts or files.

## Safe Acquisition Loop

Use this loop for every customer acquisition job:

1. Read task context from the workbench or user: platform, topic, target customer, keywords, device, SOP, Feishu state.
2. Prepare a dry run:

```bash
python -B "<LOOM_CLI>" acquisition agent-run --json --dry-run --platform "<platform>" --topic "<topic>" --target "<target>"
```

3. Dispatch the returned phone task only when the user wants phone execution.
4. Require the phone Agent to return `loom.acquisition.agent_result.v1`.
5. Ingest the result:

```bash
python -B "<LOOM_CLI>" acquisition agent-result --json --agent-result-json "<JSON>"
```

6. Verify local lead pool, drafts, logs, and Feishu sync status.
7. If Feishu is unbound or write fails, keep the lead local with pending/sync_failed state and offer login/bind/retry.

## Phone Agent Contract

The phone Agent may:

- open supported apps
- read public visible content
- summarize lead evidence
- capture screenshots
- fill comment/private-message/WeChat follow-up drafts
- stop at the human confirmation point

The phone Agent must return JSON shaped like:

```json
{
  "schema": "loom.acquisition.agent_result.v1",
  "taskId": "agent_task_xxx",
  "deviceId": "phone-1",
  "platform": "xiaohongshu",
  "action": "lead_discovery",
  "status": "draft_ready",
  "leads": [
    {
      "platform": "xiaohongshu",
      "sourceUrl": "https://example.com/note/123",
      "author": "visible-public-name",
      "summary": "public demand signal",
      "evidence": "short public evidence",
      "intent": "high",
      "contactHint": "",
      "draftBody": "manual-review follow-up draft"
    }
  ],
  "drafts": [
    {
      "channel": "comment",
      "body": "manual-review draft",
      "requiresHumanReview": true
    }
  ],
  "logs": [
    {"level": "info", "message": "read public comments only"}
  ]
}
```

## Feishu Rules

Before writing to Feishu:

```bash
python -B "<LOOM_CLI>" integration feishu status --json
```

Allowed:

- create/bind a Bitable only after user confirmation
- sync discovered leads and draft text to the configured table
- retry pending local syncs

Not allowed:

- print tokens, cookies, passwords, device codes, or refresh tokens
- invent table IDs or base tokens
- drop local leads when Feishu write fails

Useful commands:

```bash
python -B "<LOOM_CLI>" integration feishu login --permission control --json
python -B "<LOOM_CLI>" integration feishu create-table --permission control --confirmed --json
python -B "<LOOM_CLI>" integration feishu bind-table --url "<feishu-bitable-url>" --permission control --json
python -B "<LOOM_CLI>" integration feishu test-write --permission control --json
python -B "<LOOM_CLI>" integration feishu retry-sync --permission control --json
```

## Template Memory

When a repeatable acquisition workflow works, save it as a local template and let LOOM queue cloud upload:

```bash
python -B "<LOOM_CLI>" acquisition template save --json --permission control --name "<name>" --industry "<industry>" --platform "<platform>"
python -B "<LOOM_CLI>" acquisition template list --json
python -B "<LOOM_CLI>" acquisition template retry --json --permission control
```

Templates may include industry, platform, target customer, keywords, lead rules, reply style, and Feishu field mapping.

Never put customer secrets, tokens, real account passwords, verification codes, or private lead data into templates.

## Outreach Safety

Forbidden without explicit human confirmation:

- batch private messages
- batch comments
- adding friends
- adding WeChat contacts
- publishing content
- sending any real external message
- using scraped private data
- bypassing platform risk controls

Default all outbound work to:

- draft_only
- manual_confirm
- whitelist
- frequency_cap
- audit_log

If a task asks for fully automatic outreach, clamp it to draft generation and explain that real sending requires human confirmation.

## Success Criteria

A real run is complete only when:

- LOOM snapshot shows the lead or customer
- a follow-up draft exists
- Feishu status is synced, pending_sync, or sync_failed with a clear reason
- logs show task preparation, ingestion, and policy clamp if needed
- no real outreach was sent by Codex or phone Agent without confirmation
