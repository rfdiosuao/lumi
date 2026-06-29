import { invoke } from '@tauri-apps/api/core';

let bridgeStartup: Promise<void> | null = null;
const BRIDGE_STARTUP_RETRIES = 480;
const BRIDGE_STARTUP_INTERVAL_MS = 500;

function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    if (typeof record.error === 'string') return record.error;
    if (typeof record.message === 'string') return record.message;
  }
  return '';
}

export function parseErrorText(value: unknown): string {
  const text = getErrorMessage(value).trim();
  if (!text) return '';
  const jsonStart = text.indexOf('{');
  if (jsonStart >= 0) {
    const candidate = text.slice(jsonStart);
    try {
      const payload = JSON.parse(candidate) as Record<string, any>;
      const metaMessage = payload?._meta?.error?.message;
      if (typeof metaMessage === 'string' && metaMessage.trim()) return friendlyErrorText(metaMessage.trim());
      if (typeof payload.error === 'string' && payload.error.trim()) return friendlyErrorText(payload.error.trim());
      if (typeof payload.message === 'string' && payload.message.trim()) return friendlyErrorText(payload.message.trim());
    } catch {
      // Keep the original text below.
    }
  }
  return friendlyErrorText(text.replace(/^\[\d+\]\s*/, '').trim());
}

function friendlyErrorText(text: string): string {
  if (/cannot read properties of undefined \(reading 'invoke'\)/i.test(text) || /__tauri(_internals)?__/i.test(text)) {
    return '当前不在 LOOM 桌面运行环境中，无法连接本地 Bridge。请使用桌面应用运行，或打开诊断查看 Bridge 状态。';
  }
  if (/ipc.*not.*available/i.test(text) || /tauri.*not.*available/i.test(text)) {
    return '桌面通信通道不可用，请使用 LOOM 桌面应用运行。';
  }
  if (/username or password is incorrect/i.test(text)) {
    return '用户名、邮箱或密码错误，或账号已被禁用';
  }
  if (/^newapi_network_error:/i.test(text)) {
    return '无法连接中转站，请检查网络、中转站地址或稍后重试';
  }
  if (/launcher_token_bridge_no_key/i.test(text)) {
    return '中转站未返回可用的 API Key，请在中转站确认账号权限或手动提供 API Token';
  }
  if (/bind ticket is required/i.test(text)) {
    return '请输入网站绑定码';
  }
  if (/bind_ticket_no_key/i.test(text)) {
    return '网站绑定成功但未返回可用 API Key，请重新生成绑定码后再试';
  }
  if (/not_logged_in/i.test(text)) {
    return '尚未登录中转站账号';
  }
  if (/invalid parameters?/i.test(text)) {
    return '请求参数无效，请检查用户名/邮箱、密码和中转站地址';
  }
  if (/unauthorized, not logged in/i.test(text)) {
    return '未登录或访问令牌无效';
  }
  return text;
}

function isTransientStatusReadError(error: unknown): boolean {
  const message = getErrorMessage(error).toLowerCase();
  if (!message) return false;
  return [
    'live_bridge_unavailable',
    'bridge unavailable',
    'bridge not available',
    'bridge not ready',
    'bridge未启动',
    'bridge unavailable',
    'failed to fetch',
    'fetch failed',
    'econnrefused',
    'connection refused',
    'service unavailable',
    '502',
    '503',
    '504',
  ].some((token) => message.includes(token));
}

async function ensureBridgeStarted(invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>) {
  const currentPort = await invoke<number>('get_bridge_port');
  if (currentPort > 0) return;

  if (!bridgeStartup) {
    bridgeStartup = (async () => {
      await invoke<string>('start_bridge');
      for (let i = 0; i < BRIDGE_STARTUP_RETRIES; i += 1) {
        const port = await invoke<number>('get_bridge_port');
        if (port > 0) return;
        await new Promise((resolve) => setTimeout(resolve, BRIDGE_STARTUP_INTERVAL_MS));
      }
      throw new Error('Bridge 启动超时，请到环境诊断里查看 Bridge 启动失败快照');
    })().finally(() => {
      bridgeStartup = null;
    });
  }
  await bridgeStartup;
}

