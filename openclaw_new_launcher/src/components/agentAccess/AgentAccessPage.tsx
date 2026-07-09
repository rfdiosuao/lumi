import { Button, showToast } from '../common';
import {
  buildMcpJson,
  buildOneShotAgentPrompt,
  CLI_SMOKE,
  LOOM_COMMAND_BRAIN_SKILL_PATH,
  LOOM_COMMAND_BRAIN_SKILL_URLS,
  LOOM_COMMAND_BRAIN_WORKFLOWS_PATH,
  LOOM_COMMAND_BRAIN_WORKFLOWS_URLS,
  LUMING_ACQUISITION_SKILL_PATH,
  LUMING_ACQUISITION_SKILL_URLS,
  MCP_CONFIG_PATH,
  MCP_SMOKE,
} from './agentPrompt';

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
                value={`LOOM Command Brain Skill\n${LOOM_COMMAND_BRAIN_SKILL_PATH}\n\nLuming Acquisition Skill\n${LUMING_ACQUISITION_SKILL_PATH}\n\nWorkflow Reference\n${LOOM_COMMAND_BRAIN_WORKFLOWS_PATH}\n\n总控 Skill 源：\n${LOOM_COMMAND_BRAIN_SKILL_URLS.join('\n')}\n\n获客 Skill 源：\n${LUMING_ACQUISITION_SKILL_URLS.join('\n')}\n\n工作流源：\n${LOOM_COMMAND_BRAIN_WORKFLOWS_URLS.join('\n')}`}
              />
              <CopyBlock
                title="MCP 配置"
                desc={`保存或合并到 ${MCP_CONFIG_PATH}，把 \${LOOM_CLI_DIR} 换成 loom_cli.py 所在目录。`}
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
