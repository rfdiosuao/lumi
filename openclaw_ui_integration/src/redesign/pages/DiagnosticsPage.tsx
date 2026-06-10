import React from 'react';
import { Download, RefreshCcw, Wrench } from 'lucide-react';
import { Button, Chip, EmptyState, InlineState, Panel, SectionHeader, StatTile } from '../components/ui';
import { exportDiagnostics, loadDiagnosticsSnapshot, repairDiagnostics } from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';
import { CodeBlock } from '../components/ui';

export function DiagnosticsPage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadDiagnosticsSnapshot(settings), [settings], { cacheKey: "diagnostics", ttlMs: 60000 });
  const [busy, setBusy] = React.useState(false);

  const handleRepair = async () => {
    setBusy(true);
    try {
      const result = await repairDiagnostics(settings);
      pushToast({ tone: 'ok', title: '修复完成', detail: `已执行 ${result.data?.actions?.length || 0} 个动作` });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '修复失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    setBusy(true);
    try {
      const result = await exportDiagnostics(settings);
      pushToast({ tone: 'ok', title: '诊断包已导出', detail: result.data?.filename || '导出完成' });
    } catch (err) {
      pushToast({ tone: 'danger', title: '导出失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">环境检测</div>
          <h1>环境检测要像报告，不像一堆报错弹窗。</h1>
          <p>检测、修复和导出都放在同一页，方便邀请制内测时快速定位机器问题。</p>
        </div>
        <div className="hero-actions">
          <Button variant="primary" icon={RefreshCcw} onClick={refresh}>刷新</Button>
          <Button variant="secondary" icon={Wrench} onClick={handleRepair} disabled={busy}>修复</Button>
          <Button variant="secondary" icon={Download} onClick={handleExport} disabled={busy}>导出</Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatTile label="状态" value={toCnStatus(data?.summary.status || 'warn')} hint={`${data?.summary.ok ?? 0}/${data?.summary.total ?? 0} 项检测`} tone={data?.summary.status === 'ok' ? 'ok' : data?.summary.status === 'warn' ? 'warn' : 'danger'} />
        <StatTile label="警告" value={data?.summary.warnings ?? 0} tone="warn" />
        <StatTile label="失败" value={data?.summary.failed ?? 0} tone={data?.summary.failed ? 'danger' : 'ok'} />
        <StatTile label="可修复" value={data?.repairAvailable ? '是' : '否'} tone={data?.repairAvailable ? 'ok' : 'warn'} />
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取诊断信息...</Panel>
      ) : error ? (
        <Panel className="panel-error"><InlineState tone="danger" title="诊断信息读取失败" description={error} /></Panel>
      ) : data ? (
        <section className="content-grid content-grid-diagnostics">
          <Panel className="surface-panel">
            <SectionHeader eyebrow="检测项" title="健康报告" subtitle="每一项直接映射诊断报告里的状态、消息和详情。" action={<Chip tone={data.source === 'live' ? 'ok' : 'warn'}>{sourceLabel(data.source)}</Chip>} />
            <div className="check-list">
              {data.checks.map((check) => (
                <div key={check.id} className={`check-row check-row-${check.status}`}>
                  <div className="check-head">
                    <strong>{check.label}</strong>
                    <Chip tone={check.status === 'ok' ? 'ok' : check.status === 'warn' ? 'warn' : 'danger'}>{toCnStatus(check.status)}</Chip>
                  </div>
                  <div className="check-message">{check.message}</div>
                  {check.detail ? <div className="check-detail">{check.detail}</div> : null}
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="运行时" title="启动上下文" subtitle="这些字段对应后端诊断返回值。" />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">根路径</span><span className="detail-value">{data.basePath}</span></div>
              <div className="detail-row"><span className="detail-label">服务运行</span><span className="detail-value">{data.serviceRunning ? '是' : '否'}</span></div>
              <div className="detail-row"><span className="detail-label">PID</span><span className="detail-value">{data.servicePid ?? '未知'}</span></div>
              <div className="detail-row"><span className="detail-label">启动状态</span><span className="detail-value">{data.startupState}</span></div>
              <div className="detail-row"><span className="detail-label">启动错误</span><span className="detail-value">{data.startupError || '无'}</span></div>
            </div>
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="产物" title="导出与修复记录" subtitle="保留可追踪的诊断产物，方便内测用户反馈。" />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">快照路径</span><span className="detail-value">{data.startupSnapshotPath || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">已耗时</span><span className="detail-value">{data.startupElapsedSec}s</span></div>
              <div className="detail-row"><span className="detail-label">超时</span><span className="detail-value">{data.startupTimeoutSec}s</span></div>
            </div>
            <CodeBlock text={JSON.stringify(data.summary, null, 2)} maxHeight={220} />
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="导出" title="修复结果" subtitle="适配层会返回修复动作列表和更新后的诊断对象。" />
            {busy ? <div className="panel-loading-inline">处理中...</div> : <EmptyState title="当前没有任务" description="使用上方按钮触发修复或导出。" />}
          </Panel>
        </section>
      ) : null}
    </div>
  );
}

function toCnStatus(value: string) {
  const map: Record<string, string> = {
    ok: '正常',
    warn: '警告',
    fail: '失败',
  };
  return map[String(value || '').toLowerCase()] || value;
}

function sourceLabel(value: string) {
  const map: Record<string, string> = {
    mock: '预览',
    live: '真实接口',
    mixed: '混合',
  };
  return map[value] || value;
}
