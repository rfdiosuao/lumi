import React from 'react';
import { Camera, Download, MessageCircleMore, RefreshCcw, Send, ShieldCheck, SquareTerminal, SquareStack, StopCircle } from 'lucide-react';
import { Button, EmptyState, Field, Input, InlineState, Panel, SectionHeader, TextArea, Toggle } from '../components/ui';
import {
  installDesktopAgentLayer,
  loadDesktopSnapshot,
  requestBridgeData,
  saveDesktopAgentConfig,
  startDesktopAgent,
  stopDesktopAgent,
} from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

export function DesktopPage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadDesktopSnapshot(settings), [settings], { cacheKey: 'desktop' });
  const [configDraft, setConfigDraft] = React.useState<Record<string, any>>({});
  const [screenshot, setScreenshot] = React.useState('');
  const [message, setMessage] = React.useState('你好，这是一条来自 OpenClaw 桌面 RPA 的预设回复。');
  const [installing, setInstalling] = React.useState(false);

  React.useEffect(() => {
    if (data?.config) setConfigDraft(data.config);
  }, [data]);

  const handleInstall = async () => {
    setInstalling(true);
    try {
      await installDesktopAgentLayer(settings);
      pushToast({
        tone: 'ok',
        title: '桌面组件已安装',
        detail: 'Luminode Desktop Agent 已写入 OpenClawFiles/agents/luminode-desktop。',
      });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '桌面组件安装失败', detail: String(err) });
    } finally {
      setInstalling(false);
    }
  };

  const handleStart = async () => {
    if (!data?.present) {
      await handleInstall();
      return;
    }
    try {
      await startDesktopAgent(settings);
      pushToast({ tone: 'ok', title: '桌面 Agent 已启动', detail: '已启动 Luminode 桌面控制组件。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '启动失败', detail: String(err) });
    }
  };

  const handleStop = async () => {
    try {
      await stopDesktopAgent(settings);
      pushToast({ tone: 'warn', title: '桌面 Agent 已停止', detail: '桌面控制组件已停止。' });
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
      await requestBridgeData(settings, path, 'POST', { confirmed: true, ...body });
      pushToast({ tone: 'ok', title: '动作已发送', detail: path });
    } catch (err) {
      pushToast({ tone: 'danger', title: '动作失败', detail: String(err) });
    }
  };

  const resolvedAgentDir = String((data?.config as any)?.resolvedAgentDir || (data?.config as any)?.agentDir || '');
  const installButtonLabel = installing ? '安装中...' : '下载并安装桌面组件';
  const primaryAction = !data?.present ? (
    <Button variant="primary" icon={Download} onClick={handleInstall} disabled={installing || loading}>
      {installButtonLabel}
    </Button>
  ) : data.running ? (
    <Button variant="danger" icon={StopCircle} onClick={handleStop}>
      停止
    </Button>
  ) : (
    <Button variant="primary" icon={SquareTerminal} onClick={handleStart} disabled={installing}>
      启动
    </Button>
  );

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">桌面 RPA</div>
          <h1>桌面控制端，接入原来的自动回复项目。</h1>
          <p>启动 Luminode Agent，读取当前桌面画面，并通过受控 Bridge 执行截图、未读检测和微信回复动作。</p>
        </div>
        <div className="hero-actions">
          {primaryAction}
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh} disabled={installing}>
            刷新
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="运行状态" value={data?.running ? '运行中' : '未运行'} tone={data?.running ? 'ok' : 'warn'} />
        <StatCard label="API 状态" value={data?.apiReady ? '就绪' : '等待'} tone={data?.apiReady ? 'ok' : 'warn'} />
        <StatCard label="桌面组件" value={data?.present ? '已安装' : '未安装'} tone={data?.present ? 'ok' : 'warn'} />
        <StatCard label="配置" value={data?.configured ? '已配置' : '默认配置'} tone={data?.configured ? 'ok' : 'warn'} />
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取桌面 Agent 状态...</Panel>
      ) : error ? (
        <Panel className="panel-error"><InlineState tone="danger" title="桌面 Agent 状态读取失败" description={error} /></Panel>
      ) : data ? (
        <>
          {!data.present ? (
            <Panel className="surface-panel">
              <InlineState
                tone="warn"
                icon={ShieldCheck}
                title="桌面 RPA 组件未安装"
                description="在线便携包默认不带 Luminode 桌面组件。点击安装后会从 manifest 镜像下载、校验 sha256，并安装到 OpenClawFiles/agents/luminode-desktop。"
              />
              <div className="button-row">
                <Button variant="primary" icon={Download} onClick={handleInstall} disabled={installing}>
                  {installButtonLabel}
                </Button>
              </div>
            </Panel>
          ) : null}

          <section className="content-grid content-grid-desktop">
            <Panel className="surface-panel">
              <SectionHeader eyebrow="状态" title="桌面 Agent 健康状态" subtitle="读取 /api/desktop-agent/status 与 /health 返回值。" />
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">PID</span><span className="detail-value">{data.pid ?? '未知'}</span></div>
                <div className="detail-row"><span className="detail-label">组件目录</span><span className="detail-value">{resolvedAgentDir || '待安装'}</span></div>
                <div className="detail-row"><span className="detail-label">命令</span><span className="detail-value">{data.command.join(' ') || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">健康状态</span><span className="detail-value">{String((data.health as any)?.message || (data.apiReady ? 'ready' : '暂无'))}</span></div>
              </div>
              {screenshot ? <img className="desktop-shot" src={screenshot} alt="桌面截图" /> : <EmptyState title="暂无截图" description="点击截图后显示桌面 Agent 当前画面。" />}
            </Panel>

            <Panel className="surface-panel rpa-actions-panel">
              <SectionHeader eyebrow="操作" title="自动回复动作" subtitle="通过现有 API 截屏、读取未读消息，或发送准备好的微信回复。" />
              <div className="button-row">
                <Button variant="secondary" icon={Camera} onClick={handleScreenshot} disabled={!data.present || installing}>截图</Button>
                <Button variant="secondary" icon={MessageCircleMore} onClick={() => handleAction('/api/desktop-agent/wechat/unread', {})} disabled={!data.present || installing}>未读</Button>
                <Button variant="success" icon={Send} onClick={() => handleAction('/api/desktop-agent/wechat/send', { text: message })} disabled={!data.present || installing}>发送</Button>
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
                    <Field label="令牌预览"><Input value={configDraft.tokenPreview || ''} readOnly /></Field>
                  </div>
                  <Toggle checked={Boolean(configDraft.enabled)} onChange={(checked) => setConfigDraft((state) => ({ ...state, enabled: checked }))} label="启用" hint="通过 /api/desktop-agent/config 持久化" />
                  <Toggle
                    checked={Boolean(configDraft.policy?.allowClick)}
                    onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy || {}), allowClick: checked } }))}
                    label="允许点击"
                    hint="桌面模拟点击，默认关闭。"
                  />
                  <Toggle
                    checked={Boolean(configDraft.policy?.allowType)}
                    onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy || {}), allowType: checked } }))}
                    label="允许打字"
                    hint="桌面模拟输入文本，默认关闭。"
                  />
                  <Toggle
                    checked={Boolean(configDraft.policy?.allowWechatSend)}
                    onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy || {}), allowWechatSend: checked } }))}
                    label="允许微信发送"
                    hint="允许自动发送微信回复，默认关闭。"
                  />
                  <Toggle
                    checked={(configDraft.wechat?.sendMode || 'draft_only') === 'auto_enter'}
                    onChange={(checked) => setConfigDraft((state) => ({ ...state, wechat: { ...(state.wechat || {}), sendMode: checked ? 'auto_enter' : 'draft_only' } }))}
                    label="微信自动回车发送"
                    hint="关闭时只填入草稿；开启后自动回车发送。"
                  />
                  <div className="button-row">
                    <Button variant="primary" icon={SquareStack} onClick={handleSave}>保存配置</Button>
                  </div>
                </div>
              </details>
            </Panel>
          </section>
        </>
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
