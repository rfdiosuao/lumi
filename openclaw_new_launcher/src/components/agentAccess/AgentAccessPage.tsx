import { Button, showToast } from '../common';

const MCP_CONFIG_PATH = '.mcp.json';
const MCP_SERVER_PATH = 'python/loom_mcp.py';
const LOOM_COMMAND_BRAIN_SKILL_PATH = '~/.codex/skills/loom-command-brain/SKILL.md';
const CLI_SMOKE = 'python -B python/loom_cli.py status --json';
const MCP_SMOKE = 'python -B python/loom_mcp.py';

const CODEX_CONFIG = `# ~/.codex/config.toml
# 不要把真实 API Key 写进配置文件。
model_provider = "loom"
model = "你的可用文本模型"

[model_providers.loom]
name = "麓鸣中转站"
base_url = "https://api.heang.top/v1"
env_key = "LOOM_CODEX_API_KEY"
`;

const CODEX_ENV = `# PowerShell，保存到当前 Windows 用户
[Environment]::SetEnvironmentVariable("LOOM_CODEX_API_KEY", "sk-你的中转站Key", "User")

# 新开终端后验证
codex doctor
codex -c model_provider='"loom"' -m "你的可用文本模型"`;

const CONTROL_PROMPT = `你是 LOOM / 麓鸣的总控 Agent。

你只能通过 LOOM MCP/CLI 调用本地能力，不直接读写用户敏感配置。
优先路径：Direct -> Template -> Agent。
截图、读屏、返回、Home、连接检测走快速路径。
复杂任务才调用手机 Agent。
涉及私信、评论、批量触达、视频发布、验证码、账号异常时必须请求人工确认。
每次任务都要返回 queued/running/step/result/error 状态，并写入任务台账。
不要记录 API Key、Token、密码、私钥。

默认模型：
LOOM 主模型：使用模型账号页已选的可用文本模型；不要硬编码不可用模型。
手机 Agent：agnes-2.0-flash`;

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
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-black text-text">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-text-muted">{desc}</p>
      </div>
      <Button variant="primary" onClick={() => void copyText(value)}>复制</Button>
    </div>
    <pre className="mt-4 max-h-[300px] overflow-auto rounded-[8px] border border-border bg-surface p-4 text-xs leading-5 text-text">
      {value}
    </pre>
  </section>
);

export const AgentAccessPage = () => {
  const mcpJson = JSON.stringify(
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

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="text-[11px] font-bold tracking-[0.34em] text-accent">AGENT ACCESS</div>
        <h1 className="mt-2 text-[30px] font-black leading-tight text-text">Agent 接入</h1>
        <p className="mt-2 max-w-[760px] text-sm leading-6 text-text-muted">
          给 Codex、Claude Code 或其他 Agent 复制 MCP 配置、验证命令和总控提示词。
        </p>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="mx-auto grid w-full max-w-[1120px] gap-5">
          <CopyBlock
            title="复制 Skill 路径"
            desc="给 Codex / Claude Code 作为 LOOM 总控大脑规范，先读 Skill 再调用 CLI 或 MCP。"
            value={`LOOM Command Brain Skill\n${LOOM_COMMAND_BRAIN_SKILL_PATH}\n\n使用方式：让 Agent 读取 loom-command-brain，再通过 LOOM CLI/MCP 调度安装、模型、创作、手机矩阵和日志能力。`}
          />

          <CopyBlock
            title="MCP 配置"
            desc={`保存到 ${MCP_CONFIG_PATH}，让 Codex / Claude Code 能调用 LOOM。`}
            value={mcpJson}
          />

          <div className="grid gap-5 lg:grid-cols-2">
            <CopyBlock
              title="CLI 验证"
              desc="用于确认 LOOM CLI 和 MCP 入口能正常启动。"
              value={`${CLI_SMOKE}\n${MCP_SMOKE}`}
            />
            <CopyBlock
              title="Codex 中转站模型"
              desc="API Key 放进环境变量，不写入源码、日志或配置文件。"
              value={`${CODEX_CONFIG}\n${CODEX_ENV}`}
            />
          </div>

          <CopyBlock
            title="总控提示词"
            desc="给 Codex 或 Claude Code 使用，让它按 LOOM 的安全边界调度手机矩阵。"
            value={CONTROL_PROMPT}
          />
        </div>
      </main>
    </div>
  );
};
