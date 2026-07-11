import { APP_DISPLAY_NAME } from '../../version';

export const MCP_CONFIG_PATH = '.mcp.json';
export const MCP_SERVER_PATH = '${LOOM_CLI_DIR}/loom_mcp.py';
export const LOOM_COMMAND_BRAIN_SKILL_PATH = '${CODEX_HOME}/skills/loom-command-brain/SKILL.md';
export const LOOM_COMMAND_BRAIN_WORKFLOWS_PATH = '${CODEX_HOME}/skills/loom-command-brain/references/WORKFLOWS.md';
export const LUMING_ACQUISITION_SKILL_PATH = '${CODEX_HOME}/skills/luming-acquisition-agent/SKILL.md';
export const LOOM_COMMAND_BRAIN_SKILL_URLS = [
  'https://gitee.com/rfdiosuao/lumi/raw/master/skills/loom-command-brain/SKILL.md',
  'https://api-cn.heang.top/loom-release-channel/skills/loom-command-brain/SKILL.md',
  'https://raw.githubusercontent.com/rfdiosuao/loom-release-channel/main/skills/loom-command-brain/SKILL.md',
  '/skills/loom-command-brain/SKILL.md',
];
export const LOOM_COMMAND_BRAIN_WORKFLOWS_URLS = [
  'https://gitee.com/rfdiosuao/lumi/raw/master/skills/loom-command-brain/references/WORKFLOWS.md',
  'https://api-cn.heang.top/loom-release-channel/skills/loom-command-brain/references/WORKFLOWS.md',
  'https://raw.githubusercontent.com/rfdiosuao/loom-release-channel/main/skills/loom-command-brain/references/WORKFLOWS.md',
  '/skills/loom-command-brain/references/WORKFLOWS.md',
];
export const LUMING_ACQUISITION_SKILL_URLS = [
  'https://gitee.com/rfdiosuao/lumi/raw/master/skills/luming-acquisition-agent/SKILL.md',
  'https://api-cn.heang.top/loom-release-channel/skills/luming-acquisition-agent/SKILL.md',
  'https://raw.githubusercontent.com/rfdiosuao/loom-release-channel/main/skills/luming-acquisition-agent/SKILL.md',
  '/skills/luming-acquisition-agent/SKILL.md',
];

export const CLI_SMOKE = 'python -B "${LOOM_CLI}" doctor --json';
export const MCP_SMOKE = 'python -B "${LOOM_CLI_DIR}/loom_mcp.py"';

const CODEX_CONFIG = `# Codex user config: config.toml under CODEX_HOME.
# Do not paste the real API key here. LOOM injects it through env.
model_provider = "heang"
model = "glm-5.2-coding"

[model_providers.heang]
name = "heang"
base_url = "https://api-cn.heang.top/v1"
env_key = "LOOM_CODEX_API_KEY"
wire_api = "chat"
`;

const CONTROL_PROMPT = `You are the ${APP_DISPLAY_NAME} / LOOM command brain.
Use LOOM CLI/MCP first. Do not only chat.
Discover paths instead of assuming one computer:
- Codex home: CODEX_HOME env first; otherwise Windows %USERPROFILE%\\.codex; macOS/Linux $HOME/.codex.
- LOOM CLI: LOOM_CLI env first; otherwise find _up_/python/loom_cli.py, python/loom_cli.py, or openclaw_new_launcher/python/loom_cli.py in common install/source roots. Run doctor --json before choosing npm root.
- Skill file: <CodexHome>/skills/loom-command-brain/SKILL.md.
If Computer Use, Node REPL, Browser, Chrome, or desktop control is unavailable, keep working through LOOM CLI/MCP, file writes, and phone matrix direct/template/agent routes.
For phone work, choose the narrowest surface: loom_cli.py for control-plane work, npm run phone:* helpers for APKClaw Agent, vision, recording, images, fleet, game/canvas, publishing relay, and demos.
For creative work, use LOOM CLI/MCP: generate images with media image, generate videos with media video, then dispatch the phone/matrix step in read-only mode first. Full publishing or external posting requires explicit human confirmation.
Generated HTML/Markdown/scripts/config must be UTF-8. HTML must include <!doctype html>, <html lang="zh-CN">, <meta charset="UTF-8">, and viewport metadata.
Never log API keys, tokens, passwords, private keys, verification codes, or phone pairing secrets.
For acquisition, lead pool, customer pool, Feishu Bitable, phone Agent follow-up, comments, private messages, or WeChat follow-up tasks, read luming-acquisition-agent after loom-command-brain and enforce draft-only/manual-confirm policy.
Phone default model is qwen3.7-plus unless LOOM returns another selected available model.`;

