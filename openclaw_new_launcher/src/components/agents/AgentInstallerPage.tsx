import React from 'react';
import {
  componentApi,
  diagnosticsApi,
  jobApi,
  parseErrorText,
  type BridgeJob,
  type ComponentSnapshot,
  type ComponentSummary,
  type DiagnosticCheck,
  type DiagnosticReport,
  type DiagnosticStatus,
} from '../../services/api';
import { BusyOverlay, Button, showConfirm, showToast } from '../common';
import { AgentLogo } from './AgentLogo';

const PINNED_COMPONENT_IDS = [
  'codex-desktop',
  'claude-code',
  'opencode',
  'openclaw-companion',
  'hermes',
];

const FALLBACK_COMPONENTS: Record<string, { name: string; description: string; category: string }> = {
  'codex-desktop': { name: 'Codex', description: 'OpenAI 编程智能体', category: 'agent' },
  'claude-code': { name: 'Claude Code', description: 'Anthropic 命令行编程智能体', category: 'agent' },
  opencode: { name: 'opencode', description: '终端优先的 AI 编程工具', category: 'agent' },
  'openclaw-companion': { name: 'OpenClaw', description: '多智能体编程工作台', category: 'agent' },
  hermes: { name: 'Hermes', description: 'Hermes 智能体运行时', category: 'agent' },
};

