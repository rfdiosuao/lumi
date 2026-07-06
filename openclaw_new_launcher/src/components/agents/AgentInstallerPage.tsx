import React from 'react';
import { loomClient } from '../../services/loomClient';
import { loomErrorText } from '../../services/loomErrors';
import type {
  AgentModelConfigStatus,
  BridgeJob,
  ComponentSnapshot,
  ComponentSummary,
  DiagnosticCheck,
  DiagnosticReport,
  DiagnosticStatus,
} from '../../services/loomContracts';
import { loadCachedPreflight, preflightCacheUsable, saveCachedPreflight } from '../../services/startupCache';
import { buildMcpJson, buildOneShotAgentPrompt } from '../agentAccess/AgentAccessPage';
import { BusyOverlay, Button, Input, Select, showConfirm, showToast } from '../common';
import { AgentLogo } from './AgentLogo';
import { APP_DISPLAY_NAME } from '../../version';

const PINNED_COMPONENT_IDS = [
  'codex-desktop',
  'claude-code',
  'opencode',
  'openclaw-companion',
  'hermes',
];

const FALLBACK_COMPONENTS: Record<string, { name: string; description: string; category: string }> = {
  'codex-desktop': { name: 'Codex 桌面端', description: 'OpenAI Codex 桌面应用', category: 'agent' },
  'claude-code': { name: 'Claude Code', description: 'Anthropic 命令行编程智能体', category: 'agent' },
  opencode: { name: 'opencode', description: '终端优先的 AI 编程工具', category: 'agent' },
  'openclaw-companion': { name: 'OpenClaw', description: '多智能体编程工作台', category: 'agent' },
  hermes: { name: 'Hermes', description: 'Hermes 智能体运行时', category: 'agent' },
};

const PREREQ_IDS = ['python_runtime', 'node', 'npm', 'git', 'git_bash', 'uv', 'webview2', 'data_dir'];
const MODEL_CONFIG_COMPONENT_IDS = new Set(['codex-desktop', 'claude-code', 'openclaw-companion']);
const INSTALL_LOG_VISIBLE_LIMIT = 6;
const OPENCLAW_WEB_URL = 'http://127.0.0.1:18790';

type CustomProviderOption = {
  id: string;
  label: string;
  baseUrl: string;
};

const CUSTOM_PROVIDER_OPTIONS: CustomProviderOption[] = [
  { id: 'custom', label: '自定义...', baseUrl: '' },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
  { id: 'anthropic', label: 'Anthropic', baseUrl: 'https://api.anthropic.com/v1' },
  { id: 'gemini', label: 'Google Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { id: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1' },
  { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
  { id: 'moonshot', label: 'Moonshot - Kimi', baseUrl: 'https://api.moonshot.cn/v1' },
];

type AgentCustomProviderDraft = {
  provider: string;
  baseUrl: string;
  apiKey: string;
  model: string;
};

function providerOptionById(id: string): CustomProviderOption {
  return CUSTOM_PROVIDER_OPTIONS.find((option) => option.id === id) || CUSTOM_PROVIDER_OPTIONS[0];
}

function providerIdForLabel(label?: string): string {
  const normalized = (label || '').trim().toLowerCase();
  if (!normalized) return 'custom';
  return CUSTOM_PROVIDER_OPTIONS.find((option) => option.label.toLowerCase() === normalized)?.id || 'custom';
}

type InstallLogEntry = {
  id: string;
  componentId?: string;
  message: string;
  tone: string;
  time: string;
};

const PREREQ_PLACEHOLDER_LABELS: Record<string, string> = {
  python_runtime: 'Python',
  node: 'Node.js',
  npm: 'npm',
  git: 'Git',
  git_bash: 'Git Bash',
  uv: 'uv',
  webview2: 'WebView2',
  data_dir: '数据目录',
  portable_integrity: '便携包完整性',
};

export function statusLabel(status: string): string {
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
    uninstalling: '卸载中',
    upgrade_available: '需升级',
    manual_install_required: '待手动安装',
    simulation_ready: '待检测',
    started: '已启动',
    download_failed: '下载失败',
    verify_failed: '校验失败',
    extract_failed: '安装失败',
    config_failed: '配置失败',
    health_failed: '检测失败',
    start_failed: '启动失败',
    uninstall_failed: '卸载失败',
    rollback_available: '可回滚',
    rolling_back: '回滚中',
    rollback_failed: '回滚失败',
  };
  return labels[status] || status || '-';
}

function displayStatusLabel(status: string): string {
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
    uninstalling: '卸载中',
    upgrade_available: '可升级',
    manual_install_required: '待手动安装',
    simulation_ready: '待检测',
    started: '已启动',
    download_failed: '下载失败',
    verify_failed: '校验失败',
    extract_failed: '安装失败',
    config_failed: '配置失败',
    health_failed: '检测失败',
    start_failed: '启动失败',
    uninstall_failed: '卸载失败',
    rollback_available: '可回滚',
    rolling_back: '回滚中',
    rollback_failed: '回滚失败',
  };
  return labels[status] || status || '-';
}

function statusClass(status: string): string {
  if (status === 'ready' || status === 'started') return 'border-status-success/30 bg-status-success/10 text-status-success';
  if (status === 'upgrade_available') return 'border-status-success/40 bg-status-success/10 text-status-success';
  if (status === 'simulation_ready') return 'border-border/80 bg-surface-alt/60 text-text-muted';
  if (status.endsWith('_failed')) return 'border-status-danger/30 bg-status-danger/10 text-status-danger';
  if (status === 'not_installed' || status === 'manual_install_required') {
    return 'border-[#0B4A3E]/30 bg-[#0B4A3E]/10 text-[#0B4A3E]';
  }
  return 'border-[#0B4A3E]/30 bg-[#0B4A3E]/10 text-[#0B4A3E]';
}

function diagnosticLabel(status: DiagnosticStatus): string {
  if (status === 'ok') return '已就绪';
  if (status === 'warn') return '需处理';
  return '缺失';
}

function diagnosticClass(status: DiagnosticStatus): string {
  if (status === 'ok') return 'border-status-success/30 bg-status-success/10 text-status-success';
  if (status === 'warn') return 'border-[#0B4A3E]/25 bg-[#0B4A3E]/10 text-[#0B4A3E]';
  return 'border-status-danger/30 bg-status-danger/10 text-status-danger';
}

function displayDiagnosticLabel(status: DiagnosticStatus): string {
  if (status === 'ok') return '已就绪';
  if (status === 'warn') return '需处理';
  return '缺失';
}

function prerequisiteChecks(report: DiagnosticReport | null): DiagnosticCheck[] {
  const checks = report?.checks || [];
  const byId = new Map(checks.map((check) => [check.id, check]));
  return PREREQ_IDS.map((id) => byId.get(id)).filter(Boolean) as DiagnosticCheck[];
}

function prerequisiteSummary(checks: DiagnosticCheck[]): { ready: number; total: number; failed: number; repairable: number } {
  return {
    ready: checks.filter((check) => check.status === 'ok').length,
    total: checks.length,
    failed: checks.filter((check) => check.status === 'fail').length,
    repairable: checks.filter((check) => check.repairable).length,
  };
}

function prerequisiteNeedsRepair(report: DiagnosticReport | null): boolean {
  return prerequisiteChecks(report).some((check) => check.status === 'fail' || (check.status === 'warn' && Boolean(check.repairable)));
}

function blockingPrerequisiteIssues(report: DiagnosticReport | null): DiagnosticCheck[] {
  return prerequisiteChecks(report).filter((check) => check.status === 'fail');
}

function isWorking(status: string): boolean {
  return ['resolving_manifest', 'downloading', 'verifying', 'extracting', 'configuring', 'health_checking', 'starting', 'uninstalling'].includes(status);
}

function isFailedStatus(status: string): boolean {
  return status.endsWith('_failed');
}

function needsInstallAfterDetect(component?: ComponentSummary): boolean {
  if (!component) return true;
  return !['ready', 'started'].includes(component.status);
}

function isComponentInstalled(component?: ComponentSummary): boolean {
  return Boolean(component && ['ready', 'started', 'upgrade_available'].includes(component.status));
}

function isOpenClawComponent(component?: ComponentSummary): boolean {
  return component?.id === 'openclaw-companion';
}

function componentWebUrl(component?: ComponentSummary): string {
  if (!component) return '';
  return component.officialUrl || (isOpenClawComponent(component) ? 'https://openclaw.ai' : '');
}