const LOOM_COMMAND_BRAIN_SKILL_MARKDOWN = String.raw`---
name: loom-command-brain
description: "Use when Codex, Claude Code, or another agent needs to operate 麓鸣AI矩阵获客工作台 (LOOM/Luming) through CLI or MCP: inspect capabilities, configure models, dispatch or monitor phone workers, read screenshots/logs, run phone templates, capture phone video, use phone vision/media/publish helpers, recover ADB/phone connection issues, or turn repeated phone work into reusable templates."
---

# LOOM Command Brain

Use LOOM as the local control plane. Codex is the Command Brain; LOOM is the Matrix Control Plane; each connected APKClaw phone is a Phone Worker.

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
3. Resolve LOOM npm root:
   - Do not require package.json and python/loom_cli.py to live together.
   - Packaged Windows installs may use _up_/python for CLI and LOOMFiles for npm/package.json.
   - Run loom_cli.py doctor --json first and use data.paths.npmRoot, data.paths.scriptsRoot, data.paths.pythonExe, and data.scripts.

## First Move

Run doctor, then the capability catalog before taking action:

python -B "<LOOM_CLI>" doctor --json
python -B "<LOOM_CLI>" commands --json

Prefer MCP tools when available. Prefer CLI when you need deterministic JSON, dry-runs, or local subprocess verification. Every CLI command must include --json; use --dry-run before destructive or unfamiliar actions.

## Capability Map

- System: status, doctor, commands, models
- Account/model wire: account current, account sync, wire current, wire custom, wire verify, wire rollback
- Agents: agents list, agents start, agents model-status, agents model-apply, agents model-rollback
- Single phone via loom_cli.py: phone status, phone screenshot, phone read, phone events-start, phone events-status, phone events-stop, phone template-task, phone quick-task
- Phone npm helpers from doctor.data.paths.npmRoot: phone:agent, phone:vision, phone:video, phone:image, phone:image:edit, phone:fleet, phone:game, phone:publish, phone:relay, phone:relay:check, phone:relay:smoke, phone:demo:shopping, phone:demo:read, phone:demo:game
- LOOM phone npm aliases: loom:phone, loom:phone:fleet, loom:phone:vision, loom:phone:video, loom:phone:publish
- Phone recovery: phone adb-doctor with --permission admin
- Matrix: matrix status, matrix dispatch, matrix watch, matrix retry, matrix cancel
- Media config/generation: media config, media save-image, media save-video, media test-image, media test-video, media image, media video
- Templates and experience: template run, experience report, logs ledger

## Operating Rules

1. Use Direct -> Template -> Agent. Screenshots, status checks, Back, Home, and read-screen should not call a deep model.
2. During a running phone task, do not repeatedly interrupt the Phone Worker. Watch events and logs instead: matrix watch, jobs get, logs ledger.
3. For correction, inspect first: phone screenshot or phone read; then decide retry, cancel, or dispatch a narrower task.
4. For multi-phone work, dispatch once, then supervise by events. Codex should do macro-control, not micromanage every tap.
5. For outbound messages, comments, private messages, publishing, batch reach-out, account changes, or paid actions, require explicit user confirmation.
6. Never print or store raw API keys, tokens, passwords, launcher secrets, or phone tokens.
7. For npm run phone:* commands, work from doctor.data.paths.npmRoot, always add --json, and prefer saved launcher phone config. Pass --phone-url / --phone-token only for explicit debugging.
8. Phone screen recording requires clear user intent and may show an Android MediaProjection consent prompt. doctor reports this as a system prompt; do not claim it can always be bypassed.
9. Generated HTML, Markdown, scripts, and config files must be UTF-8. HTML files must include <!doctype html>, <html lang="zh-CN">, <meta charset="UTF-8">, and a viewport meta tag.
10. If Computer Use, Node REPL, Browser, Chrome, or desktop automation tools are unavailable, do not stop the task. Continue through LOOM CLI/MCP, local file edits, direct phone/matrix commands, phone npm helpers, and concise manual handoff only for login, captcha, payment, 2FA, or OS permission prompts.

## Phone CLI Surface

There are two phone command layers:

- python -B "<LOOM_CLI>" ... --json: LOOM control-plane commands, best for status, Matrix, templates, logs, and ADB recovery.
- npm run phone:* -- ... --json from doctor.data.paths.npmRoot: bundled OpenClaw helpers, best for APKClaw Agent, low-level vision, recording, image upload/generation, multi-device fan-out, game/canvas fallback, and publish relay work.

Use the capability catalog first, then choose the narrowest layer.

| Need | Preferred command |
| --- | --- |
| Environment self-check | python -B "<LOOM_CLI>" doctor --json |
| Current phone health | python -B "<LOOM_CLI>" phone status --json |
| One screenshot | python -B "<LOOM_CLI>" phone screenshot --json |
| Read current screen | python -B "<LOOM_CLI>" phone read --prompt "Read the current screen." --json |
| Run a bounded task | npm run phone:agent -- run --prompt "..." --mode safe --json |
| Submit/watch/cancel async Agent work | npm run phone:agent -- submit/status/events/cancel --json |
| Runtime speed/queue metrics | npm run phone:agent -- metrics --json |
| Signed phone event stream | npm run phone:agent -- events-sync --json or loom_cli.py phone events-start/status/stop --json |
| Fast screen tree or profile read | npm run phone:vision -- read --json |
| Vision frame with grid | npm run phone:vision -- frame --out ./data/phone-frames/frame.jpg --json |
| Explicit guarded visual action | npm run phone:vision -- action --force-action --action-body-file ./action.json --json; prefer observe_fast selector ref with click_ref, then click_text/click_node, all through action_fast |
| Start/stop/download phone recording | npm run phone:video -- start/stop/download --json |
| Generate or upload image to phone | npm run phone:image -- --prompt "..." --json or npm run phone:image -- --image ./file.png --json |
| Edit image and upload | npm run phone:image:edit -- --reference-image ./input.png --prompt "..." --json |
| Run one task on several APKClaw devices | npm run phone:fleet -- run --target all --prompt "..." --mode observe --concurrency 2 --json |
| Game/canvas visual loop | npm run phone:game -- run --goal "..." --json |
| Direct or reverse platform publish | npm run phone:publish -- --platform xiaohongshu --title "..." --body "..." --max-rounds 60 --json |
| Publish relay server/check/smoke | npm run phone:relay -- ..., npm run phone:relay:check -- ..., npm run phone:relay:smoke -- ... |
| Demo wrappers | npm run phone:demo:shopping -- --query "..." --json; npm run phone:demo:read -- --json; npm run phone:demo:game -- --goal "..." --json |
| LOOM aliases | npm run loom:phone -- ...; npm run loom:phone:vision -- ...; npm run loom:phone:video -- ...; npm run loom:phone:fleet -- ...; npm run loom:phone:publish -- ... |

Common npm helper options: --device-id, --phone-url, --phone-token, --json. Keep raw tokens out of logs and files.

## Extra Reference

For full recipes and command examples, read references/WORKFLOWS.md in this skill directory. If the file is missing, continue with the Phone CLI Surface table above.
`;

