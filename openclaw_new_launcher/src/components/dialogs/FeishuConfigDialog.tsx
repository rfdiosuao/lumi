import React, { useCallback, useState } from 'react';
import { Command } from '@tauri-apps/plugin-shell';
import { Button, FieldLabel, Input, Loading, showToast } from '../common';
import { configApi, systemApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const LARK_PACKAGE_PATH = 'data/.openclaw/extensions/openclaw-lark/package.json';
const OPENCLAW_CONFIG_PATH = 'data/.openclaw/openclaw.json';
const INSTALL_ARGS = ['-y', '@larksuite/openclaw-lark', 'install'];

type PluginStatus = 'unknown' | 'installed' | 'missing' | 'error';

function isInstalledPackage(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  const pkg = data as { name?: unknown };
  return typeof pkg.name === 'string' && pkg.name.length > 0;
}

async function runInstallCommand(cwd?: string) {
  const options = cwd ? { cwd, encoding: 'utf-8' as const } : { encoding: 'utf-8' as const };

  try {
    return await Command.create('install-openclaw-lark', INSTALL_ARGS, options).execute();
  } catch (error) {
    const message = String(error || '');
    if (!message.toLowerCase().includes('not found') && !message.toLowerCase().includes('denied')) {
      throw error;
    }
    return await Command.create('install-openclaw-lark-cmd', INSTALL_ARGS, options).execute();
  }
}

export const FeishuConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [appId, setAppId] = useState('');
  const [secret, setSecret] = useState('');
  const [pluginStatus, setPluginStatus] = useState<PluginStatus>('unknown');
  const [checking, setChecking] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [statusMessage, setStatusMessage] = useState('正在检测飞书插件...');
  const appendLog = useLogStore((s) => s.append);

  const checkPlugin = useCallback(async () => {
    setChecking(true);
    setStatusMessage('正在检测飞书插件...');
    try {
      const [pluginResp, configResp] = await Promise.all([
        configApi.read(LARK_PACKAGE_PATH, null),
        configApi.read(OPENCLAW_CONFIG_PATH, {}),
      ]);

      const config = configResp.data as any;
      const feishu = config?.channels?.feishu;
      if (feishu?.appId) setAppId(feishu.appId);

      const installed = isInstalledPackage(pluginResp.data);
      setPluginStatus(installed ? 'installed' : 'missing');
      setStatusMessage(installed ? '飞书插件已安装' : '未检测到飞书插件');
      appendLog(`[飞书] 插件检测：${installed ? '已安装' : '未安装'}\n`);
      return installed;
    } catch (error) {
      setPluginStatus('error');
      setStatusMessage('插件检测失败，请查看服务日志');
      appendLog(`[飞书] 插件检测失败：${error}\n`);
      return false;
    } finally {
      setChecking(false);
    }
  }, [appendLog]);

  React.useEffect(() => {
    checkPlugin();
  }, [checkPlugin]);

  const cleanupOldConfig = async () => {
    const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {});
    const data = (configResp.data as any) || {};
    const plugins = data.plugins || {};

    if (plugins.entries?.['openclaw-lark']) {
      delete plugins.entries['openclaw-lark'];
    }
    if (Array.isArray(plugins.allow)) {
      plugins.allow = plugins.allow.filter((name: string) => name !== 'openclaw-lark');
    }

    data.plugins = plugins;
    await configApi.write(OPENCLAW_CONFIG_PATH, data);
  };

  const handleInstall = async () => {
    setInstalling(true);
    setStatusMessage('正在安装飞书插件...');
    appendLog(`[飞书] 执行安装命令：npx ${INSTALL_ARGS.join(' ')}\n`);

    try {
      await cleanupOldConfig();
      appendLog('[飞书] 已清理旧插件配置残留\n');

      const systemInfo = await systemApi.info().catch(() => null);
      const output = await runInstallCommand(systemInfo?.base_path);
      if (output.stdout) appendLog(`[飞书] ${String(output.stdout).trim()}\n`);
      if (output.stderr) appendLog(`[飞书] ${String(output.stderr).trim()}\n`);

      if (output.code !== 0) {
        throw new Error(`安装命令退出码：${output.code}`);
      }

      const installed = await checkPlugin();
      if (!installed) {
        throw new Error('安装命令已完成，但未找到 openclaw-lark/package.json');
      }

      showToast('飞书插件安装完成', 'success');
    } catch (error: any) {
      const message = error?.message || String(error);
      setPluginStatus('error');
      setStatusMessage(`安装失败：${message}`);
      appendLog(`[飞书] 插件安装失败：${message}\n`);
      showToast(`飞书插件安装失败：${message}`, 'error');
    } finally {
      setInstalling(false);
    }
  };

  const handleSave = async () => {
    if (pluginStatus !== 'installed') {
      showToast('请先安装飞书插件', 'error');
      return;
    }
    if (!appId.trim() || !secret.trim()) {
      showToast('请输入 App ID 和 App Secret', 'error');
      return;
    }

    try {
      const configResp = await configApi.read(OPENCLAW_CONFIG_PATH, {});
      const data = (configResp.data as any) || {};
      data.channels = data.channels || {};
      data.channels.feishu = {
        enabled: true,
        appId: appId.trim(),
        appSecret: secret.trim(),
        domain: 'feishu',
        connectionMode: 'websocket',
        requireMention: true,
        dmPolicy: 'open',
        groupPolicy: 'open',
        streaming: true,
      };

      const plugins = data.plugins || {};
      plugins.allow = Array.isArray(plugins.allow) ? plugins.allow : [];
      if (!plugins.allow.includes('openclaw-lark')) plugins.allow.push('openclaw-lark');
      plugins.entries = plugins.entries || {};
      plugins.entries['openclaw-lark'] = { enabled: true };
      data.plugins = plugins;

      await configApi.write(OPENCLAW_CONFIG_PATH, data);
      appendLog('[飞书] 飞书通道配置已保存\n');
      showToast('飞书配置已保存', 'success');
      onClose();
    } catch (error: any) {
      showToast('保存失败：' + (error?.error || error), 'error');
    }
  };

  if (checking) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
        <div className="relative rounded-lg border border-border bg-surface/95 p-6 shadow-xl">
          <Loading text={statusMessage} />
        </div>
      </div>
    );
  }

  const installed = pluginStatus === 'installed';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative mx-4 max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg border border-border bg-surface/95 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.55),0_0_32px_rgba(157,78,221,0.16)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text">飞书机器人</h2>
          <button onClick={onClose} className="text-xl text-text-muted hover:text-text">&times;</button>
        </div>
        <p className="mb-4 text-sm text-text-muted">自动检测并安装 OpenClaw 飞书插件，然后写入飞书通道配置。</p>

        <div className="mb-4 rounded-lg border border-border bg-surface-alt/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className={`text-sm font-semibold ${installed ? 'text-status-success' : 'text-status-warning'}`}>
                {statusMessage}
              </p>
              <p className="mt-1 font-mono text-xs text-text-subtle">npx -y @larksuite/openclaw-lark install</p>
            </div>
            <Button onClick={checkPlugin} variant="quiet" disabled={checking || installing}>
              重新检测
            </Button>
          </div>
        </div>

        {!installed ? (
          <>
            <Button onClick={handleInstall} variant="primary" disabled={installing}>
              {installing ? '安装中...' : '安装飞书插件'}
            </Button>
            <p className="mt-2 text-xs text-text-muted">
              点击后会自动执行安装命令，安装完成后会再次检测插件目录。
            </p>
          </>
        ) : (
          <>
            <p className="mb-2 text-xs font-medium text-text-subtle">应用信息</p>
            <p className="mb-2 text-xs text-text-muted">在飞书开放平台创建应用后，复制 App ID 和 App Secret。</p>
            <a href="https://open.feishu.cn/app" target="_blank" rel="noreferrer" className="mb-4 block text-xs text-accent hover:underline">
              打开飞书开放平台
            </a>

            <div className="space-y-3">
              <div>
                <FieldLabel text="App ID" />
                <Input value={appId} onChange={(event) => setAppId(event.target.value)} placeholder="cli_xxx" />
              </div>
              <div>
                <FieldLabel text="App Secret" />
                <Input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="******" />
              </div>
              <div className="flex gap-3 pt-2">
                <Button onClick={handleSave} variant="primary">保存配置</Button>
                <Button onClick={onClose} variant="quiet">取消</Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
