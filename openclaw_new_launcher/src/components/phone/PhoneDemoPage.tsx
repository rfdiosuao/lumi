import React from 'react';
import {
  accountApi,
  jobApi,
  matrixApi,
  parseErrorText,
  phoneApi,
  wireApi,
  type BridgeJob,
  type MatrixDeviceSummary,
  type MatrixEvent,
  type MatrixStatusSnapshot,
  type PhoneConfigSnapshot,
  type PhoneDeviceSummary,
  type PhoneTaskMode,
  type PhoneTaskProfile,
} from '../../services/api';
import { BusyOverlay, Button, Input, TextArea, showConfirm, showToast } from '../common';

type CliResult = {
  success?: boolean;
  stdout?: string;
  stderr?: string;
  code?: number | string;
  message?: string;
  error?: string;
  wire?: {
    models?: {
      phone?: string;
      text?: string;
    };
  };
  syncResults?: Array<{ target?: string; ok?: boolean; error?: string }>;
};

type UiTone = 'ok' | 'warn' | 'neutral';

const PHONE_JOB_LABELS = new Set([
  '手机控制',
  '多设备',
  '手机视觉',
  '手机录屏',
  '手机设备',
  '手机连接',
  '手机截图',
  '读取屏幕',
  '手机最近任务',
  '手机模型同步',
]);
const DEFAULT_PHONE_PORT = '9527';
const DEFAULT_PHONE_MODEL = 'qwen3.7-plus';
const PHONE_AGENT_APK_URL = 'https://gitee.com/rfdiosuao/lumiapkclaw/releases/download/lumiclaw13241/OpenClaw-AgentPhone.apk';
const PHONE_AGENT_QR_SRC = '/phone-agent-apk-qr.svg';
const DEFAULT_READ_PROMPT = '只读取当前手机屏幕，不要点击、输入或滑动。请用中文返回当前页面名称和三个可见内容。';
const DEFAULT_ACTION_PROMPT = '请观察当前手机屏幕，并完成一个明确的小任务。执行后用中文返回做了什么、当前页面名称和是否需要我继续。';

const TASK_MODE_OPTIONS: Array<{ value: PhoneTaskMode; title: string; desc: string; badge: string }> = [
  { value: 'observe', title: '只读', desc: '只读屏幕，不点击、不输入、不滑动。', badge: 'observe' },
  { value: 'safe', title: '受控', desc: '允许执行任务，敏感动作会按安全策略收敛。', badge: 'safe' },
  { value: 'full', title: '完整控制', desc: '允许点击、输入、滑动等完整手机控制。', badge: 'full' },
];

const TASK_PROFILE_OPTIONS: Array<{ value: PhoneTaskProfile; title: string; desc: string }> = [
  { value: 'fast', title: '快速', desc: '演示优先，读屏和轻动作更快返回。' },
  { value: 'standard', title: '标准', desc: '保留原有稳定预算。' },
  { value: 'deep', title: '深度', desc: '复杂任务使用更长等待窗口。' },
];

const DEFAULT_PHONE_WAIT_BUDGET_MS = 45_000;
const PHONE_LONG_TASK_SETTLE_MS = 1_800;
const PHONE_JOB_POLL_DELAYS_MS = [500, 800, 1200];

type PhoneTaskBudget = {
  timeoutSec: number;
  maxWaitSec: number;
  maxRounds: number;
  pollMs: number;
};

type RunPhoneOptions = {
  waitBudgetMs?: number;
  releaseWhenSubmitted?: boolean;
};

const TASK_PROFILE_BUDGETS: Record<PhoneTaskProfile, Record<PhoneTaskMode, PhoneTaskBudget>> = {
  fast: {
    observe: { timeoutSec: 45, maxWaitSec: 60, maxRounds: 4, pollMs: 500 },
    safe: { timeoutSec: 120, maxWaitSec: 75, maxRounds: 12, pollMs: 500 },
    full: { timeoutSec: 300, maxWaitSec: 75, maxRounds: 30, pollMs: 500 },
  },
  standard: {
    observe: { timeoutSec: 90, maxWaitSec: 105, maxRounds: 8, pollMs: 800 },
    safe: { timeoutSec: 240, maxWaitSec: 260, maxRounds: 30, pollMs: 800 },
    full: { timeoutSec: 600, maxWaitSec: 620, maxRounds: 60, pollMs: 800 },
  },
  deep: {
    observe: { timeoutSec: 180, maxWaitSec: 210, maxRounds: 12, pollMs: 1200 },
    safe: { timeoutSec: 600, maxWaitSec: 630, maxRounds: 60, pollMs: 1200 },
    full: { timeoutSec: 900, maxWaitSec: 930, maxRounds: 90, pollMs: 1200 },
  },
};

const QUICK_TASKS = [
  '读取当前屏幕，告诉我页面名称和三个可见内容。',
  '返回上一页，然后告诉我现在停留在哪个页面。',
  '回到桌面，并告诉我桌面上能看到哪些主要应用。',
  '打开系统设置，停在设置首页后返回页面名称。',
];

function statusLabel(status: string): string {
  const key = String(status || '').toLowerCase();
  if (key === 'queued') return '排队中';
  if (key === 'running') return '执行中';
  if (['succeeded', 'success', 'completed', 'complete'].includes(key)) return '已完成';
  if (['failed', 'error'].includes(key)) return '失败';
  return status || '-';
}

function jobTone(status: string): string {
  const key = String(status || '').toLowerCase();
  if (['succeeded', 'success', 'completed', 'complete'].includes(key)) return 'border-status-success/30 bg-status-success/10 text-status-success';
  if (['failed', 'error'].includes(key)) return 'border-status-danger/30 bg-status-danger/10 text-status-danger';
  if (['queued', 'running'].includes(key)) return 'border-accent/30 bg-accent/10 text-accent';
  return 'border-border/70 bg-surface/35 text-text-muted';
}

function parseJsonMaybe(text?: string): any {
  const value = String(text || '').trim();
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function isDoneStatus(status: string): boolean {
  return ['succeeded', 'success', 'completed', 'complete'].includes(String(status || '').toLowerCase());
}

function isFailedStatus(status: string): boolean {
  return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status || '').toLowerCase());
}

function friendlyPhoneText(input?: string): string {
  const text = String(input || '').trim();
  if (!text) return '';
  if (/No APKClaw devices are configured/i.test(text)) {
    return '未配置手机设备。请先保存手机 IP 和连接令牌，然后重新检测。';
  }
  if (/Missing phone URL/i.test(text)) {
    return '缺少手机 IP。请先在手机页保存手机 IP 和连接令牌。';
  }
  if (/Missing phone token/i.test(text)) {
    return '缺少手机连接令牌。请先配置手机端连接令牌，或重新完成手机配对。';
  }
  if (/Unknown APKClaw device id/i.test(text)) {
    return '未找到指定手机设备。请刷新设备列表后重新选择。';
  }
  if (/fetch failed|ECONNREFUSED|ETIMEDOUT|timed out|network/i.test(text)) {
    return '手机连接失败。请确认手机端 App 已启动，并且电脑与手机在同一网络。';
  }
  return text;
}

