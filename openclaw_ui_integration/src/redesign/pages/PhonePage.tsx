import React from 'react';
import { Camera, CheckCircle2, Copy, KeyRound, PlayCircle, Plus, RefreshCcw, Save, ShieldCheck, Smartphone, StopCircle, Trash2, Unlock } from 'lucide-react';
import { Button, Chip, EmptyState, Field, Input, InlineState, Modal, Panel, SectionHeader, TextArea, Toggle } from '../components/ui';
import { getMockPhoneInventory, removeMockPhoneDevice, setMockPhoneSelection, upsertMockPhoneDevice } from '../api/mock';
import { formatDateTime, maskSecret } from '../lib/format';
import { readConfigValue, requestPhoneData, writeConfigValue } from '../api/adapters';
import { clearPhoneSecurePairing, warmPhoneSecurePairing, type PhonePairingSummary } from '../api/client';
import { displayPhoneBaseUrl, normalizeOrCleanPhoneBaseUrl, normalizePhoneBaseUrl } from '../lib/phoneUrl';
import { usePreviewStore } from '../store/appStore';
import QRCode from 'qrcode';

// 手机端 App(APKClaw)下载地址。更新 apk 时只改这一行;
// 建议 Gitee 上用固定文件名(如 OpenClaw-AgentPhone.apk)让链接永久不变,二维码一劳永逸。
const PHONE_APK_DOWNLOAD_URL =
  'https://gitee.com/rfdiosuao/lumiapkclaw/releases/download/lumiclaw13241/OpenClaw-AgentPhone.apk';

interface PhoneDevice {
  id: string;
  name: string;
  baseUrl: string;
  token: string;
  relayBaseUrl?: string;
  relayChannelId?: string;
  relayToken?: string;
  enabled?: boolean;
  tags?: string[];
  online?: boolean;
  active?: boolean;
  lastSeenAt?: string;
  lastAuthorizedAt?: string;
}

interface PhoneSnapshot {
  status: any;
  screenshotUrl: string;
  profile: any;
  vision: any;
  tree: any;
  recordings: any[];
  recordStatus: any;
  agentTask: any;
}

type TaskLogTone = 'info' | 'ok' | 'warn' | 'danger';

interface TaskLogEntry {
  id: string;
  at: string;
  tone: TaskLogTone;
  title: string;
  detail?: string;
}

interface AuthState {
  tone: 'neutral' | 'ok' | 'warn' | 'danger';
  title: string;
  detail?: string;
  pairing?: PhonePairingSummary;
}

const PHONE_AGENT_PATH = 'data/.openclaw/launcher/phone-agent.json';
const PHONE_AGENTS_PATH = 'data/.openclaw/launcher/phone-agents.json';
const TERMINAL_TASK_STATES = new Set(['success', 'error', 'cancelled', 'canceled']);
const CORE_SNAPSHOT_TIMEOUT_MS = 7000;
const EXTRA_SNAPSHOT_TIMEOUT_MS = 2200;

function createEmptySnapshot(): PhoneSnapshot {
  return {
    status: null,
    screenshotUrl: '',
    profile: null,
    vision: null,
    tree: null,
    recordings: [],
    recordStatus: null,
    agentTask: null,
  };
}

function defaultDevice(baseUrl = '', token = ''): PhoneDevice {
  return {
    id: 'primary-phone',
    name: '主 APKClaw 设备',
    baseUrl: normalizePhoneBaseUrl(baseUrl),
    token,
    relayBaseUrl: '',
    relayChannelId: '',
    relayToken: '',
    enabled: true,
    tags: ['primary'],
    online: false,
    active: true,
  };
}

function createPhoneDeviceDraft(existing: PhoneDevice[]): PhoneDevice {
  const used = new Set(existing.map((item) => item.id));
  let id = `phone-${Date.now().toString(36)}`;
  let counter = 2;
  while (used.has(id)) {
    id = `phone-${Date.now().toString(36)}-${counter}`;
    counter += 1;
  }
  return {
    id,
    name: 'APKClaw 设备',
    baseUrl: '',
    token: '',
    relayBaseUrl: '',
    relayChannelId: '',
    relayToken: '',
    enabled: true,
    tags: [],
    online: false,
    active: true,
  };
}

function snapshotRequest<T>(promise: Promise<T>, label: string, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(`${label} timeout after ${timeoutMs}ms`)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function hasVisibleSnapshot(snapshot: PhoneSnapshot) {
  return Boolean(snapshot.status || snapshot.screenshotUrl || snapshot.profile || snapshot.vision);
}

function formatBattery(profile: any) {
  const level = profile?.battery?.level ?? profile?.batteryLevel ?? profile?.batteryPercent;
  const numeric = Number(level);
  return Number.isFinite(numeric) ? `${Math.round(numeric)}%` : '暂无';
}

function nowIso() {
  return new Date().toISOString();
}

function terminalTaskStatus(value: unknown): boolean {
  return TERMINAL_TASK_STATES.has(String(value || '').toLowerCase());
}

function taskEvents(task: any): any[] {
  if (Array.isArray(task?.events)) return task.events;
  if (Array.isArray(task?.result?.events)) return task.result.events;
  return [];
}

function formatAgentEvent(event: any, index: number): { title: string; detail?: string; tone: TaskLogTone } {
  const type = String(event?.type || event?.event || `step_${index + 1}`);
  const round = event?.round != null ? `R${event.round} ` : '';
  const tool = event?.toolName || event?.tool_id || event?.toolId;
  const message = event?.message || event?.answer || event?.error || event?.parameters || '';
  const success = event?.success;
  return {
    title: `${round}${tool ? `${tool}` : type}`,
    detail: typeof message === 'string' ? message : JSON.stringify(message),
    tone: success === false || type.toLowerCase().includes('error') ? 'danger' : success === true ? 'ok' : 'info',
  };
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error || 'unknown_error');
}