const PREREQ_IDS = ['python_runtime', 'node', 'npm', 'git', 'git_bash', 'uv', 'webview2', 'data_dir', 'portable_integrity'];

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
  onRefresh: () => void;
  onRepair: () => void;
}> = ({ report, loading, repairing, error, onRefresh, onRepair }) => {
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
    ? repairing ? '正在安装或修复必要组件...' : '正在检测 Python、Node、npm、Git...'
    : allReady ? '可以继续安装和启动智能体。' : '缺失项会优先处理，详情可展开查看。';

  return (
    <section className="px-6 py-5">
      <div className="rounded-[18px] border border-border/80 bg-surface/70 p-5 shadow-[0_18px_48px_rgba(8,35,48,0.06)]">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] ${
              allReady ? 'bg-status-success/12 text-status-success' : busy ? 'bg-[#0B4A3E]/10 text-[#0B4A3E]' : 'bg-surface-alt text-text-muted'
            }`}>
              {busy ? <ActivityRing /> : <span className="text-lg font-black">{allReady ? '✓' : '•'}</span>}
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-black tracking-[0.22em] text-text-subtle">前置环境</div>
              <h2 className="mt-0.5 text-xl font-black text-text">{title}</h2>
              <p className="mt-1 text-sm text-text-muted">{subtitle}</p>
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

        <div className="mt-5 h-2 overflow-hidden rounded-full bg-[#0B4A3E]/10">
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

        <div className="mt-4 grid gap-3 md:grid-cols-5">
          {visibleChecks.map((check) => (
            <div key={check.id} className="rounded-[12px] border border-border/70 bg-surface/60 px-3 py-3">
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

export const AgentInstallerPage: React.FC = () => {
  const [snapshot, setSnapshot] = React.useState<ComponentSnapshot | null>(null);
  const [selectedId, setSelectedId] = React.useState('');
  const [loading, setLoading] = React.useState(true);
  const [busyId, setBusyId] = React.useState('');
  const [busyAction, setBusyAction] = React.useState('');
  const [error, setError] = React.useState('');
  const [preflight, setPreflight] = React.useState<DiagnosticReport | null>(null);
  const [preflightLoading, setPreflightLoading] = React.useState(true);
  const [preflightRepairing, setPreflightRepairing] = React.useState(false);
  const [preflightError, setPreflightError] = React.useState('');
  const [jobs, setJobs] = React.useState<BridgeJob[]>([]);
  const [installLog, setInstallLog] = React.useState<InstallLogEntry[]>([]);
  const [logError, setLogError] = React.useState('');

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
      const result = await jobApi.list(20);
      setJobs(result.jobs || []);
    } catch (err: any) {
      setLogError(parseErrorText(err) || '安装日志暂不可用');
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
      setSnapshot(await componentApi.status());
    } catch (err: any) {
      setError(parseErrorText(err) || '组件目录读取失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshPreflight = React.useCallback(async () => {
    setPreflightLoading(true);
    setPreflightError('');
    try {
      setPreflight(await diagnosticsApi.run());
    } catch (err: any) {
      setPreflightError(parseErrorText(err) || '前置环境检测失败');
    } finally {
      setPreflightLoading(false);
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
      const next = await diagnosticsApi.repair({ confirmed: true });
      setPreflight(next.diagnostics);
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
      setPreflightError(parseErrorText(err) || '前置环境修复失败');
      showToast(parseErrorText(err) || '前置环境修复失败', 'error');
    } finally {
      setPreflightRepairing(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
    void refreshPreflight();
    void refreshJobs();
  }, [refresh, refreshJobs, refreshPreflight]);

  const components = componentRows(snapshot);
  React.useEffect(() => {
    if (!selectedId && components.length) setSelectedId(components[0].id);
  }, [components, selectedId]);

  const selected = components.find((item) => item.id === selectedId) || components[0];
  const readyCount = components.filter((item) => item.status === 'ready' || item.status === 'started').length;
  const selectedLogEntries = React.useMemo(() => {
    const selectedComponentId = selected?.id || '';
    const localEntries = installLog.filter((entry) => !selectedComponentId || !entry.componentId || entry.componentId === selectedComponentId);
    return [...jobHistoryEntries(jobs, selectedComponentId), ...localEntries].slice(-36).reverse();
  }, [installLog, jobs, selected?.id]);

  React.useEffect(() => {
    if (!busyId) return undefined;
    const timer = window.setInterval(() => {
      void refreshJobs();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [busyId, refreshJobs]);

  const ensurePreflightReady = async (): Promise<DiagnosticReport | null> => {
    setPreflightLoading(true);
    setPreflightError('');
    let report: DiagnosticReport | null = null;
    try {
      report = await diagnosticsApi.run();
      setPreflight(report);
    } catch (err: any) {
      const message = parseErrorText(err) || '前置环境检测失败';
      setPreflightError(message);
      throw new Error(message);
    } finally {
      setPreflightLoading(false);
    }

    const checks = prerequisiteChecks(report);
    const needsRepair = checks.some((check) => check.status !== 'ok');
    if (!needsRepair || report.repairAvailable === false) return report;

    setPreflightRepairing(true);
    try {
      const repaired = await diagnosticsApi.repair({ confirmed: true });
      setPreflight(repaired.diagnostics);
      return repaired.diagnostics;
    } finally {
      setPreflightRepairing(false);
    }
  };

  const prepareComponent = async (
    component: ComponentSummary,
    options: { autoStart?: boolean; confirmAction?: boolean } = {},
  ) => {
    const autoStart = options.autoStart ?? false;
    const shouldConfirm = options.confirmAction ?? true;
    if (shouldConfirm) {
      const ok = await showConfirm({
        title: `${component.status === 'upgrade_available' ? '升级' : '安装'} ${component.name}`,
        message: `${component.status === 'upgrade_available' ? '升级' : '安装'}前会先检测前置环境；缺失时会尝试补齐 Git / Node.js / Python 等工具，然后下载、安装并启动组件。继续吗？`,
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
        next = await componentApi.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
        const detected = next.components.find((item) => item.id === component.id);
        if (needsInstallAfterDetect(detected)) {
          showToast(`${component.name} 检测到需安装或升级，开始下载并安装`, 'info');
          pushLog(`${component.name} 检测到需安装或升级，开始下载安装`, 'neutral', component.id);
          next = await componentApi.install(component.id, { confirmed: true, onProgress: (job) => recordJobProgress(job, component.id) });
          setSnapshot(next);
          next = await componentApi.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
          setSnapshot(next);
        }
      } catch {
        showToast(`${component.name} 未检测到可用安装，开始下载并安装`, 'info');
        pushLog(`${component.name} 未检测到可用安装，开始下载安装`, 'neutral', component.id);
        next = await componentApi.install(component.id, { confirmed: true, onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
        next = await componentApi.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(next);
      }

      const current = next.components.find((item) => item.id === component.id);
      if (!current || !['ready', 'started'].includes(current.status)) {
        throw new Error(current?.errorMessage || `${component.name} 安装后仍未就绪，请打开诊断查看原因`);
      }

      if (autoStart) {
        const started = await componentApi.start(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
        setSnapshot(started);
        pushLog(`${component.name} 已检测、安装并启动`, 'ok', component.id);
        showToast(`${component.name} 已检测、安装并启动`, 'success');
      } else {
        pushLog(`${component.name} 已检测并安装就绪`, 'ok', component.id);
        showToast(`${component.name} 已检测并安装就绪`, 'success');
      }
    } catch (err: any) {
      const message = parseErrorText(err) || err?.message || `${component.name} 准备失败`;
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
      try {
        setPreflight(await diagnosticsApi.run());
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
    const ok = await showConfirm({
      title: '全部安装',
      message: 'LOOM 会按顺序检测、下载并安装五个组件。为了避免一次打开多个终端，批量安装完成后不会批量启动进程。',
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
      const next = await componentApi.rollback(component.id);
      setSnapshot(next);
      pushLog(`${component.name} 已回滚`, 'ok', component.id);
      showToast(`${component.name} 已回滚`, 'info');
    } catch (err: any) {
      const message = parseErrorText(err) || '回滚失败';
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
      message: '这会删除 LOOM 管理的组件目录；如果组件提供官方卸载命令，也会一并执行。确定继续吗？',
      confirmText: '一键卸载',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(component.id);
    setBusyAction('uninstall');
    try {
      pushLog(`开始卸载 ${component.name}`, 'warning', component.id);
      const next = await componentApi.uninstall(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      pushLog(`${component.name} 已卸载`, 'ok', component.id);
      showToast(`${component.name} 已卸载`, 'info');
    } catch (err: any) {
      const message = parseErrorText(err) || '卸载失败';
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
    setBusyId(component.id);
    setBusyAction('detect');
    try {
      pushLog(`开始检测 ${component.name}`, 'neutral', component.id);
      const next = await componentApi.detect(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      pushLog(`${component.name} 检测完成`, 'ok', component.id);
      showToast(`${component.name} 检测完成`, 'success');
    } catch (err: any) {
      const message = parseErrorText(err) || '检测失败，请先安装或重新安装';
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
    setBusyId(component.id);
    setBusyAction('start');
    try {
      pushLog(`开始启动 ${component.name}`, 'neutral', component.id);
      const next = await componentApi.start(component.id, { onProgress: (job) => recordJobProgress(job, component.id) });
      setSnapshot(next);
      pushLog(`${component.name} 已提交启动`, 'ok', component.id);
      showToast(`${component.name} 已提交启动`, 'success');
    } catch (err: any) {
      const message = parseErrorText(err) || '启动失败，请先检测组件状态';
      pushLog(message, 'danger', component.id);
      showToast(message, 'error');
      await refresh();
    } finally {
      void refreshJobs();
      setBusyId('');
      setBusyAction('');
    }
  };

  const activeBusyName = busyId ? components.find((item) => item.id === busyId)?.name || '' : '';
  const busyOverlayActive = loading || Boolean(busyId) || preflightLoading || preflightRepairing;
  const busyOverlayTitle = preflightRepairing
    ? '正在修复前置环境'
    : preflightLoading
      ? '正在检测前置环境'
      : loading
        ? '正在读取安装清单'
        : busyAction === 'detect'
          ? '正在检测组件'
          : busyAction === 'start'
            ? '正在启动组件'
            : busyAction === 'uninstall'
              ? '正在卸载组件'
              : busyAction === 'rollback'
                ? '正在回滚组件'
                : '正在安装或升级组件';
  const busyOverlayDetail = activeBusyName
    ? `${activeBusyName} 正在处理，请稍候。`
    : 'LOOM 正在检查本机环境和组件状态。';

  return (
    <div data-agent-page-scroll className="h-full overflow-y-auto bg-app-bg">
      <BusyOverlay active={busyOverlayActive} title={busyOverlayTitle} detail={busyOverlayDetail} />
      <div className="mx-auto flex w-full max-w-[1220px] flex-col gap-6 px-8 py-7">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">智能体</div>
            <h1 className="mt-2 text-[38px] font-black leading-tight text-text">智能体安装器</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-border/70 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text">
              {readyCount}/{components.length} 已就绪
            </span>
            <Button variant="primary" onClick={() => void prepareAll()} disabled={loading || Boolean(busyId) || !components.length}>
              {busyAction === 'prepare' ? '安装中...' : '全部安装'}
            </Button>
            <Button variant="quiet" onClick={refresh} disabled={loading || Boolean(busyId)}>刷新</Button>
          </div>
        </header>

        <section data-agent-page-shell className="border-y border-border/80 bg-surface/55">
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
            onRefresh={() => void refreshPreflight()}
            onRepair={() => void repairPreflight()}
          />

          <section className="border-t border-border/70 px-6 py-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">安装清单</div>
                <h2 className="mt-1 text-2xl font-black text-text">Codex / Claude Code / opencode / OpenClaw / Hermes</h2>
              </div>
              {error ? <span className="text-sm font-bold text-status-danger">{error}</span> : null}
            </div>

            <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,0.92fr)_minmax(420px,1.08fr)]">
              <div>
                {loading ? (
                  <div className="border-t border-border/70 py-5 text-sm text-text-muted">正在读取组件目录...</div>
                ) : (
                  <div className="border-y border-border/70 bg-surface/30">
                    {components.map((component, index) => (
                      <button
                        type="button"
                        key={component.id}
                        onClick={() => setSelectedId(component.id)}
                        className={`flex w-full items-center gap-4 border-b border-border/60 px-4 py-4 text-left transition last:border-b-0 ${
                          selected?.id === component.id
                            ? 'bg-accent/[0.07]'
                            : 'hover:bg-surface-alt/45'
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

                    {selected.errorMessage ? (
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
                        检测到可升级版本。点击下方绿色“升级并启动”按钮即可更新到清单版本并拉起组件。
                      </div>
                    ) : selected.status === 'ready' || selected.status === 'started' ? (
                      <div className="rounded-[16px] border border-status-success/30 bg-status-success/10 p-4 text-sm text-status-success">
                        {selected.status === 'started' ? '组件已启动' : '组件可用'}
                      </div>
                    ) : selected.status === 'simulation_ready' ? (
                      <div className="rounded-[16px] border border-border/70 bg-surface-alt/50 p-4 text-sm text-text-muted">
                        还没确认本机安装状态。可以直接点击“安装”，LOOM 会自动检测前置环境。
                      </div>
                    ) : selected.status === 'manual_install_required' ? (
                      <div className="rounded-[16px] border border-border/70 bg-surface-alt/50 p-4 text-sm text-text-muted">
                        安装器已保存。建议点击“安装”重新接管安装流程，或完成后重新检测。
                      </div>
                    ) : null}

                    <div className="flex flex-wrap gap-3">
                      <Button
                        variant="primary"
                        className="min-w-[132px]"
                        onClick={() => void (primaryAgentAction(selected) === 'start' ? start(selected) : install(selected))}
                        disabled={Boolean(busyId) || isWorking(selected.status)}
                      >
                        {primaryAgentButtonLabel(selected, busyId, busyAction)}
                      </Button>
                      <Button
                        variant="quiet"
                        onClick={() => detect(selected)}
                        disabled={Boolean(busyId) || isWorking(selected.status)}
                      >
                        {busyId === selected.id && busyAction === 'detect' ? '检测中...' : '重新检测'}
                      </Button>
                      {['ready', 'started'].includes(selected.status) ? (
                        <Button
                          variant="quiet"
                          onClick={() => install(selected)}
                          disabled={Boolean(busyId) || isWorking(selected.status)}
                        >
                          {busyId === selected.id && busyAction === 'prepare' ? '安装中...' : '重新安装'}
                        </Button>
                      ) : null}
                      {isFailedStatus(selected.status) ? (
                        <Button
                          data-agent-retry-button
                          variant="danger"
                          onClick={() => install(selected)}
                          disabled={Boolean(busyId) || isWorking(selected.status)}
                        >
                          重试安装
                        </Button>
                      ) : null}
                      <Button
                        variant="quiet"
                        onClick={() => uninstall(selected)}
                        disabled={Boolean(busyId) || isWorking(selected.status) || selected.status === 'not_installed'}
                      >
                        {busyId === selected.id && busyAction === 'uninstall' ? '卸载中...' : '一键卸载'}
                      </Button>
                      <Button
                        variant="quiet"
                        onClick={() => rollback(selected)}
                        disabled={Boolean(busyId) || !selected.previousVersion}
                      >
                        {busyId === selected.id && busyAction === 'rollback' ? '回滚中...' : '回滚'}
                      </Button>
                    </div>

                    <section data-agent-log-panel className="border-t border-border/70 pt-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-black text-text">安装日志</div>
                          <div className="mt-1 text-xs text-text-subtle">记录检测、下载、安装、启动、失败和重试结果</div>
                        </div>
                        <Button variant="quiet" onClick={() => void refreshJobs()} disabled={Boolean(busyId)}>
                          刷新日志
                        </Button>
                      </div>
                      {logError ? (
                        <div className="mt-3 rounded-[12px] border border-status-warning/30 bg-status-warning/10 px-3 py-2 text-xs text-status-warning">
                          {logError}
                        </div>
                      ) : null}
                      <div className="mt-3 border-l border-border/80 pl-4">
                        {selectedLogEntries.length ? (
                          selectedLogEntries.map((entry) => (
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
                    </section>

                    <details className="border-t border-border/70 pt-4">
                      <summary className="cursor-pointer text-sm font-bold text-text">高级信息</summary>
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
                  <div className="py-10 text-sm text-text-muted">选择一个组件</div>
                )}
              </div>
            </div>
          </section>
        </section>
      </div>
    </div>
  );
};
