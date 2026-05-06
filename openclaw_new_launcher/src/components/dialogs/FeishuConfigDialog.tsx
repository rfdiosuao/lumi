import React, { useState } from 'react';
import { Button, FieldLabel, Input, Loading, showToast } from '../common';
import { configApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

export const FeishuConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [appId, setAppId] = useState('');
  const [secret, setSecret] = useState('');
  const [pluginInstalled, setPluginInstalled] = useState(false);
  const [checking, setChecking] = useState(true);
  const [installing, setInstalling] = useState(false);
  const appendLog = useLogStore((s) => s.append);

  React.useEffect(() => {
    (async () => {
      try {
        const [pluginResp, configResp] = await Promise.all([
          configApi.read('data/.openclaw/extensions/openclaw-lark/package.json', null),
          configApi.read('data/.openclaw/openclaw.json', {}),
        ]);
        const data = configResp.data as any;
        setPluginInstalled(pluginResp.data !== null);
        const feishu = data?.channels?.feishu;
        if (feishu) {
          setAppId(feishu.appId || '');
        }
      } catch (e) {
        appendLog('[飞书] 配置加载失败: ' + e + '\n');
      }
      setChecking(false);
    })();
  }, [appendLog]);

  const handleInstall = async () => {
    setInstalling(true);
    appendLog('[飞书] 正在安装飞书插件...\n');
    try {
      const configResp = await configApi.read('data/.openclaw/openclaw.json', {});
      const data = configResp.data as any;
      const plugins = data.plugins || {};
      if (plugins.entries && plugins.entries['openclaw-lark']) delete plugins.entries['openclaw-lark'];
      if (plugins.allow) plugins.allow = plugins.allow.filter((p: string) => p !== 'openclaw-lark');
      await configApi.write('data/.openclaw/openclaw.json', data);
      appendLog('[飞书] 已清理旧配置残留\n');
    } catch (e) {
      appendLog('[飞书] 清理旧配置失败: ' + e + '\n');
    } finally {
      setInstalling(false);
    }

    showToast('请先在命令行运行: npx -y @larksuite/openclaw-lark install', 'info');
    appendLog('[飞书] 请在终端执行: npx -y @larksuite/openclaw-lark install\n');
  };

  const handleSave = async () => {
    if (!appId || !secret) {
      showToast('请输入 App ID 和 App Secret', 'error');
      return;
    }

    try {
      const configResp = await configApi.read('data/.openclaw/openclaw.json', {});
      const data = configResp.data as any;
      data.channels = data.channels || {};
      data.channels.feishu = {
        enabled: true,
        appId,
        appSecret: secret,
        domain: 'feishu',
        connectionMode: 'websocket',
        requireMention: true,
        dmPolicy: 'open',
        groupPolicy: 'open',
        streaming: true,
      };

      const plugins = data.plugins || {};
      if (!plugins.allow) plugins.allow = [];
      if (!plugins.allow.includes('openclaw-lark')) plugins.allow.push('openclaw-lark');
      plugins.entries = plugins.entries || {};
      plugins.entries['openclaw-lark'] = { enabled: true };
      data.plugins = plugins;
      await configApi.write('data/.openclaw/openclaw.json', data);

      showToast('飞书配置已保存', 'success');
      onClose();
    } catch (e: any) {
      showToast('保存失败: ' + (e?.error || e), 'error');
    }
  };

  if (checking) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div className="absolute inset-0 bg-black/40" />
        <div className="relative bg-surface rounded-lg shadow-xl p-6"><Loading /></div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative bg-surface rounded-lg shadow-xl w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-text">飞书机器人</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text text-xl">&times;</button>
        </div>
        <p className="text-sm text-text-muted mb-4">安装插件并写入飞书通道配置。</p>

        <div className="bg-surface-alt rounded-lg border border-border p-4 mb-4">
          {pluginInstalled && appId ? (
            <p className="text-sm text-status-success">飞书已配置<br />App ID: {appId}</p>
          ) : pluginInstalled ? (
            <p className="text-sm text-status-warning">插件已安装，尚未填写应用信息</p>
          ) : (
            <p className="text-sm text-status-warning">飞书插件未安装</p>
          )}
        </div>

        {!pluginInstalled ? (
          <>
            <Button onClick={handleInstall} variant="primary" disabled={installing}>
              {installing ? '安装中...' : '安装飞书插件'}
            </Button>
            <p className="text-xs text-text-muted mt-2">安装会打开命令行显示进度，完成后重新进入此弹窗即可配置。</p>
          </>
        ) : (
          <>
            <p className="text-xs text-text-subtle font-medium mb-2">应用信息</p>
            <p className="text-xs text-text-muted mb-2">在飞书开放平台创建应用后复制 App ID 和 Secret。</p>
            <a href="https://open.feishu.cn/app" target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline block mb-4">打开飞书开放平台</a>

            <div className="space-y-3">
              <div>
                <FieldLabel text="App ID" />
                <Input value={appId} onChange={(e) => setAppId(e.target.value)} placeholder="cli_xxx" />
              </div>
              <div>
                <FieldLabel text="App Secret" />
                <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="******" />
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