function authErrorHelp(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes('missing_token')) return '缺少 APKClaw Token。请在手机端查看控制台令牌并填入。';
  if (lower.includes('invalid_phone_base_url') || lower.includes('invalid url') || lower.includes('ipv4')) return '手机地址格式不正确。局域网地址应类似 http://192.168.1.4:9527。';
  if (lower.includes('lumi_signature_repair_failed') || lower.includes('invalid lumi signature')) return 'Lumi 安全签名修复失败。启动器已尝试重新配对仍未通过；请确认电脑和手机时间一致，手机端 APKClaw 服务仍是最新版本，然后点击“重新配对”。';
  if (lower.includes('lumi body hash mismatch')) return 'Lumi 请求体校验失败。通常是任务内容在代理转发时被改写；请重新提交任务，若仍失败请升级启动器和 APKClaw。';
  if (lower.includes('lumi request timestamp') || lower.includes('invalid lumi timestamp')) return 'Lumi 时间戳校验失败。请把电脑和手机时间同步到自动网络时间后再重试。';
  if (lower.includes('lumi nonce has already been used')) return 'Lumi 防重放校验触发。请稍等几秒后重新提交任务。';
  if (lower.includes('missing lumi security headers') || lower.includes('unknown lumi launcher') || lower.includes('lumi_pair_failed')) return '安全配对失败或已失效。请确认 APKClaw 版本支持 Lumi 安全通道，然后点击“重新配对”。';
  if (lower.includes('401') || lower.includes('unauthorized')) return 'Token 无效。请重新复制手机端显示的令牌。';
  if (lower.includes('failed to fetch') || lower.includes('sending request') || lower.includes('network')) return '无法访问手机服务。确认电脑和手机在同一网络，APKClaw 控制服务正在运行。';
  return message;
}