type AgentPrimaryAction = 'install' | 'upgrade' | 'start';

function primaryAgentAction(component?: ComponentSummary): AgentPrimaryAction {
  if (!component) return 'install';
  if (component.status === 'upgrade_available') return 'upgrade';
  if (component.status === 'ready' || component.status === 'started') return 'start';
  return 'install';
}

function primaryAgentButtonLabel(component: ComponentSummary, busyId: string, busyAction: string): string {
  const busy = busyId === component.id;
  if (busy) {
    if (busyAction === 'start') return '启动中...';
    if (busyAction === 'prepare-start') return component.status === 'upgrade_available' ? '升级启动中...' : '安装启动中...';
    return component.status === 'upgrade_available' ? '升级中...' : '安装中...';
  }
  const action = primaryAgentAction(component);
  if (action === 'start') return '启动';
  if (action === 'upgrade') return '升级并启动';
  return isFailedStatus(component.status) ? '重新安装并启动' : '安装并启动';
}

function toneClass(tone: string): string {
  if (tone === 'ok' || tone === 'success') return 'text-status-success';
  if (tone === 'danger' || tone === 'error') return 'text-status-danger';
  if (tone === 'warning' || tone === 'warn') return 'text-status-warning';
  return 'text-text-muted';
}

function jobHistoryEntries(jobs: BridgeJob[], selectedId: string): InstallLogEntry[] {
  return jobs.flatMap((job) => {
    const componentId = typeof (job.progress as any)?.componentId === 'string' ? (job.progress as any).componentId : undefined;
    if (selectedId && componentId && componentId !== selectedId) return [];
    const history = job.progress?.history || [];
    return history.map((entry, index) => ({
      id: `${job.id}-${index}`,
      componentId,
      message: entry.message || job.message || job.label || job.id,
      tone: entry.tone || job.progress?.tone || 'neutral',
      time: entry.updatedAt ? new Date(entry.updatedAt * 1000).toLocaleTimeString() : '-',
    }));
  });
}

function formatInstallLogEntries(entries: InstallLogEntry[]): string {
  return entries
    .map((entry) => `[${entry.time || '-'}] ${entry.message}`)
    .join('\n');
}

