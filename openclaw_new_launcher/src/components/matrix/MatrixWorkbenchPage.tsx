import React from 'react';
import {
  matrixApi,
  parseErrorText,
  type MatrixDeviceSummary,
  type MatrixEvent,
  type MatrixStatusSnapshot,
  type PhoneTaskMode,
  type PhoneTaskProfile,
} from '../../services/api';
import { Button, TextArea, showConfirm, showToast } from '../common';

type WorkerState = 'running' | 'idle' | 'offline' | 'blocked';

type WorkerView = MatrixDeviceSummary & {
  platform: string;
  account: string;
  task: string;
  progress: number;
  elapsed: string;
  queue: number;
  state: WorkerState;
};

type TemplateOption = {
  id: string;
  label: string;
  kind: 'direct' | 'template' | 'agent';
  review?: boolean;
};

type ExperienceReport = {
  summary?: {
    total?: number;
    success?: number;
    failure?: number;
    successRate?: number;
  };
  templateSuggestions?: Array<{ id?: string; reason?: string }>;
};

const DEFAULT_PHONE_MODEL = 'qwen3.7-plus';
const PHONE_AGENT_APK_URL = 'https://gitee.com/rfdiosuao/lumiapkclaw/releases/download/lumiclaw13241/OpenClaw-AgentPhone.apk';
const PHONE_AGENT_QR_SRC = '/phone-agent-apk-qr.svg';

const TEMPLATES: TemplateOption[] = [
  { id: 'screen-summary', label: '读取屏幕', kind: 'direct' },
  { id: 'open-settings', label: '打开设置', kind: 'template' },
  { id: 'publish-note', label: '发布内容草稿', kind: 'agent', review: true },
  { id: 'comment-review', label: '评论处理', kind: 'agent', review: true },
];