export function PhonePage() {
  const settings = usePreviewStore((state) => state.settings);
  const updateSettings = usePreviewStore((state) => state.updateSettings);
  const selectedPhoneId = usePreviewStore((state) => state.selectedPhoneId);
  const setSelectedPhoneId = usePreviewStore((state) => state.setSelectedPhoneId);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const initialInventory = React.useMemo(() => getMockPhoneInventory(), []);
  const [devices, setDevices] = React.useState<PhoneDevice[]>(() => initialInventory.devices.map((item: any, index: number) => normalizePhoneDevice(item, `mock-${index + 1}`)).filter(Boolean) as PhoneDevice[]);
  const [snapshot, setSnapshot] = React.useState<PhoneSnapshot>(() => createEmptySnapshot());
  const [selectedId, setSelectedId] = React.useState<string | null>(selectedPhoneId || initialInventory.selectedDeviceId || devices[0]?.id || null);
  const [deviceDraft, setDeviceDraft] = React.useState<PhoneDevice>(() => devices[0] || defaultDevice(settings.phoneBaseUrl, settings.phoneToken));
  const [configOpen, setConfigOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [checkingDevice, setCheckingDevice] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [authState, setAuthState] = React.useState<AuthState>({ tone: 'neutral', title: '等待授权检查' });
  const [apkModalOpen, setApkModalOpen] = React.useState(false);
  const [apkQrDataUrl, setApkQrDataUrl] = React.useState('');

  React.useEffect(() => {
    if (!apkModalOpen) return;
    let cancelled = false;
    QRCode.toDataURL(PHONE_APK_DOWNLOAD_URL, { width: 240, margin: 1 })
      .then((url) => { if (!cancelled) setApkQrDataUrl(url); })
      .catch(() => { if (!cancelled) setApkQrDataUrl(''); });
    return () => { cancelled = true; };
  }, [apkModalOpen]);

  const [actionPrompt, setActionPrompt] = React.useState('读取当前屏幕，判断下一步可以安全执行的动作。');
  const [sending, setSending] = React.useState(false);
  const [activeTaskId, setActiveTaskId] = React.useState('');
  const [taskLogs, setTaskLogs] = React.useState<TaskLogEntry[]>([]);
  const taskRunRef = React.useRef(0);
  const selectedDeviceRef = React.useRef<PhoneDevice | null>(null);
  const refreshRunRef = React.useRef(0);
  const refreshInFlightRef = React.useRef(false);
  const taskBusyRef = React.useRef(false);

  const draftPersisted = Boolean(deviceDraft.id && devices.some((device) => device.id === deviceDraft.id));
  const selectedDevice = selectedId ? devices.find((device) => device.id === selectedId) || null : null;

  React.useEffect(() => {
    selectedDeviceRef.current = selectedDevice;
  }, [selectedDevice]);

  const addTaskLog = React.useCallback((tone: TaskLogTone, title: string, detail?: string) => {
    setTaskLogs((items) => [
      ...items,
      { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, at: nowIso(), tone, title, detail },
    ].slice(-120));
  }, []);

  const updateDeviceRuntime = React.useCallback((deviceId: string, patch: Partial<PhoneDevice>) => {
    setDevices((items) => items.map((item) => (item.id === deviceId ? { ...item, ...patch } : item)));
    setDeviceDraft((state) => (state.id === deviceId ? { ...state, ...patch } : state));
  }, []);

  React.useEffect(() => {
    let cancelled = false;

    async function loadPersistedDevices() {
      try {
        const [store, single] = await Promise.all([
          readConfigValue(settings, PHONE_AGENTS_PATH, null).catch(() => null),
          readConfigValue(settings, PHONE_AGENT_PATH, null).catch(() => null),
        ]);
        const loaded = normalizePhoneInventory(store, single);
        if (cancelled) return;

        if (loaded.devices.length) {
          const nextSelected =
            loaded.devices.find((device) => device.id === (selectedPhoneId || loaded.selectedDeviceId)) ||
            loaded.devices[0];
          setDevices(loaded.devices);
          setSelectedId(nextSelected.id);
          setDeviceDraft(nextSelected);
          loaded.devices.forEach(upsertMockPhoneDevice);
          setMockPhoneSelection(nextSelected.id);
          if (settings.phoneBaseUrl !== nextSelected.baseUrl || settings.phoneToken !== nextSelected.token) {
            updateSettings({ phoneBaseUrl: nextSelected.baseUrl, phoneToken: nextSelected.token });
          }
          return;
        }

        if (settings.phoneBaseUrl.trim() && settings.phoneToken.trim()) {
          const migrated = normalizePhoneDevice({
            ...defaultDevice(settings.phoneBaseUrl, settings.phoneToken),
            name: '主 APKClaw 设备',
          }, 'primary-phone');
          if (!migrated) return;
          await savePhoneInventoryConfig(settings, [migrated], migrated.id);
          if (cancelled) return;
          setDevices([migrated]);
          setSelectedId(migrated.id);
          setDeviceDraft(migrated);
          upsertMockPhoneDevice(migrated);
          setMockPhoneSelection(migrated.id);
          pushToast({ tone: 'ok', title: '手机配置已迁移', detail: PHONE_AGENT_PATH });
          return;
        }

        setDevices([]);
        setSelectedId(null);
        setDeviceDraft(defaultDevice(settings.phoneBaseUrl, settings.phoneToken));
      } catch {
        if (!cancelled && !initialInventory.devices.length) {
          setDevices([]);
          setSelectedId(null);
        }
      }
    }

    loadPersistedDevices();
    return () => {
      cancelled = true;
    };
  }, [
    settings.bridgeBaseUrl,
    settings.bridgeToken,
    settings.transportMode,
    settings.phoneBaseUrl,
    settings.phoneToken,
    selectedPhoneId,
    updateSettings,
    pushToast,
    initialInventory.devices.length,
  ]);

  React.useEffect(() => {
    if (!selectedId && devices[0]) setSelectedId(devices[0].id);
  }, [devices, selectedId]);

  React.useEffect(() => {
    if (!selectedId) return;
    setSelectedPhoneId(selectedId);
    setMockPhoneSelection(selectedId);
    const next = devices.find((device) => device.id === selectedId);
    if (next) setDeviceDraft(next);
  }, [selectedId, devices, setSelectedPhoneId]);

  const selectDevice = React.useCallback(async (device: PhoneDevice) => {
    setSelectedId(device.id);
    setDeviceDraft(device);
    setSelectedPhoneId(device.id);
    setMockPhoneSelection(device.id);
    updateSettings({ phoneBaseUrl: device.baseUrl, phoneToken: device.token });
    setSnapshot(createEmptySnapshot());
    setError(null);
    setAuthState({ tone: device.lastAuthorizedAt ? 'ok' : 'neutral', title: device.lastAuthorizedAt ? '已保存安全配对' : '等待授权检查', detail: device.lastAuthorizedAt ? `最近验证 ${formatDateTime(device.lastAuthorizedAt)}` : undefined });
    try {
      await savePhoneInventoryConfig(settings, devices, device.id);
    } catch {
      // Selection is still useful locally even if the bridge is temporarily unavailable.
    }
  }, [devices, settings, setSelectedPhoneId, updateSettings]);

  const testDevice = React.useCallback(async (device: PhoneDevice, forcePair = false): Promise<PhoneDevice> => {
    const context = { baseUrl: device.baseUrl, token: device.token };
    const status = await requestPhoneData<any>(settings, context, '/api/device/status');
    const pairing = await warmPhoneSecurePairing(device.baseUrl, device.token, forcePair);
    await requestPhoneData(settings, context, '/api/lumi/device/profile?includeApps=false&appLimit=1', 'GET', undefined, { timeoutMs: 12_000 });
    const now = nowIso();
    setAuthState({
      tone: 'ok',
      title: 'Token 与 Lumi 安全通道已验证',
      detail: `Launcher ${pairing.launcherId.slice(0, 18)} · 过期 ${formatDateTime(pairing.expiresAt)}`,
      pairing,
    });
    return {
      ...device,
      online: Boolean((status.data as any)?.online ?? true),
      lastSeenAt: now,
      lastAuthorizedAt: now,
    };
  }, [settings]);

  const refresh = React.useCallback(async (_reason: 'auto' | 'manual' = 'manual') => {
    const device = selectedDeviceRef.current;
    if (!device) return;
    if (!device.baseUrl.trim() || !device.token.trim()) return;
    if (refreshInFlightRef.current) return;
    if (taskBusyRef.current) return;
    const runId = refreshRunRef.current + 1;
    refreshRunRef.current = runId;
    refreshInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const context = { baseUrl: device.baseUrl, token: device.token };
      // 并发拉快照前,先用一个轻量探针把 Lumi 安全通道配好/自愈一次。
      // 否则下面那批并发签名请求会各自发现密钥失效(例如刚重装手机端 APKClaw、
      // 密钥被重置后)、各自抢着重新配对、互相清掉对方刚配好的密钥,刷出好几条
      // “任务失败”。先探针 → 内置重试只干净地重配一次 → 这批请求复用好密钥。
      try {
        // device/status 是 token 鉴权(手机时钟偏差也能通过),且携带 serverTime →
        // 先拿它把"手机↔电脑时钟偏差"记下来,后面的签名请求才能落在手机的时间窗口内,
        // 避免客户手机时间不准导致 Lumi 签名 403。
        await requestPhoneData(settings, context, '/api/device/status', 'GET', undefined, { timeoutMs: 12_000 });
        await warmPhoneSecurePairing(device.baseUrl, device.token);
        await requestPhoneData(
          settings,
          context,
          '/api/lumi/device/profile?includeApps=false&appLimit=1',
          'GET',
          undefined,
          { timeoutMs: 12_000 },
        );
      } catch {
        // 探针失败不阻断快照:基于 token 的 status/截图/screen_tree 仍可返回,
        // 真正的配对/时间问题会由下面的快照给出一条清晰错误。
      }
      const settled = await Promise.allSettled([
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/device/status', 'GET', undefined, { timeoutMs: CORE_SNAPSHOT_TIMEOUT_MS }), '/api/device/status', CORE_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/tool/screenshot', 'GET', undefined, { timeoutMs: CORE_SNAPSHOT_TIMEOUT_MS }), '/api/tool/screenshot', CORE_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/lumi/device/profile?includeApps=true&appLimit=80', 'GET', undefined, { timeoutMs: CORE_SNAPSHOT_TIMEOUT_MS }), '/api/lumi/device/profile', CORE_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/lumi/vision/frame?_lumi=1', 'GET', undefined, { timeoutMs: CORE_SNAPSHOT_TIMEOUT_MS }), '/api/lumi/vision/frame', CORE_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/tool/screen_tree', 'GET', undefined, { timeoutMs: EXTRA_SNAPSHOT_TIMEOUT_MS }), '/api/tool/screen_tree', EXTRA_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/lumi/media/videos?_lumi=1', 'GET', undefined, { timeoutMs: EXTRA_SNAPSHOT_TIMEOUT_MS }), '/api/lumi/media/videos', EXTRA_SNAPSHOT_TIMEOUT_MS),
        snapshotRequest(requestPhoneData<any>(settings, context, '/api/lumi/media/record/status?_lumi=1', 'GET', undefined, { timeoutMs: EXTRA_SNAPSHOT_TIMEOUT_MS }), '/api/lumi/media/record/status', EXTRA_SNAPSHOT_TIMEOUT_MS),
      ]);
      if (refreshRunRef.current !== runId || selectedDeviceRef.current?.id !== device.id) return;
      const [status, screenshot, profile, vision, tree, recordings, recordStatus] = settled.map((item) => (item.status === 'fulfilled' ? item.value.data : null));
      const failures = settled
        .map((item) => (item.status === 'rejected' ? authErrorHelp(errorText(item.reason)) : ''))
        .filter(Boolean);
      const coreReady = Boolean(status || screenshot || profile || vision);

      setSnapshot((state) => ({
        ...state,
        status: status || state.status,
        screenshotUrl: extractScreenshotUrl(screenshot) || extractScreenshotUrl(vision?.image) || state.screenshotUrl,
        profile: profile || state.profile,
        vision: vision || state.vision,
        tree: tree || state.tree,
        recordings: recordings?.recordings || state.recordings,
        recordStatus: recordStatus || state.recordStatus,
      }));

      if (status || profile || vision) {
        const now = nowIso();
        updateDeviceRuntime(device.id, { online: true, lastSeenAt: now, lastAuthorizedAt: profile || vision ? now : device.lastAuthorizedAt });
        setAuthState({
          tone: profile || vision ? 'ok' : 'warn',
          title: profile || vision ? '授权正常' : '基础连接正常，安全接口未完成',
          detail: failures[0],
        });
      }
      if (failures.length) {
        if (!coreReady) setError(failures[0]);
        addTaskLog('warn', coreReady ? '设备附加快照部分失败' : '设备快照读取失败', failures[0]);
      }
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      setError(message);
      setAuthState({ tone: 'danger', title: '授权或连接失败', detail: message });
      updateDeviceRuntime(device.id, { online: false });
      addTaskLog('danger', '刷新失败', message);
    } finally {
      refreshInFlightRef.current = false;
      if (refreshRunRef.current === runId) setLoading(false);
    }
  }, [addTaskLog, settings, updateDeviceRuntime]);

  React.useEffect(() => {
    refresh('auto');
  }, [refresh, selectedDevice?.id, selectedDevice?.baseUrl, selectedDevice?.token]);

  const runPhoneAction = async (label: string, path: string, body: Record<string, unknown> = {}) => {
    if (!selectedDevice) return null;
    try {
      const result = await requestPhoneData(settings, { baseUrl: selectedDevice.baseUrl, token: selectedDevice.token }, path, 'POST', body, { timeoutMs: 30_000 });
      pushToast({ tone: 'ok', title: label, detail: selectedDevice.name });
      addTaskLog('ok', label, selectedDevice.name);
      return result.data;
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      pushToast({ tone: 'danger', title: `${label}失败`, detail: message });
      addTaskLog('danger', `${label}失败`, message);
      return null;
    }
  };

  const handleCapture = async () => {
    if (!selectedDevice) return;
    try {
      const response = await requestPhoneData(settings, { baseUrl: selectedDevice.baseUrl, token: selectedDevice.token }, '/api/tool/screenshot', 'GET', undefined, { timeoutMs: 12_000 });
      const screenshotUrl = extractScreenshotUrl(response.data);
      if (!screenshotUrl) {
        pushToast({ tone: 'warn', title: '截图已返回但没有图片数据', detail: selectedDevice.name });
        addTaskLog('warn', '截图无图片数据', selectedDevice.name);
        return;
      }
      setSnapshot((state) => ({ ...state, screenshotUrl }));
      pushToast({ tone: 'ok', title: '截图已获取', detail: selectedDevice.name });
      addTaskLog('ok', '截图已获取', selectedDevice.name);
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      pushToast({ tone: 'danger', title: '截图失败', detail: message });
      addTaskLog('danger', '截图失败', message);
    }
  };

  const handleWake = async () => {
    await runPhoneAction('唤醒指令已发送', '/api/device/wake');
    refresh('manual');
  };

  const handleTask = async () => {
    if (!selectedDevice) return;
    if (sending) return;
    const prompt = actionPrompt.trim();
    if (!prompt) {
      pushToast({ tone: 'warn', title: '任务说明不能为空' });
      return;
    }
    const runId = taskRunRef.current + 1;
    const seenEvents = new Set<string>();
    taskRunRef.current = runId;
    taskBusyRef.current = true;
    refreshRunRef.current += 1;
    setLoading(false);
    setSending(true);
    setError(null);
    addTaskLog('info', '提交手机任务', prompt);
    try {
      const start = await requestPhoneData<any>(
        settings,
        { baseUrl: selectedDevice.baseUrl, token: selectedDevice.token },
        '/api/lumi/agent/tasks',
        'POST',
        {
          prompt,
          use_template: true,
          force_agent: false,
          read_only: false,
          tool_policy: 'safe_action',
          timeout_sec: 120,
        },
        { timeoutMs: 60_000 },
      );
      const taskId = extractTaskId(start.data);
      if (!taskId) throw new Error('APKClaw did not return a task id.');
      setActiveTaskId(taskId);
      setSnapshot((state) => ({ ...state, agentTask: { ...start.data, taskId, status: start.data?.status || 'running' } }));
      pushToast({ tone: 'ok', title: '任务已提交', detail: selectedDevice.name });
      addTaskLog('ok', '任务已提交', taskId);

      for (let i = 0; i < 120; i += 1) {
        if (taskRunRef.current !== runId) return;
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const result = await requestPhoneData<any>(
          settings,
          { baseUrl: selectedDevice.baseUrl, token: selectedDevice.token },
          `/api/lumi/agent/tasks/${encodeURIComponent(taskId)}`,
          'GET',
          undefined,
          { timeoutMs: 15_000 },
        );
        const task = result.data;
        setSnapshot((state) => ({ ...state, agentTask: task }));
        taskEvents(task).forEach((event, index) => {
          const key = `${event?.round || ''}:${event?.type || ''}:${event?.toolId || event?.toolName || ''}:${event?.message || ''}:${index}`;
          if (seenEvents.has(key)) return;
          seenEvents.add(key);
          const formatted = formatAgentEvent(event, index);
          addTaskLog(formatted.tone, formatted.title, formatted.detail);
        });
        if (terminalTaskStatus(task?.status)) {
          addTaskLog(task.status === 'success' ? 'ok' : task.status === 'cancelled' ? 'warn' : 'danger', `任务${task.status === 'success' ? '完成' : '结束'}`, task?.error || task?.result?.answer || taskId);
          return;
        }
      }
      addTaskLog('warn', '任务轮询超时', taskId);
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      pushToast({ tone: 'danger', title: '任务失败', detail: message });
      addTaskLog('danger', '任务失败', message);
    } finally {
      if (taskRunRef.current === runId) {
        setSending(false);
        setActiveTaskId('');
      }
      taskBusyRef.current = false;
    }
  };

  const handleCancelTask = async () => {
    if (!selectedDevice) return;
    const taskId = activeTaskId || extractTaskId(snapshot.agentTask);
    if (!taskId) return;
    taskRunRef.current += 1;
    taskBusyRef.current = true;
    setSending(false);
    setActiveTaskId('');
    addTaskLog('warn', '请求停止任务', taskId);
    try {
      const cancelled = await requestPhoneData(
        settings,
        { baseUrl: selectedDevice.baseUrl, token: selectedDevice.token },
        `/api/lumi/agent/tasks/${encodeURIComponent(taskId)}/cancel`,
        'POST',
        {},
        { timeoutMs: 30_000 },
      );
      setSnapshot((state) => ({ ...state, agentTask: cancelled.data || { taskId, status: 'cancelled' } }));
      pushToast({ tone: 'warn', title: '任务已停止', detail: taskId.slice(0, 12) });
      addTaskLog('warn', '任务已停止', taskId);
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      pushToast({ tone: 'danger', title: '停止任务失败', detail: message });
      addTaskLog('danger', '停止任务失败', message);
    } finally {
      taskBusyRef.current = false;
    }
  };

  const handleToggleRecord = async () => {
    const active = Boolean(snapshot.recordStatus?.recording);
    const result = await runPhoneAction(active ? '录屏已停止' : '录屏已开始', active ? '/api/lumi/media/record/stop' : '/api/lumi/media/record/start');
    if (result) setSnapshot((state) => ({ ...state, recordStatus: result }));
  };

  const handleAddDevice = () => {
    const draft = createPhoneDeviceDraft(devices);
    setDeviceDraft(draft);
    setSelectedId(draft.id);
    setConfigOpen(true);
    setSnapshot(createEmptySnapshot());
    setAuthState({ tone: 'neutral', title: '新设备待验证', detail: '输入局域网 IP 会自动补全 http:// 和 9527 端口。' });
  };

  const buildValidatedDraft = React.useCallback((): { device?: PhoneDevice; error?: string } => {
    const normalizedBaseUrl = normalizePhoneBaseUrl(deviceDraft.baseUrl);
    if (deviceDraft.baseUrl.trim() && !normalizedBaseUrl) {
      return { error: `手机地址格式不正确：${deviceDraft.baseUrl.trim()}` };
    }
    const token = textValue(deviceDraft.token);
    if (!normalizedBaseUrl || !token) {
      return { error: '请填写 APKClaw 地址和 Token。' };
    }
    const usedIds = new Set(devices.filter((item) => item.id !== deviceDraft.id).map((item) => item.id));
    const id = uniqueDeviceId(textValue(deviceDraft.id) || slugFromUrl(normalizedBaseUrl), usedIds);
    return {
      device: {
        ...deviceDraft,
        id,
        name: textValue(deviceDraft.name) || 'APKClaw 设备',
        baseUrl: normalizedBaseUrl,
        token,
        relayBaseUrl: normalizePhoneBaseUrl(deviceDraft.relayBaseUrl),
        relayChannelId: textValue(deviceDraft.relayChannelId),
        relayToken: textValue(deviceDraft.relayToken),
        enabled: deviceDraft.enabled !== false,
        tags: deviceDraft.tags || [],
      },
    };
  }, [deviceDraft, devices]);

  const persistDevice = React.useCallback(async (device: PhoneDevice) => {
    const persisted = upsertPhoneDeviceList(devices, device);
    await savePhoneInventoryConfig(settings, persisted, device.id);
    setDevices(persisted);
    upsertMockPhoneDevice(device);
    setSelectedId(device.id);
    setDeviceDraft(device);
    setSelectedPhoneId(device.id);
    setMockPhoneSelection(device.id);
    updateSettings({ phoneBaseUrl: device.baseUrl, phoneToken: device.token });
  }, [devices, settings, setSelectedPhoneId, updateSettings]);

  const handleSaveDevice = async (mode: 'save' | 'test') => {
    const { device, error: validationError } = buildValidatedDraft();
    if (!device) {
      const message = validationError || '设备配置不完整。';
      setAuthState({ tone: 'danger', title: '设备配置无效', detail: message });
      pushToast({ tone: 'danger', title: '设备配置无效', detail: message });
      return;
    }
    setSaving(true);
    setCheckingDevice(mode === 'test');
    try {
      const next = mode === 'test' ? await testDevice(device, false) : device;
      await persistDevice(next);
      pushToast({ tone: 'ok', title: mode === 'test' ? '设备已验证并保存' : '设备已保存', detail: next.name });
      addTaskLog('ok', mode === 'test' ? '设备验证通过' : '设备已保存', `${next.name} · ${next.baseUrl}`);
      setConfigOpen(false);
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      setAuthState({ tone: 'danger', title: '设备验证失败', detail: message });
      pushToast({ tone: 'danger', title: '设备验证失败', detail: message });
      addTaskLog('danger', '设备验证失败', message);
    } finally {
      setSaving(false);
      setCheckingDevice(false);
    }
  };

  const handleRepairPairing = async () => {
    const { device, error: validationError } = buildValidatedDraft();
    if (!device) {
      setAuthState({ tone: 'danger', title: '无法重新配对', detail: validationError });
      return;
    }
    setCheckingDevice(true);
    try {
      await clearPhoneSecurePairing(device.baseUrl, device.token);
      const repaired = await testDevice(device, true);
      await persistDevice(repaired);
      pushToast({ tone: 'ok', title: '安全通道已重新配对', detail: repaired.name });
      addTaskLog('ok', '安全通道已重新配对', repaired.baseUrl);
    } catch (err) {
      const message = authErrorHelp(errorText(err));
      setAuthState({ tone: 'danger', title: '重新配对失败', detail: message });
      addTaskLog('danger', '重新配对失败', message);
    } finally {
      setCheckingDevice(false);
    }
  };

  const handleRemoveDevice = async (id: string) => {
    const removed = devices.find((item) => item.id === id);
    const persisted = devices.filter((item) => item.id !== id);
    const nextSelected = persisted[0] || null;
    try {
      await savePhoneInventoryConfig(settings, persisted, nextSelected?.id || '');
      if (removed) await clearPhoneSecurePairing(removed.baseUrl, removed.token);
    } catch (err) {
      pushToast({ tone: 'danger', title: '手机配置写入失败', detail: errorText(err) });
      return;
    }
    setDevices(persisted);
    removeMockPhoneDevice(id);
    setSelectedId(nextSelected?.id || null);
    if (nextSelected) {
      setDeviceDraft(nextSelected);
      updateSettings({ phoneBaseUrl: nextSelected.baseUrl, phoneToken: nextSelected.token });
    } else {
      updateSettings({ phoneBaseUrl: '', phoneToken: '' });
      setDeviceDraft(defaultDevice('', ''));
      setSnapshot(createEmptySnapshot());
    }
    pushToast({ tone: 'warn', title: '设备已移除', detail: id });
    addTaskLog('warn', '设备已移除', id);
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">APKClaw 星桥</div>
          <h1>手机控制台只做安全控制桥。</h1>
          <p>桌面端负责授权、下发任务和留痕；APKClaw 只接收经过 Token 与 Lumi 签名校验的控制请求。</p>
        </div>
        <div className="hero-actions">
          <Button variant="quiet" icon={Smartphone} onClick={() => setApkModalOpen(true)}>下载手机端App</Button>
          <Button variant="primary" icon={RefreshCcw} onClick={() => refresh('manual')} disabled={!selectedDevice || loading}>刷新</Button>
          <Button variant="secondary" icon={Camera} onClick={handleCapture} disabled={!selectedDevice}>截图</Button>
          <Button variant="success" icon={Unlock} onClick={handleWake} disabled={!selectedDevice}>唤醒</Button>
        </div>
      </section>

      <section className="content-grid content-grid-phone">
        <Panel className="surface-panel surface-panel-narrow">
          <SectionHeader
            eyebrow="设备"
            title="已保存设备"
            subtitle="选择一个目标设备；新增设备先验证 Token 与安全通道。"
            action={<Button variant="quiet" icon={Plus} onClick={handleAddDevice}>新增</Button>}
          />
          <div className="device-list device-list-compact">
            {devices.length ? devices.map((device) => (
              <button
                key={device.id}
                type="button"
                className={selectedId === device.id ? 'device-card device-card-active' : 'device-card'}
                onClick={() => void selectDevice(device)}
              >
                <div className="device-card-head">
                  <strong>{device.name}</strong>
                  <Chip tone={device.online ? 'ok' : device.lastAuthorizedAt ? 'warn' : 'neutral'}>{device.online ? '在线' : device.lastAuthorizedAt ? '已授权' : '已保存'}</Chip>
                </div>
                <div className="device-card-meta">{displayPhoneBaseUrl(device.baseUrl)}</div>
                <div className="device-card-meta">{maskSecret(device.token)}</div>
                {device.lastSeenAt ? <div className="device-card-meta">最近连接 {formatDateTime(device.lastSeenAt)}</div> : null}
              </button>
            )) : (
              <EmptyState title="没有设备" description="点击新增，填入 APKClaw 局域网地址和 Token。" />
            )}
          </div>
        </Panel>

        <div className="phone-workspace phone-workspace-simple">
          <Panel className="surface-panel phone-focus-panel">
            <SectionHeader
              eyebrow="实时状态"
              title={selectedDevice?.name || '未选择设备'}
              subtitle={selectedDevice ? displayPhoneBaseUrl(selectedDevice.baseUrl) : '先新增 APKClaw 设备。'}
              action={<Chip tone={snapshot.status?.online || selectedDevice?.online ? 'ok' : authState.tone === 'danger' ? 'danger' : 'warn'}>{snapshot.status?.online || selectedDevice?.online ? '已连接' : '待确认'}</Chip>}
            />
            {!selectedDevice ? (
              <EmptyState title="没有设备" description="在设备配置区新增 APKClaw 地址和 Token。" />
            ) : loading && !hasVisibleSnapshot(snapshot) ? (
              <div className="panel-loading-inline">正在读取设备快照...</div>
            ) : error ? (
              <InlineState tone="danger" title="设备快照读取失败" description={error} />
            ) : (
              <div className="phone-simple-grid">
                <div className="phone-screen">
                  {snapshot.screenshotUrl ? <img src={snapshot.screenshotUrl} alt="APKClaw screenshot" /> : <div className="phone-screen-placeholder" aria-label="暂无截图" />}
                </div>
                <div className="phone-summary">
                  {(() => {
                    const st = snapshot.status as any;
                    if (!st) return null;
                    const issues: string[] = [];
                    if (st.accessibilityRunning === false) {
                      issues.push('无障碍服务未开启：截图、点击、滑动都会失效。请到手机「设置 → 无障碍」开启本应用（若开关是灰色，先到「应用信息 → ⋮ → 允许受限的设置」）。');
                    }
                    if (st.keyguardLocked === true || st.deviceLocked === true) {
                      issues.push('手机当前锁屏：请点上方「唤醒」或手动解锁后再操作。');
                    }
                    if (st.overlayPermission === false) {
                      issues.push('悬浮窗权限未开：光标预览不可用（不影响截图与点击）。');
                    }
                    if (!issues.length) return null;
                    const critical = st.accessibilityRunning === false;
                    return (
                      <InlineState
                        tone={critical ? 'danger' : 'warn'}
                        title={critical ? '演示前请先修复：手机无障碍服务已关闭' : '设备状态提醒'}
                        description={issues.join(' ')}
                      />
                    );
                  })()}
                  <div className="detail-stack">
                    <div className="detail-row"><span className="detail-label">版本</span><span className="detail-value">{snapshot.status?.versionInfo || snapshot.status?.version || '暂无'}</span></div>
                    <div className="detail-row"><span className="detail-label">屏幕</span><span className="detail-value">{snapshot.status?.screenOn ? '亮屏' : '未知'}</span></div>
                    <div className="detail-row"><span className="detail-label">无障碍</span><span className="detail-value">{snapshot.status?.accessibilityRunning ? '运行中' : (snapshot.status ? '未开启 ⚠' : '未确认')}</span></div>
                    <div className="detail-row"><span className="detail-label">电量</span><span className="detail-value">{formatBattery(snapshot.profile)}</span></div>
                  </div>
                  {loading ? <InlineState tone="neutral" title="正在刷新快照" description="截图和状态会先显示，视频/录屏等附加能力稍后更新。" /> : null}
                  <InlineState tone={authState.tone} title={authState.title} description={authState.detail} icon={authState.tone === 'ok' ? ShieldCheck : KeyRound} />
                  <div className="button-row">
                    <Button variant="secondary" icon={Camera} onClick={handleCapture}>截图</Button>
                    <Button variant="success" icon={PlayCircle} onClick={handleTask} disabled={sending}>{sending ? '执行中...' : '执行任务'}</Button>
                    {activeTaskId || sending ? <Button variant="danger" icon={StopCircle} onClick={() => void handleCancelTask()}>停止任务</Button> : null}
                    <Button variant="danger" icon={StopCircle} onClick={handleToggleRecord}>录屏</Button>
                  </div>
                  <Field label="任务说明" hint="/api/lumi/agent/tasks">
                    <TextArea rows={5} value={actionPrompt} onChange={(event) => setActionPrompt(event.target.value)} />
                  </Field>
                </div>
              </div>
            )}
          </Panel>

          <Panel className="surface-panel">
            <details
              className="settings-details"
              open={configOpen}
              onToggle={(event) => setConfigOpen(event.currentTarget.open)}
            >
              <summary>设备配置</summary>
              <div className="form-grid form-grid-phone">
                <Field label="设备 ID"><Input value={deviceDraft.id} onChange={(event) => setDeviceDraft((state) => ({ ...state, id: event.target.value }))} /></Field>
                <Field label="名称"><Input value={deviceDraft.name} onChange={(event) => setDeviceDraft((state) => ({ ...state, name: event.target.value }))} placeholder="Redmi Note" /></Field>
                <Field label="APKClaw 地址" hint={normalizePhoneBaseUrl(deviceDraft.baseUrl) || '输入 192.168.1.4 会自动补 http:// 和 :9527'}>
                  <Input
                    value={deviceDraft.baseUrl}
                    onChange={(event) => setDeviceDraft((state) => ({ ...state, baseUrl: normalizePhoneInputDraft(event.target.value) }))}
                    onBlur={(event) => setDeviceDraft((state) => ({ ...state, baseUrl: normalizeOrCleanPhoneBaseUrl(event.target.value) }))}
                    placeholder="http://192.168.1.4:9527"
                  />
                </Field>
                <Field label="Token"><Input type="password" value={deviceDraft.token} onChange={(event) => setDeviceDraft((state) => ({ ...state, token: event.target.value.trim() }))} placeholder="APKClaw 控制台令牌" /></Field>
                <Field label="转发地址">
                  <Input
                    value={deviceDraft.relayBaseUrl || ''}
                    onChange={(event) => setDeviceDraft((state) => ({ ...state, relayBaseUrl: normalizePhoneInputDraft(event.target.value) }))}
                    onBlur={(event) => setDeviceDraft((state) => ({ ...state, relayBaseUrl: normalizeOrCleanPhoneBaseUrl(event.target.value) }))}
                  />
                </Field>
                <Field label="转发频道"><Input value={deviceDraft.relayChannelId || ''} onChange={(event) => setDeviceDraft((state) => ({ ...state, relayChannelId: event.target.value }))} /></Field>
                <Field label="转发 Token"><Input type="password" value={deviceDraft.relayToken || ''} onChange={(event) => setDeviceDraft((state) => ({ ...state, relayToken: event.target.value.trim() }))} /></Field>
                <Field label="标签"><Input value={(deviceDraft.tags || []).join(', ')} onChange={(event) => setDeviceDraft((state) => ({ ...state, tags: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) }))} /></Field>
              </div>
              <div className="button-row">
                <Button variant="primary" icon={CheckCircle2} onClick={() => void handleSaveDevice('test')} disabled={saving || checkingDevice}>{checkingDevice ? '验证中...' : '测试并保存'}</Button>
                <Button variant="secondary" icon={Save} onClick={() => void handleSaveDevice('save')} disabled={saving}>仅保存</Button>
                <Button variant="quiet" icon={ShieldCheck} onClick={() => void handleRepairPairing()} disabled={checkingDevice}>重新配对</Button>
                {draftPersisted ? <Button variant="danger" icon={Trash2} onClick={() => handleRemoveDevice(deviceDraft.id)}>移除当前</Button> : null}
                <Toggle checked={deviceDraft.enabled !== false} onChange={(checked) => setDeviceDraft((state) => ({ ...state, enabled: checked }))} label="启用" hint="控制该设备是否可被选择。" />
              </div>
            </details>
          </Panel>

          <Panel className="surface-panel">
            <details className="settings-details">
              <summary>诊断、节点树和录屏</summary>
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">采集时间</span><span className="detail-value">{formatDateTime(snapshot.profile?.capturedAt)}</span></div>
                <div className="detail-row"><span className="detail-label">应用数量</span><span className="detail-value">{Array.isArray(snapshot.profile?.apps) ? snapshot.profile.apps.length : 0}</span></div>
                <div className="detail-row"><span className="detail-label">视觉状态</span><span className="detail-value">{snapshot.vision?.mode || snapshot.vision?.currentScreen?.title || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">任务状态</span><span className="detail-value">{snapshot.agentTask?.status || 'idle'}</span></div>
              </div>
              <div className="tree-list">
                {Array.isArray(snapshot.tree?.nodes) && snapshot.tree.nodes.length ? snapshot.tree.nodes.slice(0, 8).map((node: any, index: number) => (
                  <div key={node.id || index} className="tree-row">
                    <span>{node.depth}</span>
                    <strong>{node.className}</strong>
                    <span>{node.text || node.description || node.resourceId || 'node'}</span>
                  </div>
                )) : <EmptyState title="暂无节点树" description="刷新快照后获取界面层级。" />}
              </div>
              <div className="recording-list">
                {snapshot.recordings.length ? snapshot.recordings.map((record: any) => (
                  <div key={record.id || record.path} className="record-card">
                    <strong>{record.filename || 'recording'}</strong>
                    <span>{record.downloadUrl || record.path}</span>
                    <span>{record.mimeType || 'video/mp4'}</span>
                  </div>
                )) : <EmptyState title="暂无录屏" description="需要留证时使用录屏按钮。" />}
              </div>
            </details>
          </Panel>

          <Panel className="surface-panel phone-task-log-panel">
            <SectionHeader
              eyebrow="任务日志"
              title="手机执行日志"
              subtitle="设备验证、任务提交、Agent 事件和停止动作都会在这里留痕。"
              action={<Button variant="quiet" icon={Trash2} onClick={() => setTaskLogs([])}>清空</Button>}
            />
            <div className="phone-task-log">
              {taskLogs.length ? taskLogs.map((item) => (
                <div key={item.id} className={`phone-task-log-row phone-task-log-row-${item.tone}`}>
                  <span>{formatDateTime(item.at)}</span>
                  <strong>{item.title}</strong>
                  {item.detail ? <p>{item.detail}</p> : null}
                </div>
              )) : <EmptyState title="暂无任务日志" description="执行手机任务后，步骤和结果会显示在这里。" />}
            </div>
          </Panel>
        </div>
      </section>

      <Modal
        open={apkModalOpen}
        title="下载手机端 App"
        subtitle="让客户用手机扫码下载安装 APKClaw"
        onClose={() => setApkModalOpen(false)}
      >
        <div className="apk-download-modal">
          {apkQrDataUrl ? (
            <img
              src={apkQrDataUrl}
              alt="手机端 App 下载二维码"
              width={240}
              height={240}
              style={{ display: 'block', margin: '0 auto', borderRadius: 12 }}
            />
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0' }}>二维码生成中...</div>
          )}
          <p style={{ textAlign: 'center', marginTop: 12 }}>
            让客户用手机相机/浏览器扫码，或复制下方链接在手机里打开下载。
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <code
              style={{
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 12,
                padding: '8px 10px',
                background: 'rgba(0,0,0,0.06)',
                borderRadius: 8,
              }}
            >
              {PHONE_APK_DOWNLOAD_URL}
            </code>
            <Button
              variant="secondary"
              icon={Copy}
              onClick={() => {
                void navigator.clipboard?.writeText(PHONE_APK_DOWNLOAD_URL);
                pushToast({ tone: 'ok', title: '链接已复制' });
              }}
            >
              复制
            </Button>
          </div>
          <InlineState
            tone="neutral"
            title="安装三步"
            description="① 手机文件管理器点 apk 安装　② 小米/红米先到开发者选项关「MIUI 优化」　③ 开无障碍若变灰，到 应用信息→右上角⋮→允许受限的设置。"
          />
        </div>
      </Modal>
    </div>
  );
}

