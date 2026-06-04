import React from 'react';
import { Camera, MessageCircleMore, RefreshCcw, Send, SquareTerminal, SquareStack, StopCircle } from 'lucide-react';
import { Button, Chip, EmptyState, Field, Input, InlineState, Panel, SectionHeader, TextArea, Toggle } from '../components/ui';
import { loadDesktopSnapshot, requestBridgeData, saveDesktopAgentConfig, startDesktopAgent, stopDesktopAgent } from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

export function DesktopPage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadDesktopSnapshot(settings), [settings]);
  const [configDraft, setConfigDraft] = React.useState<Record<string, any>>({});
  const [screenshot, setScreenshot] = React.useState('');
  const [message, setMessage] = React.useState('你好，这是一条来自 OpenClaw 预览控制台的回复。');

  React.useEffect(() => {
    if (data?.config) setConfigDraft(data.config);
  }, [data]);

  const handleStart = async () => {
    try {
      await startDesktopAgent(settings);
      pushToast({ tone: 'ok', title: '桌面 Agent 已启动', detail: '启动接口已返回成功。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '启动失败', detail: String(err) });
    }
  };

  const handleStop = async () => {
    try {
      await stopDesktopAgent(settings);
      pushToast({ tone: 'warn', title: '桌面 Agent 已停止', detail: '停止接口已返回成功。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '停止失败', detail: String(err) });
    }
  };

  const handleSave = async () => {
    try {
      await saveDesktopAgentConfig(settings, configDraft);
      pushToast({ tone: 'ok', title: '配置已保存', detail: '桌面 Agent 配置已持久化。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '保存失败', detail: String(err) });
    }
  };

  const handleScreenshot = async () => {
    try {
      const response = await requestBridgeData(settings, '/api/desktop-agent/screenshot', 'POST', {});
      setScreenshot(response.data?.screenshot || '');
      pushToast({ tone: 'ok', title: '桌面截图已获取', detail: '已收到桌面 Agent 截图响应。' });
    } catch (err) {
      pushToast({ tone: 'danger', title: '截图失败', detail: String(err) });
    }
  };

  const handleAction = async (path: string, body: Record<string, unknown>) => {
    try {
      await requestBridgeData(settings, path, 'POST', body);
      pushToast({ tone: 'ok', title: '动作已发送', detail: path });
    } catch (err) {
      pushToast({ tone: 'danger', title: '动作失败', detail: String(err) });
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">桌面 RPA</div>
          <h1>桌面控制端是原来内置的 RPA 自动回复项目。</h1>
          <p>启动 Agent、查看当前桌面画面，并通过现有桥接接口发送受控的微信自动回复动作。</p>
        </div>
        <div className="hero-actions">
          {data?.running ? (
            <Button variant="danger" icon={StopCircle} onClick={handleStop}>
              停止
            </Button>
          ) : (
            <Button variant="primary" icon={SquareTerminal} onClick={handleStart}>
              启动
            </Button>
          )}
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh}>
            刷新
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="运行状态" value={data?.running ? '运行中' : '未运行'} tone={data?.running ? 'ok' : 'warn'} />
        <StatCard label="API 状态" value={data?.apiReady ? '就绪' : '等待'} tone={data?.apiReady ? 'ok' : 'warn'} />
        <StatCard label="项目存在" value={data?.present ? '是' : '否'} tone={data?.present ? 'ok' : 'warn'} />
        <StatCard label="配置" value={data?.configured ? '已配置' : '未设置'} tone={data?.configured ? 'ok' : 'warn'} />
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取桌面 Agent 状态...</Panel>
      ) : error ? (
        <Panel className="panel-error"><InlineState tone="danger" title="桌面 Agent 状态读取失败" description={error} /></Panel>
      ) : data ? (
        <section className="content-grid content-grid-desktop">
          <Panel className="surface-panel">
            <SectionHeader eyebrow="状态" title="桌面 Agent 健康状态" subtitle="读取 /api/desktop-agent/status 与 /health 返回值。" action={<Chip tone={data.source === 'live' ? 'ok' : 'warn'}>{sourceLabel(data.source)}</Chip>} />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">PID</span><span className="detail-value">{data.pid ?? '未知'}</span></div>
              <div className="detail-row"><span className="detail-label">命令</span><span className="detail-value">{data.command.join(' ') || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">健康状态</span><span className="detail-value">{String((data.health as any)?.message || '暂无')}</span></div>
            </div>
            {screenshot ? <img className="desktop-shot" src={screenshot} alt="桌面截图" /> : <EmptyState title="暂无截图" description="点击截图后显示桌面 Agent 当前画面。" />}
          </Panel>

          <Panel className="surface-panel rpa-actions-panel">
            <SectionHeader eyebrow="操作" title="自动回复操作" subtitle="通过现有 API 截屏、读取未读消息或发送准备好的微信回复。" />
            <div className="button-row">
              <Button variant="secondary" icon={Camera} onClick={handleScreenshot}>截图</Button>
              <Button variant="secondary" icon={MessageCircleMore} onClick={() => handleAction('/api/desktop-agent/wechat/unread', {})}>未读</Button>
              <Button variant="success" icon={Send} onClick={() => handleAction('/api/desktop-agent/wechat/send', { text: message })}>发送</Button>
            </div>
            <Field label="回复内容"><TextArea rows={5} value={message} onChange={(event) => setMessage(event.target.value)} /></Field>
          </Panel>

          <Panel className="surface-panel surface-panel-wide">
            <SectionHeader eyebrow="配置" title="Agent 配置" subtitle="连接配置默认折叠，避免占用日常控制区。" />
            <details className="settings-details">
              <summary>编辑桌面 Agent 配置</summary>
              <div className="desktop-config-stack">
                <div className="form-grid">
                  <Field label="Agent 目录"><Input value={configDraft.agentDir || ''} onChange={(event) => setConfigDraft((state) => ({ ...state, agentDir: event.target.value }))} /></Field>
                  <Field label="端口"><Input type="number" value={configDraft.port || 0} onChange={(event) => setConfigDraft((state) => ({ ...state, port: Number(event.target.value) || 0 }))} /></Field>
                  <Field label="应用类型"><Input value={configDraft.appType || ''} onChange={(event) => setConfigDraft((state) => ({ ...state, appType: event.target.value }))} /></Field>
                <Field label="令牌预览"><Input value={configDraft.tokenPreview || ''} onChange={(event) => setConfigDraft((state) => ({ ...state, tokenPreview: event.target.value }))} /></Field>
                </div>
                <Toggle checked={Boolean(configDraft.enabled)} onChange={(checked) => setConfigDraft((state) => ({ ...state, enabled: checked }))} label="启用" hint="通过 /api/desktop-agent/config 持久化" />
                <div className="button-row">
                  <Button variant="primary" icon={SquareStack} onClick={handleSave}>保存配置</Button>
                </div>
              </div>
            </details>
          </Panel>
        </section>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, tone = 'neutral' }: { label: string; value: React.ReactNode; tone?: 'ok' | 'warn' | 'danger' | 'neutral' }) {
  return (
    <div className={`stat-tile stat-tile-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function sourceLabel(value: string) {
  const map: Record<string, string> = {
    mock: '预览',
    live: '真实接口',
    mixed: '混合',
  };
  return map[value] || value;
}