const LOOM_COMMAND_BRAIN_WORKFLOWS_MARKDOWN = String.raw`# LOOM Command Brain Workflows

## Common CLI Prefix

python -B "<LOOM_CLI>"

Always add --json. Use --dry-run before unfamiliar control/admin commands.

For bundled phone helpers, run from doctor.data.paths.npmRoot:

cd "<doctor.data.paths.npmRoot>"

Always add --json. Prefer saved launcher phone config; use --phone-url / --phone-token only for explicit debugging and never print raw tokens.

## Phone Helper Catalog

- Agent runtime: npm run phone:agent -- run/submit/status/events/cancel/metrics/events-sync --json
- Vision: npm run phone:vision -- status/frame/read/action --json; when observe_fast returns a selector ref, prefer actionBody {"action":"click_ref","ref":"...","targetLabel":"..."} through action_fast
- Recording: npm run phone:video -- status/start/stop/list/download --json
- Image transfer/generation: npm run phone:image -- --prompt "..." --json or npm run phone:image -- --image ./file.png --json
- Image editing: npm run phone:image:edit -- --reference-image ./input.png --prompt "..." --json
- Multi-device helper: npm run phone:fleet -- list/status/run --json
- Game/canvas fallback: npm run phone:game -- run --goal "..." --json
- Publishing helper: npm run phone:publish -- --platform xiaohongshu --title "..." --body "..." --max-rounds 60 --json
- Publish relay: npm run phone:relay -- ..., npm run phone:relay:check -- ..., npm run phone:relay:smoke -- ...
- Demos: npm run phone:demo:shopping -- --query "..." --json; npm run phone:demo:read -- --json; npm run phone:demo:game -- --goal "..." --json
- LOOM aliases: npm run loom:phone -- ...; npm run loom:phone:vision -- ...; npm run loom:phone:video -- ...; npm run loom:phone:fleet -- ...; npm run loom:phone:publish -- ...

## Matrix Dispatch Recipe

1. doctor --json
2. commands --json
3. matrix status --json
4. matrix dispatch --prompt "<task>" --device "<deviceId>" --json --permission control
5. matrix watch --campaign "<campaignId>" --json
6. logs ledger --limit 20 --json
7. experience report --json

If an action involves publishing, private messaging, comments, batch reach-out, or account-affecting work, require user confirmation before dispatch.

## Phone Recording Recipe

Use this when the user wants a proof video, failure replay, demo capture, or task review:

1. Confirm the purpose of recording.
2. npm run phone:video -- status --json
3. npm run phone:video -- start --max-seconds 180 --filename "<name>.mp4" --json
4. Tell the user to approve the Android screen-capture consent prompt if it appears.
5. Run the phone task or Matrix dispatch.
6. npm run phone:video -- stop --json
7. npm run phone:video -- download --latest --out-dir ./data/phone-videos --json
8. Report the local MP4 path.

## Phone Vision and Game Recipe

Use this when screen text is insufficient, a canvas/game has no accessibility tree, or a single visual action needs proof:

1. npm run phone:vision -- status --json
2. npm run phone:vision -- frame --out ./data/phone-frames/frame.jpg --json
3. For read-only analysis, npm run phone:vision -- read --json
4. For game/canvas loop, npm run phone:game -- run --goal "<safe goal>" --json
5. For an explicit fallback action, write an action JSON file with action, gridCell, targetLabel, and reason, then run npm run phone:vision -- action --force-action --action-body-file ./action.json --json

## Phone Media and Publish Recipe

Use media helpers before publishing so APKClaw receives files through the signed channel:

1. Generate/upload image: npm run phone:image -- --prompt "..." --json or npm run phone:image -- --image ./file.png --json
2. Edit/upload image: npm run phone:image:edit -- --reference-image ./input.png --prompt "..." --json
3. Publish direct: npm run phone:publish -- --platform xiaohongshu --title "..." --body "..." --image ./a.png --max-rounds 60 --json
4. Publish reverse packet: npm run phone:publish -- --transport reverse --platform douyin --packet-out ./publish-packet.json --json
5. Publishing, comments, private messages, batch reach-out, account changes, and paid actions require explicit user confirmation.

## Multi-Phone Helper Recipe

Use phone:fleet when the task is the same across several configured APKClaw devices and Matrix is heavier than needed:

1. npm run phone:fleet -- list --json
2. npm run phone:fleet -- status --target all --json
3. npm run phone:fleet -- run --target all --prompt "<bounded task>" --mode observe --concurrency 2 --json
4. For long or retry-heavy work, switch to Matrix dispatch/watch instead of repeatedly running fleet commands.
`;

