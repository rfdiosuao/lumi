import React from 'react';
import { Camera, Download, MessageCircleMore, RefreshCcw, Send, ShieldCheck, SquareTerminal, SquareStack, StopCircle } from 'lucide-react';
import { Button, Chip, EmptyState, Field, Input, InlineState, Panel, SectionHeader, TextArea, Toggle } from '../components/ui';
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
  const [message, setMessage] = React.useState('你好，这是一条来自 lumi 桌面自动化的回复。');
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
      setScreenshot(normalizeScreenshot(response.data?.screenshot || response.data?.image || ''));
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

  const config = (data?.config || {}) as Record<string, any>;
  const policy = (config.policy || {}) as Record<string, any>;
  const resolvedAgentDir = String(config.resolvedAgentDir || config.agentDir || '');
  const commandText = data?.command?.length ? data.command.join(' ') : '';
  const apiPort = Number(config.port || 21900);
  const allowSend = Boolean(policy.allowWechatSend);
  const sendMode = String((config.wechat || {}).sendMode || 'draft_only');
  const canSend = Boolean(data?.apiReady && allowSend);
  const healthMessage = String((data?.health as any)?.message || (data?.apiReady ? 'API ready' : '等待桌面 Agent 上线'));
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
          <div className="eyebrow">桌面自动化</div>
          <h1>lumi 桌面控制台</h1>
          <p>统一托管 Luminode 代理，支持 Windows 与 macOS 桌面截图、微信未读检测和受控自动回复。</p>
        </div>
        <div className="hero-actions">
          {primaryAction}
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh} disabled={installing}>
            刷新
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="代理进程" value={data?.running ? '运行中' : '未运行'} hint={data?.pid ? `PID ${data.pid}` : '等待启动'} tone={data?.running ? 'ok' : 'warn'} />
        <StatCard label="本地 API" value={data?.apiReady ? '就绪' : '等待'} hint={`127.0.0.1:${apiPort}`} tone={data?.apiReady ? 'ok' : 'warn'} />
        <StatCard label="桌面组件" value={data?.present ? '已安装' : '未安装'} hint={shortPath(resolvedAgentDir || 'agents/luminode-desktop')} tone={data?.present ? 'ok' : 'warn'} />
        <StatCard label="发送策略" value={allowSend ? '已允许' : '需开启'} hint={sendModeLabel(sendMode)} tone={allowSend ? 'ok' : 'warn'} />
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
              <SectionHeader
                eyebrow="状态"
                title="桌面代理健康状态"
                subtitle="启动器通过 /api/desktop-agent/status 管理 Luminode sidecar。"
                action={<Chip tone={data.source === 'live' ? 'ok' : 'warn'}>{sourceLabel(data.source)}</Chip>}
              />
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">代理目录</span><span className="detail-value">{resolvedAgentDir || '待安装 OpenClawFiles/agents/luminode-desktop'}</span></div>
                <div className="detail-row"><span className="detail-label">启动命令</span><span className="detail-value">{commandText || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">健康状态</span><span className="detail-value">{healthMessage}</span></div>
              </div>
              {screenshot ? <img className="desktop-shot" src={screenshot} alt="桌面截图" /> : <EmptyState title="暂无桌面截图" description="启动代理并点击截图后，这里会显示当前桌面画面。" />}
            </Panel>

            <Panel className="surface-panel rpa-actions-panel">
              <SectionHeader eyebrow="操作" title="受控桌面动作" subtitle="截图和未读检测默认安全可用；自动发送需要在策略里明确开启。" />
              <div className="button-row">
                <Button variant="secondary" icon={Camera} onClick={handleScreenshot} disabled={!data.present || installing || !data.apiReady}>截图</Button>
                <Button variant="secondary" icon={MessageCircleMore} onClick={() => handleAction('/api/desktop-agent/wechat/unread', {})} disabled={!data.present || installing || !data.apiReady}>未读</Button>
                <Button variant="success" icon={Send} onClick={() => handleAction('/api/desktop-agent/wechat/send', { text: message, confirmed: true })} disabled={!data.present || installing || !canSend}>发送</Button>
              </div>
              {!canSend ? (
                <InlineState
                  tone="warn"
                  title="自动发送当前未开启"
                  description="在下方策略中开启“允许微信发送”，并确认发送模式后再执行。"
                  icon={ShieldCheck}
                />
              ) : null}
              <Field label="回复内容" hint={sendModeLabel(sendMode)}><TextArea rows={5} value={message} onChange={(event) => setMessage(event.target.value)} /></Field>
            </Panel>

            <Panel className="surface-panel surface-panel-wide">
              <SectionHeader eyebrow="配置" title="代理配置" subtitle="留空目录时自动查找 OpenClawFiles/agents/luminode-desktop，Mac 包会解析 Luminode.app。" />
              <details className="settings-details">
                <summary>编辑桌面代理配置</summary>
                <div className="desktop-config-stack">
                  <div className="form-grid">
                    <Field label="Agent 目录" hint="可留空使用默认代理目录"><Input value={configDraft.agentDir || ''} placeholder="agents/luminode-desktop 或 Luminode.app" onChange={(event) => setConfigDraft((state) => ({ ...state, agentDir: event.target.value }))} /></Field>
                    <Field label="端口"><Input type="number" value={configDraft.port || 21900} onChange={(event) => setConfigDraft((state) => ({ ...state, port: Number(event.target.value) || 21900 }))} /></Field>
                    <Field label="应用类型"><Input value={configDraft.appType || 'weixin'} onChange={(event) => setConfigDraft((state) => ({ ...state, appType: event.target.value }))} /></Field>
                    <Field label="Token"><Input value={config.tokenPreview || '自动生成'} readOnly /></Field>
                  </div>
                  <Toggle checked={Boolean(configDraft.enabled)} onChange={(checked) => setConfigDraft((state) => ({ ...state, enabled: checked }))} label="启用" hint="通过 /api/desktop-agent/config 持久化" />
                  <div className="form-grid">
                    <Toggle checked={Boolean((configDraft.policy as any)?.allowScreenshot ?? true)} onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy as any), allowScreenshot: checked } }))} label="允许截图" />
                    <Toggle checked={Boolean((configDraft.policy as any)?.allowClick)} onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy as any), allowClick: checked } }))} label="允许点击" hint="桌面模拟点击默认关闭" />
                    <Toggle checked={Boolean((configDraft.policy as any)?.allowType)} onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy as any), allowType: checked } }))} label="允许打字" hint="桌面模拟输入默认关闭" />
                    <Toggle checked={Boolean((configDraft.policy as any)?.allowWechatSend)} onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy as any), allowWechatSend: checked } }))} label="允许微信发送" hint="危险动作，需要显式开启" />
                    <Toggle checked={Boolean((configDraft.policy as any)?.requireConfirmForSend ?? true)} onChange={(checked) => setConfigDraft((state) => ({ ...state, policy: { ...(state.policy as any), requireConfirmForSend: checked } }))} label="发送需要确认" />
                    <Toggle
                      checked={Boolean((configDraft.wechat as any)?.sendMode === 'auto_enter')}
                      onChange={(checked) => setConfigDraft((state) => ({ ...state, wechat: { ...(state.wechat as any), sendMode: checked ? 'auto_enter' : 'draft_only' } }))}
                      label="微信自动回车发送"
                      hint="关闭时只生成草稿"
                    />
                  </div>
                  <div className="button-row">
                    <Button variant="primary" icon={SquareStack} onClick={handleSave}>保存代理配置</Button>
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

function StatCard({ label, value, hint, tone = 'neutral' }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: 'ok' | 'warn' | 'danger' | 'neutral' }) {
  return (
    <div className={`stat-tile stat-tile-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint ? <div className="stat-hint">{hint}</div> : null}
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

function normalizeScreenshot(value: string) {
  if (!value) return '';
  if (value.startsWith('data:')) return value;
  return `data:image/png;base64,${value}`;
}

function shortPath(value: string) {
  if (!value) return '未配置';
  const parts = value.split(/[\\/]/).filter(Boolean);
  return parts.length > 3 ? `.../${parts.slice(-3).join('/')}` : value;
}

function sendModeLabel(value: string) {
  const map: Record<string, string> = {
    draft_only: '只生成草稿',
    paste_only: '只粘贴不发送',
    auto_enter: '允许回车发送',
  };
  return map[value] || value || '未设置';
}
