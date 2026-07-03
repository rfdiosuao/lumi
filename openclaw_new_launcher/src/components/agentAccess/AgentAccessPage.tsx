import { Button, showToast } from '../common';

const MCP_CONFIG_PATH = '.mcp.json';
const MCP_SERVER_PATH = '${LOOM_HOME}/python/loom_mcp.py';
const LOOM_COMMAND_BRAIN_SKILL_PATH = '${CODEX_HOME}/skills/loom-command-brain/SKILL.md';
const LOOM_COMMAND_BRAIN_SKILL_URLS = [
  'https://gitee.com/rfdiosuao/lumi/raw/master/skills/loom-command-brain/SKILL.md',
  'https://api.heang.top/loom-release-channel/skills/loom-command-brain/SKILL.md',
  'https://raw.githubusercontent.com/rfdiosuao/loom-release-channel/main/skills/loom-command-brain/SKILL.md',
  '/skills/loom-command-brain/SKILL.md',
];

const CLI_SMOKE = 'python -B "${LOOM_HOME}/python/loom_cli.py" status --json';
const MCP_SMOKE = 'python -B "${LOOM_HOME}/python/loom_mcp.py"';

const CODEX_CONFIG = `# Codex user config: config.toml under CODEX_HOME.
# Do not paste the real API key here. LOOM injects it through env.
model_provider = "heang"
model = "qwen3.7-plus"

[model_providers.heang]
name = "heang"
base_url = "https://api.heang.top/v1"
env_key = "LOOM_CODEX_API_KEY"
wire_api = "chat"
`;

const CONTROL_PROMPT = `You are the LOOM / Luming command brain.
Use LOOM CLI/MCP first. Do not only chat.
Discover paths instead of assuming one computer:
- Codex home: CODEX_HOME env first; otherwise Windows %USERPROFILE%\\.codex; macOS/Linux $HOME/.codex.
- LOOM home: LOOM_HOME env first; otherwise find loom_cli.py in the current project, then common installs: Windows %LOCALAPPDATA%\\LOOM, %ProgramFiles%\\LOOM, D:\\LOOM, C:\\LOOM; macOS /Applications/LOOM.app/Contents/Resources, ~/Applications/LOOM.app/Contents/Resources, ~/Library/Application Support/LOOM; Linux /opt/loom, ~/.local/share/LOOM.
- Skill file: <CodexHome>/skills/loom-command-brain/SKILL.md.
If Computer Use, Node REPL, Browser, Chrome, or desktop control is unavailable, keep working through LOOM CLI/MCP, file writes, and phone matrix direct/template/agent routes.
For creative work, use LOOM CLI/MCP: generate images with media image, generate videos with media video, then dispatch the phone/matrix step in read-only mode first. Full publishing or external posting requires explicit human confirmation.
Generated HTML/Markdown/scripts/config must be UTF-8. HTML must include <!doctype html>, <html lang="zh-CN">, <meta charset="UTF-8">, and viewport metadata.
Never log API keys, tokens, passwords, private keys, verification codes, or phone pairing secrets.
Phone default model is qwen3.7-plus unless LOOM returns another selected available model.`;

const LOOM_COMMAND_BRAIN_SKILL_MARKDOWN = String.raw`---
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
  return `请把你自己接入 LOOM / 麓鸣，之后把 LOOM 当作本地总控能力使用。你只需要做这些事：
1. 自动发现 Codex Home：优先 CODEX_HOME；Windows 用 %USERPROFILE%\\.codex；macOS/Linux 用 $HOME/.codex。
2. 自动发现 LOOM Home：优先 LOOM_HOME；否则从当前项目寻找 openclaw_new_launcher/python/loom_cli.py；再检查 Windows/macOS/Linux 常见安装目录。
3. 优先从 BEGIN_SKILL_URLS 里的线上地址下载 loom-command-brain Skill，并安装到 <CodexHome>/skills/loom-command-brain/SKILL.md。
4. 如果所有线上地址下载失败，就把 BEGIN_SKILL_MD 到 END_SKILL_MD 的内容写入 <CodexHome>/skills/loom-command-brain/SKILL.md 作为离线兜底。
5. 如果当前项目支持 MCP，把 BEGIN_MCP_JSON 到 END_MCP_JSON 的内容合并进项目 ${MCP_CONFIG_PATH}；不要覆盖其他 MCP server。
6. 验证 CLI：${CLI_SMOKE}
7. MCP 可启动时再验证：${MCP_SMOKE}
8. 之后先读 loom-command-brain，再通过 LOOM CLI/MCP 执行用户任务。
9. 你可以用 LOOM CLI/MCP 生成图片、生成视频，并把素材交给手机矩阵执行后续任务；默认先只读观察，真正发布、评论、私信或外发必须请求用户确认。

