import React from 'react';
import { Button, FieldLabel, Input, showToast } from '../common';
import {
  loadPhoneConfig,
  phoneApi,
  PhoneConnectionConfig,
  PhoneScreenshot,
  PhoneStatus,
  savePhoneConfig,
} from '../../services/phoneApi';

interface ActionLog {
  id: number;
  message: string;
  tone: 'info' | 'success' | 'error';
}

let logId = 0;

function maskToken(token: string): string {
  if (!token) return '未配置';
  if (token.length <= 4) return '****';
  return `${'*'.repeat(Math.max(4, token.length - 4))}${token.slice(-4)}`;
}

function errorMessage(error?: string): string {
  switch (error) {
    case 'missing_base_url':
      return '请先填写 APKClaw 地址';
    case 'missing_token':
      return '请先填写 Token';
    case 'unauthorized':
      return 'Token 无效或未配置';
    case 'empty_screenshot':
      return '截图为空';
    case 'invalid_response':
      return '手机端返回格式异常';
    default:
      return error || '请求失败';
  }
}

export const PhoneControlPage: React.FC = () => {
  const [config, setConfig] = React.useState<PhoneConnectionConfig>(() => loadPhoneConfig());
  const [status, setStatus] = React.useState<PhoneStatus | null>(null);
  const [screenshot, setScreenshot] = React.useState<PhoneScreenshot | null>(null);
  const [naturalSize, setNaturalSize] = React.useState<{ width: number; height: number } | null>(null);
  const [loading, setLoading] = React.useState<'connect' | 'screenshot' | 'tap' | null>(null);
  const [logs, setLogs] = React.useState<ActionLog[]>([]);
  const imageRef = React.useRef<HTMLImageElement | null>(null);

  const addLog = React.useCallback((message: string, tone: ActionLog['tone'] = 'info') => {
    const id = ++logId;
    setLogs((items) => [{ id, message, tone }, ...items].slice(0, 12));
  }, []);

  const updateConfig = (patch: Partial<PhoneConnectionConfig>) => {
    setConfig((current) => ({ ...current, ...patch }));
  };

  const persistConfig = React.useCallback(() => {
    const saved = savePhoneConfig(config);
    setConfig(saved);
    return saved;
  }, [config]);

  const handleConnect = async () => {
    const saved = persistConfig();
    setLoading('connect');
    const result = await phoneApi.status(saved);
    setLoading(null);
    if (!result.ok || !result.data) {
      setStatus(null);
      const message = errorMessage(result.error);
      addLog(`连接失败：${message}`, 'error');
      showToast(`连接失败：${message}`, 'error');
      return;
    }
    setStatus(result.data);
    addLog('连接成功，已读取手机端状态', 'success');
    showToast('APKClaw 连接成功', 'success');
  };

  const handleScreenshot = async () => {
    const saved = persistConfig();
    setLoading('screenshot');
    const result = await phoneApi.screenshot(saved);
    setLoading(null);
    if (!result.ok || !result.data) {
      const message = errorMessage(result.error);
      addLog(`截图失败：${message}`, 'error');
      showToast(`截图失败：${message}`, 'error');
      return;
    }
    setScreenshot(result.data);
    addLog('截图已刷新', 'success');
  };

  const handleImageLoad = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight });
  };

  const handleImageClick = async (event: React.MouseEvent<HTMLImageElement>) => {
    if (!screenshot || loading) return;
    const img = imageRef.current;
    const size = naturalSize || (img ? { width: img.naturalWidth, height: img.naturalHeight } : null);
    if (!img || !size?.width || !size?.height) return;

    const rect = img.getBoundingClientRect();
    const previewX = event.clientX - rect.left;
    const previewY = event.clientY - rect.top;
    const x = Math.max(0, Math.min(size.width, Math.round((previewX / rect.width) * size.width)));
    const y = Math.max(0, Math.min(size.height, Math.round((previewY / rect.height) * size.height)));

    const saved = persistConfig();
    setLoading('tap');
    addLog(`发送点击：x=${x}, y=${y}`, 'info');
    const result = await phoneApi.tap(saved, { x, y, visualize: true, traceId: `tap_${Date.now()}` });
    setLoading(null);
    if (!result.ok) {
      const message = errorMessage(result.error);
      addLog(`点击失败：${message}`, 'error');
      showToast(`点击失败：${message}`, 'error');
      return;
    }
    addLog(`点击完成：x=${x}, y=${y}`, 'success');
    window.setTimeout(() => {
      handleScreenshot();
    }, 350);
  };

  const canRequest = Boolean(config.baseUrl.trim() && config.token.trim());
  const statusItems = [
    { label: '连接状态', value: status ? '在线' : '未连接', ok: Boolean(status) },
    { label: '无障碍服务', value: status?.accessibilityRunning ? '运行中' : '未知/未运行', ok: Boolean(status?.accessibilityRunning) },
    { label: 'LLM 配置', value: status?.llmConfigured ? '已配置' : '未知/未配置', ok: Boolean(status?.llmConfigured) },
    { label: '任务状态', value: status?.taskRunning ? '执行中' : status ? '空闲' : '未知', ok: status ? !status.taskRunning : false },
  ];

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="flex items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.42em] text-accent">PHONE CONNECTOR</div>
            <h1 className="mt-2 text-[28px] font-black leading-tight text-text">手机控制</h1>
            <p className="mt-1 text-sm text-text-muted">连接 APKClaw，先完成截图预览和坐标点击的最小闭环。</p>
          </div>
          <div className="rounded-[14px] border border-border/80 bg-surface-alt/35 px-4 py-3 text-right">
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-text-subtle">TOKEN</div>
            <div className="mt-1 text-xs font-semibold text-text-muted">{maskToken(config.token)}</div>
          </div>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[340px_1fr] gap-5 overflow-hidden p-6">
        <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto">
          <section className="rounded-[16px] border border-border/80 bg-surface-alt/35 p-4">
            <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">连接配置</div>
            <div className="space-y-3">
              <div>
                <FieldLabel text="设备名称" />
                <Input value={config.name || ''} onChange={(event) => updateConfig({ name: event.target.value })} placeholder="Android Phone" />
              </div>
              <div>
                <FieldLabel text="APKClaw 地址" required />
                <Input
                  value={config.baseUrl}
                  onChange={(event) => updateConfig({ baseUrl: event.target.value })}
                  placeholder="http://192.168.1.100:9527"
                />
              </div>
              <div>
                <FieldLabel text="Token" required />
                <Input
                  value={config.token}
                  onChange={(event) => updateConfig({ token: event.target.value })}
                  type="password"
                  placeholder="X-AGENT-PHONE-TOKEN"
                />
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button onClick={handleConnect} disabled={!canRequest || loading !== null} variant="primary">
                  {loading === 'connect' ? '连接中...' : '连接测试'}
                </Button>
                <Button onClick={handleScreenshot} disabled={!canRequest || loading !== null} variant="quiet">
                  {loading === 'screenshot' ? '截图中...' : '刷新截图'}
                </Button>
              </div>
            </div>
          </section>

          <section className="rounded-[16px] border border-border/80 bg-surface-alt/35 p-4">
            <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">设备状态</div>
            <div className="space-y-2">
              {statusItems.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-surface/45 px-3 py-2">
                  <div className="text-xs text-text-muted">{item.label}</div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${item.ok ? 'bg-status-success' : 'bg-text-subtle'}`} />
                    <span className="text-xs font-bold text-text">{item.value}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="min-h-[180px] rounded-[16px] border border-border/80 bg-surface-alt/35 p-4">
            <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">动作日志</div>
            <div className="space-y-2">
              {logs.length === 0 ? (
                <p className="text-xs leading-5 text-text-subtle">连接、截图、点击结果会显示在这里。Token 不会写入日志。</p>
              ) : (
                logs.map((log) => (
                  <div
                    key={log.id}
                    className={`rounded-xl border px-3 py-2 text-xs ${
                      log.tone === 'success'
                        ? 'border-status-success/25 bg-status-success/8 text-status-success'
                        : log.tone === 'error'
                          ? 'border-status-danger/25 bg-status-danger/8 text-status-danger'
                          : 'border-border/70 bg-surface/45 text-text-muted'
                    }`}
                  >
                    {log.message}
                  </div>
                ))
              )}
            </div>
          </section>
        </aside>

        <main className="flex min-h-0 flex-col overflow-hidden rounded-[18px] border border-border/80 bg-surface-alt/25">
          <div className="flex shrink-0 items-center justify-between border-b border-border/70 px-5 py-4">
            <div>
              <div className="text-sm font-black text-text">手机画面</div>
              <div className="mt-0.5 text-xs text-text-subtle">
                {naturalSize ? `${naturalSize.width} x ${naturalSize.height}` : '等待截图'}
              </div>
            </div>
            <div className="text-xs text-text-subtle">点击截图会发送 tap 坐标</div>
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-surface-deeper/70 p-5">
            {screenshot ? (
              <img
                ref={imageRef}
                src={screenshot.dataUrl}
                alt="APKClaw screenshot"
                onLoad={handleImageLoad}
                onClick={handleImageClick}
                className={`max-h-full max-w-full rounded-[14px] border border-border/80 bg-black object-contain shadow-[0_24px_80px_rgba(0,0,0,0.38)] ${
                  loading ? 'cursor-wait opacity-80' : 'cursor-crosshair'
                }`}
                draggable={false}
              />
            ) : (
              <div className="flex max-w-md flex-col items-center justify-center rounded-[18px] border border-dashed border-border/80 bg-surface-alt/25 px-10 py-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-[16px] border border-border-strong/60 bg-accent/[0.08] text-sm font-black text-accent">
                  PH
                </div>
                <h2 className="mt-4 text-base font-black text-text">还没有手机截图</h2>
                <p className="mt-2 text-sm leading-6 text-text-muted">
                  填写 APKClaw 地址和 Token，先连接测试，再刷新截图。第一轮只做“看见手机”和“点击手机”。
                </p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
};