function numberOr(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function formatDuration(ms?: number): string {
  const total = Math.max(0, Math.floor(numberOr(ms, 0) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function modeLabel(value: PhoneTaskMode): string {
  if (value === 'observe') return '只读';
  if (value === 'safe') return '受控';
  return '完整控制';
}

function profileLabel(value: PhoneTaskProfile): string {
  if (value === 'fast') return '快速';
  if (value === 'standard') return '标准';
  return '深度';
}

function kindLabel(value: TemplateOption['kind']): string {
  if (value === 'direct') return '直连';
  if (value === 'template') return '模板';
  return '智能体';
}

function stateLabel(value: WorkerState): string {
  if (value === 'running') return '运行中';
  if (value === 'blocked') return '阻塞';
  if (value === 'offline') return '离线';
  return '空闲';
}

function stateClasses(value: WorkerState): string {
  if (value === 'running') return 'border-emerald-300/30 bg-emerald-300/[0.08]';
  if (value === 'blocked') return 'border-rose-300/35 bg-rose-300/[0.10]';
  if (value === 'offline') return 'border-white/10 bg-white/[0.03] opacity-75';
  return 'border-cyan-300/18 bg-cyan-300/[0.06]';
}

function eventTone(type: string): string {
  if (type === 'error') return 'bg-rose-400/15 text-rose-100 ring-rose-400/25';
  if (type === 'result') return 'bg-emerald-400/15 text-emerald-100 ring-emerald-400/25';
  if (type === 'step' || type === 'assigned') return 'bg-amber-400/15 text-amber-100 ring-amber-400/25';
  return 'bg-sky-400/15 text-sky-100 ring-sky-400/25';
}

function workerFromDevice(device: MatrixDeviceSummary): WorkerView {
  const failureCount = numberOr(device.failureCount, 0);
  const busy = Boolean(device.busy || device.currentTaskId);
  const online = Boolean(device.online);
  const state: WorkerState = failureCount > 0 ? 'blocked' : busy ? 'running' : online ? 'idle' : 'offline';
  const model = device.model || DEFAULT_PHONE_MODEL;
  return {
    ...device,
    platform: device.platform || device.group || '手机',
    account: device.account || model,
    task: device.currentScreenSummary || (busy ? `执行 ${device.currentTaskId}` : online ? '等待任务' : '未连接'),
    progress: clamp(numberOr(device.progress, busy ? 10 : 0)),
    elapsed: busy ? formatDuration(device.elapsedMs) : '00:00',
    queue: numberOr(device.queue, 0),
    state,
  };
}

function riskNeedsReview(templateId: string, prompt: string): boolean {
  const template = TEMPLATES.find((item) => item.id === templateId);
  return Boolean(template?.review) || /私信|评论|群发|批量|发布|自动回复/.test(prompt);
}

function metricFromSnapshot(snapshot: MatrixStatusSnapshot | null, workers: WorkerView[], experience: ExperienceReport | null) {
  const campaigns = snapshot?.campaigns || [];
  return {
    online: snapshot?.summary?.online ?? workers.filter((worker) => worker.online).length,
    total: snapshot?.summary?.total ?? workers.length,
    running: snapshot?.summary?.busy ?? workers.filter((worker) => worker.state === 'running').length,
    queue: campaigns.filter((item) => String(item.status || '') === 'queued').length + workers.reduce((sum, worker) => sum + worker.queue, 0),
    success: numberOr(experience?.summary?.success, 0),
    failed: snapshot?.summary?.failed ?? workers.filter((worker) => worker.state === 'blocked').length,
  };
}

function groupWorkers(workers: WorkerView[]): Array<[string, WorkerView[]]> {
  const groups = new Map<string, WorkerView[]>();
  workers.forEach((worker) => {
    const key = worker.group || '默认分组';
    groups.set(key, [...(groups.get(key) || []), worker]);
  });
  return Array.from(groups.entries());
}

function copyToClipboard(text: string) {
  void navigator.clipboard.writeText(text).then(
    () => showToast('已复制', 'success'),
    () => showToast('复制失败，请手动复制', 'error'),
  );
}

const MiniScreen: React.FC<{ worker: WorkerView }> = ({ worker }) => (
  <div className="relative h-[72px] w-[42px] overflow-hidden rounded-[6px] border border-white/12 bg-slate-950 shadow-inner">
    <div className="absolute inset-x-1 top-1 h-2 rounded-full bg-white/10" />
    <div className="absolute left-1 right-1 top-5 h-3 rounded bg-cyan-300/25" />
    <div className="absolute left-1 right-1 top-10 h-2 rounded bg-white/12" />
    <div className="absolute left-1 right-1 top-15 h-5 rounded bg-emerald-300/20" />
    <div className={`absolute bottom-1 left-1 h-1.5 w-1.5 rounded-full ${worker.online ? 'matrix-heartbeat bg-emerald-300' : 'bg-slate-500'}`} />
  </div>
);

const WorkerCard: React.FC<{ worker: WorkerView; selected: boolean; onToggle: () => void }> = ({ worker, selected, onToggle }) => (
  <button
    type="button"
    onClick={onToggle}
    disabled={!worker.online && !worker.busy}
    className={`group min-h-[154px] rounded-[8px] border p-3 text-left transition hover:border-cyan-300/35 disabled:cursor-not-allowed ${stateClasses(worker.state)} ${selected ? 'ring-2 ring-cyan-300/35' : ''}`}
  >
    <div className="mb-2 flex items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${worker.online ? 'matrix-heartbeat bg-emerald-300' : 'bg-slate-500'}`} />
          <span className="truncate font-mono text-[13px] font-black text-white">{worker.name || worker.deviceId}</span>
        </div>
        <div className="mt-1 truncate text-[11px] text-slate-400">{worker.platform} / {worker.account}</div>
      </div>
      <span className="rounded-full border border-current/20 px-2 py-1 text-[10px] font-black text-slate-100">{stateLabel(worker.state)}</span>
    </div>
    <div className="flex gap-3">
      <MiniScreen worker={worker} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-bold text-white">{worker.task}</div>
        <div className="mt-1 text-[11px] text-slate-400">{worker.elapsed} / 队列 {worker.queue}</div>
        <div className="mt-3 h-1.5 rounded-full bg-white/8">
          <div
            className={`h-full rounded-full ${worker.state === 'blocked' ? 'bg-rose-300' : worker.state === 'offline' ? 'bg-slate-500' : 'bg-emerald-300'}`}
            style={{ width: `${Math.max(6, worker.progress)}%` }}
          />
        </div>
        <div className="mt-2 truncate text-[11px] text-slate-400">{worker.lastResult || worker.source || '后端设备'}</div>
      </div>
    </div>
  </button>
);

const EventRow: React.FC<{ event: MatrixEvent }> = ({ event }) => (
  <div className="grid grid-cols-[66px_1fr] gap-3 border-b border-white/[0.06] py-3">
    <div className="font-mono text-[11px] text-slate-500">{String(event.timestamp || '').slice(11, 19) || '--:--:--'}</div>
    <div className="min-w-0">
      <div className="mb-1 flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-black ring-1 ${eventTone(event.type)}`}>{event.type}</span>
        <span className="truncate font-mono text-[11px] text-slate-400">{event.deviceId || event.campaignId || 'matrix'}</span>
      </div>
      <div className="text-[12px] leading-5 text-slate-200">{event.message || '事件已记录'}</div>
    </div>
  </div>
);

export const MatrixWorkbenchPage = () => {
  const [snapshot, setSnapshot] = React.useState<MatrixStatusSnapshot | null>(null);
  const [events, setEvents] = React.useState<MatrixEvent[]>([]);
  const [experience, setExperience] = React.useState<ExperienceReport | null>(null);
  const [templateId, setTemplateId] = React.useState('screen-summary');
  const [mode, setMode] = React.useState<PhoneTaskMode>('observe');
  const [profile, setProfile] = React.useState<PhoneTaskProfile>('fast');
  const [prompt, setPrompt] = React.useState('读取当前手机屏幕，告诉我页面名称和三个可见内容。');
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [confirmed, setConfirmed] = React.useState(false);
  const [dispatching, setDispatching] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const [status, watch, report] = await Promise.all([
        matrixApi.status(),
        matrixApi.watch(),
        matrixApi.experience(),
      ]);
      setSnapshot(status);
      setEvents(watch.events || []);
      setExperience(report as ExperienceReport);
    } catch (error) {
      setSnapshot({ schema: 'loom.matrix.v1', devices: [], summary: { total: 0, online: 0, busy: 0, failed: 0 } });
      setEvents([]);
      setExperience(null);
      const message = parseErrorText(error);
      if (message) showToast(message, 'error');
    }
  }, []);

  React.useEffect(() => {
    let closed = false;
    let source: EventSource | null = null;
    void refresh();
    void (async () => {
      try {
        await matrixApi.ensureStreamReady();
        if (closed) return;
        source = new EventSource(matrixApi.eventsStreamUrl());
        source.addEventListener('matrix', (event) => {
          const message = event as MessageEvent<string>;
          try {
            const payload = JSON.parse(message.data || '{}') as { status?: MatrixStatusSnapshot; events?: MatrixEvent[] };
            if (payload.status) setSnapshot(payload.status);
            if (Array.isArray(payload.events)) setEvents(payload.events);
          } catch {
            // Polling below keeps the page alive when an event frame is malformed.
          }
        });
        source.onerror = () => {
          if (!closed) void refresh();
        };
      } catch {
        if (!closed) void refresh();
      }
    })();
    const timer = window.setInterval(refresh, 8000);
    return () => {
      closed = true;
      source?.close();
      window.clearInterval(timer);
    };
  }, [refresh]);

  const workers = React.useMemo(() => (snapshot?.devices || []).map(workerFromDevice), [snapshot]);

  React.useEffect(() => {
    const workerIds = new Set(workers.map((worker) => worker.deviceId));
    const onlineIds = workers.filter((worker) => worker.online).slice(0, 5).map((worker) => worker.deviceId);
    setSelectedIds((current) => {
      const retained = current.filter((id) => workerIds.has(id));
      return retained.length ? retained : onlineIds;
    });
  }, [workers]);

  const metrics = metricFromSnapshot(snapshot, workers, experience);
  const visibleEvents = events.slice(-16).reverse();
  const needsReview = riskNeedsReview(templateId, prompt);
  const suggestions = experience?.templateSuggestions || [];
  const composerDisabled = dispatching || !workers.length;

  const toggleWorker = (deviceId: string) => {
    setSelectedIds((items) => items.includes(deviceId) ? items.filter((item) => item !== deviceId) : [...items, deviceId]);
  };

  const dispatchTask = async () => {
    if (!workers.length) {
      showToast('还没有后端设备，请先在手机页保存并检测手机。', 'info');
      return;
    }
    if (!selectedIds.length) {
      showToast('请选择至少一台在线手机。', 'info');
      return;
    }
    if (!prompt.trim()) {
      showToast('请先输入任务。', 'info');
      return;
    }
    if (needsReview && !confirmed) {
      const ok = await showConfirm({
        title: '需要人工确认',
        message: '该任务可能涉及发布、评论、私信或批量触达。请确认已经获得授权，并会遵守平台规则。',
        confirmText: '确认发布',
      });
      if (!ok) return;
      setConfirmed(true);
    }
    setDispatching(true);
    try {
      await matrixApi.dispatch({
        prompt,
        template: templateId,
        mode,
        profile,
        confirmed: needsReview ? true : confirmed,
        target: { deviceIds: selectedIds },
      });
      showToast('任务已发布到真实设备队列。', 'success');
      await refresh();
    } catch (error) {
      showToast(parseErrorText(error) || '任务发布失败', 'error');
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div data-white-label-layout="phone-matrix" className="loom-matrix-shell h-full overflow-hidden bg-[#07131B] text-slate-100">
      <div className="flex h-full flex-col">
        <header className="shrink-0 border-b border-white/[0.08] bg-[#091722]/95 px-6 py-4">
          <div className="grid grid-cols-[1fr_auto] items-center gap-4">
            <div className="min-w-0">
              <div className="text-[11px] font-black tracking-[0.28em] text-cyan-200/70">手机工作台</div>
              <h1 className="mt-1 truncate text-[24px] font-black text-white">手机矩阵任务发布工作台</h1>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="quiet" disabled className="!rounded-[8px] !border-white/12 !bg-white/[0.04] !text-slate-400">全局暂停</Button>
              <Button variant="danger" disabled className="!rounded-[8px] !opacity-70">紧急停止</Button>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-4 gap-2 xl:grid-cols-8">
            {[
              ['Codex 总控', '待接入', 'text-sky-200'],
              ['MCP / CLI', '可调度', 'text-emerald-200'],
              ['在线手机', `${metrics.online}/${metrics.total}`, 'text-emerald-200'],
              ['运行中', String(metrics.running), 'text-emerald-200'],
              ['等待队列', String(metrics.queue), 'text-amber-200'],
              ['累计成功', String(metrics.success), 'text-emerald-200'],
              ['失败设备', String(metrics.failed), 'text-rose-200'],
              ['默认模型', DEFAULT_PHONE_MODEL, 'text-cyan-200'],
            ].map(([label, value, tone]) => (
              <div key={label} className="rounded-[8px] border border-white/[0.07] bg-white/[0.035] px-3 py-2">
                <div className="text-[10px] font-bold text-slate-500">{label}</div>
                <div className={`mt-1 truncate text-[15px] font-black ${tone}`}>{value}</div>
              </div>
            ))}
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto px-6 py-5">
          <div className="loom-matrix-layout mx-auto grid min-h-[680px] w-full max-w-[1180px] grid-cols-[280px_minmax(420px,1fr)_280px] gap-4">
            <section className="loom-matrix-composer flex min-h-0 flex-col rounded-[8px] border border-white/[0.08] bg-white/[0.035]">
              <div className="border-b border-white/[0.07] px-4 py-3">
                <div className="text-[11px] font-black tracking-[0.22em] text-cyan-200/70">任务</div>
                <h2 className="mt-1 text-lg font-black text-white">任务编排</h2>
              </div>
              <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
                <label className="block">
                  <span className="text-xs font-bold text-slate-400">任务模板</span>
                  <select
                    value={templateId}
                    onChange={(event) => {
                      setTemplateId(event.target.value);
                      setConfirmed(false);
                    }}
                    className="mt-2 w-full rounded-[8px] border border-white/10 bg-[#0D1D27] px-3 py-2 text-sm text-white outline-none focus:border-cyan-300/50"
                  >
                    {TEMPLATES.map((template) => (
                      <option key={template.id} value={template.id}>{template.label} / {kindLabel(template.kind)}</option>
                    ))}
                  </select>
                </label>

                <div>
                  <span className="text-xs font-bold text-slate-400">执行设备</span>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedIds.slice(0, 8).map((id) => (
                      <button key={id} type="button" onClick={() => toggleWorker(id)} className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-xs font-bold text-cyan-100">
                        {id} x
                      </button>
                    ))}
                    <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-400">已选 {selectedIds.length}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {(['observe', 'safe', 'full'] as PhoneTaskMode[]).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setMode(item)}
                      className={`rounded-[8px] border px-3 py-2 text-left text-xs font-black ${mode === item ? 'border-cyan-300/50 bg-cyan-300/12 text-cyan-100' : 'border-white/10 bg-white/[0.03] text-slate-400'}`}
                    >
                      {modeLabel(item)}
                    </button>
                  ))}
                  {(['fast', 'standard', 'deep'] as PhoneTaskProfile[]).map((item) => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setProfile(item)}
                      className={`rounded-[8px] border px-3 py-2 text-left text-xs font-black ${profile === item ? 'border-emerald-300/50 bg-emerald-300/12 text-emerald-100' : 'border-white/10 bg-white/[0.03] text-slate-400'}`}
                    >
                      {profileLabel(item)}
                    </button>
                  ))}
                </div>

                <label className="block">
                  <span className="text-xs font-bold text-slate-400">任务内容</span>
                  <TextArea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    rows={6}
                    className="mt-2 !rounded-[8px] !border-white/10 !bg-[#0D1D27] !text-slate-100"
                  />
                </label>

                <div className={`rounded-[8px] border px-3 py-3 ${needsReview ? 'border-amber-300/25 bg-amber-300/10' : 'border-emerald-300/20 bg-emerald-300/8'}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-black text-white">安全确认</div>
                      <div className="mt-1 text-xs text-slate-400">{needsReview ? '外发、评论、批量任务需要人工确认' : '当前任务可直接执行'}</div>
                    </div>
                    <label className="flex items-center gap-2 text-xs font-bold text-slate-200">
                      <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                      已授权
                    </label>
                  </div>
                </div>

                {!workers.length ? (
                  <div className="matrix-empty-state rounded-[8px] border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs font-bold text-amber-100">
                    暂无手机。先到手机页保存并检测设备。
                  </div>
                ) : null}
                <Button variant="primary" disabled={composerDisabled} onClick={() => void dispatchTask()} className="matrix-dispatch w-full !rounded-[8px]">
                  {dispatching ? '发布中...' : '发布任务'}
                </Button>
              </div>
            </section>

            <section className="loom-matrix-workers min-h-0 rounded-[8px] border border-white/[0.08] bg-white/[0.035]">
              <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3">
                <div>
                  <div className="text-[11px] font-black tracking-[0.22em] text-cyan-200/70">设备</div>
                  <h2 className="mt-1 text-lg font-black text-white">电子员工矩阵</h2>
                </div>
                <Button variant="quiet" onClick={() => void refresh()} className="!rounded-[8px] !border-white/12 !bg-white/[0.04] !text-slate-200">刷新</Button>
              </div>
              <div className="max-h-[620px] overflow-auto p-4">
                {workers.length ? (
                  <div className="space-y-4">
                    {groupWorkers(workers).map(([group, groupItems]) => (
                      <div key={group}>
                        <div className="mb-2 flex items-center justify-between">
                          <div className="text-sm font-black text-white">{group}</div>
                          <div className="text-xs text-slate-500">{groupItems.filter((item) => item.online).length}/{groupItems.length} 在线</div>
                        </div>
                        <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
                          {groupItems.map((worker) => (
                            <WorkerCard key={worker.deviceId} worker={worker} selected={selectedIds.includes(worker.deviceId)} onToggle={() => toggleWorker(worker.deviceId)} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="matrix-empty-state flex h-[340px] items-center justify-center rounded-[8px] border border-dashed border-white/12 bg-white/[0.025] text-center">
                    <div>
                      <div className="text-lg font-black text-white">暂无真实后端设备</div>
                      <div className="mt-2 text-sm text-slate-400">手机页保存配置后会自动出现在这里。</div>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <aside className="flex min-h-0 flex-col gap-4">
              <section className="loom-matrix-stream min-h-0 flex-1 rounded-[8px] border border-white/[0.08] bg-white/[0.035]">
                <div className="border-b border-white/[0.07] px-4 py-3">
                  <div className="text-[11px] font-black tracking-[0.22em] text-cyan-200/70">日志</div>
                  <h2 className="mt-1 text-lg font-black text-white">实时任务流</h2>
                </div>
                <div className="max-h-[486px] overflow-auto px-4">
                  {visibleEvents.length ? (
                    visibleEvents.map((event, index) => <EventRow key={event.eventId || `${event.type}-${index}`} event={event} />)
                  ) : (
                    <div className="matrix-empty-state py-10 text-sm text-slate-400">暂无任务事件。</div>
                  )}
                </div>
              </section>

              <section data-matrix-phone-app-download className="rounded-[8px] border border-white/[0.08] bg-white/[0.035] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-black tracking-[0.22em] text-cyan-200/70">手机端</div>
                    <h2 className="mt-1 text-lg font-black text-white">下载手机端 App</h2>
                  </div>
                  <Button variant="quiet" onClick={() => copyToClipboard(PHONE_AGENT_APK_URL)} className="!rounded-[8px] !border-white/12 !bg-white/[0.04] !text-slate-200">
                    复制链接
                  </Button>
                </div>
                <div className="mt-3 flex items-center gap-3">
                  <img src={PHONE_AGENT_QR_SRC} alt="手机端 App 下载二维码" className="h-20 w-20 rounded-[6px] bg-white p-1" />
                  <div className="min-w-0 text-xs leading-5 text-slate-400">
                    <div className="truncate font-mono text-slate-300">{PHONE_AGENT_APK_URL}</div>
                    <div>手机扫码安装后，在手机页保存 IP 和令牌。</div>
                  </div>
                </div>
              </section>

              <section className="rounded-[8px] border border-white/[0.08] bg-white/[0.035] p-4">
                <div className="text-[11px] font-black tracking-[0.22em] text-cyan-200/70">经验</div>
                <h2 className="mt-1 text-lg font-black text-white">任务沉淀</h2>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="rounded-[8px] border border-white/8 bg-white/[0.03] p-3">
                    <div className="text-[11px] text-slate-500">成功率</div>
                    <div className="mt-1 text-xl font-black text-emerald-200">{Math.round(numberOr(experience?.summary?.successRate, 0) * 100)}%</div>
                  </div>
                  <div className="rounded-[8px] border border-white/8 bg-white/[0.03] p-3">
                    <div className="text-[11px] text-slate-500">样本数</div>
                    <div className="mt-1 text-xl font-black text-cyan-200">{numberOr(experience?.summary?.total, 0)}</div>
                  </div>
                </div>
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  {suggestions.length ? suggestions.slice(0, 2).map((item) => (
                    <div key={item.id || item.reason} className="rounded-[8px] border border-cyan-300/15 bg-cyan-300/8 p-3">
                      {item.reason || '后端建议可固化为模板。'}
                    </div>
                  )) : (
                    <div className="matrix-empty-state rounded-[8px] border border-white/10 bg-white/[0.03] p-3">暂无后端经验样本。</div>
                  )}
                </div>
              </section>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
};