function normalizePhoneInventory(store: any, single: any): { selectedDeviceId: string; devices: PhoneDevice[] } {
  const storeDevices = Array.isArray(store?.devices)
    ? store.devices
        .map((item: any, index: number) => normalizePhoneDevice(item, `phone-${index + 1}`))
        .filter(Boolean) as PhoneDevice[]
    : [];
  if (storeDevices.length) {
    return {
      selectedDeviceId: textValue(store?.selectedDeviceId) || storeDevices[0].id,
      devices: storeDevices,
    };
  }

  const singleDevice = normalizePhoneDevice(single, 'primary-phone');
  return {
    selectedDeviceId: singleDevice?.id || '',
    devices: singleDevice ? [singleDevice] : [],
  };
}

function extractScreenshotUrl(value: any): string {
  if (!value) return '';
  if (typeof value === 'string') return normalizeImageString(value, 'image/png');
  if (typeof value !== 'object') return '';
  const mime = textValue(value.mime || value.mimeType || value.image?.mime || value.image?.mimeType) || 'image/png';
  return (
    normalizeImageString(value.dataUrl, mime) ||
    normalizeImageString(value.screenshot, mime) ||
    normalizeImageString(value.screenshotBase64, mime) ||
    normalizeImageString(value.imageBase64, mime) ||
    normalizeImageString(value.base64, mime) ||
    normalizeImageString(value.bitmap, mime) ||
    normalizeImageString(value.content, mime) ||
    normalizeImageString(value.image?.dataUrl, mime) ||
    normalizeImageString(value.image?.base64, mime) ||
    normalizeImageString(value.image?.imageBase64, mime) ||
    normalizeImageString(value.data?.dataUrl, mime) ||
    normalizeImageString(value.data?.screenshot, mime) ||
    normalizeImageString(value.data?.screenshotBase64, mime) ||
    normalizeImageString(value.data?.imageBase64, mime) ||
    normalizeImageString(value.data?.base64, mime) ||
    ''
  );
}

