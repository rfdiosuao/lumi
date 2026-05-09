export interface PhoneConnectionConfig {
  name?: string;
  baseUrl: string;
  token: string;
}

export interface PhoneApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  raw?: unknown;
}

export interface PhoneStatus {
  online: boolean;
  taskRunning: boolean;
  agentInitialized: boolean;
  llmConfigured: boolean;
  accessibilityRunning: boolean;
  screenshotSupported?: boolean;
  version?: string;
}

export interface PhoneScreenshot {
  mime: 'image/png';
  base64: string;
  dataUrl: string;
  capturedAt: string;
  width?: number;
  height?: number;
}

export interface PhoneTapRequest {
  x: number;
  y: number;
  traceId?: string;
  visualize?: boolean;
}

const STORAGE_KEY = 'lumi_phone_connector_config';
const TOKEN_HEADER = 'X-AGENT-PHONE-TOKEN';
const LEGACY_TOKEN_HEADER = 'X-APKCLAW-TOKEN';

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '');
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function parseMaybeJsonObject(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    try {
      return asObject(JSON.parse(value));
    } catch {
      return {};
    }
  }
  return asObject(value);
}

async function request<T>(
  config: PhoneConnectionConfig,
  path: string,
  options: RequestInit = {},
  transform: (payload: unknown) => T
): Promise<PhoneApiResult<T>> {
  const baseUrl = normalizeBaseUrl(config.baseUrl);
  if (!baseUrl) return { ok: false, error: 'missing_base_url' };
  if (!config.token.trim()) return { ok: false, error: 'missing_token' };

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        [TOKEN_HEADER]: config.token,
        [LEGACY_TOKEN_HEADER]: config.token,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
  } catch (error: any) {
    return { ok: false, error: error?.message || 'network_error' };
  }

  if (response.status === 401) {
    return { ok: false, error: 'unauthorized' };
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return { ok: false, error: 'invalid_response' };
  }

  const body = asObject(payload);
  if (body.success === false) {
    return {
      ok: false,
      error: typeof body.error === 'string' ? body.error : 'request_failed',
      raw: payload,
    };
  }

  try {
    return { ok: true, data: transform(payload), raw: payload };
  } catch (error: any) {
    return { ok: false, error: error?.message || 'invalid_response', raw: payload };
  }
}

export function loadPhoneConfig(): PhoneConnectionConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { name: 'Android Phone', baseUrl: 'http://192.168.1.100:9527', token: '' };
    const parsed = JSON.parse(raw);
    return {
      name: String(parsed?.name || 'Android Phone'),
      baseUrl: String(parsed?.baseUrl || ''),
      token: String(parsed?.token || ''),
    };
  } catch {
    return { name: 'Android Phone', baseUrl: 'http://192.168.1.100:9527', token: '' };
  }
}

export function savePhoneConfig(config: PhoneConnectionConfig): PhoneConnectionConfig {
  const clean = {
    name: (config.name || 'Android Phone').trim() || 'Android Phone',
    baseUrl: normalizeBaseUrl(config.baseUrl),
    token: config.token.trim(),
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
  return clean;
}

export const phoneApi = {
  status: (config: PhoneConnectionConfig): Promise<PhoneApiResult<PhoneStatus>> =>
    request(config, '/api/agent/status', {}, (payload) => {
      const body = asObject(payload);
      const data = parseMaybeJsonObject(body.data);
      return {
        online: true,
        taskRunning: Boolean(data.taskRunning),
        agentInitialized: Boolean(data.agentInitialized),
        llmConfigured: Boolean(data.llmConfigured),
        accessibilityRunning: Boolean(data.accessibilityRunning),
      };
    }),

  screenshot: (config: PhoneConnectionConfig): Promise<PhoneApiResult<PhoneScreenshot>> =>
    request(config, '/api/tool/screenshot', {}, (payload) => {
      const body = asObject(payload);
      const data = body.data;
      let base64 = '';
      let width: number | undefined;
      let height: number | undefined;

      if (typeof data === 'string') {
        base64 = data;
      } else {
        const obj = asObject(data);
        base64 = String(obj.base64 || '');
        width = typeof obj.width === 'number' ? obj.width : undefined;
        height = typeof obj.height === 'number' ? obj.height : undefined;
      }

      if (!base64) throw new Error('empty_screenshot');
      return {
        mime: 'image/png',
        base64,
        dataUrl: `data:image/png;base64,${base64}`,
        capturedAt: new Date().toISOString(),
        width,
        height,
      };
    }),

  tap: (config: PhoneConnectionConfig, requestBody: PhoneTapRequest): Promise<PhoneApiResult<{ x: number; y: number }>> =>
    request(
      config,
      '/api/tool/tap',
      {
        method: 'POST',
        body: JSON.stringify({ x: requestBody.x, y: requestBody.y }),
      },
      () => ({ x: requestBody.x, y: requestBody.y })
    ),
};