function formatSize(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '-';
  if (size >= 1024 * 1024 * 1024) return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(0)} MB`;
  return `${Math.ceil(size / 1024)} KB`;
}

function sortComponents(components: ComponentSummary[]): ComponentSummary[] {
  return [...components].sort((a, b) => {
    const ai = PINNED_COMPONENT_IDS.indexOf(a.id);
    const bi = PINNED_COMPONENT_IDS.indexOf(b.id);
    const ax = ai === -1 ? 999 : ai;
    const bx = bi === -1 ? 999 : bi;
    if (ax !== bx) return ax - bx;
    return a.name.localeCompare(b.name);
  });
}

function componentRows(snapshot: ComponentSnapshot | null): ComponentSummary[] {
  const byId = new Map((snapshot?.components || []).map((item) => [item.id, item]));
  const rows = PINNED_COMPONENT_IDS.map((id) => {
    const existing = byId.get(id);
    if (existing) return existing;
    const fallback = FALLBACK_COMPONENTS[id];
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
      category: fallback?.category || 'component',
      officialUrl: '',
      description: fallback?.description || '',
      urls: [],
      updatedAt: null,
      errorCode: null,
      errorMessage: null,
    };
  });
  const extra = (snapshot?.components || []).filter((item) => !PINNED_COMPONENT_IDS.includes(item.id));
  return sortComponents([...rows, ...extra]);
}

function manifestInstallLocked(snapshot: ComponentSnapshot | null): boolean {
  if (!snapshot) return false;
  return Boolean(snapshot.installLocked || snapshot.manifestErrorCode === 'manifest_unavailable' || !snapshot.manifest);
}

const InfoTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="border-t border-border/70 pt-3">
    <div className="text-[11px] font-bold text-text-subtle">{label}</div>
    <div className="mt-1 truncate text-sm font-black text-text" title={value}>{value}</div>
  </div>
);

const ActivityRing: React.FC<{ active?: boolean; className?: string }> = ({ active = true, className = '' }) => (
  <span className={`loom-activity-ring ${active ? '' : 'opacity-45'} ${className}`} aria-hidden="true" />
);

export const PrerequisitePanel: React.FC<{
  report: DiagnosticReport | null;
  loading: boolean;
  repairing: boolean;
  error: string;
  onRefresh: () => void;
  onRepair: () => void;
}> = ({ report, loading, repairing, error, onRefresh, onRepair }) => {
  const checks = prerequisiteChecks(report);
  const summary = prerequisiteSummary(checks);
  const allReady = checks.length > 0 && summary.ready === summary.total;
  const overall =
    !checks.length
      ? '待检测'
      : summary.failed
        ? `${summary.failed} 项缺失`
        : summary.ready === summary.total
          ? '前置已就绪'
          : `${summary.total - summary.ready} 项需处理`;

  return (
    <section className="px-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="max-w-3xl">
          <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">前置环境</div>
          <h2 className="mt-1 text-2xl font-black text-text">先检测 Python / Node / npm / Git / Git Bash</h2>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            普通用户电脑可能没有开发环境；LOOM 会先检查随包运行时和必要工具，缺失时优先处理前置，再继续安装智能体。
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-3">
          <span className={`rounded-full border px-3 py-2 text-xs font-black ${
            summary.failed ? 'border-status-danger/30 bg-status-danger/10 text-status-danger' : 'border-status-success/30 bg-status-success/10 text-status-success'
          }`}>
            {overall}
          </span>
          <Button variant="quiet" onClick={onRefresh} disabled={loading || repairing}>
            {loading ? '检测中...' : '检测前置'}
          </Button>
          <Button variant="primary" onClick={onRepair} disabled={loading || repairing || allReady}>
            {repairing ? '处理中...' : '安装/修复前置'}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="mt-5 rounded-[14px] border border-status-danger/30 bg-status-danger/10 p-3 text-sm text-status-danger">
          {error}
        </div>
      ) : null}

      <div className="mt-5 grid gap-x-6 gap-y-4 md:grid-cols-3 xl:grid-cols-4">
        {(checks.length ? checks : PREREQ_IDS.map((id) => ({
          id,
          label: PREREQ_PLACEHOLDER_LABELS[id] || id,
          status: 'warn' as DiagnosticStatus,
          message: '等待检测',
          detail: '',
          repairable: false,
        } satisfies DiagnosticCheck))).map((check) => (
          <div key={check.id} className="border-t border-border/70 pt-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-black text-text">{check.label}</div>
                <div className="mt-1 line-clamp-2 text-xs leading-5 text-text-muted">{check.message}</div>
              </div>
              <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${diagnosticClass(check.status)}`}>
                {diagnosticLabel(check.status)}
              </span>
            </div>
            {check.detail ? (
              <details className="mt-3 text-xs text-text-subtle">
                <summary className="cursor-pointer font-bold">详情</summary>
                <div className="mt-2 break-all font-mono leading-5">{check.detail}</div>
              </details>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
};

const CompactPrerequisitePanel: React.FC<{
  report: DiagnosticReport | null;
  loading: boolean;
  repairing: boolean;
  error: string;
  installLocked?: boolean;
  onRefresh: () => void;
  onRepair: () => void;
}> = ({ report, loading, repairing, error, installLocked = false, onRefresh, onRepair }) => {
  const checks = prerequisiteChecks(report);
  const summary = prerequisiteSummary(checks);
  const visibleChecks = (checks.length ? checks : PREREQ_IDS.map((id) => ({
    id,
    label: PREREQ_PLACEHOLDER_LABELS[id] || id,
    status: 'warn' as DiagnosticStatus,
    message: '等待检测',
    detail: '',
    repairable: false,
  } satisfies DiagnosticCheck))).slice(0, 5);
  const total = Math.max(summary.total || visibleChecks.length, 1);
  const ready = summary.ready || 0;
  const pct = checks.length ? Math.round((ready / total) * 100) : 0;
  const allReady = checks.length > 0 && summary.ready === summary.total;
  const busy = loading || repairing;
  const title = !checks.length
    ? '准备检测前置环境'
    : summary.failed
      ? `${summary.failed} 项需要处理`
      : allReady
        ? '前置环境已就绪'
        : `${summary.total - summary.ready} 项待处理`;
  const subtitle = busy
    ? repairing ? '正在安装或修复必要环境...' : '正在检测 Python、Node、npm、Git...'
    : installLocked
      ? '安装清单未就绪，安装和启动暂不可用。'
      : allReady ? '可以继续安装和启动智能体。' : '缺失项会优先处理，详情可展开查看。';

  return (
    <section className="px-6 py-3">
      <div className="rounded-[14px] border border-border/80 bg-surface/70 p-4 shadow-[0_12px_30px_rgba(8,35,48,0.05)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] ${
              allReady ? 'bg-status-success/12 text-status-success' : busy ? 'bg-[#0B4A3E]/10 text-[#0B4A3E]' : 'bg-surface-alt text-text-muted'
            }`}>
              {busy ? <ActivityRing /> : <span className="text-lg font-black">{allReady ? '✓' : '•'}</span>}
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-black tracking-[0.22em] text-text-subtle">前置环境</div>
              <h2 className="mt-0.5 text-lg font-black text-text">{title}</h2>
              <p className="mt-1 text-xs text-text-muted">{subtitle}</p>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-2">
            <Button variant="quiet" onClick={onRefresh} disabled={loading || repairing}>
              {loading ? '检测中...' : '重新检测'}
            </Button>
            <Button variant="primary" onClick={onRepair} disabled={loading || repairing || allReady}>
              {repairing ? '处理中...' : '一键补齐'}
            </Button>
          </div>
        </div>

        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#0B4A3E]/10">
          <div
            className={`h-full rounded-full bg-[#0B4A3E] transition-all duration-300 ${busy ? 'loom-scan-line' : ''}`}
            style={{ width: `${Math.max(8, pct)}%` }}
          />
        </div>

        {error ? (
          <div className="mt-4 rounded-[12px] border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-sm text-status-danger">
            {error}
          </div>
        ) : null}

        <div className="mt-3 grid gap-2 md:grid-cols-5">
          {visibleChecks.map((check) => (
            <div key={check.id} className="rounded-[10px] border border-border/70 bg-surface/60 px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="truncate text-sm font-black text-text">{check.label}</div>
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                  check.status === 'ok' ? 'bg-status-success' : check.status === 'fail' ? 'bg-status-danger' : 'bg-[#0B4A3E]/50'
                }`} />
              </div>
              <div className="mt-1 truncate text-xs text-text-muted" title={check.message}>{check.message || displayDiagnosticLabel(check.status)}</div>
            </div>
          ))}
        </div>

        {checks.some((check) => check.detail) ? (
          <details className="mt-4 text-xs text-text-muted">
            <summary className="cursor-pointer font-bold text-text-subtle">查看检测详情</summary>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {checks.filter((check) => check.detail).map((check) => (
                <div key={check.id} className="rounded-[10px] border border-border/70 bg-surface/50 p-3">
                  <div className="font-bold text-text">{check.label}</div>
                  <div className="mt-1 break-all font-mono leading-5">{check.detail}</div>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
};

function supportsModelConfig(component?: ComponentSummary): boolean {
  return Boolean(component && MODEL_CONFIG_COMPONENT_IDS.has(component.id));
}

function canWriteAgentModelConfig(component: ComponentSummary, status?: AgentModelConfigStatus): boolean {
  return Boolean(status?.installed || ['ready', 'started', 'upgrade_available'].includes(component.status));
}

function modelConfigLabel(status?: AgentModelConfigStatus): string {
  if (!status) return '读取中';
  if (status.status === 'not_installed') return '未安装';
  if (status.status === 'no_wire') return '待同步模型';
  if (status.status === 'configured') return '已配置';
  if (status.status === 'failed') return '配置失败';
  if (status.status === 'unconfigured') return '未配置';
  return status.message || status.status || '未配置';
}

function modelConfigTone(status?: AgentModelConfigStatus): string {
  if (!status) return 'border-border/70 bg-surface-alt/50 text-text-muted';
  if (status.status === 'configured') return 'border-status-success/30 bg-status-success/10 text-status-success';
  if (status.status === 'failed') return 'border-status-danger/30 bg-status-danger/10 text-status-danger';
  if (status.status === 'not_installed' || status.status === 'no_wire') return 'border-border/70 bg-surface-alt/50 text-text-muted';
  return 'border-[#0B4A3E]/30 bg-[#0B4A3E]/10 text-[#0B4A3E]';
}

const AgentModelConfigPanel: React.FC<{
  component: ComponentSummary;
  status?: AgentModelConfigStatus;
  draftModel: string;
  busy: boolean;
  locked: boolean;
  onDraftModelChange: (value: string) => void;
  onApply: () => void;
  onApplyCustom: (draft: AgentCustomProviderDraft) => void;
  onRollback: () => void;
}> = ({ component, status, draftModel, busy, locked, onDraftModelChange, onApply, onApplyCustom, onRollback }) => {
  const [sourceMode, setSourceMode] = React.useState<'off' | 'oneClick' | 'custom'>('custom');
  const [customProviderId, setCustomProviderId] = React.useState('custom');
  const [customProvider, setCustomProvider] = React.useState('OpenAI 兼容');
  const [customBaseUrl, setCustomBaseUrl] = React.useState('');
  const [customApiKey, setCustomApiKey] = React.useState('');
  const availableModels = status?.availableModels || [];
  const canUseWire = Boolean(status?.installed && status.status !== 'no_wire');
  const managedBy = status?.managedBy || '';
  const isManagedAccount = managedBy === 'heang_account' || managedBy === 'newapi_account';
  const hasDraftModel = Boolean(draftModel.trim());
  const canApply = sourceMode === 'custom'
    ? canUseWire && hasDraftModel
    : canUseWire && availableModels.length > 0;
  const detail = status?.message || '读取模型配置状态';
  const oneClickLocked = locked || !canUseWire || !isManagedAccount || availableModels.length === 0;
  const customModelPlaceholder = '输入当前账号可用文本模型';
  const modelConfigTitle = isOpenClawComponent(component) ? 'OpenClaw 模型' : 'Codex / Claude Code 模型';
  const customProviderOption = providerOptionById(customProviderId);
  const customProviderName = customProviderId === 'custom' ? customProvider.trim() : customProviderOption.label;
  const canApplyCustom = Boolean(customProviderName && customBaseUrl.trim() && customApiKey.trim() && draftModel.trim());

  React.useEffect(() => {
    if (status?.managedBy !== 'custom_provider') return;
    const provider = status.provider || 'OpenAI 兼容';
    setSourceMode('custom');
    setCustomProvider(provider);
    setCustomProviderId(providerIdForLabel(provider));
    setCustomBaseUrl(status.baseUrl || '');
  }, [status?.managedBy, status?.provider, status?.baseUrl]);

  const selectCustomProvider = (providerId: string) => {
    const option = providerOptionById(providerId);
    setCustomProviderId(providerId);
    setCustomProvider(option.label);
    if (option.baseUrl) setCustomBaseUrl(option.baseUrl);
  };

  return (
    <section data-agent-model-config className="border-t border-border/70 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-black text-text">{modelConfigTitle}</div>
          <div className="mt-1 text-xs text-text-subtle">{component.name} 使用 LOOM 中转站模型配置</div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold ${modelConfigTone(status)}`}>
          {busy ? '配置中' : modelConfigLabel(status)}
        </span>
      </div>

      <div data-agent-model-source-card className="mt-4 rounded-[16px] border border-border/70 bg-surface-alt/35 p-4">
        <div className="text-sm font-black text-text">模型来源</div>
        <div className="mt-1 text-xs leading-5 text-text-muted">
          不接入额外配置时，启动时沿用该工具自带的默认设置。
        </div>
        <div className="mt-4 grid grid-cols-3 rounded-full border border-border/70 bg-app-bg/70 p-1">
          <button
            type="button"
            onClick={() => setSourceMode('off')}
            disabled={locked || busy}
            className={`h-10 rounded-full text-xs font-black transition ${sourceMode === 'off' ? 'bg-surface text-text shadow-sm' : 'text-text-muted hover:text-text'}`}
          >
            关闭
          </button>
          <button
            data-agent-one-click-config-lock
            type="button"
            onClick={() => {
              setSourceMode('oneClick');
              if (!oneClickLocked) onApply();
            }}
            disabled={oneClickLocked || busy}
            title={oneClickLocked ? '登录后解锁：请先同步中转站模型' : `一键写入 ${APP_DISPLAY_NAME} 托管模型`}
            className={`h-10 rounded-full text-xs font-black transition ${sourceMode === 'oneClick' ? 'bg-surface text-text shadow-sm' : 'text-text-muted hover:text-text'} disabled:cursor-not-allowed disabled:opacity-65`}
          >
            <span className="inline-flex items-center justify-center gap-2">
              <span className="flex h-4 w-4 items-center justify-center rounded-[4px] border border-current text-[10px] leading-none">
                {oneClickLocked ? '锁' : '开'}
              </span>
              一键配置
            </span>
          </button>
          <button
            type="button"
            onClick={() => setSourceMode('custom')}
            disabled={locked || busy}
            className={`h-10 rounded-full text-xs font-black transition ${sourceMode === 'custom' ? 'bg-[#0B6B57] text-white shadow-[0_12px_24px_rgba(11,107,87,0.22)]' : 'text-text-muted hover:text-text'}`}
          >
            自定义
          </button>
        </div>
        <div className="mt-3 text-xs text-text-muted">
          {sourceMode === 'custom'
            ? '自定义会先保存本机第三方 Provider；已安装智能体会继续写入配置。'
            : oneClickLocked ? '一键配置需登录后解锁，并同步中转站模型。' : '一键配置会写入当前中转站默认模型。'}
        </div>
      </div>

      {sourceMode === 'custom' ? (
        <div data-agent-custom-provider-card className="mt-4 rounded-[14px] border border-border/70 bg-surface-alt/25 p-4">
          <div className="grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
            <label className="block">
              <div className="mb-2 text-xs font-bold text-text-muted">Provider</div>
              <Select
                data-agent-custom-provider-select
                value={customProviderId}
                onChange={(event) => selectCustomProvider(event.target.value)}
                disabled={locked || busy}
                className="w-full"
              >
                {CUSTOM_PROVIDER_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </Select>
            </label>
            <label className="block">
              <div className="mb-2 text-xs font-bold text-text-muted">默认文本模型</div>
              <Input
                data-agent-custom-model-input
                value={draftModel}
                onChange={(event) => onDraftModelChange(event.target.value)}
                disabled={locked || busy}
                placeholder={customModelPlaceholder}
                className="w-full"
              />
            </label>
            {customProviderId === 'custom' ? (
              <label className="block md:col-span-2">
                <div className="mb-2 text-xs font-bold text-text-muted">Provider 名称</div>
                <Input
                  data-agent-custom-provider-name-input
                  value={customProvider}
                  onChange={(event) => setCustomProvider(event.target.value)}
                  disabled={locked || busy}
                  placeholder="自定义..."
                />
              </label>
            ) : null}
            <label className="block md:col-span-2">
              <div className="mb-2 text-xs font-bold text-text-muted">Base URL</div>
              <Input
                data-agent-custom-base-url-input
                value={customBaseUrl}
                onChange={(event) => setCustomBaseUrl(event.target.value)}
                disabled={locked || busy}
                placeholder="https://example.com/v1"
              />
            </label>
            <label className="block md:col-span-2">
              <div className="mb-2 flex items-center justify-between gap-3 text-xs font-bold text-text-muted">
                <span>API Key</span>
                <span className="text-[#0B6B57]">仅保存到本机受保护配置</span>
              </div>
              <Input
                data-agent-custom-api-key-input
                type="password"
                value={customApiKey}
                onChange={(event) => setCustomApiKey(event.target.value)}
                disabled={locked || busy}
                placeholder="粘贴自己的 API Key"
                autoComplete="off"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              onClick={() => onApplyCustom({
                provider: customProviderName,
                baseUrl: customBaseUrl,
                apiKey: customApiKey,
                model: draftModel,
              })}
              disabled={locked || busy || !canApplyCustom}
            >
              {busy ? '写入中...' : canUseWire ? '保存并写入' : '保存配置'}
            </Button>
            <Button variant="quiet" onClick={onRollback} disabled={locked || busy || !status?.backupAvailable}>
              回滚配置
            </Button>
            <span className="text-xs font-bold text-text-muted">密钥不会回显；换 Key 时重新粘贴即可覆盖。</span>
          </div>
        </div>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto]">
          <Select
            value={draftModel}
            onChange={(event) => onDraftModelChange(event.target.value)}
            disabled={locked || busy || sourceMode === 'off' || !canUseWire || availableModels.length === 0}
            className="w-full"
          >
            {(availableModels.length ? availableModels : [draftModel || status?.model]).filter(Boolean).map((model) => (
              <option key={model} value={model}>{model}</option>
            ))}
          </Select>
          <Button variant="primary" onClick={onApply} disabled={locked || busy || !canApply || sourceMode === 'off'}>
            {busy ? '写入中...' : '写入配置'}
          </Button>
          <Button variant="quiet" onClick={onRollback} disabled={locked || busy || !status?.backupAvailable}>
            回滚配置
          </Button>
        </div>
        )}

      <div className="mt-3 grid gap-2 text-xs text-text-muted md:grid-cols-3">
        <div className="truncate">模型：{status?.model || draftModel || '-'}</div>
        <div className="truncate">来源：{status?.provider || 'LOOM'}</div>
        <div className="truncate">{detail}</div>
      </div>
    </section>
  );
};

export const AgentInstallerPage: React.FC = () => {
  const cachedPreflight = React.useRef<DiagnosticReport | null>(loadCachedPreflight());
  const [snapshot, setSnapshot] = React.useState<ComponentSnapshot | null>(null);
  const [selectedId, setSelectedId] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [busyId, setBusyId] = React.useState('');
  const [busyAction, setBusyAction] = React.useState('');
  const [error, setError] = React.useState('');
  const [preflight, setPreflight] = React.useState<DiagnosticReport | null>(() => cachedPreflight.current);
  const [preflightLoading, setPreflightLoading] = React.useState(() => !cachedPreflight.current);
  const [preflightRepairing, setPreflightRepairing] = React.useState(false);
  const [preflightError, setPreflightError] = React.useState('');
  const [jobs, setJobs] = React.useState<BridgeJob[]>([]);
  const [installLog, setInstallLog] = React.useState<InstallLogEntry[]>([]);
  const [logError, setLogError] = React.useState('');
  const [modelConfigs, setModelConfigs] = React.useState<Record<string, AgentModelConfigStatus>>({});
  const [modelDrafts, setModelDrafts] = React.useState<Record<string, string>>({});
  const [modelConfigBusy, setModelConfigBusy] = React.useState('');

  const copyAgentAccessPrompt = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(buildOneShotAgentPrompt(buildMcpJson()));
      showToast('接入提示词已复制', 'success');
    } catch {
      showToast('复制失败，请打开 Agent 接入页手动复制', 'error');
    }
  }, []);

  const pushLog = React.useCallback((message: string, tone = 'neutral', componentId?: string) => {
    const entry: InstallLogEntry = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      componentId,
      message,
      tone,
      time: new Date().toLocaleTimeString(),
    };
    setInstallLog((current) => [...current, entry].slice(-40));
  }, []);

  const refreshJobs = React.useCallback(async () => {
    setLogError('');
    try {
      const result = await loomClient.jobs.list(20);
      setJobs(result.jobs || []);
    } catch (err: any) {
      setLogError(loomErrorText(err, '安装日志暂不可用'));
    }
  }, []);

  const recordJobProgress = React.useCallback((job: BridgeJob, componentId: string) => {
    setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 20));
    const message = job.progress?.message || job.message;
    if (message && message !== 'queued' && message !== 'running') {
      pushLog(message, job.progress?.tone || 'neutral', componentId);
    }
  }, [pushLog]);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSnapshot(await loomClient.components.status());
    } catch (err: any) {
      setError(loomErrorText(err, '安装清单读取失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshPreflight = React.useCallback(async (options: { preferCache?: boolean; force?: boolean } = {}) => {
    if (options.preferCache && !options.force) {
      const cached = loadCachedPreflight();
      if (cached) {
        cachedPreflight.current = cached;
        setPreflight(cached);
        setPreflightError('');
        setPreflightLoading(false);
        return;
      }
    }
    setPreflightLoading(true);
    setPreflightError('');
    try {
      const report = await loomClient.diagnostics.run();
      setPreflight(report);
      saveCachedPreflight(report);
    } catch (err: any) {
      setPreflightError(loomErrorText(err, '前置环境检测失败'));
    } finally {
      setPreflightLoading(false);
    }
  }, []);

  const refreshModelConfig = React.useCallback(async (componentId: string) => {
    if (!MODEL_CONFIG_COMPONENT_IDS.has(componentId)) return;
    try {
      const result = await loomClient.components.modelConfigStatus(componentId);
      const status = result.status;
      setModelConfigs((current) => ({ ...current, [componentId]: status }));
      setModelDrafts((current) => {
        if (current[componentId]) return current;
        const firstModel = status.model || status.availableModels?.[0] || '';
        return { ...current, [componentId]: firstModel };
      });
    } catch (err: any) {
      setModelConfigs((current) => ({
        ...current,
        [componentId]: {
          componentId,
          supported: true,
          configured: false,
          status: 'failed',
          message: loomErrorText(err, '模型配置状态读取失败'),
          availableModels: [],
        },
      }));
    }
  }, []);

  const repairPreflight = React.useCallback(async () => {
    const confirmPreflightRepair = await showConfirm({
      title: '安装/修复前置环境',
      message: 'LOOM 会检查并可能安装 Git、Node.js、Python、uv 或 WebView2，也可能处理本地运行环境。继续吗？',
      confirmText: '继续处理',
    });
    if (!confirmPreflightRepair) return;
    setPreflightRepairing(true);
    setPreflightError('');
    try {
      const next = await loomClient.diagnostics.repair({ confirmed: true });
      setPreflight(next.diagnostics);
      saveCachedPreflight(next.diagnostics);
      const hasFailedAction = next.actions.some((action) => action.status === 'fail');
      const hasWarnAction = next.actions.some((action) => action.status === 'warn');
      if (hasFailedAction) {
        showToast('前置环境处理未完成，请查看检测结果中的失败项', 'error');
      } else if (hasWarnAction) {
        showToast('前置环境仍有需要手动处理的项目，请查看检测结果', 'info');
      } else {
        showToast('已执行前置环境处理，请查看检测结果', 'success');
      }
    } catch (err: any) {
      setPreflightError(loomErrorText(err, '前置环境修复失败'));
      showToast(loomErrorText(err, '前置环境修复失败'), 'error');
    } finally {
      setPreflightRepairing(false);
    }
  }, []);

  const repairMissingPrerequisites = React.useCallback(async (currentReport: DiagnosticReport | null): Promise<DiagnosticReport> => {
    if (!prerequisiteNeedsRepair(currentReport)) {
      return currentReport as DiagnosticReport;
    }
    if (currentReport?.repairAvailable === false) {
      const blocking = blockingPrerequisiteIssues(currentReport);
      const names = blocking.map((check) => check.label || check.id).join('、') || '必要环境';
      throw new Error(`前置环境未就绪：${names}。请使用完整安装包或手动安装后重新检测。`);
    }
    setPreflightRepairing(true);
    setPreflightError('');
    try {
      const repaired = await loomClient.diagnostics.repair({ confirmed: true });
      const report = repaired.diagnostics;
      setPreflight(report);
      saveCachedPreflight(report);
      const blocking = blockingPrerequisiteIssues(report);
      if (blocking.length) {
        const names = blocking.map((check) => check.label || check.id).join('、');
        throw new Error(`前置环境仍未就绪：${names}。请查看检测详情后重试。`);
      }
      return report;
    } finally {
      setPreflightRepairing(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
    void refreshPreflight({ preferCache: true });
    void refreshJobs();
  }, [refresh, refreshJobs, refreshPreflight]);

  const components = componentRows(snapshot);
  React.useEffect(() => {
    if (!selectedId && components.length) setSelectedId(components[0].id);
  }, [components, selectedId]);

  const selected = components.find((item) => item.id === selectedId) || components[0];
  const selectedModelConfig = selected ? modelConfigs[selected.id] : undefined;
  const selectedModelDraft = selected ? (modelDrafts[selected.id] || selectedModelConfig?.model || selectedModelConfig?.availableModels?.[0] || '') : '';
  const readyCount = components.filter((item) => item.status === 'ready' || item.status === 'started').length;
  const installActionsLocked = manifestInstallLocked(snapshot);
  const selectedLogEntries = React.useMemo(() => {
    const selectedComponentId = selected?.id || '';
    const localEntries = installLog.filter((entry) => !selectedComponentId || !entry.componentId || entry.componentId === selectedComponentId);
    return [...jobHistoryEntries(jobs, selectedComponentId), ...localEntries].slice(-36).reverse();
  }, [installLog, jobs, selected?.id]);
  const visibleLogEntries = selectedLogEntries.slice(0, INSTALL_LOG_VISIBLE_LIMIT);
  const hiddenLogEntries = selectedLogEntries.slice(INSTALL_LOG_VISIBLE_LIMIT);
  const hiddenLogCount = hiddenLogEntries.length;

  React.useEffect(() => {
    if (!busyId) return undefined;
    const timer = window.setInterval(() => {
      void refreshJobs();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [busyId, refreshJobs]);

  React.useEffect(() => {
    if (!selected || !supportsModelConfig(selected)) return;
    void refreshModelConfig(selected.id);
  }, [refreshModelConfig, selected?.id, selected?.status]);

  const ensurePreflightReady = async (): Promise<DiagnosticReport | null> => {
    const cached = loadCachedPreflight();
    const reusablePreflight = preflightCacheUsable(preflight) ? preflight : cached;
    let report: DiagnosticReport | null = reusablePreflight;
    if (reusablePreflight) {
      cachedPreflight.current = reusablePreflight;
      setPreflight(reusablePreflight);
      setPreflightError('');
      setPreflightLoading(false);
    } else {
      setPreflightLoading(true);
      setPreflightError('');
      try {
        report = await loomClient.diagnostics.run();
        setPreflight(report);
        saveCachedPreflight(report);
      } catch (err: any) {
        const message = loomErrorText(err, '前置环境检测失败');
        setPreflightError(message);
        throw new Error(message);
      } finally {
        setPreflightLoading(false);
      }
    }

    report = await repairMissingPrerequisites(report);
    const blocking = blockingPrerequisiteIssues(report);
    if (blocking.length) {
      const names = blocking.map((check) => check.label || check.id).join('、');
      throw new Error(`前置环境未就绪：${names}。请先点“一键补齐”或查看检测详情。`);
    }
    return report;
  };

  const prepareComponent = async (
    component: ComponentSummary,
    options: { autoStart?: boolean; confirmAction?: boolean } = {},
  ) => {
    if (installActionsLocked) {
      const message = '安装清单未就绪，安装和启动暂不可用。请刷新后重试。';
      pushLog(message, 'warning', component.id);
      showToast(message, 'error');
      return;
    }
    const autoStart = options.autoStart ?? false;
    const shouldConfirm = options.confirmAction ?? true;
    if (shouldConfirm) {
      const ok = await showConfirm({
        title: `${component.status === 'upgrade_available' ? '升级' : '安装'} ${component.name}`,
        message: `${component.status === 'upgrade_available' ? '升级' : '安装'}前会先检测必要环境；缺失时会尝试补齐 Git / Node.js / Python 等工具，然后下载、安装并启动智能体。继续吗？`,
        confirmText: component.status === 'upgrade_available' ? '升级并启动' : '安装并启动',
      });
      if (!ok) return;
    }

    setBusyId(component.id);
    setBusyAction(autoStart ? 'prepare-start' : 'prepare');
    try {
      showToast(`开始处理 ${component.name}：检测前置环境`, 'info');
      pushLog(`开始处理 ${component.name}：检测前置环境`, 'neutral', component.id);
      await ensurePreflightReady();

      let next: ComponentSnapshot | null = null;
      try {
        next = await loomClient.components.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
        const detected = next.components.find((item) => item.id === component.id);
        if (needsInstallAfterDetect(detected)) {
          showToast(`${component.name} 检测到需安装或升级，开始下载并安装`, 'info');
          pushLog(`${component.name} 检测到需安装或升级，开始下载安装`, 'neutral', component.id);
          next = await loomClient.components.install(component.id, { confirmed: true, onProgress: (job) => recordJobProgress(job, component.id) });
          setSnapshot(next);
          next = await loomClient.components.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
          setSnapshot(next);
        }
      } catch {
        showToast(`${component.name} 未检测到可用安装，开始下载并安装`, 'info');
        pushLog(`${component.name} 未检测到可用安装，开始下载安装`, 'neutral', component.id);
        next = await loomClient.components.install(component.id, { confirmed: true, onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
        next = await loomClient.components.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
      }

      const current = next.components.find((item) => item.id === component.id);
      if (!current || !['ready', 'started'].includes(current.status)) {
        throw new Error(current?.errorMessage || `${component.name} 安装后仍未就绪，请打开诊断查看原因`);
      }

      if (autoStart) {
        const started = await loomClient.components.start(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(started);
        pushLog(`${component.name} 已检测、安装并启动`, 'ok', component.id);
        showToast(`${component.name} 已检测、安装并启动`, 'success');
      } else {
        pushLog(`${component.name} 已检测并安装就绪`, 'ok', component.id);
        showToast(`${component.name} 已检测并安装就绪`, 'success');
      }
      if (supportsModelConfig(component)) {
        void refreshModelConfig(component.id);
      }
    } catch (err: any) {
      const message = loomErrorText(err, err?.message || `${component.name} 准备失败`);
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
      try {
        const report = await loomClient.diagnostics.run();
        setPreflight(report);
        saveCachedPreflight(report);
      } catch {
        // Keep the component error visible if diagnostics cannot be refreshed.
      }
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const prepareAll = async () => {
    if (installActionsLocked) {
      showToast('安装清单未就绪，暂不能批量安装。', 'error');
      return;
    }
    const ok = await showConfirm({
      title: '一键安装',
      message: 'LOOM 会按顺序检测、下载并安装五个智能体。为了避免一次打开多个窗口，批量安装完成后不会批量启动。',
      confirmText: '开始安装',
    });
    if (!ok) return;
    for (const component of components) {
      await prepareComponent(component, { autoStart: false, confirmAction: false });
    }
  };

  const install = async (component: ComponentSummary) => {
    await prepareComponent(component, { autoStart: true });
  };

  const rollback = async (component: ComponentSummary) => {
    const ok = await showConfirm({
      title: `回滚 ${component.name}`,
      message: '当前版本会被替换为上一版本。确定继续吗？',
      confirmText: '回滚',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(component.id);
    setBusyAction('rollback');
    try {
      pushLog(`开始回滚 ${component.name}`, 'warning', component.id);
      const next = await loomClient.components.rollback(component.id);
      setSnapshot(next);
      if (supportsModelConfig(component)) void refreshModelConfig(component.id);
      pushLog(`${component.name} 已回滚`, 'ok', component.id);
      showToast(`${component.name} 已回滚`, 'info');
    } catch (err: any) {
      const message = loomErrorText(err, '回滚失败');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const uninstall = async (component: ComponentSummary) => {
    const ok = await showConfirm({
      title: `卸载 ${component.name}`,
      message: '这会删除 LOOM 管理的安装目录；如果智能体提供官方卸载命令，也会一并执行。确定继续吗？',
      confirmText: '一键卸载',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(component.id);
    setBusyAction('uninstall');
    try {
      pushLog(`开始卸载 ${component.name}`, 'warning', component.id);
      const next = await loomClient.components.uninstall(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      if (supportsModelConfig(component)) void refreshModelConfig(component.id);
      pushLog(`${component.name} 已卸载`, 'ok', component.id);
      showToast(`${component.name} 已卸载`, 'info');
    } catch (err: any) {
      const message = loomErrorText(err, '卸载失败');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const detect = async (component: ComponentSummary) => {
    if (installActionsLocked) {
      const message = '安装清单未就绪，暂不能检测。请先刷新清单。';
      pushLog(message, 'warning', component.id);
      showToast(message, 'error');
      return;
    }
    setBusyId(component.id);
    setBusyAction('detect');
    try {
      pushLog(`开始检测 ${component.name}`, 'neutral', component.id);
      const next = await loomClient.components.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      if (supportsModelConfig(component)) void refreshModelConfig(component.id);
      pushLog(`${component.name} 检测完成`, 'ok', component.id);
      showToast(`${component.name} 检测完成`, 'success');
    } catch (err: any) {
      const message = loomErrorText(err, '检测失败，请先安装或重新安装');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const start = async (component: ComponentSummary) => {
    if (installActionsLocked) {
      const message = '安装清单未就绪，启动暂不可用。请先刷新清单。';
      pushLog(message, 'warning', component.id);
      showToast(message, 'error');
      return;
    }
    setBusyId(component.id);
    setBusyAction('start');
    try {
      pushLog(`开始启动 ${component.name}`, 'neutral', component.id);
      const next = await loomClient.components.start(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      if (supportsModelConfig(component)) void refreshModelConfig(component.id);
      pushLog(`${component.name} 已提交启动`, 'ok', component.id);
      showToast(`${component.name} 已提交启动`, 'success');
    } catch (err: any) {
      const message = loomErrorText(err, '启动失败，请先检测安装状态');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const updateModelDraft = (componentId: string, model: string) => {
    setModelDrafts((current) => ({ ...current, [componentId]: model }));
  };

  const applyModelConfig = async (component: ComponentSummary) => {
    const model = (modelDrafts[component.id] || modelConfigs[component.id]?.model || '').trim();
    if (!model) {
      showToast('请先输入或选择模型', 'info');
      return;
    }
    setModelConfigBusy(component.id);
    try {
      const result = await loomClient.components.applyModelConfig({ componentId: component.id, model });
      setModelConfigs((current) => ({ ...current, [component.id]: result.status }));
      setModelDrafts((current) => ({ ...current, [component.id]: result.status.model || model }));
      pushLog(`${component.name} 模型配置已写入`, 'ok', component.id);
      showToast(`${component.name} 模型配置已写入`, 'success');
    } catch (err: any) {
      const message = loomErrorText(err, '模型配置写入失败');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refreshModelConfig(component.id);
    } finally {
      setModelConfigBusy('');
    }
  };

  const applyCustomModelConfig = async (component: ComponentSummary, draft: AgentCustomProviderDraft) => {
    const provider = draft.provider.trim() || '自定义 Provider';
    const baseUrl = draft.baseUrl.trim();
    const apiKey = draft.apiKey.trim();
    const model = draft.model.trim();
    if (!baseUrl || !apiKey || !model) {
      showToast('请填写 Base URL、API Key 和默认文本模型', 'error');
      return;
    }
    setModelConfigBusy(component.id);
    try {
      await loomClient.wire.custom({
        provider,
        baseUrl,
        apiKey,
        textModel: model,
      });
      let message = '第三方模型配置已保存';
      if (canWriteAgentModelConfig(component, modelConfigs[component.id])) {
        const result = await loomClient.components.applyModelConfig({ componentId: component.id, model });
        setModelConfigs((current) => ({ ...current, [component.id]: result.status }));
        message = `${component.name} 第三方模型已保存并写入`;
      } else {
        await refreshModelConfig(component.id);
        message = '第三方模型已保存；安装智能体后可写入配置';
      }
      setModelDrafts((current) => ({ ...current, [component.id]: model }));
      pushLog(message, 'ok', component.id);
      showToast(message, 'success');
    } catch (err: any) {
      const message = loomErrorText(err, '第三方模型配置失败');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refreshModelConfig(component.id);
    } finally {
      setModelConfigBusy('');
    }
  };

  const rollbackModelConfig = async (component: ComponentSummary) => {
    setModelConfigBusy(component.id);
    try {
      const result = await loomClient.components.rollbackModelConfig(component.id);
      setModelConfigs((current) => ({ ...current, [component.id]: result.status }));
      pushLog(`${component.name} 模型配置已回滚`, 'ok', component.id);
      showToast(`${component.name} 模型配置已回滚`, 'info');
    } catch (err: any) {
      const message = loomErrorText(err, '模型配置回滚失败');
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refreshModelConfig(component.id);
    } finally {
      setModelConfigBusy('');
    }
  };

  const copyInstallLog = async () => {
    const text = formatInstallLogEntries(selectedLogEntries);
    if (!text) {
      showToast('暂无可复制的日志', 'info');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast('日志已复制', 'success');
    } catch {
      showToast('复制日志失败，请展开后手动选择复制', 'error');
    }
  };

  const exportInstallLog = () => {
    const text = formatInstallLogEntries(selectedLogEntries);
    if (!text) {
      showToast('暂无可导出的日志', 'info');
      return;
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `loom-install-log-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('日志已导出', 'success');
  };

  const openWeb = async (component: ComponentSummary) => {
    if (isOpenClawComponent(component)) {
      if (!['ready', 'started', 'upgrade_available'].includes(component.status)) {
        const message = '请先安装 OpenClaw，再打开网页版';
        pushLog(message, 'warning', component.id);
        showToast(message, 'error');
        return;
      }
      setBusyId(component.id);
      setBusyAction('open-web');
      try {
        const status = await loomClient.process.status();
        if (!status.running) {
          if (!status.starting) {
            await loomClient.process.start();
          }
          await loomClient.process.waitForReady({ timeoutMs: 180000, intervalMs: 800 });
        }
        window.open(OPENCLAW_WEB_URL, '_blank', 'noopener,noreferrer');
        pushLog('OpenClaw 网页版已打开', 'ok', component.id);
        showToast('OpenClaw 网页版已打开', 'success');
      } catch (err: any) {
        const detail = loomErrorText(err, '');
        const message = detail ? `OpenClaw 网页版启动失败：${detail}` : 'OpenClaw 网页版启动失败';
        pushLog(message, 'danger', component.id);
        showToast(message, 'error');
      } finally {
        setBusyId('');
        setBusyAction('');
      }
      return;
    }
    const url = componentWebUrl(component);
    if (!url) {
      showToast('暂无可打开的网页', 'info');
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const activeBusyName = busyId
    ? components.find((item) => item.id === busyId)?.name || ''
    : modelConfigBusy
      ? components.find((item) => item.id === modelConfigBusy)?.name || ''
      : '';
  const preflightBusy = preflightLoading || preflightRepairing;
  const blockingBusy = loading || Boolean(busyId) || Boolean(modelConfigBusy);
  const busyOverlayActive = blockingBusy || preflightBusy;
  const pageLocked = blockingBusy;
  const controlsLocked = blockingBusy;
  const busyOverlayMode = preflightBusy && !blockingBusy ? 'corner' : 'blocking';
  const busyOverlayTitle = modelConfigBusy
    ? '正在写入模型配置'
    : preflightRepairing
    ? '正在修复前置环境'
    : preflightLoading
      ? '正在检测前置环境'
      : loading
        ? '正在读取安装清单'
        : busyAction === 'detect'
          ? '正在检测安装状态'
          : busyAction === 'open-web'
            ? '正在打开 OpenClaw 网页版'
            : busyAction === 'start'
              ? '正在启动智能体'
            : busyAction === 'uninstall'
              ? '正在卸载智能体'
              : busyAction === 'rollback'
                ? '正在回滚智能体'
                : '正在安装或升级智能体';
  const busyOverlayDetail = activeBusyName
    ? `${activeBusyName} 正在处理，请稍候。`
    : `${APP_DISPLAY_NAME} 正在检查本机环境和安装状态。`;

  return (
    <div
      data-agent-page-scroll
      data-white-label-layout="installer"
      data-agent-page-locked={pageLocked ? 'true' : undefined}
      aria-busy={busyOverlayActive}
      className={`loom-white-page loom-installer-shell h-full bg-app-bg ${pageLocked ? 'overflow-y-hidden' : 'overflow-y-auto'}`}
    >
      <BusyOverlay active={busyOverlayActive} mode={busyOverlayMode} title={busyOverlayTitle} detail={busyOverlayDetail} />
      <div className="mx-auto flex w-full max-w-[1220px] flex-col gap-6 px-8 py-7">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">安装</div>
            <h1 className="mt-2 text-[38px] font-black leading-tight text-text">安装智能体</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
              先检查必要环境，再安装、更新或启动智能体。高级信息默认收起。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-border/70 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text">
              {readyCount}/{components.length} 已就绪
            </span>
            <Button variant={installActionsLocked ? 'quiet' : 'primary'} onClick={() => void prepareAll()} disabled={controlsLocked || installActionsLocked || !components.length}>
              {installActionsLocked ? '清单未就绪' : busyAction === 'prepare' ? '安装中...' : '一键安装'}
            </Button>
            <Button variant="quiet" onClick={refresh} disabled={controlsLocked}>刷新</Button>
          </div>
        </header>

        <section data-agent-page-shell className="loom-panel loom-installer-stage border-y border-border/80 bg-surface/55">
          {snapshot?.warning ? (
            <div className="border-b border-border/70 px-6 py-4 text-sm text-status-warning">
              {snapshot.warning}
            </div>
          ) : null}

          <CompactPrerequisitePanel
            report={preflight}
            loading={preflightLoading}
            repairing={preflightRepairing}
            error={preflightError}
            installLocked={installActionsLocked}
            onRefresh={() => void refreshPreflight({ force: true })}
            onRepair={() => void repairPreflight()}
          />

          <section data-agent-access-inline className="border-t border-border/70 px-6 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-[14px] border border-[#0B4A3E]/15 bg-[#0B4A3E]/[0.035] px-4 py-3">
              <div className="min-w-0">
                <div className="text-[10px] font-black tracking-[0.24em] text-accent">AGENT 接入</div>
                <h2 className="mt-1 text-base font-black text-text">让 Codex / Claude Code 控制 LOOM</h2>
                <p className="mt-1 text-xs leading-5 text-text-muted">
                  一条提示词接入 CLI/MCP，支持安装智能体、生图、生视频、手机矩阵和只读监控。
                </p>
              </div>
              <Button variant="quiet" onClick={() => void copyAgentAccessPrompt()}>
                复制接入提示词
              </Button>
            </div>
          </section>

          <section className="border-t border-border/70 px-6 py-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">可安装智能体</div>
                <h2 className="mt-1 text-2xl font-black text-text">Codex / Claude Code / opencode / OpenClaw / Hermes</h2>
              </div>
              {error ? <span className="text-sm font-bold text-status-danger">{error}</span> : null}
            </div>

            <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,0.92fr)_minmax(420px,1.08fr)]">
              <div>
                {loading ? (
                  <div className="border-t border-border/70 py-5 text-sm text-text-muted">正在读取安装清单...</div>
                ) : (
                  <div className="border-y border-border/70 bg-surface/30">
                    {components.map((component, index) => (
                      <button
                        type="button"
                        key={component.id}
                        onClick={() => setSelectedId(component.id)}
                        disabled={controlsLocked}
                        className={`flex w-full items-center gap-4 border-b border-border/60 px-4 py-4 text-left transition last:border-b-0 ${
                          selected?.id === component.id
                            ? 'bg-accent/[0.07]'
                            : controlsLocked ? '' : 'hover:bg-surface-alt/45'
                        }`}
                      >
                        <span className="w-5 text-center text-xs font-black text-text-subtle">{index + 1}</span>
                        <AgentLogo id={component.id} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-base font-black text-text">{component.name}</span>
                          <span className="mt-1 block truncate text-xs text-text-muted">{component.description || component.id}</span>
                        </span>
                        <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${statusClass(component.status)}`}>
                          {isWorking(component.status) ? <ActivityRing /> : null}
                          {displayStatusLabel(component.status)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="min-w-0 border-t border-border/70 pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
                {selected ? (
                  <div className="space-y-6">
                    <div className="flex items-start justify-between gap-5">
                      <div className="flex min-w-0 items-start gap-4">
                        <AgentLogo id={selected.id} size="large" />
                        <div className="min-w-0">
                          <div className="text-[11px] font-bold uppercase tracking-[0.3em] text-text-subtle">
                            {selected.category || 'component'} / {selected.platform} / {selected.arch}
                          </div>
                          <h2 className="mt-2 truncate text-[34px] font-black leading-tight text-text">{selected.name}</h2>
                          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">{selected.description || selected.id}</p>
                        </div>
                      </div>
                      <span className={`rounded-full border px-3 py-1.5 text-xs font-black ${statusClass(selected.status)}`}>
                        {displayStatusLabel(selected.status)}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-x-5 gap-y-4 xl:grid-cols-4">
                      <InfoTile label="版本" value={selected.version} />
                      <InfoTile label="已安装" value={selected.installedVersion || '-'} />
                      <InfoTile label="大小" value={formatSize(selected.size)} />
                      <InfoTile label="类型" value={selected.type} />
                    </div>

                    {installActionsLocked ? (
                      <div className="rounded-[16px] border border-status-warning/30 bg-status-warning/10 p-4 text-sm font-bold text-status-warning">
                        安装清单未就绪，暂时不能安装或启动。请刷新后重试。
                      </div>
                    ) : selected.errorMessage ? (
                      <div className="rounded-[16px] border border-status-danger/30 bg-status-danger/10 p-4 text-sm text-status-danger">
                        {selected.errorMessage}
                      </div>
                    ) : isWorking(selected.status) ? (
                      <div className="rounded-[16px] border border-[#0B4A3E]/30 bg-[#0B4A3E]/10 p-4 text-sm font-bold text-[#0B4A3E]">
                        <span className="inline-flex items-center gap-2">
                          <ActivityRing />
                          {displayStatusLabel(selected.status)}{selected.jobId ? ` · ${selected.jobId}` : ''}
                        </span>
                      </div>
                    ) : selected.status === 'upgrade_available' ? (
                      <div className="rounded-[16px] border border-status-success/35 bg-status-success/10 p-4 text-sm font-bold text-status-success">
                        检测到可升级版本。点击下方绿色“升级并启动”即可更新并启动。
                      </div>
                    ) : selected.status === 'ready' || selected.status === 'started' ? (
                      <div className="rounded-[16px] border border-status-success/30 bg-status-success/10 p-4 text-sm text-status-success">
                        {selected.status === 'started' ? '已启动' : '已安装，可启动'}
                      </div>
                    ) : selected.status === 'simulation_ready' ? (
                      <div className="rounded-[16px] border border-border/70 bg-surface-alt/50 p-4 text-sm text-text-muted">
                        还没确认本机安装状态。可以直接点击“安装”，LOOM 会先检测必要环境。
                      </div>
                    ) : selected.status === 'manual_install_required' ? (
                      <div className="rounded-[16px] border border-border/70 bg-surface-alt/50 p-4 text-sm text-text-muted">
                        已发现本机安装器。建议点击“安装”接管流程，完成后再启动。
                      </div>
                    ) : null}

                    <div className="flex flex-wrap gap-3">
                      <Button
                        variant={installActionsLocked ? 'quiet' : 'primary'}
                        className="min-w-[132px]"
                        onClick={() => void (primaryAgentAction(selected) === 'start' ? start(selected) : install(selected))}
                        disabled={controlsLocked || installActionsLocked || isWorking(selected.status)}
                      >
                        {installActionsLocked ? '清单未就绪' : primaryAgentButtonLabel(selected, busyId, busyAction)}
                      </Button>
                      <Button
                        variant="quiet"
                        onClick={() => detect(selected)}
                        disabled={controlsLocked || installActionsLocked || isWorking(selected.status)}
                      >
                        {installActionsLocked ? '等待清单' : busyId === selected.id && busyAction === 'detect' ? '检测中...' : '重新检测'}
                      </Button>
                      {isOpenClawComponent(selected) ? (
                        <Button
                          data-agent-open-web-button
                          variant="quiet"
                          onClick={() => void openWeb(selected)}
                          disabled={controlsLocked || installActionsLocked || !isComponentInstalled(selected)}
                        >
                          打开网页
                        </Button>
                      ) : null}
                      {['ready', 'started'].includes(selected.status) ? (
                        <Button
                          variant="quiet"
                          onClick={() => install(selected)}
                          disabled={controlsLocked || installActionsLocked || isWorking(selected.status)}
                        >
                          {busyId === selected.id && busyAction === 'prepare' ? '安装中...' : '重新安装'}
                        </Button>
                      ) : null}
                      {isFailedStatus(selected.status) ? (
                        <Button
                          data-agent-retry-button
                          variant="danger"
                          onClick={() => install(selected)}
                          disabled={controlsLocked || installActionsLocked || isWorking(selected.status)}
                        >
                          重试安装
                        </Button>
                      ) : null}
                    </div>

                    {supportsModelConfig(selected) ? (
                      <AgentModelConfigPanel
                        component={selected}
                        status={selectedModelConfig}
                        draftModel={selectedModelDraft}
                        busy={modelConfigBusy === selected.id}
                        locked={controlsLocked}
                        onDraftModelChange={(value) => updateModelDraft(selected.id, value)}
                        onApply={() => void applyModelConfig(selected)}
                        onApplyCustom={(draft) => void applyCustomModelConfig(selected, draft)}
                        onRollback={() => void rollbackModelConfig(selected)}
                      />
                    ) : null}

                    <section data-agent-danger-zone className="border-t border-border/70 pt-4">
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-black text-text">更多操作</div>
                          <div className="mt-1 text-xs text-text-subtle">卸载会移除本机安装文件；回滚只在存在上一版本备份时可用。</div>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <Button
                            variant="quiet"
                            onClick={() => uninstall(selected)}
                            disabled={controlsLocked || installActionsLocked || isWorking(selected.status) || selected.status === 'not_installed'}
                          >
                            {busyId === selected.id && busyAction === 'uninstall' ? '卸载中...' : `卸载 ${selected.name}`}
                          </Button>
                          <Button
                            variant="quiet"
                            onClick={() => rollback(selected)}
                            disabled={controlsLocked || !selected.previousVersion}
                          >
                            {busyId === selected.id && busyAction === 'rollback' ? '回滚中...' : '回滚'}
                          </Button>
                        </div>
                      </div>
                    </section>

                    <section data-agent-log-panel className="border-t border-border/70 pt-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-black text-text">安装日志</div>
                          <div className="mt-1 text-xs text-text-subtle">默认显示最近 {INSTALL_LOG_VISIBLE_LIMIT} 条，完整历史可展开</div>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button data-agent-copy-log-button variant="quiet" onClick={() => void copyInstallLog()} disabled={!selectedLogEntries.length}>
                            复制日志
                          </Button>
                          <Button data-agent-export-log-button variant="quiet" onClick={exportInstallLog} disabled={!selectedLogEntries.length}>
                            导出日志
                          </Button>
                          <Button variant="quiet" onClick={() => void refreshJobs()} disabled={controlsLocked}>
                            刷新日志
                          </Button>
                        </div>
                      </div>
                      {logError ? (
                        <div className="mt-3 rounded-[12px] border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-xs text-status-warning">
                          {logError}
                        </div>
                      ) : null}
                      <div data-agent-log-compact className="mt-3 border-l border-border/80 pl-4">
                        {selectedLogEntries.length ? (
                          visibleLogEntries.map((entry) => (
                            <div key={entry.id} className="mb-3 last:mb-0">
                              <div className="text-[11px] font-bold text-text-subtle">{entry.time}</div>
                              <div className={`mt-1 text-xs leading-5 ${toneClass(entry.tone)}`}>{entry.message}</div>
                            </div>
                          ))
                        ) : (
                          <div className="py-3 text-xs leading-5 text-text-muted">
                            等待安装任务。点击“安装”“升级”或“启动”后，这里会显示实时进度和失败原因。
                          </div>
                        )}
                      </div>
                      {hiddenLogCount ? (
                        <details data-agent-log-full className="mt-3 rounded-[12px] border border-border/70 bg-surface-alt/35 px-3 py-2 text-xs text-text-muted">
                          <summary className="cursor-pointer font-bold text-text-subtle">
                            查看完整日志（多 {hiddenLogCount} 条）
                          </summary>
                          <div className="mt-3 border-l border-border/70 pl-4">
                            {hiddenLogEntries.map((entry) => (
                              <div key={entry.id} className="mb-3 last:mb-0">
                                <div className="text-[11px] font-bold text-text-subtle">{entry.time}</div>
                                <div className={`mt-1 text-xs leading-5 ${toneClass(entry.tone)}`}>{entry.message}</div>
                              </div>
                            ))}
                          </div>
                        </details>
                      ) : null}
                    </section>

                    <details data-agent-advanced-settings className="border-t border-border/70 pt-4">
                      <summary className="cursor-pointer text-sm font-bold text-text">高级详情</summary>
                      <div className="mt-4 space-y-2 text-xs text-text-muted">
                        <div className="font-mono">id: {selected.id}</div>
                        <div className="font-mono">entry: {selected.entry || '-'}</div>
                        <div className="font-mono">installPath: {selected.installPath || '-'}</div>
                        {selected.installCommand?.length ? (
                          <div className="break-all font-mono">install: {selected.installCommand.join(' ')}</div>
                        ) : null}
                        {selected.uninstallCommand?.length ? (
                          <div className="break-all font-mono">uninstall: {selected.uninstallCommand.join(' ')}</div>
                        ) : null}
                        {selected.officialUrl ? (
                          <button
                            type="button"
                            onClick={() => window.open(selected.officialUrl || '', '_blank', 'noopener,noreferrer')}
                            className="font-mono text-accent hover:text-accent-hover"
                          >
                            officialUrl: {selected.officialUrl}
                          </button>
                        ) : null}
                        {selected.urls.slice(0, 4).map((url) => (
                          <div key={url} className="truncate font-mono" title={url}>{url}</div>
                        ))}
                      </div>
                    </details>
                  </div>
                ) : (
                  <div className="py-10 text-sm text-text-muted">选择一个智能体</div>
                )}
              </div>
            </div>
          </section>
        </section>
      </div>
    </div>
  );
};
