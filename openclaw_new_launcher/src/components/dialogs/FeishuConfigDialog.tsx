import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Command, type Child, type TerminatedPayload } from '@tauri-apps/plugin-shell';
import { Button, FieldLabel, Input, Loading, showToast } from '../common';
import { configApi, systemApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const OPENCLAW_CONFIG_PATH = 'data/.openclaw/openclaw.json';

type PluginStatus = 'unknown' | 'installed' | 'missing' | 'error';
type BotChannelKey = 'feishu' | 'weixin';

interface BotChannel {
  key: BotChannelKey;
  title: string;
  description: string;
  pluginName: string;
  packagePaths: string[];
  installCommand: string;
  commandName: string;
  fallbackCommandName: string;
  installArgs: string[];
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
    title: '飞书机器人',
    description: '安装 OpenClaw 飞书插件，并写入飞书开放平台应用配置。',
    pluginName: 'openclaw-lark',
    packagePaths: [
      'data/.openclaw/extensions/openclaw-lark/package.json',
      'data/.openclaw/extensions/lark/package.json',
    ],
    installCommand: 'npx -y @larksuite/openclaw-lark install',
    commandName: 'install-openclaw-lark',
    fallbackCommandName: 'install-openclaw-lark-cmd',
    installArgs: ['-y', '@larksuite/openclaw-lark', 'install'],
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
    title: '微信机器人',
    description: '安装 OpenClaw 微信绑定插件。微信绑定只能通过命令行输出中的二维码扫码完成。',
    pluginName: 'openclaw-weixin',
    packagePaths: [
      'data/.openclaw/extensions/openclaw-weixin/package.json',
      'data/.openclaw/extensions/weixin/package.json',
      'data/.openclaw/extensions/wechat/package.json',
    ],
    installCommand: 'npx -y @tencent-weixin/openclaw-weixin-cli@latest install',
    commandName: 'install-openclaw-weixin',
    fallbackCommandName: 'install-openclaw-weixin-cmd',
    installArgs: ['-y', '@tencent-weixin/openclaw-weixin-cli@latest', 'install'],
    idLabel: '',
    idPlaceholder: '',
    secretLabel: '',
    secretPlaceholder: '',
    manualConfig: false,
  },
};

function isInstalledPackage(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  const pkg = data as { name?: unknown };
  return typeof pkg.name === 'string' && pkg.name.length > 0;
}

function stripAnsi(text: string): string {
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '');
}

function normalizeCommandOutput(data: unknown): string {
  if (typeof data === 'string') return stripAnsi(data);
  if (data instanceof Uint8Array) return new TextDecoder('utf-8').decode(data);
  return stripAnsi(String(data ?? ''));
}

