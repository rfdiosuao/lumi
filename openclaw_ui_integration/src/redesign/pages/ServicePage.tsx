import React from 'react';
import { Download, RefreshCcw, Server, StopCircle, Trash2 } from 'lucide-react';
import { Button, Chip, CodeBlock, EmptyState, InlineState, Panel, SectionHeader, StatTile } from '../components/ui';
import { useAsync } from '../lib/useAsync';
import { loadServiceSnapshot, clearLogs, loadUpdateSnapshot, runUpdate, startProcess, stopProcess } from '../api/adapters';
import { usePreviewStore } from '../store/appStore';

export function ServicePage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadServiceSnapshot(settings), [settings]);
  const [updating, setUpdating] = React.useState(false);

  const handleStart = async () => {
    try {
      await startProcess(settings);
      pushToast({ tone: 'ok', title: '核心服务已启动', detail: '进程接口已接收启动指令。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '启动失败', detail: String(err) });
    }
  };

  const handleStop = async () => {
    try {
      await stopProcess(settings);
      pushToast({ tone: 'warn', title: '核心服务已停止', detail: '进程已回到空闲状态。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '停止失败', detail: String(err) });
    }
  };

  const handleClearLogs = async () => {
    try {
      await clearLogs(settings);
      pushToast({ tone: 'warn', title: '日志已清空', detail: '当前日志缓冲区已经清空。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '清空失败', detail: String(err) });
    }
  };

  const handleUpdate = async () => {
    setUpdating(true);
    try {
      const check = await loadUpdateSnapshot(settings);
      if (!check.data?.hasUpdate) {
        pushToast({ tone: 'ok', title: '暂无更新', detail: `${check.data?.current || '当前版本'} 已是最新。` });
        return;
      }
      const result = await runUpdate(settings);
      pushToast({ tone: result.data?.success ? 'ok' : 'danger', title: '更新完成', detail: result.data?.current_version || '未知版本' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '更新失败', detail: String(err) });
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">运行时 / CLI</div>
          <h1>启动 OpenClaw 核心服务，并保留 CLI 与日志。</h1>
          <p>这里是原启动器运行时能力的预览重排：启动、停止、日志、更新和系统信息都对齐同一套桥接接口。</p>
        </div>
        <div className="hero-actions">
          {data?.running ? (
            <Button variant="danger" icon={StopCircle} onClick={handleStop}>
              停止
            </Button>
          ) : (
            <Button variant="primary" icon={Server} onClick={handleStart}>
              启动
            </Button>
          )}
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh}>
            刷新
          </Button>
          <Button variant="secondary" icon={Download} onClick={handleUpdate} disabled={updating}>
            {updating ? '检查中...' : '检查更新'}
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatTile label="进程" value={data?.running ? '运行中' : '已停止'} hint={data?.pid ? `PID ${data.pid}` : '没有活动 PID'} tone={data?.running ? 'ok' : 'warn'} />
        <StatTile label="启动状态" value={toCnState(data?.startupState || 'idle')} hint={`${data?.startupElapsedSec ?? 0}s / ${data?.startupTimeoutSec ?? 420}s`} tone={data?.startupState === 'running' ? 'warn' : 'neutral'} />
        <StatTile label="桥接" value={data?.portReady ? '就绪' : '等待中'} hint={toCnState(data?.startupStage || '暂无阶段')} tone={data?.portReady ? 'ok' : 'warn'} />
        <StatTile label="日志" value={data?.logTail.length || 0} hint="最近输出行数" tone="neutral" />
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取服务详情...</Panel>
      ) : error ? (
        <Panel className="panel-error">
          <InlineState tone="danger" title="服务状态读取失败" description={error} />
        </Panel>
      ) : data ? (
        <section className="content-grid content-grid-service">
          <Panel className="surface-panel">
            <SectionHeader eyebrow="进程" title="核心服务状态" subtitle="对齐原启动器的 /api/process/* 接口契约。" action={<Chip tone={data.source === 'live' ? 'ok' : 'warn'}>{toCnState(data.source)}</Chip>} />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">状态</span><span className="detail-value">{toCnState(data.statusLabel)}</span></div>
              <div className="detail-row"><span className="detail-label">PID</span><span className="detail-value">{data.pid ?? '未知'}</span></div>
              <div className="detail-row"><span className="detail-label">阶段</span><span className="detail-value">{toCnState(data.startupStage)}</span></div>
              <div className="detail-row"><span className="detail-label">网关模式</span><span className="detail-value">{toCnState(data.licenseGate)}</span></div>
              {data.startupError ? <InlineState tone="danger" title="启动错误" description={data.startupError} /> : null}
            </div>
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="系统" title="桥接运行信息" subtitle="基础路径与 Node 可执行文件来自 /api/system/info。" />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">Node</span><span className="detail-value">{data.system.nodePath}</span></div>
              <div className="detail-row"><span className="detail-label">根路径</span><span className="detail-value">{data.system.basePath}</span></div>
              <div className="detail-row"><span className="detail-label">版本</span><span className="detail-value">{data.system.version}</span></div>
              <div className="detail-row"><span className="detail-label">日志来源</span><span className="detail-value">{data.source}</span></div>
            </div>
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="CLI / 日志" title="实时日志尾部" subtitle="CLI 与日志能力保留在服务页，方便排错。" action={<Button variant="quiet" icon={Trash2} onClick={handleClearLogs}>清空</Button>} />
            {data.logTail.length ? <CodeBlock text={data.logTail.join('\n')} maxHeight={280} /> : <EmptyState title="暂无日志" description="接口没有返回最近日志。" />}
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader eyebrow="更新" title="版本检查" subtitle="更新接口返回当前版本与最新版本。" />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">当前版本</span><span className="detail-value">{data.update.current || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">最新版本</span><span className="detail-value">{data.update.latest || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">是否可更新</span><span className="detail-value">{data.update.hasUpdate ? '是' : '否'}</span></div>
            </div>
          </Panel>
        </section>
      ) : null}
    </div>
  );
}

function toCnState(value: string) {
  const lower = String(value || '').toLowerCase();
  const map: Record<string, string> = {
    idle: '待命',
    running: '运行中',
    stopped: '已停止',
    ready: '就绪',
    waiting: '等待中',
    none: '无',
    manual: '手动',
    member: '成员',
    mock: '预览',
    live: '真实接口',
    mixed: '混合',
  };
  return map[lower] || value;
}
