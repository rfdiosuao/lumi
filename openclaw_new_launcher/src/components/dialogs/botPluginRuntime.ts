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

function visibleAnsiQrBlocks(text: string): string {
  return text
    .replace(/\x1B\[(?:\d+;)*(?:47|46|107|106)m( +)\x1B\[0m/g, (_, spaces: string) => '█'.repeat(spaces.length))
    .replace(/\x1B\[(?:\d+;)*(?:40|100)m( +)\x1B\[0m/g, (_, spaces: string) => ' '.repeat(spaces.length))
    .replace(/\x1B\[7m( +)\x1B\[0m/g, (_, spaces: string) => '█'.repeat(spaces.length));
}

export function normalizeCommandOutput(data: unknown): string {
  const text = data instanceof Uint8Array
    ? new TextDecoder('utf-8').decode(data)
    : String(data ?? '');
  return stripAnsi(visibleAnsiQrBlocks(text));
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

  const portablePath = [
    `${cwd}\\node`,
    `${cwd}\\SystemData\\.core\\node`,
    `${cwd}\\node_modules\\.bin`,
    `${cwd}\\SystemData\\.core\\node_modules\\.bin`,
    'C:\\Windows\\System32',
    'C:\\Windows',
    'C:\\Windows\\System32\\WindowsPowerShell\\v1.0',
  ].join(';');
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