function buildChannelConfig(channel: BotChannel, idValue: string, secretValue: string) {
  if (channel.key === 'weixin') {
    return {
      enabled: true,
      robotId: idValue,
      robotKey: secretValue,
      key: secretValue,
      appId: idValue,
      appSecret: secretValue,
      domain: 'weixin',
      connectionMode: 'websocket',
      requireMention: false,
      dmPolicy: 'open',
      groupPolicy: 'open',
      streaming: true,
    };
  }

  return {
    enabled: true,
    appId: idValue,
    appSecret: secretValue,
    domain: 'feishu',
    connectionMode: 'websocket',
    requireMention: true,
    dmPolicy: 'open',
    groupPolicy: 'open',
    streaming: true,
  };
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
  const appendMainLog = useLogStore((s) => s.append);

  const installed = pluginStatus === 'installed';
  const hasCommandLog = commandLog.length > 0;

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
    try {
      const [configResp, ...packageResponses] = await Promise.all([
        configApi.read(OPENCLAW_CONFIG_PATH, {}),
        ...channel.packagePaths.map((path) => configApi.read(path, null).catch(() => ({ data: null }))),
      ]);

      const config = (configResp.data as any) || {};
      const savedChannel = config?.channels?.[channel.key];
      if (savedChannel?.appId || savedChannel?.robotId) {
        setIdValue(String(savedChannel.appId || savedChannel.robotId));
      }

      const detected = packageResponses.some((resp) => isInstalledPackage(resp.data));
      setPluginStatus(detected ? 'installed' : 'missing');
      setStatusMessage(detected ? `${channel.title}插件已安装` : `未检测到${channel.title}插件`);
      appendMainLog(`[${channel.title}] 插件检测：${detected ? '已安装' : '未安装'}\n`);
      return detected;
    } catch (error) {
      setPluginStatus('error');
      setStatusMessage('插件检测失败，请查看服务日志');
      appendMainLog(`[${channel.title}] 插件检测失败：${error}\n`);
      return false;
    } finally {
      setChecking(false);
    }
  }, [appendMainLog, channel]);

  useEffect(() => {
    checkPlugin();
  }, [checkPlugin]);

  const cleanupOldConfig = async () => {
    const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {});
    const data = (configResp.data as any) || {};
    const plugins = data.plugins || {};

    if (plugins.entries?.[channel.pluginName]) {
      delete plugins.entries[channel.pluginName];
    }
    if (Array.isArray(plugins.allow)) {
      plugins.allow = plugins.allow.filter((name: string) => name !== channel.pluginName);
    }

    data.plugins = plugins;
    await configApi.write(OPENCLAW_CONFIG_PATH, data);
  };

  const spawnCommand = async (cwd?: string) => {
    const options = cwd ? { cwd, encoding: 'utf-8' as const } : { encoding: 'utf-8' as const };

    const attachListeners = (command: Command<string>) => {
      command.stdout.on('data', (data) => pushCommandLog(data));
      command.stderr.on('data', (data) => pushCommandLog(data));
      command.on('error', (error) => {
        setCommandRunning(false);
        setPluginStatus('error');
        setStatusMessage(`安装命令启动失败：${error}`);
        pushCommandLog(`\n[error] ${error}\n`);
        showToast(`${channel.title}安装命令启动失败`, 'error');
      });
      command.on('close', async (payload: TerminatedPayload) => {
        setCommandRunning(false);
        childRef.current = null;
        pushCommandLog(`\n[exit] code=${payload.code ?? 'null'} signal=${payload.signal ?? 'null'}\n`);
        const detected = await checkPlugin();
        if (payload.code === 0 && detected) {
          showToast(`${channel.title}插件安装完成`, 'success');
        } else if (payload.code === 0) {
          showToast('命令已结束，请确认扫码/绑定是否完成后重新检测', 'info');
        } else {
          showToast(`${channel.title}安装命令已退出，请查看输出`, 'error');
        }
      });
    };

    try {
      const command = Command.create(channel.commandName, channel.installArgs, options);
      attachListeners(command);
      return await command.spawn();
    } catch (error) {
      const message = String(error || '');
      if (!message.toLowerCase().includes('not found') && !message.toLowerCase().includes('denied')) {
        throw error;
      }
      pushCommandLog(`[fallback] ${channel.commandName} 不可用，改用 ${channel.fallbackCommandName}\n`);
      const fallback = Command.create(channel.fallbackCommandName, channel.installArgs, options);
      attachListeners(fallback);
      return await fallback.spawn();
    }
  };

  const handleInstall = async () => {
    if (commandRunning) return;

    setCommandLog([]);
    setCommandRunning(true);
    setStatusMessage('安装命令已启动，请在下方查看二维码或链接输出');
    pushCommandLog(`> ${channel.installCommand}\n`, false);

    try {
      await cleanupOldConfig();
      pushCommandLog('[launcher] 已清理旧插件配置残留\n');

      const systemInfo = await systemApi.info().catch(() => null);
      const child = await spawnCommand(systemInfo?.base_path);
      childRef.current = child;
      pushCommandLog(`[launcher] 命令已启动，PID ${child.pid}\n`);
      pushCommandLog('[launcher] 如果这里出现二维码或网页登录链接，请直接扫码/打开链接完成绑定。\n');
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
      await child.kill();
      pushCommandLog('\n[launcher] 已停止安装命令\n');
    } catch (error) {
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
      const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {});
      const data = (configResp.data as any) || {};
      data.channels = data.channels || {};
      data.channels[channel.key] = buildChannelConfig(channel, idValue.trim(), secretValue.trim());

      const plugins = data.plugins || {};
      plugins.allow = Array.isArray(plugins.allow) ? plugins.allow : [];
      if (!plugins.allow.includes(channel.pluginName)) plugins.allow.push(channel.pluginName);
      plugins.entries = plugins.entries || {};
      plugins.entries[channel.pluginName] = { enabled: true };
      data.plugins = plugins;

      await configApi.write(OPENCLAW_CONFIG_PATH, data);
      appendMainLog(`[${channel.title}] 通道配置已保存\n`);
      showToast(`${channel.title}配置已保存`, 'success');
      onClose();
    } catch (error: any) {
      showToast('保存失败：' + (error?.error || error), 'error');
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
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
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
                <p className="mt-1 break-all font-mono text-xs text-text-subtle">{channel.installCommand}</p>
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
              <div className="mt-4 rounded-lg border border-border bg-terminal-bg px-3 py-2 font-mono text-xs leading-5 text-terminal-text">
                {channel.installCommand}
              </div>
            </div>
          )}
        </div>

        <div className="flex min-h-[360px] min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-terminal-bg shadow-inner lg:min-h-[520px]">
          <div className="flex shrink-0 items-center justify-between border-b border-border bg-terminal-header px-4 py-3">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-accent">Install Console</div>
              <div className="mt-1 font-mono text-xs text-text-subtle">{channel.installCommand}</div>
            </div>
            <button
              onClick={() => setCommandLog([])}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-muted transition hover:bg-hover hover:text-text"
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
              : '点击安装后，这里会实时显示命令行输出。\n如果安装器输出二维码、验证码或登录链接，客户可以直接在这里扫码/复制。'}
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
