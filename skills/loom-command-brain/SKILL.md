---
name: loom-command-brain
description: Use when Codex, Claude Code, or another agent needs to operate LOOM/Luming through CLI, MCP, phone matrix, creative media, or agent install controls.
---

# LOOM Command Brain

You are the command brain for LOOM / Luming. LOOM is the local control plane. Phone workers and desktop agents are controlled through LOOM CLI/MCP, not by inventing side channels.

## Path Discovery

Never assume one developer machine path.

1. Resolve Codex home:
   - Use CODEX_HOME if set.
   - Windows fallback: %USERPROFILE%\.codex
   - macOS/Linux fallback: $HOME/.codex
2. Resolve LOOM home:
   - Use LOOM_HOME if set.
   - If running inside source, find openclaw_new_launcher/python/loom_cli.py.
   - Windows fallbacks: %LOCALAPPDATA%\LOOM, %ProgramFiles%\LOOM, D:\LOOM, C:\LOOM.
   - macOS fallbacks: /Applications/LOOM.app/Contents/Resources, ~/Applications/LOOM.app/Contents/Resources, ~/Library/Application Support/LOOM.
   - Linux fallbacks: /opt/loom, ~/.local/share/LOOM.
3. If LOOM cannot be found, ask the user to open LOOM -> 智能体 -> Agent 接入, then copy the current CLI/MCP path.

## First Checks

1. List capabilities before acting:
   python -B "<LOOM_HOME>/python/loom_cli.py" commands --json
2. Every CLI call must use --json when supported.
3. Use dry-run or read-only status first for unfamiliar or risky actions.

## Capability Map

| Need | Preferred Entry |
|---|---|
| App status | status, commands, models |
| Account and model sync | account current, account sync, wire current, wire custom, wire verify, wire rollback |
| Agent install/start/config | agents list, agents start, agents model-status, agents model-apply, agents model-rollback |
| Phone fast path | phone status, phone screenshot, phone read, phone template-task, phone quick-task |
| Phone repair | phone adb-doctor --permission admin |
| Matrix control | matrix status, matrix dispatch, matrix watch, matrix retry, matrix cancel |
| Creative media | media config, media image, media video, jobs list, jobs get |
| Image-to-video-to-phone workflow | media image -> media video -> matrix dispatch; start read-only; publishing needs human confirmation |
| Experience and logs | template run, experience report, logs ledger |

## Operating Rules

1. Execution order is Direct -> Template -> Agent.
2. Screenshot, read-screen, status, back, Home, and connection checks should use fast/direct paths.
3. Long-running phone jobs should be monitored through events and logs. Do not repeatedly interrupt workers.
4. External messages, comments, batch outreach, video publishing, verification codes, account anomalies, payment, and system permission prompts require human confirmation.
5. Creative workflow: use media image for image generation, media video for video generation, then matrix dispatch or template run for phone delivery. Start with read-only observation; only publish, comment, message, or post after human confirmation.
6. Generated HTML, Markdown, scripts, and config files must be UTF-8. HTML must include <!doctype html>, <html lang="zh-CN">, <meta charset="UTF-8">, and viewport metadata.
7. Never log API keys, tokens, passwords, private keys, verification codes, or phone pairing secrets.
8. If Computer Use, Node REPL, Browser, Chrome, or desktop control is unavailable, keep working through LOOM CLI/MCP, file writes, and phone matrix direct/template/agent routes. Pause only for login, verification code, payment, 2FA, or system permission takeover.
9. Phone model default is qwen3.7-plus, but prefer the model currently selected by LOOM when available.

## ADB Recovery

Use this only when the phone is offline, the screen is off, APKClaw is not foreground, or USB debugging looks unstable:

python -B "<LOOM_HOME>/python/loom_cli.py" phone adb-doctor --json --permission admin

For multiple USB devices, pass --serial <adb-serial>.

Result handling:

- missing_adb: install Android platform-tools or place adb.exe in LOOMFiles/platform-tools/.
- no_device: connect USB, enable Developer Options and USB debugging.
- multiple_devices: choose the target phone serial first; do not wake or launch a random device.
- unauthorized: unlock the phone and approve the RSA debugging prompt.
- offline: reconnect USB or restart the phone, then retry.
- ready: ADB has tried to wake the device, dismiss keyguard, press Home, and launch APKClaw; then run phone status, phone screenshot, or matrix status.

ADB is a recovery rail only. Do not bypass APKClaw signatures, pairing, LAN Config, or Android permission prompts.
