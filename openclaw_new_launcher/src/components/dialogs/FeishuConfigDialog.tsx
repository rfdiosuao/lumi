import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Command, type Child, type TerminatedPayload } from '@tauri-apps/plugin-shell';
import { Button, FieldLabel, Input, Loading, showToast } from '../common';
import { configApi, runtimeApi, systemApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const OPENCLAW_CONFIG_PATH = 'data/.openclaw/openclaw.json';

type PluginStatus = 'unknown' | 'installed' | 'missing' | 'error';
type BotChannelKey = 'feishu' | 'weixin';

interface InstallStep {
  label: string;
  displayCommand: string;
  commandName: string;
  fallbackCommandName: string;
  args: string[];
  successMessage: string;
}

interface BotChannel {
  key: BotChannelKey;
  configKey: string;
  legacyConfigKey?: string;
  title: string;
  description: string;
  pluginName: string;
  packageName: string;
  packagePaths: string[];
  installSteps: InstallStep[];
  idLabel: string;
  idPlaceholder: string;
  secretLabel: string;
  secretPlaceholder: string;
  docsUrl?: string;
  docsLabel?: string;
  manualConfig: boolean;
}

const CHANNELS: Record<BotChannelKey, BotChannel> = {
  feishu: {
    key: 'feishu',
    configKey: 'openclaw-lark',
    legacyConfigKey: 'feishu',
    title: '飞书机器人',
    description: '安装 OpenClaw 飞书插件，并写入飞书开放平台应用配置。',
    pluginName: 'openclaw-lark',
    packageName: '@larksuite/openclaw-lark',
    packagePaths: [
      'node_modules/@larksuite/openclaw-lark/package.json',
      'data/.openclaw/extensions/openclaw-lark/package.json',
      'data/.openclaw/extensions/lark/package.json',
    ],
    installSteps: [
      {
        label: '安装飞书插件',
        displayCommand: 'node scripts/bot-plugin-helper.mjs install feishu',
        commandName: 'bot-plugin-install-feishu',
        fallbackCommandName: 'bot-plugin-install-feishu-node-exe',
        args: ['scripts/bot-plugin-helper.mjs', 'install', 'feishu'],
        successMessage: '飞书插件已写入本地配置。填写 App ID 和 App Secret 后，重启核心服务生效。',
      },
    ],
    idLabel: 'App ID',
    idPlaceholder: 'cli_xxx',
    secretLabel: 'App Secret',
    secretPlaceholder: '请输入 App Secret',
    docsUrl: 'https://open.feishu.cn/app',
    docsLabel: '打开飞书开放平台',
    manualConfig: true,
  },
  weixin: {
    key: 'weixin',
    configKey: 'openclaw-weixin',
    title: '微信机器人',
    description: '安装 OpenClaw 微信绑定插件。微信绑定只能通过命令行输出中的二维码扫码完成。',
    pluginName: 'openclaw-weixin',
    packageName: '@tencent-weixin/openclaw-weixin',
    packagePaths: [
      'node_modules/@tencent-weixin/openclaw-weixin/package.json',
      'data/.openclaw/extensions/openclaw-weixin/package.json',
      'data/.openclaw/extensions/weixin/package.json',
      'data/.openclaw/extensions/wechat/package.json',
    ],
    installSteps: [
      {
        label: '安装微信插件',
        displayCommand: 'node scripts/bot-plugin-helper.mjs install weixin',
        commandName: 'bot-plugin-install-weixin',
        fallbackCommandName: 'bot-plugin-install-weixin-node-exe',
        args: ['scripts/bot-plugin-helper.mjs', 'install', 'weixin'],
        successMessage: '微信插件已写入本地配置，准备打开扫码绑定命令。',
      },
      {
        label: '微信扫码绑定',
        displayCommand: 'node scripts/bot-plugin-helper.mjs login-weixin',
        commandName: 'bot-plugin-login-weixin',
        fallbackCommandName: 'bot-plugin-login-weixin-node-exe',
        args: ['scripts/bot-plugin-helper.mjs', 'login-weixin'],
        successMessage: '微信扫码绑定命令已结束。绑定完成后，请重启核心服务生效。',
      },
    ],
    idLabel: '',
    idPlaceholder: '',
    secretLabel: '',
    secretPlaceholder: '',
    manualConfig: false,
  },
};

function isInstalledPackage(data: unknown, packageName?: string): boolean {
  if (!data || typeof data !== 'object') return false;
  const pkg = data as { name?: unknown };
  if (typeof pkg.name !== 'string' || pkg.name.length === 0) return false;
  return packageName ? pkg.name === packageName : true;
}

function stripAnsi(text: string): string {
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
}

function normalizeCommandOutput(data: unknown): string {
  if (typeof data === 'string') return stripAnsi(data);
  if (data instanceof Uint8Array) return stripAnsi(new TextDecoder('utf-8').decode(data));
  return stripAnsi(String(data ?? ''));
}

function buildChannelConfig(channel: BotChannel, idValue: string, secretValue: string) {
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

function getSavedChannelConfig(config: any, channel: BotChannel) {
  return config?.channels?.[channel.configKey] || (
    channel.legacyConfigKey ? config?.channels?.[channel.legacyConfigKey] : null
  );
}

function configHasPlugin(config: any, channel: BotChannel): boolean {
  const entries = config?.plugins?.entries || {};
  const paths = config?.plugins?.load?.paths || [];
  if (entries?.[channel.pluginName]?.enabled) return true;
  if (Array.isArray(paths)) {
    return paths.some((item) => String(item).toLowerCase().includes(channel.pluginName.toLowerCase()));
  }
  return false;
}

function makeCommandOptions(cwd?: string) {
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

async function resolvePortableBasePath() {
  try {
    return await runtimeApi.basePath();
  } catch {
    const systemInfo = await systemApi.info().catch(() => null);
    return systemInfo?.base_path || undefined;
  }
}

const BotConfigDialog: React.FC<{ channel: BotChannel; onClose: () => void }> = ({ channel, onClose }) => {
  const [idValue, setIdValue] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [pluginStatus, setPluginStatus] = useState<PluginStatus>('unknown');
  const [checking, setChecking] = useState(true);
  const [commandRunning, setCommandRunning] = useState(false);
  const [statusMessage, setStatusMessage] = useState(`正在检测${channel.title}插件...`);
  const [commandLog, setCommandLog] = useState<string[]>([]);
  const childRef = useRef<Child | null>(null);
  const outputRef = useRef<HTMLPreElement | null>(null);
  const stoppingRef = useRef(false);
  const appendMainLog = useLogStore((s) => s.append);

  const installed = pluginStatus === 'installed';
  const hasCommandLog = commandLog.length > 0;
  const commandSummary = useMemo(
    () => channel.installSteps.map((step) => step.displayCommand).join('\n'),
    [channel.installSteps],
  );

  const pushCommandLog = useCallback((text: string, mirrorToServiceLog = true) => {
    const clean = normalizeCommandOutput(text);
    if (!clean) return;
    setCommandLog((items) => [...items, clean]);
    if (mirrorToServiceLog) {
      appendMainLog(`[${channel.title}] ${clean.endsWith('\n') ? clean : `${clean}\n`}`);
    }
  }, [appendMainLog, channel.title]);

  useEffect(() => {
    if (!outputRef.current) return;
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [commandLog]);

  useEffect(() => {
    return () => {
      childRef.current?.kill().catch(() => undefined);
      childRef.current = null;
    };
  }, []);

  const checkPlugin = useCallback(async () => {
    setChecking(true);
    setStatusMessage(`正在检测${channel.title}插件...`);

    const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {}).catch((error) => {
      appendMainLog(`[${channel.title}] 配置读取失败，继续检测本地插件包：${error}\n`);
      return { data: {} };
    });

    const packageResponses = await Promise.all(
      channel.packagePaths.map((packagePath) => configApi.read(packagePath, null).catch(() => ({ data: null }))),
    );

    const config = (configResp.data as any) || {};
    const savedChannel = getSavedChannelConfig(config, channel);
    if (savedChannel?.appId || savedChannel?.robotId) {
      setIdValue(String(savedChannel.appId || savedChannel.robotId));
    }

    const bundledPackage = packageResponses.some((resp) => isInstalledPackage(resp.data, channel.packageName));
    const configured = configHasPlugin(config, channel);
    const detected = bundledPackage || configured;

    setPluginStatus(detected ? 'installed' : 'missing');
    setStatusMessage(
      detected
        ? configured
          ? `${channel.title}插件已安装`
          : `${channel.title}插件包已预置，点击安装写入配置`
        : `未检测到${channel.title}插件包，请重新打包`,
    );
    appendMainLog(`[${channel.title}] 插件检测：${detected ? '已预置/已安装' : '未检测到'}\n`);
    setChecking(false);
    return detected;
  }, [appendMainLog, channel]);

  useEffect(() => {
    checkPlugin().catch((error) => {
      setPluginStatus('error');
      setStatusMessage(`插件检测失败：${error?.message || error}`);
      setChecking(false);
    });
  }, [checkPlugin]);

  const spawnInstallStep = async (
    step: InstallStep,
    cwd: string | undefined,
    onCloseStep: (payload: TerminatedPayload) => void | Promise<void>,
  ) => {
    const options = makeCommandOptions(cwd);

    const attachListeners = (command: Command<string>) => {
      command.stdout.on('data', (data) => pushCommandLog(data));
      command.stderr.on('data', (data) => pushCommandLog(data));
      command.on('error', (error) => {
        setCommandRunning(false);
        setPluginStatus('error');
        setStatusMessage(`${step.label}启动失败：${error}`);
        pushCommandLog(`\n[error] ${error}\n`);
        showToast(`${step.label}启动失败`, 'error');
      });
      command.on('close', onCloseStep);
    };

    try {
      const command = Command.create(step.commandName, step.args, options);
      attachListeners(command);
      return await command.spawn();
    } catch (error) {
      pushCommandLog(`[fallback] ${step.commandName} 不可用，改用 ${step.fallbackCommandName}\n`);
      const fallback = Command.create(step.fallbackCommandName, step.args, options);
      attachListeners(fallback);
      return await fallback.spawn();
    }
  };

  const handleInstall = async () => {
    if (commandRunning) return;

    setCommandLog([]);
    setCommandRunning(true);
    stoppingRef.current = false;
    setStatusMessage('命令已启动，请在右侧查看实时输出');

    try {
      const cwd = await resolvePortableBasePath();

      const startStep = async (index: number): Promise<void> => {
        const step = channel.installSteps[index];
        setStatusMessage(`${step.label}运行中...`);
        pushCommandLog(`\n> ${step.displayCommand}\n`, false);

        const child = await spawnInstallStep(step, cwd, async (payload) => {
          childRef.current = null;
          pushCommandLog(`\n[exit] ${step.label} code=${payload.code ?? 'null'} signal=${payload.signal ?? 'null'}\n`);

          if (stoppingRef.current) {
            stoppingRef.current = false;
            setCommandRunning(false);
            setStatusMessage('命令已停止');
            return;
          }

          if (payload.code !== 0) {
            setCommandRunning(false);
            setPluginStatus('error');
            setStatusMessage(`${step.label}已退出，请查看右侧输出`);
            showToast(`${step.label}已退出，请查看输出`, 'error');
            return;
          }

          pushCommandLog(`[launcher] ${step.successMessage}\n`);
          const nextIndex = index + 1;

          if (nextIndex < channel.installSteps.length) {
            pushCommandLog('[launcher] 继续执行下一步，不会重启 OpenClaw 网关。\n');
            await startStep(nextIndex);
            return;
          }

          setCommandRunning(false);
          const detected = await checkPlugin();
          showToast(detected ? `${channel.title}安装流程完成` : '命令已结束，请确认扫码/绑定是否完成', detected ? 'success' : 'info');
        });

        childRef.current = child;
        pushCommandLog(`[launcher] ${step.label}已启动，PID ${child.pid}\n`);
        if (channel.key === 'weixin') {
          pushCommandLog('[launcher] 如果右侧出现二维码或网页登录链接，请直接扫码/打开链接完成绑定。\n');
        }
      };

      await startStep(0);
    } catch (error: any) {
      const message = error?.message || String(error);
      setCommandRunning(false);
      childRef.current = null;
      setPluginStatus('error');
      setStatusMessage(`安装失败：${message}`);
      pushCommandLog(`\n[launcher] 安装命令启动失败：${message}\n`);
      showToast(`${channel.title}安装失败：${message}`, 'error');
    }
  };

  const handleStopCommand = async () => {
    const child = childRef.current;
    if (!child) return;
    try {
      stoppingRef.current = true;
      await child.kill();
      pushCommandLog('\n[launcher] 已停止安装/绑定命令\n');
    } catch (error) {
      stoppingRef.current = false;
      pushCommandLog(`\n[launcher] 停止失败：${error}\n`);
    } finally {
      childRef.current = null;
      setCommandRunning(false);
    }
  };

  const handleSave = async () => {
    if (!idValue.trim() || !secretValue.trim()) {
      showToast(`请输入${channel.idLabel}和${channel.secretLabel}`, 'error');
      return;
    }

    try {
      const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {}).catch(() => ({ data: {} }));
      const data = (configResp.data as any) || {};
      data.channels = data.channels || {};

      const channelConfig = buildChannelConfig(channel, idValue.trim(), secretValue.trim());
      data.channels[channel.configKey] = channelConfig;
      if (channel.legacyConfigKey && channel.legacyConfigKey !== channel.configKey) {
        data.channels[channel.legacyConfigKey] = channelConfig;
      }

      const plugins = data.plugins || {};
      plugins.allow = Array.isArray(plugins.allow) ? plugins.allow : [];
      if (!plugins.allow.includes(channel.pluginName)) plugins.allow.push(channel.pluginName);
      plugins.entries = plugins.entries || {};
      plugins.entries[channel.pluginName] = { ...(plugins.entries[channel.pluginName] || {}), enabled: true };
      data.plugins = plugins;

      await configApi.write(OPENCLAW_CONFIG_PATH, data);
      appendMainLog(`[${channel.title}] 通道配置已保存\n`);
      showToast(`${channel.title}配置已保存，重启核心服务后生效`, 'success');
      onClose();
    } catch (error: any) {
      showToast(`保存失败：${error?.error || error}`, 'error');
    }
  };

  const statusClass = useMemo(() => {
    if (pluginStatus === 'installed') return 'text-status-success';
    if (pluginStatus === 'error') return 'text-status-danger';
    return 'text-status-warning';
  }, [pluginStatus]);

  if (checking && pluginStatus === 'unknown') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
        <div className="relative rounded-lg border border-border bg-surface/95 p-6 shadow-xl">
          <Loading text={statusMessage} />
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-5" onClick={onClose}>
      <div className="absolute inset-0 bg-black/72 backdrop-blur-sm" />
      <div
        className="relative grid max-h-[88vh] w-full max-w-5xl grid-cols-1 gap-5 overflow-hidden rounded-xl border border-border bg-surface/95 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.55),0_0_32px_rgba(37,99,235,0.14)] lg:grid-cols-[minmax(0,0.9fr)_minmax(360px,1.1fr)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="min-w-0 overflow-y-auto pr-1">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold text-text">{channel.title}</h2>
              <p className="mt-2 text-sm leading-6 text-text-muted">{channel.description}</p>
            </div>
            <button onClick={onClose} className="text-2xl leading-none text-text-muted hover:text-text">&times;</button>
          </div>

          <div className="mb-5 rounded-xl border border-border bg-surface-alt/85 p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className={`text-sm font-semibold ${statusClass}`}>{statusMessage}</p>
                <p className="mt-1 whitespace-pre-wrap break-all font-mono text-xs text-text-subtle">{commandSummary}</p>
              </div>
              <Button onClick={checkPlugin} variant="quiet" disabled={checking || commandRunning} className="shrink-0">
                重新检测
              </Button>
            </div>
          </div>

          <div className="mb-5 flex flex-wrap gap-3">
            <Button onClick={handleInstall} variant="primary" disabled={commandRunning}>
              {commandRunning ? '命令运行中...' : installed ? '重新执行安装/绑定' : `安装${channel.title}`}
            </Button>
            {commandRunning && (
              <Button onClick={handleStopCommand} variant="danger">
                停止命令
              </Button>
            )}
          </div>

          {channel.manualConfig ? (
            <div className="rounded-xl border border-border bg-surface-alt/70 p-4">
              <p className="text-sm font-semibold text-text">手动绑定配置</p>
              <p className="mt-1 text-xs leading-5 text-text-muted">
                安装插件后，填入开放平台中的应用信息即可写入 OpenClaw 配置。
              </p>
              {channel.docsUrl && (
                <a href={channel.docsUrl} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs font-medium text-accent hover:underline">
                  {channel.docsLabel}
                </a>
              )}

              <div className="mt-4 space-y-3">
                <div>
                  <FieldLabel text={channel.idLabel} />
                  <Input value={idValue} onChange={(event) => setIdValue(event.target.value)} placeholder={channel.idPlaceholder} />
                </div>
                <div>
                  <FieldLabel text={channel.secretLabel} />
                  <Input type="password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} placeholder={channel.secretPlaceholder} />
                </div>
                <div className="flex gap-3 pt-2">
                  <Button onClick={handleSave} variant="primary">保存配置</Button>
                  <Button onClick={onClose} variant="quiet">取消</Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-surface-alt/70 p-4">
              <p className="text-sm font-semibold text-text">扫码绑定</p>
              <p className="mt-1 text-xs leading-5 text-text-muted">
                微信机器人不支持输入 ID 和 Key 绑定。点击安装后，请在右侧命令行输出区扫描二维码，或按输出提示打开绑定链接。
              </p>
              <div className="mt-4 whitespace-pre-wrap rounded-lg border border-border bg-terminal-bg px-3 py-2 font-mono text-xs leading-5 text-terminal-text">
                {commandSummary}
              </div>
            </div>
          )}
        </div>

        <div className="flex min-h-[360px] min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-terminal-bg shadow-inner lg:min-h-[520px]">
          <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border bg-terminal-header px-4 py-3">
            <div className="min-w-0">
              <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-accent">Install Console</div>
              <div className="mt-1 whitespace-pre-wrap break-all font-mono text-xs text-text-subtle">{commandSummary}</div>
            </div>
            <button
              onClick={() => setCommandLog([])}
              className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition hover:bg-hover hover:text-text"
            >
              清空
            </button>
          </div>
          <pre
            ref={outputRef}
            className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words px-4 py-4 font-mono text-xs leading-5 text-terminal-text"
          >
            {hasCommandLog
              ? commandLog.join('')
              : '点击安装后，这里会实时显示命令行输出。\n如果输出二维码、验证码或登录链接，客户可以直接在这里扫码/复制。'}
          </pre>
        </div>
      </div>
    </div>
  );
};

export const FeishuConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => (
  <BotConfigDialog channel={CHANNELS.feishu} onClose={onClose} />
);

export const WeixinConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => (
  <BotConfigDialog channel={CHANNELS.weixin} onClose={onClose} />
);
