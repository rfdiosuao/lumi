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

const PACKAGE_VERSION = '2.1.20';
const REQUIRED_AGENT_IDS = ['codex-desktop', 'claude-code', 'opencode', 'openclaw-companion', 'hermes'];

const FALLBACK_AGENTS: Record<string, { name: string; description: string }> = {
  'codex-desktop': { name: 'Codex', description: 'OpenAI 编程智能体' },
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
  const activeStep = !accountReady ? 1 : !agentsReady ? 2 : 3;
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
              查看模型账号、智能体安装、手机演示和本地运行状态。
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
              {!accountReady ? '登录模型账号' : !agentsReady ? '打开安装' : '打开手机'}
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

        <section className="mb-7 grid grid-cols-4 gap-3">
          <StepCard
            index={1}
            title="模型账号"
            detail={accountReady ? (account?.account || licenseInfo?.licensee || '已接入') : '支持访客浏览'}
            active={activeStep === 1}
            done={accountReady}
            onClick={() => setCurrentPage('license')}
          />
          <StepCard
            index={2}
            title="安装"
            detail={`${readyAgents}/${agents.length} 已就绪`}
            active={activeStep === 2}
            done={agentsReady}
            danger={failedAgents > 0}
            onClick={() => setCurrentPage('agents')}
          />
          <StepCard
            index={3}
            title="手机"
            detail="连接 / 截图 / 读取"
            active={activeStep === 3}
            done={false}
            onClick={() => setCurrentPage('phone')}
          />
          <StepCard
            index={4}
            title="其他"
            detail="暂未开放"
            active={false}
            done={false}
            onClick={() => setCurrentPage('capabilities')}
          />
        </section>

        <section className="mb-7 grid grid-cols-4 gap-3">
          <StatusTile label="中转站" value={accountReady ? '已接入' : '未登录'} hint={account?.account || licenseInfo?.licensee || '访客模式'} tone={accountReady ? 'ok' : 'warn'} />
          <StatusTile label="模型" value={modelsReady ? '已同步' : '未同步'} hint={account?.models?.text?.[0] || licenseInfo?.gatewayDefaultModel || '登录后同步'} tone={modelsReady ? 'ok' : 'warn'} />
          <StatusTile label="智能体" value={`${readyAgents}/${agents.length}`} hint={components?.manifest?.version || '组件清单'} tone={failedAgents ? 'danger' : agentsReady ? 'ok' : 'warn'} />
          <StatusTile label="核心服务" value={serviceRunning ? '运行中' : serviceStatus === 'starting' ? '启动中' : '未启动'} hint="本地能力内核" tone={serviceRunning ? 'ok' : 'warn'} />
        </section>

        <section className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] gap-5">
          <div className="rounded-[18px] border border-border/80 bg-surface-alt/30 p-5">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">智能体</div>
                <h2 className="mt-1 text-lg font-black text-text">安装状态</h2>
              </div>
              <button
                type="button"
                onClick={() => setCurrentPage('agents')}
                className="rounded-[13px] border border-border/80 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text transition hover:border-accent/60 hover:text-accent"
              >
                智能体
              </button>
            </div>
            <div className="space-y-2">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => setCurrentPage('agents')}
                  className="flex w-full items-center justify-between gap-4 rounded-[14px] border border-border/70 bg-surface/25 px-4 py-3 text-left transition hover:border-border-strong hover:bg-surface-alt/50"
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

          <div className="rounded-[18px] border border-border/80 bg-surface-alt/30 p-5">
            <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">启动器</div>
            <h2 className="mt-1 text-lg font-black text-text">运行摘要</h2>
            <div className="mt-5 space-y-3">
              <SummaryRow label="核心服务" value={serviceRunning || serviceStatus === 'starting' ? (serviceRunning ? '运行中' : '启动中') : '未启动'} />
              <SummaryRow label="模型数量" value={`${modelCount(account)} 个`} />
              <SummaryRow label="组件清单" value={components?.manifest?.version || '未读取'} />
              <SummaryRow label="演示入口" value="安装 / 手机 / 模型账号" />
              <SummaryRow label="暂未开放" value="生图 / 生视频 / 桌面 RPA / CLI" />
              <SummaryRow label="包版本" value={PACKAGE_VERSION} />
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void refresh()}
                className="rounded-[13px] border border-border/80 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text transition hover:border-accent/60 hover:text-accent"
              >
                刷新
              </button>
              <button
                type="button"
                onClick={() => setCurrentPage('phone')}
                className="rounded-[13px] border border-border/80 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text transition hover:border-accent/60 hover:text-accent"
              >
                手机
              </button>
              <button
                type="button"
                onClick={() => setCurrentPage('capabilities')}
                className="rounded-[13px] border border-border/80 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text transition hover:border-accent/60 hover:text-accent"
              >
                其他
              </button>
              <button
                type="button"
                onClick={() => setCurrentPage('diagnostics')}
                className="rounded-[13px] border border-border/70 bg-surface/30 px-3 py-2 text-xs font-bold text-text-muted transition hover:border-border-strong hover:text-text"
              >
                高级诊断
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const StepCard: React.FC<{
  index: number;
  title: string;
  detail: string;
  done: boolean;
  active: boolean;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}> = ({ index, title, detail, done, active, danger, disabled = false, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={`min-h-[128px] rounded-[18px] border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
      danger
        ? 'border-status-danger/40 bg-status-danger/10'
        : done
          ? 'border-status-success/35 bg-status-success/10'
          : active
            ? 'border-accent/55 bg-accent/[0.07]'
            : 'border-border/80 bg-surface-alt/30 hover:border-border-strong hover:bg-surface-alt/50'
    }`}
  >
    <div className="flex items-center justify-between gap-3">
      <span className="flex h-8 w-8 items-center justify-center rounded-[10px] border border-border/80 bg-surface text-xs font-black text-accent">
        {done ? '✓' : index}
      </span>
      <span className="text-[10px] font-bold uppercase tracking-[0.22em] text-text-subtle">{active ? '当前' : done ? '完成' : '待处理'}</span>
    </div>
    <div className="mt-4 text-base font-black text-text">{title}</div>
    <div className="mt-1 text-xs leading-5 text-text-muted">{detail}</div>
  </button>
);

const StatusTile: React.FC<{ label: string; value: string; hint: string; tone: 'ok' | 'warn' | 'danger' }> = ({ label, value, hint, tone }) => (
  <div className="rounded-[16px] border border-border/80 bg-surface-alt/30 p-4">
    <div className="text-xs text-text-subtle">{label}</div>
    <div className={`mt-2 text-xl font-black ${tone === 'ok' ? 'text-status-success' : tone === 'danger' ? 'text-status-danger' : 'text-status-warning'}`}>{value}</div>
    <div className="mt-1 truncate text-xs text-text-muted" title={hint}>{hint}</div>
  </div>
);

const SummaryRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-4 border-b border-border/50 pb-3 last:border-b-0">
    <span className="text-sm text-text-muted">{label}</span>
    <span className="truncate text-sm font-bold text-text" title={value}>{value}</span>
  </div>
);