async function proxyRequest(path: string, method: string = 'GET', body?: Record<string, unknown>) {
  await ensureBridgeStarted(invoke);

  let responseText: string;
  try {
    responseText = await invoke<string>('proxy_request', {
      path,
      method,
      body: body ? JSON.stringify(body) : null,
    });
  } catch (error: any) {
    if (isTransientStatusReadError(error)) {
      await ensureBridgeStarted(invoke);
      responseText = await invoke<string>('proxy_request', {
        path,
        method,
        body: body ? JSON.stringify(body) : null,
      });
    } else {
      throw error;
    }
  }
  try {
    return JSON.parse(responseText);
  } catch {
    return { raw: responseText };
  }
}

export async function api<T = unknown>(path: string, method: string = 'GET', body?: Record<string, unknown>): Promise<T> {
  try {
    const result = await proxyRequest(path, method, body);
    if (result && typeof result === 'object' && 'error' in result) {
      throw { error: parseErrorText((result as any).error || result) };
    }
    return result as T;
  } catch (e: any) {
    if (e && typeof e === 'object' && 'error' in e) {
      throw { ...e, error: parseErrorText(e) || e.error };
    }
    const msg = typeof e === 'string' ? e : (e?.message || '未知错误');
    const cleanMsg = parseErrorText(msg) || '未知错误';
    throw { error: cleanMsg };
  }
}

// === Process API ===
export interface ProcessStatus {
  running: boolean;
  processAlive?: boolean;
  starting?: boolean;
  startupState?: 'idle' | 'starting' | 'running' | 'failed' | string;
  startupElapsedSec?: number;
  startupTimeoutSec?: number;
  startupError?: string;
  startupStage?: string | null;
  startupDurationMs?: number | null;
  pid: number | null;
  portReady?: boolean;
  status?: string;
}

export const processApi = {
  start: (): Promise<ProcessStatus> => api('/api/process/start', 'POST'),
  stop: () => api('/api/process/stop', 'POST'),
  status: (): Promise<ProcessStatus> => api('/api/process/status'),
};

export interface WaitForProcessReadyOptions {
  timeoutMs?: number;
  intervalMs?: number;
  onProgress?: (status: ProcessStatus) => void;
}