async function waitForPhoneJob(
  jobId: string,
  timeoutMs = DEFAULT_PHONE_WAIT_BUDGET_MS,
  options: { onProgress?: (job: BridgeJob<CliResult>) => void } = {},
): Promise<BridgeJob<CliResult>> {
  const deadline = Date.now() + timeoutMs;
  let lastJob: BridgeJob<CliResult> | null = null;
  while (Date.now() < deadline) {
    const resp = await jobApi.get(jobId) as { job: BridgeJob<CliResult> };
    lastJob = resp.job;
    options.onProgress?.(lastJob);
    if (isDoneStatus(lastJob.status) || isFailedStatus(lastJob.status)) return lastJob;
    const delay = PHONE_JOB_POLL_DELAYS_MS[Math.min(PHONE_JOB_POLL_DELAYS_MS.length - 1, Math.max(0, Math.floor((Date.now() + timeoutMs - deadline) / 1200)))];
    await new Promise((resolve) => window.setTimeout(resolve, delay));
  }
  throw { error: lastJob?.progress?.message || lastJob?.message || '手机任务超时，请检查手机连接状态。' };
}

function phoneWaitBudgetMs(maxWaitSec?: number): number {
  const seconds = Number.isFinite(maxWaitSec) ? Number(maxWaitSec) : DEFAULT_PHONE_WAIT_BUDGET_MS / 1000;
  return Math.max(8_000, Math.min(15 * 60 * 1000, (seconds + 12) * 1000));
}

function firstResultText(job: BridgeJob<CliResult> | null): string {
  const result = job?.result;
  if (result?.wire?.models?.phone) {
    const failed = result.syncResults?.find((item) => item.ok === false);
    if (failed) return friendlyPhoneText(failed.error || result.error || '手机模型同步失败');
    return `手机模型已同步：${result.wire.models.phone}`;
  }
  if (result?.message) return friendlyPhoneText(result.message);
  const parsed = parseJsonMaybe(result?.stdout);
  if (parsed?.final?.result?.summary) return String(parsed.final.result.summary);
  if (parsed?.final?.result?.text) return String(parsed.final.result.text);
  if (parsed?.final?.summary) return String(parsed.final.summary);
  if (parsed?.filePath || parsed?.path) {
    return '截图已保存，可在诊断日志中查看。';
  }
  if (parsed?.rows?.length) {
    return parsed.rows
      .slice(0, 3)
      .map((row: any) => row.summary || row.error || row.status || row.taskId || '')
      .filter(Boolean)
      .join('\n');
  }
  if (parsed?.devices?.length) {
    return parsed.devices
      .map((device: any) => `${device.selected ? '* ' : ''}${device.name || device.id || 'Android'}：${device.configured ? '已配置' : '未配置'}`)
      .join('\n');
  }
  if (parsed?.results?.length) {
    return parsed.results
      .map((item: any) => `${item.device?.name || item.device?.id || '设备'}：${item.ok === false ? '连接失败' : '在线'}`)
      .join('\n');
  }
  return friendlyPhoneText(result?.stdout || result?.stderr || job?.error || job?.message || '');
}

function screenshotPath(job: BridgeJob<CliResult> | null): string {
  const parsed = parseJsonMaybe(job?.result?.stdout);
  return String(parsed?.filePath || parsed?.path || '');
}

function phoneJobs(jobs: BridgeJob[]): BridgeJob[] {
  return jobs.filter((job) => PHONE_JOB_LABELS.has(String(job.label || '')) || String(job.kind || '').startsWith('phone.'));
}

function mergePhoneJob(jobs: BridgeJob[], job?: BridgeJob | null): BridgeJob[] {
  if (!job?.id) return jobs;
  return [job, ...jobs.filter((item) => item.id !== job.id)].slice(0, 12);
}

function pickActivePhoneJob(jobs: BridgeJob[]): BridgeJob<CliResult> | null {
  return (jobs.find((job) => {
    const status = String(job.status || '');
    return !isDoneStatus(status) && !isFailedStatus(status);
  }) as BridgeJob<CliResult> | undefined) || null;
}

function pickLatestPhoneJob(jobs: BridgeJob[]): BridgeJob<CliResult> | null {
  return (jobs[0] as BridgeJob<CliResult> | undefined) || null;
}

