import { runtimeApi, systemApi } from '../../services/api';
import type { BotChannel } from './botPluginTypes';

export function isInstalledPackage(data: unknown, packageName?: string): boolean {
  if (!data || typeof data !== 'object') return false;
  const pkg = data as { name?: unknown };
  if (typeof pkg.name !== 'string' || pkg.name.length === 0) return false;
  return packageName ? pkg.name === packageName : true;
}

export function stripAnsi(text: string): string {
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
}

export function normalizeCommandOutput(data: unknown): string {
  if (typeof data === 'string') return stripAnsi(data);
  if (data instanceof Uint8Array) return stripAnsi(new TextDecoder('utf-8').decode(data));
  return stripAnsi(String(data ?? ''));
}

export function buildChannelConfig(channel: BotChannel, idValue: string, secretValue: string) {
  return {
    enabled: true,
    appId: idValue,
    appSecret: secretValue,
    domain: channel.configKey,
    connectionMode: 'websocket',
    requireMention: channel.key === 'feishu',
    dmPolicy: 'open',
    groupPolicy: 'open',
    streaming: true,
  };
}

export function getSavedChannelConfig(config: any, channel: BotChannel) {
  return config?.channels?.[channel.configKey] || (
    channel.legacyConfigKey ? config?.channels?.[channel.legacyConfigKey] : null
  );
}

export function configHasPlugin(config: any, channel: BotChannel): boolean {
  const entries = config?.plugins?.entries || {};
  const paths = config?.plugins?.load?.paths || [];
  if (entries?.[channel.pluginName]?.enabled) return true;
  if (Array.isArray(paths)) {
    return paths.some((item) => String(item).toLowerCase().includes(channel.pluginName.toLowerCase()));
  }
  return false;
}

export function makeCommandOptions(cwd?: string) {
  const base = { encoding: 'utf-8' as const };
  if (!cwd) return base;

  const portablePath = `${cwd}\\node;${cwd}\\node_modules\\.bin`;
  return {
    ...base,
    cwd,
    env: {
      PATH: portablePath,
      Path: portablePath,
      OPENCLAW_STATE_DIR: `${cwd}\\data\\.openclaw`,
      OPENCLAW_CONFIG_PATH: `${cwd}\\data\\.openclaw\\openclaw.json`,
      OPENCLAW_HOME: `${cwd}\\data\\.openclaw`,
      OPENCLAW_GATEWAY_PORT: '18790',
      NO_COLOR: '1',
    },
  };
}

export async function resolvePortableBasePath() {
  try {
    return await runtimeApi.basePath();
  } catch {
    const systemInfo = await systemApi.info().catch(() => null);
    return systemInfo?.base_path || undefined;
  }
}