const LUMING_ACQUISITION_SKILL_MARKDOWN = String.raw`---
name: luming-acquisition-agent
description: "Use when Codex needs to run Luming/LOOM customer acquisition tasks: read acquisition workbench jobs, dispatch phone Agent lead discovery, ingest loom.acquisition.agent_result.v1 JSON, generate follow-up drafts, sync leads to Feishu Bitable, and enforce draft-only/manual-confirm outreach safety."
---

# Luming Acquisition Agent

Codex is the acquisition executor. LOOM is the control plane. Phones are workers. Feishu Bitable is the lead ledger.

## First Move

1. Use loom-command-brain first when available.
2. Resolve LOOM CLI, then run:

\`\`\`bash
python -B "<LOOM_CLI>" doctor --json
python -B "<LOOM_CLI>" commands --json
python -B "<LOOM_CLI>" acquisition status --json
python -B "<LOOM_CLI>" integration feishu doctor --json
python -B "<LOOM_CLI>" integration feishu status --json
\`\`\`

Never assume one computer path. Never require real account secrets in prompts or files.

## Safe Acquisition Loop

1. Read task context from the workbench or user: platform, topic, target customer, keywords, device, SOP, Feishu state.
2. Prepare a dry run:

\`\`\`bash
python -B "<LOOM_CLI>" acquisition agent-run --json --dry-run --platform "<platform>" --topic "<topic>" --target "<target>"
\`\`\`

3. Dispatch the returned phone task only when the user wants phone execution.
4. Require the phone Agent to return loom.acquisition.agent_result.v1.
5. Ingest the result:

\`\`\`bash
python -B "<LOOM_CLI>" acquisition agent-result --json --agent-result-json "<JSON>"
\`\`\`

6. Verify local lead pool, drafts, logs, and Feishu sync status.
7. If Feishu is unbound or write fails, keep the lead local with pending/sync_failed state and offer login/bind/retry.

## Phone Agent Contract

The phone Agent may read public visible content, summarize lead evidence, capture screenshots, fill drafts, and stop at human confirmation.

The phone Agent must return JSON shaped like:

\`\`\`json
{
  "schema": "loom.acquisition.agent_result.v1",
  "taskId": "agent_task_xxx",
  "deviceId": "phone-1",
  "platform": "xiaohongshu",
  "action": "lead_discovery",
  "status": "draft_ready",
  "leads": [{"platform": "xiaohongshu", "summary": "public demand signal", "evidence": "short public evidence", "draftBody": "manual-review follow-up draft"}],
  "drafts": [{"channel": "comment", "body": "manual-review draft", "requiresHumanReview": true}],
  "logs": [{"level": "info", "message": "read public comments only"}]
}
\`\`\`

## Feishu Rules

Before writing to Feishu:

\`\`\`bash
python -B "<LOOM_CLI>" integration feishu status --json
\`\`\`

Allowed: create/bind a Bitable after user confirmation, sync discovered leads and draft text, retry pending local syncs.

Not allowed: print tokens, invent table IDs, or drop local leads when Feishu write fails.

## Template Memory

When a repeatable acquisition workflow works, save it as a local template and let LOOM queue cloud upload:

\`\`\`bash
python -B "<LOOM_CLI>" acquisition template save --json --permission control --name "<name>" --industry "<industry>" --platform "<platform>"
python -B "<LOOM_CLI>" acquisition template list --json
python -B "<LOOM_CLI>" acquisition template retry --json --permission control
\`\`\`

Never put customer secrets, tokens, real account passwords, or private lead data into templates.

## Outreach Safety

Forbidden without explicit human confirmation: batch private messages, batch comments, adding friends, adding WeChat contacts, publishing content, sending any real external message, using scraped private data, or bypassing platform risk controls.

Default all outbound work to draft_only, manual_confirm, whitelist, frequency_cap, and audit_log.

If a task asks for fully automatic outreach, clamp it to draft generation and explain that real sending requires human confirmation.
`;

