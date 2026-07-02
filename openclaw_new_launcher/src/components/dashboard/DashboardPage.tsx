import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAppStore } from '../../stores/appStore';
import { BusyOverlay } from '../common';
import {
  accountApi,
  componentApi,
  parseErrorText,
  type AccountSnapshot,
  type ComponentSnapshot,
  type ComponentSummary,
} from '../../services/api';
import { AgentLogo } from '../agents/AgentLogo';
import { APP_VERSION } from '../../version';

const REQUIRED_AGENT_IDS = ['codex-desktop', 'claude-code', 'opencode', 'openclaw-companion', 'hermes'];

const FALLBACK_AGENTS: Record<string, { name: string; description: string }> = {
  'codex-desktop': { name: 'Codex 桌面端', description: 'OpenAI Codex 桌面应用' },
  'claude-code': { name: 'Claude Code', description: 'Anthropic 命令行编程智能体' },
  opencode: { name: 'opencode', description: '终端优先的 AI 编程工具' },
  'openclaw-companion': { name: 'OpenClaw 兼容运行时', description: 'OpenClaw 协议兼容组件' },
  hermes: { name: 'Hermes', description: 'Hermes 智能体运行时' },
};

function requiredRows(snapshot: ComponentSnapshot | null): ComponentSummary[] {
  const byId = new Map((snapshot?.components || []).map((item) => [item.id, item]));
  return REQUIRED_AGENT_IDS.map((id) => {
    const existing = byId.get(id);
    if (existing) return existing;
    const fallback = FALLBACK_AGENTS[id];
    return {
      id,
      name: fallback?.name || id,
      version: '-',
      installedVersion: null,
      previousVersion: null,
      status: 'not_installed',
      platform: 'windows',
      arch: 'x64',
      type: 'installer',
      size: 0,
      entry: null,
      installPath: '',
      category: 'agent',
      officialUrl: '',
      description: fallback?.description || '',
      urls: [],
      updatedAt: null,
      errorCode: null,
      errorMessage: null,
    };
  });
}

function statusText(status: string): string {
  const labels: Record<string, string> = {
    ready: '已就绪',
    not_installed: '未安装',
    resolving_manifest: '准备中',
    downloading: '下载中',
    verifying: '校验中',
    extracting: '安装中',
    configuring: '配置中',
    health_checking: '检测中',
    starting: '启动中',
    started: '已启动',
    manual_install_required: '待手动安装',
    simulation_ready: '待检测',
    download_failed: '下载失败',
    verify_failed: '校验失败',
    extract_failed: '安装失败',
    config_failed: '配置失败',
    health_failed: '检测失败',
    rollback_available: '可回滚',
    rolling_back: '回滚中',
    rollback_failed: '回滚失败',
  };
  return labels[status] || status;
}

function modelCount(account: AccountSnapshot | null): number {
  const models = account?.models || {};
  return (models.text?.length || 0) + (models.image?.length || 0) + (models.video?.length || 0);
}

