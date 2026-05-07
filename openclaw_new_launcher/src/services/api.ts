import { invoke } from '@tauri-apps/api/core';

let bridgeStartup: Promise<void> | null = null;

async function ensureBridgeStarted(invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>) {
  const currentPort = await invoke<number>('get_bridge_port');
  if (currentPort > 0) return;

  if (!bridgeStartup) {
    bridgeStartup = (async () => {
      await invoke<string>('start_bridge');
      for (let i = 0; i < 20; i += 1) {
        const port = await invoke<number>('get_bridge_port');
        if (port > 0) return;
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      throw new Error('Bridge 启动超时');
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
    const message = typeof error === 'string' ? error : (error?.message || '');
    if (message.includes('Bridge 未启动')) {
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
      throw { error: (result as any).error };
    }
    return result as T;
  } catch (e: any) {
    if (e && typeof e === 'object' && 'error' in e) {
      throw e;
    }
    const msg = typeof e === 'string' ? e : (e?.message || '未知错误');
    const cleanMsg = msg.replace(/^\[\d+\]\s*/, '');
    throw { error: cleanMsg };
  }
}

// === Process API ===
export const processApi = {
  start: () => api('/api/process/start', 'POST'),
  stop: () => api('/api/process/stop', 'POST'),
  status: (): Promise<{ running: boolean; pid: number | null }> => api('/api/process/status'),
};

// === Log API ===
export const logApi = {
  get: (): Promise<{ log: string }> => api('/api/log/get'),
  clear: () => api('/api/log/clear', 'POST'),
};

// === License API ===
export const licenseApi = {
  current: (): Promise<{ license: object | null }> => api('/api/license/current'),
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
  }): Promise<{ images: string[]; count: number }> =>
    api('/api/image/generate', 'POST', params),
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
  repair: (): Promise<DiagnosticRepairResult> => api('/api/diagnostics/repair', 'POST'),
  export: (): Promise<DiagnosticExportResult> => api('/api/diagnostics/export', 'POST'),
};