function createOptimisticPhoneJob(key: string): BridgeJob<CliResult> {
  const message = key === 'task'
    ? '手机任务已提交，正在进入执行中'
    : key === 'read'
      ? '读屏任务已提交，正在读取节点树'
      : key === 'frame'
        ? '截图任务已提交，正在获取低清帧'
        : '手机任务已提交，正在处理';
  return {
    id: `pending_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    kind: `phone.${key}`,
    label: '手机任务',
    status: 'running',
    message,
    progress: {
      message,
      tone: 'neutral',
      history: [{ message, tone: 'neutral', updatedAt: Date.now() / 1000 }],
    },
  };
}

function selectedPhoneDevice(snapshot?: PhoneConfigSnapshot, preferredId?: string): PhoneDeviceSummary | null {
  const devices = snapshot?.devices || [];
  const selectedId = String(preferredId || snapshot?.selectedDeviceId || '').trim();
  return devices.find((device) => device.id && device.id === selectedId) || devices[0] || null;
}

function nextPhoneDeviceId(devices: PhoneDeviceSummary[]): string {
  const usedIds = new Set(devices.map((device) => String(device.id || '').trim()).filter(Boolean));
  let index = Math.max(1, devices.length + 1);
  while (usedIds.has(`phone-${index}`)) index += 1;
  return `phone-${index}`;
}

function cleanPhoneAddressInput(value?: string): string {
  return String(value || '')
    .trim()
    .replace(/[：﹕꞉]/g, ':')
    .replace(/[／⁄]/g, '/')
    .replace(/[。．｡]/g, '.')
    .replace(/\s+/g, '')
    .replace(/^http:\/(?!\/)/i, 'http://')
    .replace(/^https:\/(?!\/)/i, 'https://');
}

function displayPhoneAddress(baseUrl?: string): string {
  const text = cleanPhoneAddressInput(baseUrl).replace(/\/+$/, '');
  if (!text) return '';
  try {
    const parsed = new URL(text.includes('://') ? text : `http://${text}`);
    const host = parsed.hostname || text;
    return parsed.port && parsed.port !== DEFAULT_PHONE_PORT ? `${host}:${parsed.port}` : host;
  } catch {
    return text.replace(/^https?:\/\//i, '');
  }
}

function detectDirectPhoneAction(text: string): 'back' | 'home' | '' {
  const normalized = String(text || '').toLowerCase().replace(/\s+/g, '');
  if (/^(返回|返回上一页|上一页|后退|back|pressback)$/.test(normalized)) return 'back';
  if (/^(回到桌面|返回桌面|桌面|主页|回主页|home|presshome)$/.test(normalized)) return 'home';
  return '';
}

function toneTextClass(tone: UiTone): string {
  return tone === 'ok' ? 'text-status-success' : tone === 'warn' ? 'text-status-warning' : 'text-text';
}

const Metric: React.FC<{ label: string; value: string; tone?: UiTone }> = ({ label, value, tone = 'neutral' }) => (
  <div className="min-h-[82px] border-t border-border/70 py-4">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className={`mt-2 truncate text-xl font-black ${toneTextClass(tone)}`} title={value}>
      {value}
    </div>
  </div>
);

const EvidenceCell: React.FC<{ label: string; value: string; detail?: string; tone?: UiTone }> = ({
  label,
  value,
  detail,
  tone = 'neutral',
}) => (
  <div className="min-w-0 border-t border-border/70 py-3">
    <div className="text-[11px] font-bold text-text-subtle">{label}</div>
    <div className={`mt-1 truncate text-sm font-black ${toneTextClass(tone)}`} title={value}>
      {value}
    </div>
    {detail ? <div className="mt-1 truncate text-xs text-text-muted" title={detail}>{detail}</div> : null}
  </div>
);

const JobRow: React.FC<{ job: BridgeJob<CliResult>; onSelect: () => void }> = ({ job, onSelect }) => (
  <button
    type="button"
    onClick={onSelect}
    className="w-full border-t border-border/60 py-3 text-left transition hover:border-border-strong"
  >
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-black text-text">{job.label || job.kind || job.id}</div>
        <div className="mt-1 truncate text-xs text-text-muted">{job.progress?.message || job.message || job.id}</div>
      </div>
      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${jobTone(job.status)}`}>
        {statusLabel(job.status)}
      </span>
    </div>
  </button>
);

const MatrixDeviceCard: React.FC<{ device: MatrixDeviceSummary }> = ({ device }) => {
  const online = Boolean(device.online);
  const busy = Boolean(device.busy || device.currentTaskId);
  const failed = Number(device.failureCount || 0) > 0;
  return (
    <div className="border-t border-border/70 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-black text-text">{device.name || device.deviceId}</div>
          <div className="mt-1 truncate text-xs text-text-muted">{device.group || 'default'} / {device.model || DEFAULT_PHONE_MODEL}</div>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${
          failed
            ? 'border-status-danger/30 bg-status-danger/10 text-status-danger'
            : busy
              ? 'border-accent/30 bg-accent/10 text-accent'
              : online
                ? 'border-status-success/30 bg-status-success/10 text-status-success'
                : 'border-border/70 bg-surface-alt/40 text-text-muted'
        }`}>
          {failed ? '失败' : busy ? '忙碌' : online ? '在线' : '离线'}
        </span>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-text-muted md:grid-cols-2">
        <div className="truncate">当前任务：{device.currentTaskId || '-'}</div>
        <div className="truncate">最近结果：{device.lastResult || '-'}</div>
        <div className="truncate">连接：{online ? '在线' : '离线'}</div>
        <div className="truncate">状态：{busy ? '忙碌' : '空闲'}</div>
      </div>
      <div className="mt-2 line-clamp-2 text-xs leading-5 text-text-muted">
        {device.currentScreenSummary || '暂无屏幕摘要'}
      </div>
    </div>
  );
};

const MatrixEventRow: React.FC<{ event: MatrixEvent }> = ({ event }) => (
  <div className="border-t border-border/60 py-3">
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-black text-text">{event.type}</div>
        <div className="mt-1 truncate text-xs text-text-muted">{event.message || event.deviceTaskId || event.campaignId || '-'}</div>
      </div>
      <span className="shrink-0 text-[11px] font-bold text-text-subtle">{event.deviceId || '系统'}</span>
    </div>
  </div>
);

