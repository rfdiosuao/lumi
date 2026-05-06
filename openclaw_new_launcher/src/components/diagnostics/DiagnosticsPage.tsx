import React from 'react';
import { Button, showToast } from '../common';
import { diagnosticsApi, type DiagnosticCheck, type DiagnosticReport, type DiagnosticRepairResult, type DiagnosticStatus } from '../../services/api';

const toneMap: Record<DiagnosticStatus, {
  label: string;
  dot: string;
  badge: string;
  panel: string;
}> = {
  ok: {
    label: '正常',
    dot: 'bg-status-success shadow-[0_0_12px_rgba(22,199,132,0.55)]',
    badge: 'border-status-success/30 bg-status-success/10 text-status-success',
    panel: 'border-status-success/25 bg-status-success/10',
  },
  warn: {
    label: '需注意',
    dot: 'bg-status-warning shadow-[0_0_12px_rgba(245,158,11,0.55)]',
    badge: 'border-status-warning/30 bg-status-warning/10 text-status-warning',
    panel: 'border-status-warning/25 bg-status-warning/10',
  },
  fail: {
    label: '阻塞',
    dot: 'bg-status-danger shadow-[0_0_12px_rgba(255,77,109,0.55)]',
    badge: 'border-status-danger/30 bg-status-danger/10 text-status-danger',
    panel: 'border-status-danger/25 bg-status-danger/10',
  },
};

function statusPriority(status: DiagnosticStatus): number {
  if (status === 'fail') return 0;
  if (status === 'warn') return 1;
  return 2;
}

const CheckRow: React.FC<{ check: DiagnosticCheck }> = ({ check }) => {
  const tone = toneMap[check.status] || toneMap.warn;
  return (
    <div className={`rounded-xl border p-4 ${tone.panel}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${tone.dot}`} />
            <h3 className="text-sm font-bold text-text">{check.label}</h3>
          </div>
          <p className="mt-2 text-sm text-text-muted">{check.message}</p>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-bold ${tone.badge}`}>
          {tone.label}
        </span>
      </div>
      {check.detail && (
        <div className="mt-3 break-all rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs leading-relaxed text-text-subtle">
          {check.detail}
        </div>
      )}
    </div>
  );
};

const ActionRow: React.FC<{ action: DiagnosticRepairResult['actions'][number] }> = ({ action }) => (
  <div className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
    <span className="text-sm font-medium text-text">{action.label}</span>
    <span className="text-xs text-text-muted">{action.message}</span>
  </div>
);

export const DiagnosticsPage: React.FC = () => {
  const [report, setReport] = React.useState<DiagnosticReport | null>(null);
  const [actions, setActions] = React.useState<DiagnosticRepairResult['actions']>([]);
  const [loading, setLoading] = React.useState(false);
  const [repairing, setRepairing] = React.useState(false);

  const runDiagnostics = React.useCallback(async () => {
    setLoading(true);
    try {
      const result = await diagnosticsApi.run();
      setReport(result);
      setActions([]);
    } catch (error: any) {
      showToast(`诊断失败: ${error?.error || error}`, 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    runDiagnostics();
  }, [runDiagnostics]);

  const handleRepair = async () => {
    setRepairing(true);
    try {
      const result = await diagnosticsApi.repair();
      setActions(result.actions || []);
      setReport(result.diagnostics);
      showToast('一键修复已完成', 'success');
    } catch (error: any) {
      showToast(`修复失败: ${error?.error || error}`, 'error');
    } finally {
      setRepairing(false);
    }
  };

  const sortedChecks = React.useMemo(() => {
    return [...(report?.checks || [])].sort((a, b) => statusPriority(a.status) - statusPriority(b.status));
  }, [report]);

  const summaryTone = toneMap[report?.summary?.status || 'warn'];

  return (
    <div className="flex h-full flex-col overflow-hidden bg-transparent">
      <div className="flex h-[72px] shrink-0 items-center justify-between border-b border-white/10 bg-surface/70 px-8 backdrop-blur-xl">
        <div>
          <h1 className="text-xl font-bold text-text">环境诊断</h1>
          <p className="mt-1 text-sm text-text-muted">检查授权、API、端口、运行时和残留进程</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="quiet" onClick={runDiagnostics} disabled={loading || repairing}>
            {loading ? '诊断中...' : '重新诊断'}
          </Button>
          <Button variant="primary" onClick={handleRepair} disabled={loading || repairing}>
            {repairing ? '修复中...' : '一键修复'}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-8">
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-4">
            <section className={`rounded-2xl border p-5 ${summaryTone.panel}`}>
              <div className="flex items-center gap-3">
                <span className={`h-3 w-3 rounded-full ${summaryTone.dot}`} />
                <div>
                  <div className="text-sm font-bold text-text">整体状态</div>
                  <div className="text-2xl font-black text-text">{summaryTone.label}</div>
                </div>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                  <div className="text-lg font-black text-status-success">{report?.summary?.ok ?? '-'}</div>
                  <div className="text-[11px] text-text-subtle">正常</div>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                  <div className="text-lg font-black text-status-warning">{report?.summary?.warnings ?? '-'}</div>
                  <div className="text-[11px] text-text-subtle">注意</div>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/15 p-3">
                  <div className="text-lg font-black text-status-danger">{report?.summary?.failed ?? '-'}</div>
                  <div className="text-[11px] text-text-subtle">阻塞</div>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
              <h2 className="text-sm font-bold text-text">当前安装</h2>
              <div className="mt-3 break-all rounded-lg border border-white/10 bg-black/20 px-3 py-2 font-mono text-xs text-text-subtle">
                {report?.basePath || '等待诊断结果...'}
              </div>
              <div className="mt-4 flex items-center justify-between text-sm">
                <span className="text-text-muted">服务 PID</span>
                <span className="font-mono text-text">{report?.servicePid || '未运行'}</span>
              </div>
            </section>

            {actions.length > 0 && (
              <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                <h2 className="text-sm font-bold text-text">修复记录</h2>
                <div className="mt-3 space-y-2">
                  {actions.map((action, index) => (
                    <ActionRow key={`${action.label}-${index}`} action={action} />
                  ))}
                </div>
              </section>
            )}
          </aside>

          <section className="min-w-0 rounded-2xl border border-white/10 bg-white/[0.035] p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-text-subtle">检查项</h2>
              <span className="text-xs text-text-muted">{report?.summary?.total ?? 0} items</span>
            </div>
            <div className="space-y-3">
              {sortedChecks.map((check) => (
                <CheckRow key={check.id} check={check} />
              ))}
              {!loading && sortedChecks.length === 0 && (
                <div className="rounded-xl border border-white/10 bg-black/20 p-8 text-center text-sm text-text-muted">
                  暂无诊断结果
                </div>
              )}
              {loading && (
                <div className="rounded-xl border border-white/10 bg-black/20 p-8 text-center text-sm text-text-muted">
                  正在检查本机环境...
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