不要做这些事：
- 不要写死任何单台电脑路径。
- 不要把 API Key、Token、密码、验证码写进源码、日志或文档。
- 不要因为 Computer Use、Node REPL、Browser 或 Chrome 不可用就停工；改用 LOOM CLI/MCP、文件写入、手机矩阵 direct/template/agent 通道。
- 生成 HTML/Markdown/脚本/配置必须使用 UTF-8；HTML 必须包含 <!doctype html>、<html lang="zh-CN">、<meta charset="UTF-8"> 和 viewport。

BEGIN_SKILL_URLS
${LOOM_COMMAND_BRAIN_SKILL_URLS.join('\n')}
END_SKILL_URLS

BEGIN_SKILL_MD
${LOOM_COMMAND_BRAIN_SKILL_MARKDOWN}
END_SKILL_MD

BEGIN_MCP_JSON
${mcpJson}
END_MCP_JSON

Codex 中转站配置示例，不要写真 Key 到文件：
${CODEX_CONFIG}

总控规则：
${CONTROL_PROMPT}

现在开始：先发现 LOOM CLI/MCP，再执行用户任务。`;
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    showToast('已复制', 'success');
  } catch {
    showToast('复制失败，请手动选择文本', 'error');
  }
}

const CopyBlock = ({ title, desc, value }: { title: string; desc: string; value: string }) => (
  <section className="rounded-[8px] border border-border bg-surface-alt/60 p-5">
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <h2 className="text-lg font-black text-text">{title}</h2>
        <div className="mt-1 text-sm leading-6 text-text-muted">{desc}</div>
      </div>
      <Button variant="primary" onClick={() => void copyText(value)}>复制</Button>
    </div>
  </section>
);

const CopyOnlyBlock = ({ title, desc, value }: { title: string; desc: string; value: string }) => (
  <section data-agent-one-shot-copy className="rounded-[8px] border border-accent/20 bg-accent/[0.08] p-5">
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h2 className="text-xl font-black text-text">{title}</h2>
        <div className="mt-1 text-sm leading-6 text-text-muted">{desc}</div>
        <div className="mt-2 text-xs font-bold text-accent">提示词正文不会展示在页面上，只复制给 Agent。</div>
      </div>
      <Button variant="primary" onClick={() => void copyText(value)}>复制接入提示词</Button>
    </div>
  </section>
);

export const AgentAccessPage = () => {
  const mcpJson = buildMcpJson();
  const oneShotAgentPrompt = buildOneShotAgentPrompt(mcpJson);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="text-[11px] font-bold tracking-[0.34em] text-accent">AGENT ACCESS</div>
        <h1 className="mt-2 text-[30px] font-black leading-tight text-text">Agent 接入</h1>
        <div className="mt-2 max-w-[760px] text-sm leading-6 text-text-muted">
          复制一条提示词，让 Codex、Claude Code 或其他 Agent 自动下载 Skill、发现 LOOM 路径并接入 CLI/MCP。
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto grid w-full max-w-[1120px] gap-5">
          <CopyOnlyBlock
            title="一条提示词接入"
            desc="跨 Windows、macOS、Linux；能联网就下载线上 Skill，不能联网就使用内嵌兜底。"
            value={oneShotAgentPrompt}
          />

          <details className="rounded-[8px] border border-border bg-surface-alt/40 p-5">
            <summary className="cursor-pointer text-sm font-black text-text">高级配置</summary>
            <div className="mt-5 grid gap-5">
              <CopyBlock
                title="Skill 位置"
                desc="Agent 会按 CODEX_HOME 或用户目录自动定位，不再依赖某一台电脑路径。"
                value={`LOOM Command Brain Skill\n${LOOM_COMMAND_BRAIN_SKILL_PATH}\n\n可安装源：\n${LOOM_COMMAND_BRAIN_SKILL_URLS.join('\n')}`}
              />
              <CopyBlock
                title="MCP 配置"
                desc={`保存或合并到 ${MCP_CONFIG_PATH}，把 \${LOOM_HOME} 换成自动发现到的 LOOM 目录。`}
                value={mcpJson}
              />
              <CopyBlock
                title="CLI 验证"
                desc="用于确认 LOOM CLI 和 MCP 入口能正常启动。"
                value={`${CLI_SMOKE}\n${MCP_SMOKE}`}
              />
            </div>
          </details>
        </div>
      </main>
    </div>
  );
};