const FlowStep: React.FC<{ index: number; title: string; desc: string; active?: boolean; done?: boolean }> = ({
  index,
  title,
  desc,
  active,
  done,
}) => (
  <div className={`min-h-[108px] border-t pt-4 ${
    done
      ? 'border-status-success/35'
      : active
        ? 'border-[#0B4A3E]/50'
        : 'border-border/70'
  }`}>
    <div className="flex items-center justify-between gap-3">
      <span className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-black ${
        done
          ? 'border-status-success/30 bg-status-success/10 text-status-success'
          : active
            ? 'border-[#0B4A3E]/40 bg-[#0B4A3E]/10 text-[#0B4A3E]'
            : 'border-border bg-surface-alt text-text-subtle'
      }`}>
        {done ? '✓' : index}
      </span>
      <span className="text-[10px] font-bold tracking-[0.2em] text-text-subtle">
        {done ? '完成' : active ? '当前' : '待处理'}
      </span>
    </div>
    <div className="mt-3 text-sm font-black text-text">{title}</div>
    <div className="mt-1 text-xs leading-5 text-text-muted">{desc}</div>
  </div>
);

const LockedCard: React.FC<{ title: string; desc: string }> = ({ title, desc }) => (
  <div className="border-t border-border/60 py-3">
    <div className="flex items-center justify-between gap-3">
      <div>
        <div className="text-sm font-black text-text">{title}</div>
        <div className="mt-1 text-xs leading-5 text-text-muted">{desc}</div>
      </div>
      <span className="shrink-0 rounded-full border border-status-warning/30 bg-status-warning/10 px-3 py-1 text-xs font-bold text-status-warning">
        暂未开放
      </span>
    </div>
  </div>
);

export const PhoneDemoPage: React.FC = () => {
  const [jobs, setJobs] = React.useState<BridgeJob[]>([]);
  const [busy, setBusy] = React.useState('');
  const [lastJob, setLastJob] = React.useState<BridgeJob<CliResult> | null>(null);
  const [phoneExecutionStage, setPhoneExecutionStage] = React.useState('');
  const [prompt, setPrompt] = React.useState(DEFAULT_READ_PROMPT);
  const [taskMode, setTaskMode] = React.useState<PhoneTaskMode>('safe');
  const [taskProfile, setTaskProfile] = React.useState<PhoneTaskProfile>('fast');
  const [deviceSummary, setDeviceSummary] = React.useState('未检测');
  const [connectionSummary, setConnectionSummary] = React.useState('未检测');
  const [lastScreenshotPath, setLastScreenshotPath] = React.useState('');
  const [selectedDeviceId, setSelectedDeviceId] = React.useState('phone-1');
  const [deviceName, setDeviceName] = React.useState('Android Phone');
  const [phoneAddress, setPhoneAddress] = React.useState('');
  const [phoneToken, setPhoneToken] = React.useState('');
  const [tokenAvailable, setTokenAvailable] = React.useState(false);
  const [accountLoggedIn, setAccountLoggedIn] = React.useState(false);
  const [hasWireConfig, setHasWireConfig] = React.useState(false);
  const [phoneAppModalOpen, setPhoneAppModalOpen] = React.useState(false);
  const [phoneConfigSnapshot, setPhoneConfigSnapshot] = React.useState<PhoneConfigSnapshot | null>(null);
  const [isAddingDevice, setIsAddingDevice] = React.useState(false);
  const [matrixStatus, setMatrixStatus] = React.useState<MatrixStatusSnapshot | null>(null);
  const [matrixEvents, setMatrixEvents] = React.useState<MatrixEvent[]>([]);
  const configuredPhones = React.useMemo(() => phoneConfigSnapshot?.devices || [], [phoneConfigSnapshot]);
  const canUsePhone = Boolean(phoneAddress.trim() && (tokenAvailable || phoneToken.trim()));

  const refreshJobs = React.useCallback(async () => {
    try {
      const resp = await jobApi.list(40);
      const nextJobs = phoneJobs(resp.jobs || []);
      const activePhoneJob = pickActivePhoneJob(nextJobs);
      const latestPhoneJob = activePhoneJob || pickLatestPhoneJob(nextJobs);
      setJobs(nextJobs);
      setLastJob((current) => {
        if (!current) return latestPhoneJob || null;
        const updatedJob = nextJobs.find((updatedJob) => current.id === updatedJob.id) as BridgeJob<CliResult> | undefined;
        if (updatedJob) return updatedJob;
        if (current.id.startsWith('pending_')) return latestPhoneJob || current;
        return current;
      });
      if (screenshotPath(latestPhoneJob)) {
        setLastScreenshotPath('已保存');
      }
      if (activePhoneJob) {
        setPhoneExecutionStage(activePhoneJob.progress?.message || activePhoneJob.message || '');
      }
    } catch {
      // Recent jobs are helpful but not required for the page to load.
    }
  }, []);

  const applyPhoneConfig = React.useCallback((snapshot: PhoneConfigSnapshot, preferredId?: string) => {
    setPhoneConfigSnapshot(snapshot);
    const selected = selectedPhoneDevice(snapshot, preferredId);
    setSelectedDeviceId(selected?.id || preferredId || snapshot.selectedDeviceId || 'phone-1');
    setDeviceName(selected?.name || selected?.id || 'Android Phone');
    setPhoneAddress(displayPhoneAddress(selected?.baseUrl || ''));
    setTokenAvailable(Boolean(selected?.tokenAvailable));
    setPhoneToken('');
    if (snapshot.devices?.length) {
      setDeviceSummary(`${snapshot.devices.length} 台 / ${selected?.name || selected?.id || '已配置'}`);
    } else {
      setDeviceSummary('未配置设备');
    }
  }, []);

  const startAddPhone = React.useCallback(() => {
    const nextId = nextPhoneDeviceId(configuredPhones);
    setIsAddingDevice(true);
    setSelectedDeviceId(nextId);
    setDeviceName(`Android Phone ${configuredPhones.length + 1}`);
    setPhoneAddress('');
    setPhoneToken('');
    setTokenAvailable(false);
    setConnectionSummary('未检测');
  }, [configuredPhones]);

  const selectConfiguredPhone = React.useCallback((device: PhoneDeviceSummary) => {
    const nextId = device.id || device.name || 'phone-1';
    setIsAddingDevice(false);
    setSelectedDeviceId(nextId);
    setDeviceName(device.name || nextId);
    setPhoneAddress(displayPhoneAddress(device.baseUrl || ''));
    setPhoneToken('');
    setTokenAvailable(Boolean(device.tokenAvailable));
    setConnectionSummary('未检测');
  }, []);

  const loadPhoneConfig = React.useCallback(async () => {
    try {
      const snapshot = await phoneApi.config();
      applyPhoneConfig(snapshot);
    } catch (error: any) {
      showToast(parseErrorText(error) || '读取手机连接配置失败', 'error');
    }
  }, [applyPhoneConfig]);

  const loadAccountStatus = React.useCallback(async () => {
    try {
      const resp = await accountApi.current();
      setAccountLoggedIn(Boolean(resp.account?.loggedIn));
      try {
        const current = await wireApi.current();
        setHasWireConfig(Boolean(current.wire?.ok && current.wire?.models?.phone));
      } catch {
        setHasWireConfig(false);
      }
    } catch {
      setAccountLoggedIn(false);
      setHasWireConfig(false);
    }
  }, []);

  const refreshMatrix = React.useCallback(async () => {
    try {
      const status = await matrixApi.status();
      const watched = await matrixApi.watch();
      setMatrixStatus(status);
      setMatrixEvents(watched.events || []);
    } catch {
      setMatrixStatus((current) => current || { schema: 'loom.matrix.v1', devices: [], summary: { total: 0, online: 0, busy: 0, failed: 0 } });
      setMatrixEvents((current) => current || []);
    }
  }, []);

  const updateMatrixDevicePresence = React.useCallback(async (online: boolean, summary: string, deviceIdOverride?: string) => {
    const deviceId = deviceIdOverride || selectedDeviceId || deviceName.trim() || 'phone-1';
    try {
      const next = await matrixApi.registerDevice({
        deviceId,
        name: deviceName.trim() || deviceId,
        group: 'default',
        online: Boolean(online),
        heartbeatAt: new Date().toISOString(),
        currentScreenSummary: summary,
        failureCount: online ? 0 : 1,
        model: DEFAULT_PHONE_MODEL,
      });
      setMatrixStatus(next.status);
    } catch {
      // Matrix presence is only a dashboard hint; phone control should keep working if it cannot refresh.
    }
  }, [deviceName, selectedDeviceId]);

  const copyPhoneAgentApkUrl = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(PHONE_AGENT_APK_URL);
      showToast('下载链接已复制', 'success');
    } catch {
      showToast('复制失败，请手动复制下载链接。', 'error');
    }
  }, []);

  React.useEffect(() => {
    void loadPhoneConfig();
    void loadAccountStatus();
    void refreshJobs();
    void refreshMatrix();
    const timer = window.setInterval(refreshJobs, 2200);
    const matrixTimer = window.setInterval(refreshMatrix, 3000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(matrixTimer);
    };
  }, [loadAccountStatus, loadPhoneConfig, refreshJobs, refreshMatrix]);

  const runPhone = React.useCallback(async (
    key: string,
    submit: () => Promise<unknown>,
    onDone?: (job: BridgeJob<CliResult>) => void,
    options: RunPhoneOptions = {},
  ) => {
    const waitBudgetMs = options.waitBudgetMs ?? DEFAULT_PHONE_WAIT_BUDGET_MS;
    setBusy(key);
    const optimisticJob = createOptimisticPhoneJob(key);
    setPhoneExecutionStage(optimisticJob.progress?.message || optimisticJob.message || '');
    setLastJob(optimisticJob);
    setJobs((current) => mergePhoneJob(current, optimisticJob));
    try {
      const submitted = await submit() as { jobId?: string; job?: BridgeJob<CliResult> };
      const jobId = submitted.jobId || submitted.job?.id;
      if (!jobId) throw new Error('手机任务提交失败');
      const submittedJob = submitted.job || null;
      if (submittedJob) {
        setLastJob(submittedJob);
        setJobs((current) => mergePhoneJob(current, submittedJob));
      }
      if (options.releaseWhenSubmitted) {
        showToast('手机任务已在后台执行，可以切到其他页面。', 'success');
        await refreshJobs();
        return submittedJob;
      }
      showToast('手机任务已提交', 'success');
      const done = await waitForPhoneJob(jobId, waitBudgetMs, {
        onProgress: (job) => {
          setPhoneExecutionStage(job.progress?.message || job.message || '');
          setLastJob(job);
          setJobs((current) => mergePhoneJob(current, job));
        },
      });
      setLastJob(done);
      setPhoneExecutionStage(done.progress?.message || done.message || '');
      onDone?.(done);
      await refreshJobs();
      if (isFailedStatus(done.status)) {
        showToast(firstResultText(done) || '手机任务执行失败，请检查手机连接和诊断日志', 'error');
        return done;
      }
      return done;
    } catch (error: any) {
      showToast(parseErrorText(error) || '手机任务执行失败，请检查手机连接和诊断日志', 'error');
      await refreshJobs();
      return null;
    } finally {
      setPhoneExecutionStage('');
      setBusy('');
    }
  }, [refreshJobs]);

  const saveDeviceAndDetect = async () => {
    const cleanAddress = phoneAddress.trim();
    const cleanName = deviceName.trim() || 'Android Phone';
    const cleanToken = phoneToken.trim();
    if (!cleanAddress) {
      showToast('请输入手机 IP，例如 192.168.1.78', 'error');
      return;
    }
    if (!cleanToken && !tokenAvailable) {
      showToast('请输入手机端连接令牌', 'error');
      return;
    }
    setBusy('config');
    try {
      const deviceId = selectedDeviceId.trim() || nextPhoneDeviceId(configuredPhones);
      const snapshot = await phoneApi.saveDevice({
        id: deviceId,
        name: cleanName,
        baseUrl: cleanAddress,
        token: cleanToken,
        selectedDeviceId: deviceId,
      });
      applyPhoneConfig(snapshot, deviceId);
      setIsAddingDevice(false);
      void matrixApi.registerDevice({
        deviceId,
        name: cleanName,
        group: 'default',
        online: false,
        model: DEFAULT_PHONE_MODEL,
      }).then((next) => setMatrixStatus(next.status)).catch(() => undefined);
      setPhoneToken('');
      showToast('手机连接配置已保存', 'success');
      await checkConnection(deviceId);
    } catch (error: any) {
      showToast(friendlyPhoneText(parseErrorText(error)) || '保存手机连接配置失败', 'error');
    } finally {
      setBusy('');
    }
  };

  const refreshDevices = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机 IP 和连接令牌', 'info');
      return;
    }
    await runPhone('devices', () => phoneApi.devices(), (job) => {
      const parsed = parseJsonMaybe(job.result?.stdout);
      const count = Array.isArray(parsed?.devices) ? parsed.devices.length : 0;
      const selected = parsed?.devices?.find?.((device: any) => device.selected) || parsed?.devices?.[0];
      setDeviceSummary(count ? `${count} 台 / ${selected?.name || selected?.id || '已配置'}` : '未配置设备');
    });
  };

  const checkConnection = async (deviceIdOverride?: string) => {
    if (!canUsePhone) {
      showToast('请先保存手机 IP 和连接令牌', 'info');
      return;
    }
    await runPhone('status', () => phoneApi.status(), (job) => {
      const parsed = parseJsonMaybe(job.result?.stdout);
      const text = firstResultText(job);
      const ok =
        parsed?.ok === true ||
        parsed?.success === true ||
        parsed?.results?.some?.((item: any) => item?.ok !== false);
      void updateMatrixDevicePresence(ok, ok ? '手机连接在线' : text || '手机连接失败', deviceIdOverride);
      setConnectionSummary(ok ? '已连接' : text || '检测完成');
    });
  };

  const captureFrame = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机 IP 和连接令牌', 'info');
      return;
    }
    await runPhone('frame', () => phoneApi.screenshot(), (job) => {
      const path = screenshotPath(job);
      setLastScreenshotPath(path ? '已保存' : '截图已完成');
    });
  };

  const readScreen = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机 IP 和连接令牌', 'info');
      return;
    }
    const text = prompt.trim() || DEFAULT_READ_PROMPT;
    await runPhone('read', () => phoneApi.read({ prompt: text, profile: 'fast' }), undefined, {
      waitBudgetMs: PHONE_LONG_TASK_SETTLE_MS,
      releaseWhenSubmitted: true,
    });
  };

  const executePhoneTask = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机 IP 和连接令牌', 'info');
      return;
    }
    const text = prompt.trim() || (taskMode === 'observe' ? DEFAULT_READ_PROMPT : DEFAULT_ACTION_PROMPT);
    if (taskMode === 'full') {
      const confirmed = await showConfirm({
        title: '确认完整控制',
        message: '完整控制会真实点击、输入和滑动当前手机。请确认手机已连接、任务描述清楚，并且当前页面可以操作。',
        confirmText: '开始执行',
        cancelText: '先不执行',
      });
      if (!confirmed) return;
    }
    const budget = TASK_PROFILE_BUDGETS[taskProfile][taskMode];
    const directAction = detectDirectPhoneAction(text);
    await runPhone('task', () => phoneApi.task({
      prompt: text,
      mode: taskMode,
      profile: taskProfile,
      timeoutSec: budget.timeoutSec,
      maxRounds: budget.maxRounds,
      maxWaitSec: budget.maxWaitSec,
      pollMs: budget.pollMs,
      ...(directAction ? { action: directAction } : {}),
    }), undefined, {
      waitBudgetMs: phoneWaitBudgetMs(budget.maxWaitSec),
      releaseWhenSubmitted: true,
    });
  };

  const applyQuickTask = (text: string, nextMode?: PhoneTaskMode) => {
    setPrompt(text);
    if (nextMode) setTaskMode(nextMode);
  };

  const syncPhoneModel = async () => {
    if (!accountLoggedIn && !hasWireConfig) {
      showToast('请先在模型账号页完成登录或第三方模型配置，再同步手机模型。', 'info');
      return;
    }
    await runPhone('syncModel', () => phoneApi.syncModel(), (job) => {
      const model = job.result?.wire?.models?.phone;
      if (model) showToast(`手机模型已同步：${model}`, 'success');
    });
  };

  const loadHistory = async () => {
    await runPhone('history', () => phoneApi.history());
  };

  const lastText = firstResultText(lastJob);
  const phoneTaskRunning = Boolean(busy) || Boolean(lastJob && !isDoneStatus(lastJob.status) && !isFailedStatus(lastJob.status));
  const currentStageText = phoneExecutionStage || lastJob?.progress?.message || lastJob?.message || '';
  const activeJobCount = jobs.filter((job) => !isDoneStatus(job.status) && !isFailedStatus(job.status)).length;
  const latestResult = (lastJob?.result || null) as (CliResult & {
    metrics?: Record<string, unknown>;
    mode?: string;
    executionLayer?: string;
  }) | null;
  const latestMetrics = latestResult?.metrics;
  const latestMode = String(
    latestResult?.mode
      || latestMetrics?.mode
      || latestResult?.executionLayer
      || lastJob?.progress?.executionLayer
      || (canUsePhone ? 'direct' : 'not configured'),
  );
  const latestTotalMs = latestMetrics?.totalMs;
  const latestTotalText = typeof latestTotalMs === 'number'
    ? `${Math.round(latestTotalMs)} ms`
    : typeof latestTotalMs === 'string' && latestTotalMs
      ? latestTotalMs
      : lastJob
        ? statusLabel(lastJob.status)
        : '等待首个结果';
  const metricDetail = [
    typeof latestMetrics?.screenTreeMs === 'number' ? `tree ${Math.round(latestMetrics.screenTreeMs)} ms` : '',
    typeof latestMetrics?.toolCallMs === 'number' ? `tool ${Math.round(latestMetrics.toolCallMs)} ms` : '',
    typeof latestMetrics?.rounds === 'number' ? `${Math.round(latestMetrics.rounds)} rounds` : '',
  ].filter(Boolean).join(' / ');
  const routeTone: UiTone = canUsePhone ? 'ok' : 'warn';
  const queueTone: UiTone = phoneTaskRunning ? 'warn' : 'neutral';
  const deviceTone: UiTone = canUsePhone ? 'ok' : 'warn';
  const busyOverlayTitle = busy === 'config'
    ? '正在读取手机配置'
    : busy === 'status'
      ? '正在检测手机连接'
      : busy === 'devices'
        ? '正在读取设备'
        : busy === 'frame'
          ? '正在截图'
          : busy === 'read'
            ? '正在读取屏幕'
            : busy === 'task'
              ? taskMode === 'full' ? '正在完整控制手机任务' : taskMode === 'safe' ? '正在执行受控任务' : '正在只读手机屏幕'
              : busy === 'syncModel'
                ? '正在同步手机模型'
                : busy === 'history'
                  ? '正在读取最近任务'
                  : '正在处理手机任务';

  return (
    <div className="h-full overflow-y-auto bg-app-bg">
      <BusyOverlay
        active={Boolean(busy)}
        title={busyOverlayTitle}
        detail={phoneExecutionStage || 'LOOM 正在等待手机返回结果。'}
      />
      {phoneAppModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#071916]/70 p-6 backdrop-blur-sm">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="phone-app-download-title"
            className="max-h-[92vh] w-full max-w-[760px] overflow-y-auto rounded-[24px] border border-[#0b4a3e]/18 bg-[#fffaf1] shadow-[0_28px_80px_rgba(2,28,24,0.28)]"
          >
            <div className="flex items-start justify-between gap-5 border-b border-[#0b4a3e]/12 px-7 py-6">
              <div>
                <h2 id="phone-app-download-title" className="text-2xl font-black text-[#071916]">下载手机端 App</h2>
                <p className="mt-2 text-sm font-bold text-[#58645f]">手机扫码安装手机端 App 后，再回到麓鸣保存 IP 和令牌。</p>
              </div>
              <button
                type="button"
                onClick={() => setPhoneAppModalOpen(false)}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] border border-[#0b4a3e]/16 bg-white/55 text-2xl leading-none text-[#31413b] transition hover:border-[#0b4a3e]/35 hover:text-[#071916]"
                aria-label="关闭下载手机端 App"
              >
                ×
              </button>
            </div>
            <div className="grid gap-6 px-7 py-7 md:grid-cols-[260px_minmax(0,1fr)]">
              <div className="flex flex-col items-center justify-center rounded-[18px] border border-[#0b4a3e]/12 bg-white p-5">
                <img
                  src={PHONE_AGENT_QR_SRC}
                  alt="手机端 App 下载二维码"
                  className="h-[220px] w-[220px] rounded-[12px] object-contain"
                />
                <div className="mt-4 text-center text-xs font-bold text-[#58645f]">手机相机或浏览器扫码下载</div>
              </div>
              <div className="min-w-0">
                <div className="rounded-[18px] border border-[#0b4a3e]/12 bg-white/70 p-4">
                  <div className="text-sm font-black text-[#071916]">下载链接</div>
                  <div className="mt-3 rounded-[12px] border border-[#0b4a3e]/10 bg-[#f5efe3] p-3 text-sm font-bold leading-6 text-[#26352f]">
                    手机端 App 下载链接已准备
                  </div>
                  <Button className="mt-4" variant="primary" onClick={copyPhoneAgentApkUrl}>复制</Button>
                </div>
                <div className="mt-5 rounded-[18px] border border-[#0b4a3e]/12 bg-white/70 p-4">
                  <div className="text-sm font-black text-[#071916]">安装三步</div>
                  <ol className="mt-3 space-y-2 text-sm leading-6 text-[#43524c]">
                    <li>1. 手机扫码或复制链接，在手机浏览器下载手机端 App。</li>
                    <li>2. 安装后打开手机端 App，按提示开启无障碍和悬浮窗权限。</li>
                    <li>3. 回到麓鸣填写手机 IP 与连接令牌，再点保存并检测。</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      <div className="mx-auto flex w-full max-w-[1220px] flex-col gap-7 px-8 py-7">
        <header className="flex flex-wrap items-end justify-between gap-6 rounded-[8px] border border-border/70 bg-surface/90 px-5 py-4 shadow-[0_14px_36px_rgba(17,24,21,0.06)]">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">手机控制</div>
            <h1 className="mt-2 text-[30px] font-black leading-tight text-text">手机控制</h1>
            <div className="mt-2 max-w-[680px] truncate text-sm font-bold leading-6 text-text-muted">
              {latestMode.toUpperCase()} · {activeJobCount ? `${activeJobCount} 个执行中` : '空闲'} · {latestTotalText}
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="quiet" onClick={startAddPhone} disabled={Boolean(busy)}>添加手机</Button>
            <Button variant="quiet" onClick={() => setPhoneAppModalOpen(true)}>下载手机端 App</Button>
            <Button variant="quiet" onClick={refreshJobs}>刷新任务</Button>
            <Button variant="primary" onClick={() => checkConnection()} disabled={Boolean(busy) || !canUsePhone}>
              {busy === 'status' ? '检测中...' : '检测连接'}
            </Button>
          </div>
        </header>

        <section className="grid gap-x-8 gap-y-2 md:grid-cols-3">
          <Metric label="设备" value={deviceSummary} tone={deviceSummary.includes('未') ? 'warn' : 'ok'} />
          <Metric label="连接" value={connectionSummary} tone={connectionSummary.includes('已连接') ? 'ok' : 'warn'} />
          <Metric label="最近截图" value={lastScreenshotPath ? '已保存' : '暂无'} tone={lastScreenshotPath ? 'ok' : 'neutral'} />
        </section>

        <section className="grid gap-x-6 gap-y-2 md:grid-cols-4">
          <EvidenceCell
            label="执行通道"
            value={latestMode.toUpperCase()}
            detail={`${taskProfile.toUpperCase()} / ${taskMode.toUpperCase()}`}
            tone={routeTone}
          />
          <EvidenceCell
            label="任务队列"
            value={activeJobCount ? `${activeJobCount} 个执行中` : '空闲'}
            detail={lastJob ? statusLabel(lastJob.status) : '暂无任务'}
            tone={queueTone}
          />
          <EvidenceCell
            label="当前设备"
            value={selectedDeviceId || 'phone-1'}
            detail={canUsePhone ? displayPhoneAddress(phoneAddress) : '等待保存手机地址和令牌'}
            tone={deviceTone}
          />
          <EvidenceCell
            label="最近耗时"
            value={latestTotalText}
            detail={metricDetail || '等待性能埋点'}
            tone={latestTotalMs ? 'ok' : 'neutral'}
          />
        </section>

        <section className="grid gap-3 border-t border-border/70 pt-6 md:grid-cols-4">
          <FlowStep index={1} title="下载 App" desc="手机扫码安装" done={Boolean(phoneAddress || tokenAvailable)} />
          <FlowStep index={2} title="连接手机" desc="输入 IP 和令牌" active={!canUsePhone} done={canUsePhone} />
          <FlowStep index={3} title="输入任务" desc="截图、读屏或执行" active={canUsePhone && !lastJob} done={Boolean(lastJob)} />
          <FlowStep index={4} title="查看结果" desc="任务状态会保留" active={Boolean(lastJob)} done={Boolean(lastText)} />
        </section>

        {phoneTaskRunning ? (
          <section className="border-t border-[#0B4A3E]/25 bg-[#0B4A3E]/5 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-bold tracking-[0.22em] text-[#0B4A3E]">执行中</div>
                <div className="mt-1 truncate text-sm font-black text-text">{currentStageText || '手机任务正在执行'}</div>
              </div>
              <span className="rounded-full border border-[#0B4A3E]/30 bg-white/55 px-3 py-1 text-xs font-bold text-[#0B4A3E]">
                {lastJob?.progress?.executionLayer ? String(lastJob.progress.executionLayer).toUpperCase() : taskProfile.toUpperCase()}
              </span>
            </div>
          </section>
        ) : null}

        <section className="border-t border-border/70 pt-7">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">演示流程</div>
              <h2 className="mt-1 text-2xl font-black text-text">连接手机、输入任务、查看结果</h2>
            </div>
            <span className="rounded-full border border-border/70 bg-surface-alt/40 px-3 py-1 text-xs font-bold text-text-muted">
              本机连接
            </span>
          </div>

          <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-8">
              <section className="border-t border-border/70 pt-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-black text-text">手机连接配置</h2>
                    <p className="mt-1 text-xs leading-5 text-text-muted">
                      只保存本机连接信息；连接令牌不会回显到界面。
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-border/70 bg-surface-alt/40 px-3 py-1 text-xs font-bold text-text-muted">
                      {isAddingDevice ? '新增手机' : `当前：${selectedDeviceId || 'phone-1'}`}
                    </span>
                    <Button variant="quiet" onClick={startAddPhone} disabled={Boolean(busy)}>
                      添加手机
                    </Button>
                    <Button variant="quiet" onClick={loadPhoneConfig} disabled={Boolean(busy)}>
                      读取配置
                    </Button>
                  </div>
                </div>
                {configuredPhones.length ? (
                  <div className="mb-4 flex flex-wrap gap-2">
                    {configuredPhones.map((device) => {
                      const active = !isAddingDevice && device.id === selectedDeviceId;
                      return (
                        <button
                          key={device.id}
                          type="button"
                          onClick={() => selectConfiguredPhone(device)}
                          disabled={Boolean(busy)}
                          className={`min-w-[150px] rounded-[8px] border px-3 py-2 text-left transition ${
                            active
                              ? 'border-[#0B4A3E] bg-[#0B4A3E]/10 text-[#0B4A3E]'
                              : 'border-border/70 bg-surface-alt/40 text-text hover:border-[#0B4A3E]/40'
                          } ${busy ? 'opacity-60' : ''}`}
                        >
                          <span className="block truncate text-sm font-black">{device.name || device.id}</span>
                          <span className="mt-1 block truncate text-[11px] font-bold text-text-muted">
                            {displayPhoneAddress(device.baseUrl) || '未填写地址'}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)_220px]">
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">设备名称</span>
                    <Input
                      value={deviceName}
                      onChange={(event) => setDeviceName(event.target.value)}
                      placeholder="Android Phone"
                      disabled={Boolean(busy)}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">手机 IP</span>
                    <Input
                      value={phoneAddress}
                      onChange={(event) => setPhoneAddress(event.target.value)}
                      placeholder="例如 192.168.1.78"
                      disabled={Boolean(busy)}
                    />
                    <span className="mt-1 block text-[11px] leading-4 text-text-subtle">
                      端口固定 9527，粘贴完整地址也会自动整理。
                    </span>
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">连接令牌</span>
                    <Input
                      type="password"
                      value={phoneToken}
                      onChange={(event) => setPhoneToken(event.target.value)}
                      placeholder={tokenAvailable ? '已保存，留空沿用' : '手机端连接令牌'}
                      disabled={Boolean(busy)}
                    />
                  </label>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button variant="primary" onClick={saveDeviceAndDetect} disabled={Boolean(busy)}>
                    {busy === 'config' || busy === 'status' ? '保存检测中...' : '保存并检测'}
                  </Button>
                  <span className="text-xs font-bold text-text-subtle">
                    {isAddingDevice ? '新手机会保存为独立设备' : tokenAvailable ? '令牌已保存' : '未保存令牌'}
                  </span>
                </div>
              </section>

              <section className="border-t border-border/70 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-black text-text">模型同步</div>
                    <p className="mt-1 text-xs leading-5 text-text-muted">
                      登录中转站或配置第三方模型后，一键写入手机控制模型。
                    </p>
                  </div>
                  <Button variant="primary" onClick={syncPhoneModel} disabled={Boolean(busy) || (!accountLoggedIn && !hasWireConfig)}>
                    {busy === 'syncModel' ? '同步中...' : (accountLoggedIn || hasWireConfig) ? '同步模型到手机' : '配置后同步'}
                  </Button>
                </div>
              </section>

              <section className="grid gap-x-6 gap-y-4 md:grid-cols-3">
                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">设备连接状态</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">读取已保存设备并检查当前连接。</p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button variant="primary" onClick={refreshDevices} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'devices' ? '读取中...' : '刷新设备'}
                    </Button>
                    <Button variant="quiet" onClick={() => checkConnection()} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'status' ? '检测中...' : '检测连接'}
                    </Button>
                  </div>
                </div>

                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">截图 / 读取屏幕</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">截图不操作手机；完整执行请用下方手机任务区。</p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button variant="primary" onClick={captureFrame} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'frame' ? '截图中...' : '截图'}
                    </Button>
                    <Button variant="quiet" onClick={loadHistory} disabled={Boolean(busy)}>
                      {busy === 'history' ? '读取中...' : '读取历史'}
                    </Button>
                  </div>
                </div>

                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">任务状态</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">最近任务会保留在右侧，切页后再回来也能查看。</p>
                  <Button className="mt-4" variant="quiet" onClick={refreshJobs} disabled={Boolean(busy)}>
                    刷新任务
                  </Button>
                </div>
              </section>

              <section className="border-t border-border/70 pt-6">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-black text-text">输入任务</h2>
                    <p className="mt-1 text-xs leading-5 text-text-muted">输入要手机完成的事，结果会保留在右侧最近任务。</p>
                  </div>
                  <span className="text-xs font-bold text-text-subtle">{taskMode}</span>
                </div>
                <div className="mb-4 grid gap-3 md:grid-cols-3">
                  {TASK_MODE_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTaskMode(option.value)}
                      disabled={Boolean(busy)}
                      className={`rounded-[14px] border p-4 text-left transition ${
                        taskMode === option.value
                          ? 'border-[#0B4A3E]/60 bg-[#0B4A3E]/10 text-text shadow-[0_12px_28px_rgba(8,60,49,0.12)]'
                          : 'border-border/70 bg-surface-alt/35 text-text-muted hover:border-border-strong hover:text-text'
                      }`}
                    >
                      <span className="text-sm font-black">{option.title}</span>
                      <span className="mt-1 block text-[11px] font-bold uppercase tracking-[0.16em] text-text-subtle">{option.badge}</span>
                      <span className="mt-2 block text-xs leading-5">{option.desc}</span>
                    </button>
                  ))}
                </div>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  {TASK_PROFILE_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTaskProfile(option.value)}
                      disabled={Boolean(busy)}
                      title={option.desc}
                      className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
                        taskProfile === option.value
                          ? 'border-[#0B4A3E]/60 bg-[#0B4A3E]/10 text-[#0B4A3E]'
                          : 'border-border/70 bg-surface-alt/35 text-text-muted hover:border-border-strong hover:text-text'
                      }`}
                    >
                      {option.title}
                    </button>
                  ))}
                </div>
                <TextArea
                  rows={4}
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={taskMode === 'observe' ? DEFAULT_READ_PROMPT : DEFAULT_ACTION_PROMPT}
                />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Button variant="primary" onClick={executePhoneTask} disabled={Boolean(busy)}>
                    {busy === 'task' ? '执行中...' : '执行'}
                  </Button>
                  <Button variant="quiet" onClick={readScreen} disabled={Boolean(busy)}>
                    {busy === 'read' ? '读取中...' : '读取屏幕'}
                  </Button>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {QUICK_TASKS.map((task, index) => (
                    <button
                      key={task}
                      type="button"
                      onClick={() => applyQuickTask(task, index === 0 ? 'observe' : 'safe')}
                      disabled={Boolean(busy)}
                      className="rounded-full border border-border/70 bg-surface-alt/35 px-3 py-1.5 text-xs font-bold text-text-muted transition hover:border-[#0B4A3E]/45 hover:bg-[#0B4A3E]/10 hover:text-text"
                    >
                      {task.length > 18 ? `${task.slice(0, 18)}...` : task}
                    </button>
                  ))}
                </div>
              </section>

              <section className="border-t border-border/70 pt-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">任务结果</h2>
                  {lastJob ? (
                    <span className={`rounded-full border px-3 py-1 text-xs font-bold ${jobTone(lastJob.status)}`}>
                      {statusLabel(lastJob.status)}
                    </span>
                  ) : null}
                </div>
                {lastText ? (
                  <pre className="whitespace-pre-wrap break-words border-t border-border/60 pt-4 text-sm leading-7 text-text-muted">
                    {lastText}
                  </pre>
                ) : (
                  <div className="border-t border-border/60 pt-4 text-sm text-text-muted">
                    点击上方按钮后，这里会显示设备状态、截图结果或屏幕读取结果。
                  </div>
                )}
              </section>
            </div>

            <aside className="border-t border-border/70 pt-6 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
              <section>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">多设备管理</div>
                    <h2 className="mt-1 text-lg font-black text-text">我的手机</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="quiet" onClick={startAddPhone} disabled={Boolean(busy)}>添加</Button>
                    <Button variant="quiet" onClick={refreshMatrix}>刷新</Button>
                  </div>
                </div>
                <div className="rounded-full border border-border/70 bg-surface-alt/40 px-3 py-1 text-xs font-bold text-text-muted">
                  已保存 {configuredPhones.length} 台 / {matrixStatus?.summary?.online || 0} 在线
                </div>
                {configuredPhones.length ? (
                  <div className="mt-3 space-y-2">
                    {configuredPhones.map((device) => (
                      <button
                        key={device.id}
                        type="button"
                        onClick={() => selectConfiguredPhone(device)}
                        className={`w-full rounded-[8px] border px-3 py-2 text-left transition ${
                          !isAddingDevice && device.id === selectedDeviceId
                            ? 'border-[#0B4A3E] bg-[#0B4A3E]/10'
                            : 'border-border/70 bg-surface-alt/30 hover:border-[#0B4A3E]/35'
                        }`}
                      >
                        <span className="block truncate text-sm font-black text-text">{device.name || device.id}</span>
                        <span className="mt-1 block truncate text-xs text-text-muted">
                          {displayPhoneAddress(device.baseUrl) || '未填写地址'} / {device.tokenAvailable ? '令牌已保存' : '待填令牌'}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3">
                  {matrixStatus?.devices?.length ? (
                    matrixStatus.devices.slice(0, 4).map((device) => (
                      <MatrixDeviceCard key={device.deviceId} device={device} />
                    ))
                  ) : (
                    <div className="border-t border-border/70 py-4 text-sm text-text-muted">
                      暂无设备。保存手机 IP 后会出现在这里。
                    </div>
                  )}
                </div>
              </section>

              <section className="mt-8">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">执行记录</h2>
                  <span className="rounded-full border border-border/70 bg-surface-alt/40 px-3 py-1 text-xs font-bold text-text-muted">
                    {matrixEvents.length} 条
                  </span>
                </div>
                <div>
                  {matrixEvents.length ? (
                    matrixEvents.slice(-5).reverse().map((event) => (
                      <MatrixEventRow key={event.eventId || `${event.type}-${event.timestamp}`} event={event} />
                    ))
                  ) : (
                    <div className="border-t border-border/70 py-4 text-sm text-text-muted">暂无执行记录</div>
                  )}
                </div>
              </section>

              <section className="mt-8">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">最近任务</h2>
                  <Button variant="quiet" onClick={refreshJobs}>刷新</Button>
                </div>
                <div>
                  {jobs.length ? jobs.slice(0, 8).map((job) => (
                    <JobRow key={job.id} job={job as BridgeJob<CliResult>} onSelect={() => setLastJob(job as BridgeJob<CliResult>)} />
                  )) : (
                    <div className="border-t border-border/60 py-3 text-sm text-text-muted">暂无手机任务</div>
                  )}
                </div>
              </section>

              <section className="mt-8">
                <h2 className="text-lg font-black text-text">暂未开放</h2>
                <div className="mt-2">
                  <LockedCard title="自动化模板" desc="演示版不开放复杂流程编排。" />
                  <LockedCard title="定时任务" desc="避免现场后台任务影响演示。" />
                </div>
              </section>
            </aside>
          </div>
        </section>
      </div>
    </div>
  );
};
