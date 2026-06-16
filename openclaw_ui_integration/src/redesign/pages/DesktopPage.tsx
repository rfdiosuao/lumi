import React from 'react';
import { Camera, Download, MessageCircleMore, RefreshCcw, Send, ShieldCheck, SquareTerminal, SquareStack, StopCircle } from 'lucide-react';
import { Button, CodeBlock, EmptyState, Field, Input, InlineState, Modal, Panel, SectionHeader, TextArea, Toggle } from '../components/ui';
import {
  installDesktopAgentLayer,
  loadDesktopSnapshot,
  requestBridgeData,
  saveDesktopAgentConfig,
  startDesktopAgent,
  stopDesktopAgent,
} from '../api/adapters';
import { translateError } from '../lib/errors';
import { formatBytes } from '../lib/format';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

// Distribution layer is downloaded by the Tauri side; the JS layer has no live
// size probe, so we show a conservative known-good estimate for first-run copy.
const DESKTOP_LAYER_SIZE_BYTES = 180 * 1024 * 1024;

export function DesktopPage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadDesktopSnapshot(settings), [settings], { cacheKey: 'desktop' });
  const [configDraft, setConfigDraft] = React.useState<Record<string, any>>({});
  const [screenshot, setScreenshot] = React.useState('');
  const [message, setMessage] = React.useState('你好，这是一条来自 OpenClaw 桌面 RPA 的预设回复。');
  const [installing, setInstalling] = React.useState(false);
  const [agentBusy, setAgentBusy] = React.useState<'start' | 'stop' | null>(null);
  const [actionPending, setActionPending] = React.useState<{ kind: 'start' | 'stop'; stage: string } | null>(null);
  const [allowAutoSend, setAllowAutoSend] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [confirmSendOpen, setConfirmSendOpen] = React.useState(false);

  React.useEffect(() => {
    if (data?.config) setConfigDraft(data.config);
  }, [data]);

  // Keep the inline "允许自动发送到微信" toggle in sync with the persisted policy,
  // so the danger state always reflects the real backend gate, not just local UI state.
  React.useEffect(() => {
    if (data?.config) {
      const persistedAllow = Boolean((data.config as any)?.policy?.allowWechatSend) && (data.config as any)?.wechat?.sendMode === 'auto_enter';
      setAllowAutoSend(persistedAllow);
    }
  }, [data]);

  const refreshAfterAgentAction = React.useCallback(() => {
    refresh();
    window.setTimeout(refresh, 1200);
    window.setTimeout(refresh, 3500);
  }, [refresh]);

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
    if (agentBusy || actionPending) return;
    if (!data?.present) {
      await handleInstall();
      return;
    }
    setAgentBusy('start');
    setActionPending({ kind: 'start', stage: '正在启动组件' });
    try {
      await startDesktopAgent(settings);
      setActionPending({ kind: 'start', stage: '等待健康检查' });
      // Poll a few times so the button can reflect 已就绪 once the snapshot agrees.
      let ready = false;
      for (let attempt = 0; attempt < 6 && !ready; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 700));
        const snapshot = await loadDesktopSnapshot(settings).catch(() => null);
        ready = Boolean(snapshot?.apiReady && snapshot?.running);
      }
      pushToast({ tone: 'ok', title: ready ? '桌面 Agent 已就绪' : '桌面 Agent 已启动', detail: ready ? undefined : '健康检查仍在等待中，可稍后刷新查看。' });
    } catch (err) {
      const friendly = translateError(err);
      pushToast({ tone: 'danger', title: '启动失败', detail: friendly.hint, diagnostic: friendly.diagnostic, logRoute: friendly.logRoute });
    } finally {
      setAgentBusy(null);
      setActionPending(null);
      refreshAfterAgentAction();
    }
  };

  const handleStop = async () => {
    if (agentBusy || actionPending) return;
    setAgentBusy('stop');
    setActionPending({ kind: 'stop', stage: '正在停止' });
    try {
      await stopDesktopAgent(settings);
      setActionPending({ kind: 'stop', stage: '已停止' });
      pushToast({ tone: 'warn', title: '桌面 Agent 已停止' });
    } catch (err) {
      const friendly = translateError(err);
      pushToast({ tone: 'danger', title: '停止失败', detail: friendly.hint, diagnostic: friendly.diagnostic, logRoute: friendly.logRoute });
    } finally {
      setAgentBusy(null);
      setActionPending(null);
      refreshAfterAgentAction();
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
      const friendly = translateError(err);
      pushToast({ tone: 'danger', title: '动作失败', detail: friendly.hint, diagnostic: friendly.diagnostic, logRoute: friendly.logRoute });
    }
  };

  // Default path: never touches the network. The only backend endpoint
  // (`/api/desktop-agent/wechat/send`) performs a real send and is hard-gated
  // server-side by policy.allowWechatSend + wechat.sendMode === 'auto_enter'.
  // There is no separate "write draft" call, so "写入草稿" here is a local-only
  // no-send action: it just confirms the text is staged and reminds the user
  // nothing left this machine.
  const handleWriteDraft = () => {
    pushToast({
      tone: 'ok',
      title: '已写入草稿（未发送）',
      detail: '内容仅保存在本机回复框，未发送到微信。开启“允许自动发送到微信”后才能真正发送。',
    });
  };

  // Real send path: requires the user to explicitly enable the danger toggle
  // first (which persists policy.allowWechatSend + sendMode=auto_enter), then
  // requires an explicit confirm before the actual network call.
  const handleConfirmSend = async () => {
    setConfirmSendOpen(false);
    setSending(true);
    try {
      await requestBridgeData(settings, '/api/desktop-agent/wechat/send', 'POST', { text: message, confirmed: true });
      pushToast({ tone: 'ok', title: '已发送到微信', detail: '消息已通过桌面 Agent 自动发送。' });
    } catch (err) {
      const friendly = translateError(err);
      pushToast({ tone: 'danger', title: '发送失败', detail: friendly.hint, diagnostic: friendly.diagnostic, logRoute: friendly.logRoute });
    } finally {
      setSending(false);
    }
  };

  const handleSendClick = () => {
    if (!allowAutoSend) {
      handleWriteDraft();
      return;
    }
    setConfirmSendOpen(true);
  };

  const handleAutoSendToggle = async (checked: boolean) => {
    setAllowAutoSend(checked);
    if (!checked) return;
    // Turning the danger toggle on immediately persists the matching backend
    // policy so the gate is real, not just a local label flip.
    const nextConfig = {
      ...configDraft,
      policy: { ...(configDraft.policy || {}), allowWechatSend: true },
      wechat: { ...(configDraft.wechat || {}), sendMode: 'auto_enter' },
    };
    setConfigDraft(nextConfig);
    try {
      await saveDesktopAgentConfig(settings, nextConfig);
      pushToast({ tone: 'warn', title: '已允许自动发送到微信', detail: '后续点击“发送到微信”会真正发出消息，请谨慎操作。' });
      refresh();
    } catch (err) {
      setAllowAutoSend(false);
      const friendly = translateError(err);
      pushToast({ tone: 'danger', title: '开启自动发送失败', detail: friendly.hint, diagnostic: friendly.diagnostic, logRoute: friendly.logRoute });
    }
  };

  const resolvedAgentDir = String((data?.config as any)?.resolvedAgentDir || (data?.config as any)?.agentDir || '');
  const installButtonLabel = installing ? '安装中...' : '下载并安装桌面组件';
  const runtimeStatusLabel = actionPending ? actionPending.stage : data?.running ? '运行中' : '未运行';
  const runtimeStatusTone = actionPending ? 'warn' : data?.running ? 'ok' : 'warn';
  const startStopLabel =
    actionPending?.kind === 'start'
      ? actionPending.stage
      : actionPending?.kind === 'stop'
      ? actionPending.stage
      : data?.running
      ? '停止'
      : '启动';
  const primaryAction = !data?.present ? (
    <Button variant="primary" icon={Download} onClick={handleInstall} disabled={installing || loading || Boolean(agentBusy)}>
      {installButtonLabel}
    </Button>
  ) : data.running ? (
    <Button variant="danger" icon={StopCircle} onClick={handleStop} disabled={Boolean(agentBusy) || Boolean(actionPending)}>
      {startStopLabel}
    </Button>
  ) : (
    <Button variant="primary" icon={SquareTerminal} onClick={handleStart} disabled={installing || Boolean(agentBusy) || Boolean(actionPending)}>
      {startStopLabel}
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
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh} disabled={installing || Boolean(agentBusy) || Boolean(actionPending)}>
            刷新
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="运行状态" value={runtimeStatusLabel} tone={runtimeStatusTone} />
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
                title="未安装桌面组件"
                description={`首次使用需要下载桌面组件，约 ${formatBytes(DESKTOP_LAYER_SIZE_BYTES)}，下载完成后才能启动桌面 RPA。`}
              />
              <details className="settings-details" title="下载地址、文件校验（manifest/sha256）与安装路径详情">
                <summary>查看校验详情</summary>
                <div className="detail-stack">
                  <div className="detail-row"><span className="detail-label">下载方式</span><span className="detail-value">按 manifest 镜像地址下载</span></div>
                  <div className="detail-row"><span className="detail-label">完整性校验</span><span className="detail-value">下载后核对 sha256，校验失败会自动重试</span></div>
                  <div className="detail-row"><span className="detail-label">安装位置</span><span className="detail-value">OpenClawFiles/agents/luminode-desktop</span></div>
                </div>
              </details>
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
              <SectionHeader eyebrow="操作" title="自动回复动作" subtitle="通过现有 API 截屏、读取未读消息，准备微信回复草稿。" />
              <div className="button-row">
                <Button variant="secondary" icon={Camera} onClick={handleScreenshot} disabled={!data.present || installing || Boolean(agentBusy)}>截图</Button>
                <Button variant="secondary" icon={MessageCircleMore} onClick={() => handleAction('/api/desktop-agent/wechat/unread', {})} disabled={!data.present || installing || Boolean(agentBusy)}>未读</Button>
                <Button
                  variant={allowAutoSend ? 'danger' : 'success'}
                  icon={Send}
                  onClick={handleSendClick}
                  disabled={!data.present || installing || Boolean(agentBusy) || sending}
                >
                  {sending ? '发送中...' : allowAutoSend ? '发送到微信' : '写入草稿'}
                </Button>
              </div>
              <Field label="回复内容"><TextArea rows={5} value={message} onChange={(event) => setMessage(event.target.value)} /></Field>
              <Toggle
                checked={allowAutoSend}
                onChange={handleAutoSendToggle}
                label="允许自动发送到微信"
                hint={allowAutoSend ? '危险：开启后点击“发送到微信”会立即真实发送，请确认收件对象无误。' : '关闭时仅写入本机草稿，不会真正发送到微信。'}
              />
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

      <Modal
        open={confirmSendOpen}
        title="确认发送到微信"
        subtitle="此操作会通过桌面 Agent 真实发出消息，无法撤回。"
        onClose={() => setConfirmSendOpen(false)}
        actions={
          <>
            <Button variant="quiet" onClick={() => setConfirmSendOpen(false)}>取消</Button>
            <Button variant="danger" icon={Send} onClick={handleConfirmSend} disabled={sending}>
              {sending ? '发送中...' : '确认发送'}
            </Button>
          </>
        }
      >
        <p>即将发送以下内容到当前微信会话：</p>
        <CodeBlock text={message || '（空白消息）'} maxHeight={160} />
      </Modal>
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