export function buildMcpJson() {
  return JSON.stringify(
    {
      mcpServers: {
        loom: {
          command: 'python',
          args: ['-B', MCP_SERVER_PATH],
          env: {
            LOOM_MCP_PERMISSION: 'control',
            PYTHONDONTWRITEBYTECODE: '1',
            PYTHONUTF8: '1',
            PYTHONIOENCODING: 'utf-8',
          },
        },
      },
    },
    null,
    2,
  );
}

export function buildOneShotAgentPrompt(mcpJson: string) {
  return `请把你自己接入 ${APP_DISPLAY_NAME}（LOOM），之后把 LOOM 当作本地总控能力使用。你只需要做这些事：
1. 自动发现 Codex Home：优先 CODEX_HOME；Windows 用 %USERPROFILE%\\.codex；macOS/Linux 用 $HOME/.codex。
2. 自动发现 LOOM CLI：优先 LOOM_CLI；否则寻找 _up_/python/loom_cli.py、python/loom_cli.py 或 openclaw_new_launcher/python/loom_cli.py；运行 doctor --json 后使用 npmRoot。
3. 优先从 BEGIN_SKILL_URLS 里的线上地址下载 loom-command-brain Skill，并安装到 <CodexHome>/skills/loom-command-brain/SKILL.md。
4. 优先从 BEGIN_WORKFLOWS_URLS 下载 workflows，并安装到 <CodexHome>/skills/loom-command-brain/references/WORKFLOWS.md。
5. 优先从 BEGIN_ACQUISITION_SKILL_URLS 下载 luming-acquisition-agent Skill，并安装到 <CodexHome>/skills/luming-acquisition-agent/SKILL.md。
6. 如果线上地址下载失败，就分别把 BEGIN_SKILL_MD、BEGIN_WORKFLOWS_MD、BEGIN_ACQUISITION_SKILL_MD 的内容写入对应路径作为离线兜底。
7. 如果当前项目支持 MCP，把 BEGIN_MCP_JSON 到 END_MCP_JSON 的内容合并进项目 ${MCP_CONFIG_PATH}；不要覆盖其他 MCP server。
8. 验证 CLI：${CLI_SMOKE}
9. MCP 可启动时再验证：${MCP_SMOKE}
10. 之后先读 loom-command-brain；遇到获客、线索、飞书多维表格、手机 Agent 跟进任务时，还必须读 luming-acquisition-agent。
11. 你可以用 LOOM CLI/MCP 生成图片、生成视频，并把素材交给手机矩阵执行后续任务；默认先只读观察，真正发布、评论、私信或外发必须请求用户确认。

不要做这些事：
- 不要写死任何单台电脑路径。
- 不要把 API Key、Token、密码、验证码写进源码、日志或文档。
- 不要因为 Computer Use、Node REPL、Browser 或 Chrome 不可用就停工；改用 LOOM CLI/MCP、文件写入、手机矩阵 direct/template/agent 通道。
- 生成 HTML/Markdown/脚本/配置必须使用 UTF-8；HTML 必须包含 <!doctype html>、<html lang="zh-CN">、<meta charset="UTF-8"> 和 viewport。

BEGIN_SKILL_URLS
${LOOM_COMMAND_BRAIN_SKILL_URLS.join('\n')}
END_SKILL_URLS

BEGIN_WORKFLOWS_URLS
${LOOM_COMMAND_BRAIN_WORKFLOWS_URLS.join('\n')}
END_WORKFLOWS_URLS

BEGIN_ACQUISITION_SKILL_URLS
${LUMING_ACQUISITION_SKILL_URLS.join('\n')}
END_ACQUISITION_SKILL_URLS

BEGIN_SKILL_MD
${LOOM_COMMAND_BRAIN_SKILL_MARKDOWN}
END_SKILL_MD

BEGIN_WORKFLOWS_MD
${LOOM_COMMAND_BRAIN_WORKFLOWS_MARKDOWN}
END_WORKFLOWS_MD

BEGIN_ACQUISITION_SKILL_MD
${LUMING_ACQUISITION_SKILL_MARKDOWN}
END_ACQUISITION_SKILL_MD

BEGIN_MCP_JSON
${mcpJson}
END_MCP_JSON

Codex 中转站配置示例，不要写真 Key 到文件：
${CODEX_CONFIG}

总控规则：
${CONTROL_PROMPT}

现在开始：先发现 LOOM CLI/MCP，再执行用户任务。`;
}