function normalizeImageString(value: unknown, mime: string): string {
  const text = textValue(value);
  if (!text) return '';
  if (/^data:image\//i.test(text) || /^https?:\/\//i.test(text) || /^blob:/i.test(text)) return text;
  if (/^[A-Za-z0-9+/=\r\n]+$/.test(text) && text.replace(/\s/g, '').length > 100) {
    return `data:${mime || 'image/png'};base64,${text.replace(/\s/g, '')}`;
  }
  return '';
}

function extractTaskId(value: any): string {
  if (!value || typeof value !== 'object') return '';
  return textValue(value.taskId || value.id || value.data?.taskId || value.data?.id);
}

function normalizePhoneDevice(value: any, fallbackId: string): PhoneDevice | null {
  if (!value || typeof value !== 'object') return null;
  const baseUrl = normalizePhoneBaseUrl(value.baseUrl || value.phoneUrl);
  const token = textValue(value.token || value.phoneToken);
  const id = textValue(value.id) || fallbackId;
  const name = textValue(value.name) || 'APKClaw 设备';
  if (!id && !baseUrl && !token && !name) return null;
  return {
    id,
    name,
    baseUrl,
    token,
    relayBaseUrl: normalizePhoneBaseUrl(value.relayBaseUrl),
    relayChannelId: textValue(value.relayChannelId),
    relayToken: textValue(value.relayToken),
    enabled: value.enabled !== false,
    tags: Array.isArray(value.tags) ? value.tags.map(textValue).filter(Boolean) : [],
    online: Boolean(value.online),
    active: value.active !== false,
    lastSeenAt: textValue(value.lastSeenAt),
    lastAuthorizedAt: textValue(value.lastAuthorizedAt),
  };
}

function upsertPhoneDeviceList(devices: PhoneDevice[], device: PhoneDevice): PhoneDevice[] {
  const index = devices.findIndex((item) => item.id === device.id);
  const next = [...devices];
  if (index >= 0) next[index] = device;
  else next.unshift(device);
  return next;
}

async function savePhoneInventoryConfig(settings: any, devices: PhoneDevice[], selectedDeviceId: string) {
  const selected = devices.find((device) => device.id === selectedDeviceId) || devices[0] || null;
  await Promise.all([
    writeConfigValue(settings, PHONE_AGENTS_PATH, {
      schema: 'openclaw.launcher.phone-agents.v1',
      updatedAt: new Date().toISOString(),
      selectedDeviceId: selected?.id || '',
      devices: devices.map(toStoredPhoneDevice),
    }),
    writeConfigValue(settings, PHONE_AGENT_PATH, selected ? toStoredPhoneDevice(selected) : {}),
  ]);
}

function toStoredPhoneDevice(device: PhoneDevice) {
  return {
    id: device.id,
    name: device.name,
    baseUrl: normalizePhoneBaseUrl(device.baseUrl),
    token: device.token,
    relayBaseUrl: normalizePhoneBaseUrl(device.relayBaseUrl),
    relayChannelId: device.relayChannelId || '',
    relayToken: device.relayToken || '',
    enabled: device.enabled !== false,
    tags: device.tags || [],
    lastSeenAt: device.lastSeenAt || '',
    lastAuthorizedAt: device.lastAuthorizedAt || '',
  };
}

function uniqueDeviceId(seed: string, usedIds: Set<string>): string {
  const base = slugValue(seed) || 'phone-device';
  let candidate = base;
  let counter = 2;
  while (usedIds.has(candidate)) {
    candidate = `${base}-${counter}`;
    counter += 1;
  }
  return candidate;
}

function slugFromUrl(baseUrl: string): string {
  try {
    const url = new URL(baseUrl);
    return `phone-${url.hostname}-${url.port || '9527'}`;
  } catch {
    return 'phone-device';
  }
}

function slugValue(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function normalizePhoneInputDraft(value: string): string {
  const text = value.trim();
  if (/^\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?$/.test(text)) {
    return normalizePhoneBaseUrl(text) || value;
  }
  return value;
}

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}
