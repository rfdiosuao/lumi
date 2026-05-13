import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REQUEST_TIMEOUT_MS = 615_000;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');

export function normalizePhoneUrl(url) {
  return String(url || '').trim().replace(/\/+$/, '');
}

export function ensurePhoneConfig(config) {
  if (!config.phoneUrl) throw new Error('Missing phone URL. Configure it in the launcher Phone Control page, or use --phone-url / OPENCLAW_PHONE_BASE_URL.');
  if (!config.phoneToken) throw new Error('Missing phone token. Configure it in the launcher Phone Control page, or use --phone-token / OPENCLAW_PHONE_TOKEN.');
}

export async function readLauncherPhoneConfig() {
  const candidates = [
    path.join(PROJECT_ROOT, 'data', '.openclaw', 'launcher', 'phone-agent.json'),
    path.join(PROJECT_ROOT, 'OpenClawFiles', 'data', '.openclaw', 'launcher', 'phone-agent.json'),
  ];

  for (const filePath of candidates) {
    try {
      const parsed = JSON.parse(await fs.readFile(filePath, 'utf8'));
      return {
        phoneUrl: typeof parsed?.baseUrl === 'string' ? parsed.baseUrl.trim().replace(/\/+$/, '') : '',
        phoneToken: typeof parsed?.token === 'string' ? parsed.token.trim() : '',
        source: filePath,
      };
    } catch (error) {
      if (error?.code !== 'ENOENT') throw new Error(`Failed to read launcher phone config: ${filePath}: ${error.message}`);
    }
  }

  return { phoneUrl: '', phoneToken: '', source: '' };
}

export function authHeaders(config) {
  return {
    'X-AGENT-PHONE-TOKEN': config.phoneToken,
    'X-APKCLAW-TOKEN': config.phoneToken,
  };
}

export async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

export async function pairLumiLauncher(config) {
  ensurePhoneConfig(config);
  if (config.lumiLauncherId && config.lumiLauncherSecret) {
    return {
      launcherId: config.lumiLauncherId,
      launcherSecret: config.lumiLauncherSecret,
    };
  }

  const launcherId = config.lumiLauncherId || `openclaw-cli-${crypto.randomUUID()}`;
  const response = await fetchWithTimeout(`${normalizePhoneUrl(config.phoneUrl)}/api/lumi/security/pair`, {
    method: 'POST',
    headers: {
      ...authHeaders(config),
      'Content-Type': 'application/json; charset=utf-8',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      launcherId,
      launcherName: 'OpenClaw CLI',
      clientVersion: 'openclaw-cli',
    }),
  }, 30_000);
  const payload = await parseJsonResponse(response, 'Phone pairing returned non-JSON response');
  if (!response.ok || payload?.success === false) {
    throw new Error(payload?.error || `Lumi pairing failed: HTTP ${response.status}`);
  }
  const data = payload?.data || payload;
  if (!data?.launcherId || !data?.launcherSecret) {
    throw new Error('Lumi pairing response did not include launcher credentials.');
  }
  config.lumiLauncherId = data.launcherId;
  config.lumiLauncherSecret = data.launcherSecret;
  return data;
}

export async function signedJsonRequest(config, method, endpoint, body = undefined, timeoutMs = REQUEST_TIMEOUT_MS, retryPairing = true) {
  ensurePhoneConfig(config);
  const bodyText = body === undefined ? '' : JSON.stringify(body);
  const headers = await lumiHeaders(config, method, endpoint, bodyText);
  const response = await fetchWithTimeout(`${normalizePhoneUrl(config.phoneUrl)}${endpoint}`, {
    method,
    headers: {
      ...authHeaders(config),
      ...headers,
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json; charset=utf-8' } : {}),
    },
    body: body === undefined ? undefined : bodyText,
  }, timeoutMs);
  const payload = await parseJsonResponse(response, 'Phone returned non-JSON response');
  if (response.status === 403 && retryPairing) {
    config.lumiLauncherSecret = '';
    config.lumiLauncherId = '';
    return signedJsonRequest(config, method, endpoint, body, timeoutMs, false);
  }
  if (!response.ok || payload?.success === false) {
    throw new Error(payload?.error || payload?.message || `Phone request failed: HTTP ${response.status}`);
  }
  return payload;
}

export async function signedFetch(config, method, endpoint, timeoutMs = REQUEST_TIMEOUT_MS, retryPairing = true) {
  ensurePhoneConfig(config);
  const headers = await lumiHeaders(config, method, endpoint, '');
  const response = await fetchWithTimeout(`${normalizePhoneUrl(config.phoneUrl)}${endpoint}`, {
    method,
    headers: {
      ...authHeaders(config),
      ...headers,
    },
  }, timeoutMs);
  if (response.status === 403 && retryPairing) {
    config.lumiLauncherSecret = '';
    config.lumiLauncherId = '';
    return signedFetch(config, method, endpoint, timeoutMs, false);
  }
  return response;
}

export async function uploadImageBuffer(config, bytes, filename, mime = 'image/png') {
  const dataUrl = `data:${mime};base64,${Buffer.from(bytes).toString('base64')}`;
  const payload = await signedJsonRequest(config, 'POST', '/api/lumi/media/import_image', {
    dataUrl,
    album: config.album || 'OpenClaw',
    filename,
  }, 120_000);
  return payload.data || payload;
}

async function lumiHeaders(config, method, endpoint, bodyText) {
  const pairing = await pairLumiLauncher(config);
  const timestamp = String(Date.now());
  const nonce = crypto.randomBytes(16).toString('hex');
  const bodyHash = crypto.createHash('sha256').update(bodyText, 'utf8').digest('hex');
  const signatureInput = [
    method.toUpperCase(),
    endpoint,
    timestamp,
    nonce,
    bodyHash,
  ].join('\n');
  const signature = crypto
    .createHmac('sha256', pairing.launcherSecret)
    .update(signatureInput, 'utf8')
    .digest('base64url');
  return {
    'X-LUMI-LAUNCHER-ID': pairing.launcherId,
    'X-LUMI-TIMESTAMP': timestamp,
    'X-LUMI-NONCE': nonce,
    'X-LUMI-BODY-SHA256': bodyHash,
    'X-LUMI-SIGNATURE': signature,
  };
}

async function parseJsonResponse(response, message) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${message}: HTTP ${response.status}`);
  }
}