export async function waitForProcessReady(options: WaitForProcessReadyOptions = {}): Promise<ProcessStatus> {
  const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000;
  const intervalMs = options.intervalMs ?? 1500;
  const deadline = Date.now() + timeoutMs;
  let lastStatus: ProcessStatus | null = null;

  while (Date.now() < deadline) {
    let status: ProcessStatus;
    try {
      status = await processApi.status();
    } catch (error) {
      if (!isTransientStatusReadError(error)) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      continue;
    }

    lastStatus = status;
    options.onProgress?.(status);

    if (status.running) {
      return status;
    }

    if (status.startupState === 'failed' || (!status.processAlive && !status.starting && status.startupError)) {
      throw { error: status.startupError || '核心服务启动失败' };
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  if (lastStatus?.processAlive || lastStatus?.starting) {
    return lastStatus;
  }

  throw { error: '核心服务启动超时，进程没有保持运行，请导出诊断包查看失败快照' };
}

// === Log API ===
export interface LogResponse {
  log: string;
  offset: number;
  total?: number;
  reset?: boolean;
}

export const logApi = {
  get: (offset: number = 0): Promise<LogResponse> => api(`/api/log/get?offset=${Math.max(0, offset)}`),
  clear: () => api('/api/log/clear', 'POST'),
};

// === License API ===
export const licenseApi = {
  current: (): Promise<{ license: object | null; gatewayProfile?: object | null; member?: object | null }> => api('/api/license/current'),
  clientConfig: (): Promise<{ cardSite?: { enabled?: boolean; label?: string; url?: string } }> => api('/api/license/client-config'),
  activate: (code: string): Promise<{ license: object }> => api('/api/license/activate', 'POST', { code }),
  authorized: (feature?: string): Promise<{ authorized: boolean }> => api('/api/license/authorized', 'POST', { feature }),
};

// === Image API ===
export const imageApi = {
  generate: (params: {
    baseUrl: string;
    apiKey: string;
    prompt: string;
    size: string;
    count?: number;
    editImagePath?: string;
  }): Promise<{
    images: string[];
    count: number;
    files?: Array<{ path: string; directory: string; filename: string; size: number; mime?: string }>;
  }> =>
    api('/api/image/generate', 'POST', params),
  submit: (params: {
    baseUrl?: string;
    apiKey?: string;
    prompt: string;
    size: string;
    count?: number;
    model?: string;
    editImagePath?: string;
  }): Promise<{ jobId: string; job: BridgeJob }> =>
    api('/api/image/generate/submit', 'POST', params),
};

// === Video API ===
export const videoApi = {
  generate: (params: {
    providerId?: import('../types').VideoProviderId;
    apiBase?: string;
    model?: string;
    dashKey: string;
    prompt: string;
    mode: string;
    resolution: string;
    duration: number;
    ratio: string;
    imagePath?: string;
  }): Promise<{ video: string; mime?: string; size?: number; path?: string; directory?: string; filename?: string }> =>
    api('/api/video/generate', 'POST', params),
  submit: (params: {
    providerId?: import('../types').VideoProviderId;
    apiBase?: string;
    model?: string;
    dashKey?: string;
    prompt: string;
    mode: string;
    resolution: string;
    duration: number;
    ratio: string;
    imagePath?: string;
  }): Promise<{ jobId: string; job: BridgeJob }> =>
    api('/api/video/generate/submit', 'POST', params),
};

// === Update API ===
export const updateApi = {
  check: (): Promise<{ current: string; latest: string; hasUpdate: boolean }> => api('/api/update/check'),
  do: (): Promise<{ success: boolean; current_version: string; log: string[] }> => api('/api/update/do', 'POST'),
};

// === Config API ===
export const configApi = {
  read: (path: string, defaultValue: unknown = {}): Promise<{ data: unknown }> =>
    api('/api/config/read', 'POST', { path, default: defaultValue }),
  write: (path: string, data: unknown): Promise<{ status: string }> =>
    api('/api/config/write', 'POST', { path, data }),
};

// === Theme API ===
export const themeApi = {
  current: (): Promise<{ theme: import('../types/theme').ThemeConfig; isCustom: boolean; merchantId: string | null }> =>
    api('/api/theme/current'),
};

// === System API ===
export const systemApi = {
  info: (): Promise<{ node_path: string; base_path: string; openclaw_version: string }> => api('/api/system/info'),
};

// === Runtime API ===
export const runtimeApi = {
  basePath: (): Promise<string> => invoke<string>('get_portable_base_path'),
};

// === Diagnostics API ===
export type DiagnosticStatus = 'ok' | 'warn' | 'fail';

export interface DiagnosticCheck {
  id: string;
  label: string;
  status: DiagnosticStatus;
  message: string;
  detail?: string;
  repairable?: boolean;
}

export interface DiagnosticSummary {
  status: DiagnosticStatus;
  ok: number;
  warnings: number;
  failed: number;
  total: number;
}

export interface DiagnosticReport {
  basePath: string;
  serviceRunning: boolean;
  servicePid: number | null;
  startupState?: string;
  startupElapsedSec?: number;
  startupTimeoutSec?: number;
  startupError?: string;
  startupDurationMs?: number | null;
  startupStage?: string | null;
  startupSnapshotPath?: string;
  checks: DiagnosticCheck[];
  summary: DiagnosticSummary;
  repairAvailable: boolean;
}

export interface DiagnosticRepairResult {
  actions: Array<{
    label: string;
    status: DiagnosticStatus;
    message: string;
    count?: number;
  }>;
  diagnostics: DiagnosticReport;
}

export interface DiagnosticExportResult {
  path: string;
  directory: string;
  filename: string;
  size: number;
}

export const diagnosticsApi = {
  run: (): Promise<DiagnosticReport> => api('/api/diagnostics/run'),
  bridgeStartupReport: (): Promise<DiagnosticReport> => invoke<DiagnosticReport>('bridge_startup_report'),
  repair: (params: { confirmed?: boolean } = {}): Promise<DiagnosticRepairResult> =>
    api('/api/diagnostics/repair', 'POST', params),
  export: (): Promise<DiagnosticExportResult> => api('/api/diagnostics/export', 'POST'),
};

// === Account / NewAPI ===
export interface AccountSnapshot {
  loggedIn: boolean;
  source?: string;
  account?: string;
  memberId?: string;
  plan?: string;
  status?: string;
  baseUrl?: string;
  gatewayBaseUrl?: string;
  tokenMasked?: string;
  models?: {
    text?: string[];
    image?: string[];
    video?: string[];
  };
  selectedModels?: {
    text?: string;
    image?: string;
    videoDraft?: string;
  };
  usage?: Record<string, unknown>;
  offline?: boolean;
  stale?: boolean;
  lastOnlineAt?: string;
  graceExpiresAt?: string;
  syncResults?: Array<{ target?: string; ok?: boolean; error?: string }>;
}

export const accountApi = {
  current: (): Promise<{ account: AccountSnapshot }> => api('/api/account/current'),
  sendEmailCode: (params: { email: string; baseUrl?: string }): Promise<{ sent: boolean; email?: string; maskedEmail?: string; retryAfter?: number; expiresIn?: number; message?: string }> =>
    api('/api/account/email-code/send', 'POST', params),
  loginWithEmailCode: (params: { email: string; code: string; baseUrl?: string }): Promise<{ account: AccountSnapshot; syncResults?: Array<{ target?: string; ok?: boolean; error?: string }> }> =>
    api('/api/account/email-code/login', 'POST', params),
  login: (params: { email?: string; username?: string; password: string; baseUrl?: string; apiToken?: string }): Promise<{ account: AccountSnapshot }> =>
    api('/api/account/login', 'POST', params),
  bindTicket: (params: { ticket: string; baseUrl?: string }): Promise<{ account: AccountSnapshot }> =>
    api('/api/account/bind-ticket', 'POST', params),
  sync: (): Promise<{ account: AccountSnapshot }> => api('/api/account/sync', 'POST'),
  selectModels: (params: { textModel?: string; imageModel?: string; videoModel?: string }): Promise<{ account: AccountSnapshot }> =>
    api('/api/account/models/select', 'POST', params),
  logout: (): Promise<{ account: AccountSnapshot; loggedOut?: boolean }> => api('/api/account/logout', 'POST'),
};

// === Jobs ===
export interface BridgeJob<T = unknown> {
  id: string;
  kind?: string;
  label?: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | string;
  message?: string;
  result?: T;
  error?: string;
  progress?: {
    message?: string;
    tone?: string;
    history?: Array<{ message?: string; tone?: string; updatedAt?: number }>;
  };
}

function isJobDone(status: string): boolean {
  return ['succeeded', 'success', 'completed', 'complete'].includes(status.toLowerCase());
}

function isJobFailed(status: string): boolean {
  return ['failed', 'error', 'cancelled', 'canceled'].includes(status.toLowerCase());
}

export const jobApi = {
  get: (jobId: string): Promise<{ job: BridgeJob }> => api(`/api/jobs/${encodeURIComponent(jobId)}`),
  list: (limit = 30): Promise<{ jobs: BridgeJob[] }> => api(`/api/jobs/list?limit=${Math.max(1, limit)}`),
};

export async function waitForJob<T = unknown>(
  jobId: string,
  options: { timeoutMs?: number; intervalMs?: number; onProgress?: (job: BridgeJob<T>) => void } = {},
): Promise<BridgeJob<T>> {
  const timeoutMs = options.timeoutMs ?? 60 * 60 * 1000;
  const intervalMs = options.intervalMs ?? 1500;
  const deadline = Date.now() + timeoutMs;
  let lastJob: BridgeJob<T> | null = null;

  while (Date.now() < deadline) {
    const { job } = await jobApi.get(jobId) as { job: BridgeJob<T> };
    lastJob = job;
    options.onProgress?.(job);
    if (isJobDone(String(job.status || ''))) return job;
    if (isJobFailed(String(job.status || ''))) {
      throw { error: job.error || job.message || `任务失败: ${jobId}` };
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw { error: lastJob?.progress?.message || lastJob?.message || `任务超时: ${jobId}` };
}

// === Components / Agent installer ===
export interface ComponentSummary {
  id: string;
  name: string;
  version: string;
  installedVersion?: string | null;
  previousVersion?: string | null;
  status: string;
  jobId?: string | null;
  platform: string;
  arch: string;
  type: string;
  size: number;
  entry?: string | null;
  installPath: string;
  installCommand?: string[];
  uninstallCommand?: string[];
  commandTimeoutMs?: number;
  category: string;
  officialUrl?: string | null;
  description?: string | null;
  urls: string[];
  updatedAt?: string | null;
  errorCode?: string | null;
  errorMessage?: string | null;
}

export interface ComponentSnapshot {
  manifest: {
    schemaVersion: number;
    product: string;
    channel: string;
    version: string;
    publishedAt: string;
    minLauncherVersion: string;
  } | null;
  components: ComponentSummary[];
  error?: string | null;
  warning?: string | null;
  manifestErrorCode?: string | null;
}

export const componentApi = {
  status: (): Promise<ComponentSnapshot> => api('/api/components/status'),
  install: async (
    componentId: string,
    options: { simulate?: boolean; confirmed?: boolean; onProgress?: (job: BridgeJob<{ catalog?: ComponentSnapshot }>) => void } = {},
  ): Promise<ComponentSnapshot> => {
    const submitted = await api<{
      jobId?: string;
      job?: BridgeJob<{ catalog?: ComponentSnapshot }>;
      catalog?: ComponentSnapshot;
    }>('/api/components/install', 'POST', {
      componentId,
      ...(options.simulate ? { mode: 'simulate', dryRun: true } : {}),
      ...(options.confirmed ? { confirmed: true } : {}),
    });
    const jobId = submitted.jobId || submitted.job?.id;
    if (jobId) {
      const job = await waitForJob<{ catalog?: ComponentSnapshot }>(jobId, { onProgress: options.onProgress });
      return job.result?.catalog || submitted.catalog || componentApi.status();
    }
    return submitted.catalog || componentApi.status();
  },
  rollback: async (
    componentId: string,
    options: { onProgress?: (job: BridgeJob<{ catalog?: ComponentSnapshot }>) => void } = {},
  ): Promise<ComponentSnapshot> => {
    const submitted = await api<{
      jobId?: string;
      job?: BridgeJob<{ catalog?: ComponentSnapshot }>;
      catalog?: ComponentSnapshot;
    }>('/api/components/rollback', 'POST', { componentId, confirmed: true });
    const jobId = submitted.jobId || submitted.job?.id;
    if (jobId) {
      const job = await waitForJob<{ catalog?: ComponentSnapshot }>(jobId, { onProgress: options.onProgress });
      return job.result?.catalog || submitted.catalog || componentApi.status();
    }
    return submitted.catalog || componentApi.status();
  },
  uninstall: async (
    componentId: string,
    options: { onProgress?: (job: BridgeJob<{ catalog?: ComponentSnapshot }>) => void } = {},
  ): Promise<ComponentSnapshot> => {
    const submitted = await api<{
      jobId?: string;
      job?: BridgeJob<{ catalog?: ComponentSnapshot }>;
      catalog?: ComponentSnapshot;
    }>('/api/components/uninstall', 'POST', { componentId, confirmed: true });
    const jobId = submitted.jobId || submitted.job?.id;
    if (jobId) {
      const job = await waitForJob<{ catalog?: ComponentSnapshot }>(jobId, { onProgress: options.onProgress });
      return job.result?.catalog || submitted.catalog || componentApi.status();
    }
    return submitted.catalog || componentApi.status();
  },
  detect: async (
    componentId: string,
    options: { onProgress?: (job: BridgeJob<{ catalog?: ComponentSnapshot }>) => void } = {},
  ): Promise<ComponentSnapshot> => {
    const submitted = await api<{
      jobId?: string;
      job?: BridgeJob<{ catalog?: ComponentSnapshot }>;
      catalog?: ComponentSnapshot;
    }>('/api/components/detect', 'POST', { componentId });
    const jobId = submitted.jobId || submitted.job?.id;
    if (jobId) {
      const job = await waitForJob<{ catalog?: ComponentSnapshot }>(jobId, { onProgress: options.onProgress });
      return job.result?.catalog || submitted.catalog || componentApi.status();
    }
    return submitted.catalog || componentApi.status();
  },
  start: async (
    componentId: string,
    options: { onProgress?: (job: BridgeJob<{ catalog?: ComponentSnapshot }>) => void } = {},
  ): Promise<ComponentSnapshot> => {
    const submitted = await api<{
      jobId?: string;
      job?: BridgeJob<{ catalog?: ComponentSnapshot }>;
      catalog?: ComponentSnapshot;
    }>('/api/components/start', 'POST', { componentId, confirmed: true });
    const jobId = submitted.jobId || submitted.job?.id;
    if (jobId) {
      const job = await waitForJob<{ catalog?: ComponentSnapshot }>(jobId, { onProgress: options.onProgress });
      return job.result?.catalog || submitted.catalog || componentApi.status();
    }
    return submitted.catalog || componentApi.status();
  },
};

// === CLI capability gateway ===
export interface CliCommandSummary {
  id: string;
  title: string;
  examples: string[];
}

export const cliApi = {
  catalog: (): Promise<{ commands: CliCommandSummary[] }> => api('/api/cli/catalog'),
  run: (params: { command: string; args?: string[]; confirmed?: boolean; timeoutSec?: number }): Promise<{ jobId: string; job: BridgeJob }> =>
    api('/api/cli/run', 'POST', params),
};

// === Phone demo API ===
export interface PhoneDeviceSummary {
  id: string;
  name: string;
  baseUrl: string;
  tokenAvailable: boolean;
  paired?: boolean;
  album?: string;
  lastSeenAt?: string;
}

export interface PhoneConfigSnapshot {
  selectedDeviceId: string;
  configured: boolean;
  devices: PhoneDeviceSummary[];
}

export const phoneApi = {
  config: (): Promise<PhoneConfigSnapshot> => api('/api/phone/config'),
  saveDevice: (params: {
    id?: string;
    deviceId?: string;
    name?: string;
    baseUrl: string;
    token?: string;
    selectedDeviceId?: string;
  }): Promise<PhoneConfigSnapshot> => api('/api/phone/config/device', 'POST', params),
  syncModel: (): Promise<{ jobId: string; job: BridgeJob }> => api('/api/phone/sync-model', 'POST'),
  devices: (): Promise<{ jobId: string; job: BridgeJob }> => api('/api/phone/devices', 'POST'),
  status: (): Promise<{ jobId: string; job: BridgeJob }> => api('/api/phone/status', 'POST'),
  screenshot: (): Promise<{ jobId: string; job: BridgeJob }> => api('/api/phone/screenshot', 'POST'),
  read: (params: { prompt: string }): Promise<{ jobId: string; job: BridgeJob }> =>
    api('/api/phone/read', 'POST', params),
  history: (): Promise<{ jobId: string; job: BridgeJob }> => api('/api/phone/history', 'POST'),
};

// === Runtime wire API ===
export interface WireSnapshot {
  ok?: boolean;
  managedBy?: string;
  provider?: string;
  tokenMasked?: string;
  models?: {
    text?: string;
    phone?: string;
    image?: string;
    video?: string;
  };
  targets?: Record<string, boolean>;
  updatedAt?: string;
}

export const wireApi = {
  current: (): Promise<{ wire: WireSnapshot }> => api('/api/wire/current'),
  sync: (): Promise<{ wire: WireSnapshot; syncResults?: Array<{ target?: string; ok?: boolean; error?: string }> }> =>
    api('/api/wire/sync', 'POST'),
  custom: (params: {
    provider?: string;
    baseUrl: string;
    apiKey: string;
    textModel: string;
    imageModel?: string;
    phoneModel?: string;
    videoModel?: string;
  }): Promise<{ wire: WireSnapshot; syncResults?: Array<{ target?: string; ok?: boolean; error?: string }> }> =>
    api('/api/wire/custom', 'POST', params),
  verify: (): Promise<{ ok: boolean; wire?: WireSnapshot; targets?: Record<string, { ok?: boolean; error?: string }> }> =>
    api('/api/wire/verify', 'POST'),
  rollback: (): Promise<{ wire: WireSnapshot; syncResults?: Array<{ target?: string; ok?: boolean; error?: string }> }> =>
    api('/api/wire/rollback', 'POST'),
};