export const DashboardPage: React.FC = () => {
  const {
    serviceRunning,
    serviceStatus,
    isAuthorized,
    licenseInfo,
    setCurrentPage,
  } = useAppStore();
  const [account, setAccount] = useState<AccountSnapshot | null>(null);
  const [components, setComponents] = useState<ComponentSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshError, setRefreshError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setRefreshError('');
    const [accountRes, componentRes] = await Promise.allSettled([
      accountApi.current(),
      componentApi.status(),
    ]);
    if (accountRes.status === 'fulfilled') setAccount(accountRes.value.account || null);
    else setRefreshError(parseErrorText(accountRes.reason) || '账号状态读取失败');
    if (componentRes.status === 'fulfilled') setComponents(componentRes.value);
    else setRefreshError(parseErrorText(componentRes.reason) || '组件状态读取失败');
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const agents = useMemo(() => requiredRows(components), [components]);
  const readyAgents = agents.filter((agent) => agent.status === 'ready' || agent.status === 'started').length;
  const failedAgents = agents.filter((agent) => agent.status.endsWith('_failed')).length;
  const accountReady = Boolean(account?.loggedIn || isAuthorized);
  const modelsReady = modelCount(account) > 0 || Boolean(licenseInfo?.gatewayBaseUrl);
  const agentsReady = agents.length > 0 && readyAgents === agents.length;
  const overall = refreshError
    ? '状态异常'
    : !accountReady
      ? '待配置'
      : failedAgents
        ? '安装异常'
        : !agentsReady
          ? '待安装'
          : serviceRunning
            ? '运行中'
            : '待启动';

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <BusyOverlay
        active={loading}
        title="正在刷新总览"
        detail="LOOM 正在读取账号、组件和本地服务状态。"
      />
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="flex items-end justify-between gap-8">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.42em] text-accent">LOOM</div>
            <h1 className="mt-2 text-[32px] font-black leading-tight text-text">总览</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
              先安装智能体，再连接手机。其他能力暂时收在高级入口里。
            </p>
          </div>
          <div className="flex flex-col items-end gap-3">
            <div className="rounded-full border border-border/70 bg-surface-alt/50 px-4 py-2 text-sm font-black text-text">{overall}</div>
            <button
              type="button"
              onClick={() => setCurrentPage(!accountReady ? 'license' : !agentsReady ? 'agents' : 'phone')}
              disabled={loading}
              className="min-w-[140px] rounded-[14px] border border-border/80 bg-surface-alt/50 px-5 py-2.5 text-sm font-black text-text transition hover:border-accent/60 hover:text-accent disabled:cursor-not-allowed disabled:opacity-55"
            >
              {!accountReady ? '登录模型账号' : !agentsReady ? '安装智能体' : '连接手机'}
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-8 py-7">
        {refreshError ? (
          <div className="mb-5 rounded-[16px] border border-status-danger/30 bg-status-danger/10 p-4 text-sm text-status-danger">
            {refreshError}
          </div>
        ) : null}
        {!refreshError && components?.warning ? (
          <div className="mb-5 rounded-[16px] border border-status-warning/30 bg-status-warning/10 p-4 text-sm text-status-warning">
            {components.warning}
          </div>
        ) : null}

        <section className="grid gap-5 xl:grid-cols-2">
          <PathCard
            eyebrow="第一步"
            title="安装智能体"
            detail="一键安装、更新和启动 Codex / Claude Code / opencode / OpenClaw / Hermes。"
            state={failedAgents ? '需要处理' : agentsReady ? '全部就绪' : `${readyAgents}/${agents.length} 已就绪`}
            primaryLabel={agentsReady ? '查看安装状态' : '开始安装'}
            tone={failedAgents ? 'danger' : agentsReady ? 'ok' : 'warn'}
            onClick={() => setCurrentPage('agents')}
          />
          <PathCard
            eyebrow="第二步"
            title="连接手机"
            detail="保存手机 IP 和令牌后，可以截图、读取屏幕，并执行一个简单任务。"
            state={agentsReady ? '可连接' : '建议先安装智能体'}
            primaryLabel="打开手机控制"
            tone={agentsReady ? 'ok' : 'warn'}
            onClick={() => setCurrentPage('phone')}
          />
        </section>

        <section className="mt-7 grid gap-3 md:grid-cols-4">
          <StatusTile label="模型账号" value={accountReady ? '已登录' : '访客'} hint={account?.account || licenseInfo?.licensee || '可稍后登录'} tone={accountReady ? 'ok' : 'warn'} />
          <StatusTile label="模型" value={modelsReady ? '已同步' : '未同步'} hint={account?.models?.text?.[0] || licenseInfo?.gatewayDefaultModel || '登录后同步'} tone={modelsReady ? 'ok' : 'warn'} />
          <StatusTile label="智能体" value={`${readyAgents}/${agents.length}`} hint={failedAgents ? '有失败项' : agentsReady ? '可启动' : '待安装'} tone={failedAgents ? 'danger' : agentsReady ? 'ok' : 'warn'} />
          <StatusTile label="本地服务" value={serviceRunning ? '运行中' : serviceStatus === 'starting' ? '启动中' : '待启动'} hint={`LOOM ${APP_VERSION}`} tone={serviceRunning ? 'ok' : 'warn'} />
        </section>

        <section className="mt-7 grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="border-t border-border/70 bg-surface/40 pt-5">
            <div className="mb-3 flex items-center justify-between gap-4">
              <div>
                <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">安装状态</div>
                <h2 className="mt-1 text-lg font-black text-text">五个智能体</h2>
              </div>
              <button
                type="button"
                onClick={() => setCurrentPage('agents')}
                className="rounded-[13px] border border-border/80 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text transition hover:border-accent/60 hover:text-accent"
              >
                去安装
              </button>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => setCurrentPage('agents')}
                  className="flex w-full items-center justify-between gap-4 border-t border-border/60 py-3 text-left transition hover:border-border-strong"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <AgentLogo id={agent.id} />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-black text-text">{agent.name}</div>
                      <div className="mt-1 truncate text-xs text-text-muted">{agent.description || agent.id}</div>
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${
                    agent.status === 'ready' || agent.status === 'started'
                      ? 'border-status-success/30 bg-status-success/10 text-status-success'
                      : agent.status.endsWith('_failed')
                        ? 'border-status-danger/30 bg-status-danger/10 text-status-danger'
                        : 'border-status-warning/30 bg-status-warning/10 text-status-warning'
                  }`}>
                    {statusText(agent.status)}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-border/70 pt-5">
            <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">高级</div>
            <h2 className="mt-1 text-lg font-black text-text">更多入口</h2>
            <div className="mt-4 grid gap-2">
              <SmallAction label="模型账号" onClick={() => setCurrentPage('license')} />
              <SmallAction label="其他能力" onClick={() => setCurrentPage('capabilities')} />
              <SmallAction label="高级诊断" onClick={() => setCurrentPage('diagnostics')} muted />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const PathCard: React.FC<{
  eyebrow: string;
  title: string;
  detail: string;
  state: string;
  primaryLabel: string;
  tone: 'ok' | 'warn' | 'danger';
  onClick: () => void;
}> = ({ eyebrow, title, detail, state, primaryLabel, tone, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`min-h-[220px] rounded-[20px] border p-6 text-left transition hover:-translate-y-0.5 hover:shadow-[0_18px_48px_rgba(5,35,29,0.12)] ${
      tone === 'danger'
        ? 'border-status-danger/35 bg-status-danger/8'
        : tone === 'ok'
          ? 'border-[#0B4A3E]/24 bg-[#0B4A3E]/8'
          : 'border-border/80 bg-surface-alt/45 hover:border-[#0B4A3E]/30'
    }`}
  >
    <div className="flex items-center justify-between gap-3">
      <span className="text-[11px] font-black tracking-[0.28em] text-text-subtle">{eyebrow}</span>
      <span className={`rounded-full border px-3 py-1 text-xs font-black ${
        tone === 'danger'
          ? 'border-status-danger/35 bg-status-danger/10 text-status-danger'
          : tone === 'ok'
            ? 'border-status-success/30 bg-status-success/10 text-status-success'
            : 'border-status-warning/30 bg-status-warning/10 text-status-warning'
      }`}>{state}</span>
    </div>
    <div className="mt-8 text-[30px] font-black leading-tight text-text">{title}</div>
    <div className="mt-3 max-w-[460px] text-sm leading-6 text-text-muted">{detail}</div>
    <div className="mt-7 inline-flex rounded-[14px] border border-[#0B4A3E]/35 bg-[#0B4A3E] px-5 py-2.5 text-sm font-black text-[#F5FFF9]">
      {primaryLabel}
    </div>
  </button>
);

const SmallAction: React.FC<{ label: string; muted?: boolean; onClick: () => void }> = ({ label, muted, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex items-center justify-between border-t border-border/60 py-3 text-left text-sm font-bold transition hover:border-border-strong ${
      muted ? 'text-text-muted hover:text-text' : 'text-text'
    }`}
  >
    <span>{label}</span>
    <span className="text-text-subtle">→</span>
  </button>
);

const StatusTile: React.FC<{ label: string; value: string; hint: string; tone: 'ok' | 'warn' | 'danger' }> = ({ label, value, hint, tone }) => (
  <div className="rounded-[16px] border border-border/80 bg-surface-alt/30 p-4">
    <div className="text-xs text-text-subtle">{label}</div>
    <div className={`mt-2 text-xl font-black ${tone === 'ok' ? 'text-status-success' : tone === 'danger' ? 'text-status-danger' : 'text-status-warning'}`}>{value}</div>
    <div className="mt-1 truncate text-xs text-text-muted" title={hint}>{hint}</div>
  </div>
);
