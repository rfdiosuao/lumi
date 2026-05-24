import { licenseApi } from './api';

export type GatewayMode = 'member' | 'manual';

export interface GatewayDefaults {
  baseUrl: string;
  apiKey: string;
  defaultModel: string;
  imageModel: string;
  videoModel: string;
  hasGateway: boolean;
}

export interface GatewayStoredConfig {
  mode: GatewayMode | null;
  baseUrl: string;
  apiKey: string;
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function normalizeGatewayMode(value: unknown): GatewayMode | null {
  if (value === 'member' || value === 'manual') return value;
  if (value === true) return 'member';
  if (value === false) return 'manual';
  const normalized = normalizeText(value).toLowerCase();
  if (!normalized) return null;
  if (['member', 'managed', 'auto', 'gateway', 'member-mode', 'member_mode'].includes(normalized)) return 'member';
  if (['manual', 'local', 'custom', 'local-mode', 'local_mode'].includes(normalized)) return 'manual';
  return null;
}

export function readGatewayStoredConfig(data: unknown): GatewayStoredConfig {
  const source = data && typeof data === 'object' ? (data as Record<string, unknown>) : {};
  return {
    mode: normalizeGatewayMode(source.gatewayMode ?? source.managedMode),
    baseUrl: normalizeText(source.baseUrl),
    apiKey: normalizeText(source.apiKey),
  };
}

export async function readMemberGatewayDefaults(): Promise<GatewayDefaults> {
  const resp = await licenseApi.current();
  const license = resp.license as any;
  const baseUrl = normalizeText(license?.gatewayBaseUrl || license?.gatewayUrl);
  const apiKey = normalizeText(license?.gatewayAccessToken || license?.gatewayToken);

  return {
    baseUrl,
    apiKey,
    defaultModel: normalizeText(license?.gatewayDefaultModel || license?.defaultModel),
    imageModel: normalizeText(license?.gatewayImageModel || license?.imageModel),
    videoModel: normalizeText(license?.gatewayVideoModel || license?.videoModel),
    hasGateway: Boolean(baseUrl && apiKey),
  };
}
