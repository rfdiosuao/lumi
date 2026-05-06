import React, { useState, useRef, useEffect } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { TerminalPage } from './components/terminal/TerminalPage';
import { LicensePage } from './components/license/LicensePage';
import { ImagePage } from './components/image/ImagePage';
import { VideoPage } from './components/video/VideoPage';
import { DiagnosticsPage } from './components/diagnostics/DiagnosticsPage';
import { ToastContainer, showToast } from './components/common';
import { useAppStore } from './stores/appStore';
import { useLogStore } from './stores/logStore';
import { processApi, logApi, updateApi, configApi } from './services/api';
import { open } from '@tauri-apps/plugin-shell';
import { ThemeProvider } from './providers/ThemeProvider';
import { useTheme } from './hooks/useTheme';

import { StoryboardPage } from './components/storyboard/StoryboardPage';
import { ApiConfigDialog as ModernApiConfigDialog } from './components/dialogs/ApiConfigDialog';
import { FeishuConfigDialog } from './components/dialogs/FeishuConfigDialog';

function DynamicTitle() {
  const { brandName, brandSubtitle } = useTheme();

  useEffect(() => {
    document.title = `${brandName} - ${brandSubtitle}`;
  }, [brandName, brandSubtitle]);

  return null;
}

const AUTH_PROFILES_PATH = 'data/.openclaw/agents/main/agent/auth-profiles.json';

function hasConfiguredApiProfile(data: unknown): boolean {
  const models = (data as any)?.models;
  const providers = models?.providers;
  if (!providers || typeof providers !== 'object') return false;

  return Object.values(providers).some((provider: any) => {
    const apiKey = String(provider?.apiKey || '').trim();
    const baseUrl = String(provider?.baseUrl || provider?.url || '').trim();
    return apiKey.length > 0 && baseUrl.length > 0;
  });
}


export default function App() {
  const { currentPage, setCurrentPage, serviceRunning, setServiceRunning, serviceStatus, setServiceStatus, isAuthorized, checkLicense } = useAppStore();
  const appendLog = useLogStore((s) => s.append);
  const [showApiConfig, setShowApiConfig] = useState(false);
  const [showFeishuConfig, setShowFeishuConfig] = useState(false);
  const [apiConfigured, setApiConfigured] = useState(false);
  const logInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshApiConfigured = React.useCallback(async () => {
    try {
      const resp = await configApi.read(AUTH_PROFILES_PATH, { models: { providers: {} } });
      setApiConfigured(hasConfiguredApiProfile(resp.data));
    } catch {
      setApiConfigured(false);
    }
  }, []);

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
    refreshApiConfigured();
  }, [checkLicense, refreshApiConfigured]);

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
      case 'diagnostics': return <DiagnosticsPage />;
      default: return <TerminalPage />;
    }
  };

  return (
    <ThemeProvider>
      <DynamicTitle />
      <div className="relative flex h-screen w-screen overflow-hidden bg-app-bg p-5">
        <div className="pointer-events-none absolute right-[-12%] top-[-18%] h-[46%] w-[42%] rounded-full bg-accent/15 blur-[120px]" />
        <div className="pointer-events-none absolute bottom-[-14%] left-[14%] h-[36%] w-[34%] rounded-full bg-cyan-500/10 blur-[110px]" />
        <div className="relative flex h-full w-full overflow-hidden rounded-2xl border border-white/10 bg-surface/70 shadow-[0_28px_90px_rgba(0,0,0,0.48)] backdrop-blur-xl">
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
          <main className="relative flex-1 overflow-hidden bg-surface/40">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/[0.04] to-transparent" />
            {renderPage()}
          </main>
        </div>

        <ToastContainer />
        {showApiConfig && <ModernApiConfigDialog onClose={() => setShowApiConfig(false)} onSaved={refreshApiConfigured} />}
        {showFeishuConfig && <FeishuConfigDialog onClose={() => setShowFeishuConfig(false)} />}
      </div>
    </ThemeProvider>
  );
}
