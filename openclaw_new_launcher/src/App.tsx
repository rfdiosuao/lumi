import React, { useState, useRef, useEffect } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { TerminalPage } from './components/terminal/TerminalPage';
import { LicensePage } from './components/license/LicensePage';
import { ImagePage } from './components/image/ImagePage';
import { VideoPage } from './components/video/VideoPage';
import { ToastContainer, showToast, Button, Input, FieldLabel, Loading } from './components/common';
import { useAppStore } from './stores/appStore';
import { useLogStore } from './stores/logStore';
import { processApi, logApi, updateApi, configApi } from './services/api';
import { open } from '@tauri-apps/plugin-shell';
import { ThemeProvider } from './providers/ThemeProvider';
import { useTheme } from './hooks/useTheme';

import { StoryboardPage } from './components/storyboard/StoryboardPage';

function DynamicTitle() {
  const { brandName, brandSubtitle } = useTheme();

  useEffect(() => {
    document.title = `${brandName} - ${brandSubtitle}`;
  }, [brandName, brandSubtitle]);

  return null;
}

// Dialog placeholders
const ApiConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [provider, setProvider] = useState('Heang AI');
  const [apiKey, setApiKey] = useState('');
  const [apiUrl, setApiUrl] = useState('');
  const [model, setModel] = useState('');
  const [saving, setSaving] = useState(false);

  const PROVIDERS: Record<string, { url: string; models: string[] }> = {
    'Heang AI': { url: 'https://api.heang.top/v1', models: ['kimi-k2.5', 'gpt-4o', 'gpt-4', 'gpt-3.5-turbo'] },
    'OpenAI': { url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo'] },
    'Claude': { url: 'https://api.anthropic.com/v1', models: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'] },
    'DeepSeek': { url: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-coder'] },
    '智谱AI': { url: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4', 'glm-4-flash'] },
    'Moonshot': { url: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k'] },
    '自定义': { url: '', models: [] },
  };

  useEffect(() => {
    const p = PROVIDERS[provider];
    if (p) {
      setApiUrl(p.url);
      setModel(p.models[0] || '');
    }
  }, [provider]);

  const handleSave = async () => {
    if (!apiKey) { showToast('请输入 API Key', 'error'); return; }
    setSaving(true);
    try {
      const modelIds = Array.from(new Set([model, 'qwen3.6-plus', 'claude-opus-4-7-medium', 'kimi-k2.5', 'gpt-4o'].filter(Boolean)));
      const providerId = (() => {
        try {
          const url = new URL(apiUrl.includes('://') ? apiUrl : `https://${apiUrl}`);
          const host = url.hostname.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
          return `custom-${host || 'api'}`;
        } catch {
          return `custom-${provider.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'api'}`;
        }
      })();
      const modelRef = `${providerId}/${model}`;
      const providerConfig = {
        baseUrl: apiUrl.replace(/\/+$/, ''),
        apiKey,
        api: 'openai-completions',
        models: modelIds.map((id) => ({
          id,
          name: `${id} (Custom Provider)`,
          reasoning: id.startsWith('claude') || id.startsWith('qwen3') || id.startsWith('o1') || id.startsWith('o3') || id.startsWith('o4'),
          input: ['text'],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: id.startsWith('qwen3') ? 16000000 : id.startsWith('claude') ? 200000 : 128000,
          maxTokens: id.startsWith('qwen3') ? 4096000 : 32000,
          api: 'openai-completions',
        })),
      };

      // Write to auth-profiles
      const profileKey = provider === '自定义' ? 'custom' : provider.toLowerCase().replace(/\s+/g, '_');
      const profiles = await configApi.read('data/.openclaw/agents/main/agent/auth-profiles.json', { models: { providers: {} } });
      const data = profiles.data as any;
      if (!data.models) data.models = { providers: {} };
      if (!data.models.providers) data.models.providers = {};
      data.models.providers[profileKey] = {
        id: profileKey,
        name: provider,
        baseUrl: apiUrl,
        apiKey,
        models: [model],
      };
      data.models.primary = profileKey;
      await configApi.write('data/.openclaw/agents/main/agent/auth-profiles.json', data);

      // Write to OpenClaw 2026.5+ model catalog
      const modelCatalog = await configApi.read('data/.openclaw/agents/main/agent/models.json', { providers: {} });
      const catalog = modelCatalog.data as any;
      if (!catalog.providers) catalog.providers = {};
      catalog.providers[providerId] = providerConfig;
      await configApi.write('data/.openclaw/agents/main/agent/models.json', catalog);

      // Write to openclaw.json
      const ocConfig = await configApi.read('data/.openclaw/openclaw.json', { plugins: {} });
      const oc = ocConfig.data as any;
      if (!oc.models) oc.models = { mode: 'merge', providers: {} };
      oc.models.mode = 'merge';
      if (!oc.models.providers) oc.models.providers = {};
      oc.models.providers[providerId] = providerConfig;
      if (!oc.agents) oc.agents = { defaults: {} };
      if (!oc.agents.defaults) oc.agents.defaults = {};
      oc.agents.defaults.model = { primary: modelRef };
      if (!oc.agents.defaults.models) oc.agents.defaults.models = {};
      oc.agents.defaults.models[modelRef] = { alias: model };
      await configApi.write('data/.openclaw/openclaw.json', oc);

      showToast('配置已保存', 'success');
      onClose();
    } catch (e: any) {
      showToast('保存失败: ' + (e?.error || e), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative bg-surface rounded-lg shadow-xl w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-text">API 配置</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text text-xl">&times;</button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-text-muted mb-1 block">提供商</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full px-3 py-2 rounded-md border border-border bg-surface-alt text-text text-sm focus:outline-none focus:ring-2 focus:ring-accent">
              {Object.keys(PROVIDERS).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm text-text-muted mb-1 block">API 地址</label>
            <input value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} className="w-full px-3 py-2 rounded-md border border-border bg-surface-alt text-text text-sm focus:outline-none focus:ring-2 focus:ring-accent" />
          </div>
          <div>
            <label className="text-sm text-text-muted mb-1 block">API Key</label>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className="w-full px-3 py-2 rounded-md border border-border bg-surface-alt text-text text-sm focus:outline-none focus:ring-2 focus:ring-accent" />
          </div>
          <div>
            <label className="text-sm text-text-muted mb-1 block">模型</label>
            <select value={model} onChange={(e) => setModel(e.target.value)} className="w-full px-3 py-2 rounded-md border border-border bg-surface-alt text-text text-sm focus:outline-none focus:ring-2 focus:ring-accent">
              {PROVIDERS[provider].models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="flex gap-3">
            <button onClick={handleSave} disabled={saving} className="px-4 py-2 bg-accent hover:bg-accent-hover text-white rounded-md text-sm font-medium disabled:opacity-50 cursor-pointer">
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const FeishuConfigDialog: React.FC<{ onClose: () => void }> = ({ onClose }) => {
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
  }, []);

  const handleInstall = async () => {
    setInstalling(true);
    appendLog('[飞书] 正在安装飞书插件...\n');
    try {
      // Clear old lark config
      const configResp = await configApi.read('data/.openclaw/openclaw.json', {});
      const data = configResp.data as any;
      const plugins = data.plugins || {};
      if (plugins.entries && plugins.entries['openclaw-lark']) delete plugins.entries['openclaw-lark'];
      if (plugins.allow) plugins.allow = plugins.allow.filter((p: string) => p !== 'openclaw-lark');
      await configApi.write('data/.openclaw/openclaw.json', data);
      appendLog('[飞书] 已清理旧配置残留\n');
    } catch (e) {
      appendLog('[飞书] 清理旧配置失败: ' + e + '\n');
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

  if (checking) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative bg-surface rounded-lg shadow-xl p-6"><Loading /></div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative bg-surface rounded-lg shadow-xl w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-text">飞书机器人</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text text-xl">&times;</button>
        </div>
        <p className="text-sm text-text-muted mb-4">安装插件并写入飞书通道配置。</p>

        {/* Status Card */}
        <div className="bg-surface-alt rounded-lg border border-border p-4 mb-4">
          {pluginInstalled && appId ? (
            <p className="text-sm text-status-success">飞书已配置<br/>App ID: {appId}</p>
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
            <p className="text-xs text-text-muted mt-2">安装会打开一个命令窗口显示进度，完成后重新进入此弹窗即可配置。</p>
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
                <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="●●●●●●" />
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

export default function App() {
  const { currentPage, setCurrentPage, serviceRunning, setServiceRunning, serviceStatus, setServiceStatus, isAuthorized, checkLicense } = useAppStore();
  const appendLog = useLogStore((s) => s.append);
  const [showApiConfig, setShowApiConfig] = useState(false);
  const [showFeishuConfig, setShowFeishuConfig] = useState(false);
  const [apiConfigured] = useState(false);
  const logInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll logs periodically
  const startLogPolling = () => {
    if (logInterval.current) return;
    logInterval.current = setInterval(async () => {
      try {
        const resp = await logApi.get();
        if (resp.log) {
          appendLog(resp.log);
        }
      } catch (e) {
        appendLog('[日志轮询] 错误: ' + e + '\n');
      }
    }, 1000);
  };

  const stopLogPolling = () => {
    if (logInterval.current) {
      clearInterval(logInterval.current);
      logInterval.current = null;
    }
  };

  useEffect(() => {
    checkLicense();
  }, [checkLicense]);

  const handleStart = async () => {
    if (!isAuthorized) {
      showToast('请先完成授权', 'error');
      setCurrentPage('license');
      return;
    }
    setServiceStatus('starting');
    try {
      await processApi.start();
      setServiceRunning(true);
      setServiceStatus('running');
      appendLog('[服务] 启动成功\n');
      showToast('服务已启动', 'success');
      startLogPolling();

      // Auto-open web after 3s
      setTimeout(() => open('http://127.0.0.1:18790'), 3000);
    } catch (e: any) {
      setServiceStatus('idle');
      showToast('启动失败: ' + (e?.error || e), 'error');
    }
  };

  const handleStop = async () => {
    setServiceStatus('stopping');
    try {
      await processApi.stop();
      setServiceRunning(false);
      setServiceStatus('idle');
      stopLogPolling();
      showToast('服务已停止', 'info');
    } catch (e: any) {
      setServiceStatus('idle');
      showToast('停止失败', 'error');
    }
  };

  const handleNavigate = async (key: string) => {
    // Protected pages
    if (['storyboard', 'image', 'video'].includes(key) && !isAuthorized) {
      showToast('请先输入授权码完成在线激活', 'info');
      setCurrentPage('license');
      return;
    }

    if (key === 'web') {
      open('http://127.0.0.1:18790');
      return;
    }
    if (key === 'update') {
      try {
        const resp = await updateApi.check();
        if (resp.hasUpdate) {
          showToast(`发现新版本: ${resp.current} → ${resp.latest}`, 'info');
          if (confirm(`当前: ${resp.current}\n最新: ${resp.latest}\n是否更新？`)) {
            appendLog('[更新] 开始更新...\n');
            const updateResp = await updateApi.do();
            if (updateResp.success) {
              showToast(`更新成功: ${updateResp.current_version}`, 'success');
            } else {
              showToast('更新失败', 'error');
            }
          }
        } else {
          showToast(`已是最新版本: ${resp.current}`, 'info');
        }
      } catch (e: any) {
        showToast('检查更新失败', 'error');
      }
      return;
    }
    if (key === 'help') {
      open('https://heang.top/docs.html');
      return;
    }
    if (key === 'api') {
      setShowApiConfig(true);
      return;
    }
    if (key === 'feishu') {
      setShowFeishuConfig(true);
      return;
    }

    setCurrentPage(key);
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'terminal': return <TerminalPage />;
      case 'license': return <LicensePage />;
      case 'image': return <ImagePage />;
      case 'video': return <VideoPage />;
      case 'storyboard': return <StoryboardPage />;
      default: return <TerminalPage />;
    }
  };

  return (
    <ThemeProvider>
      <DynamicTitle />
      <div className="h-screen w-screen bg-app-bg flex overflow-hidden">
        <div className="flex w-full h-full m-5 rounded-xl overflow-hidden border border-border shadow-lg">
          <Sidebar
            activePage={currentPage}
            serviceRunning={serviceRunning}
            serviceStatus={serviceStatus}
            isAuthorized={isAuthorized}
            isApiConfigured={apiConfigured}
            onNavigate={handleNavigate}
            onStart={handleStart}
            onStop={handleStop}
          />
          <div className="flex-1 overflow-hidden">
            {renderPage()}
          </div>
        </div>

        <ToastContainer />
        {showApiConfig && <ApiConfigDialog onClose={() => setShowApiConfig(false)} />}
        {showFeishuConfig && <FeishuConfigDialog onClose={() => setShowFeishuConfig(false)} />}
      </div>
    </ThemeProvider>
  );
}
