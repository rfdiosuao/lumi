import React, { useEffect, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-shell';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { Sidebar } from './components/sidebar/Sidebar';
import { WindowTitlebar } from './components/window/WindowTitlebar';
import { ToastContainer, showToast } from './components/common';
import { useAppStore } from './stores/appStore';
import { useLogStore } from './stores/logStore';
import { processApi, logApi, updateApi, configApi } from './services/api';
import { ThemeProvider } from './providers/ThemeProvider';
import { useTheme } from './hooks/useTheme';
import { getFeatureDefinition } from './features/registry';
import { renderFeaturePage } from './features/pages';
import { ApiConfigDialog as ModernApiConfigDialog } from './components/dialogs/ApiConfigDialog';
import { FeishuConfigDialog, WeixinConfigDialog } from './components/dialogs/FeishuConfigDialog';

function DynamicTitle() {
  const { windowTitle } = useTheme();

  useEffect(() => {
    document.title = windowTitle;
    getCurrentWindow().setTitle(windowTitle).catch(() => {});
  }, [windowTitle]);

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
  const {
    currentPage,
    setCurrentPage,
    serviceRunning,
    setServiceRunning,
    serviceStatus,
    setServiceStatus,
    isAuthorized,
    isLicenseChecking,
    checkLicense,
  } = useAppStore();
  const appendLog = useLogStore((s) => s.append);
  const [activeDialog, setActiveDialog] = useState<'api' | 'feishu' | 'weixin' | null>(null);
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

  const startLogPolling = () => {
    if (logInterval.current) return;
    logInterval.current = setInterval(async () => {
      try {
        const resp = await logApi.get();
        if (resp.log) {
          appendLog(resp.log);
        }
      } catch (error) {
        appendLog(`[日志轮询] 错误: ${error}\n`);
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

  useEffect(() => {
    if (!isLicenseChecking && !isAuthorized && !['license', 'diagnostics'].includes(currentPage)) {
      setCurrentPage('license');
    }
  }, [currentPage, isAuthorized, isLicenseChecking, setCurrentPage]);

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
      setTimeout(() => open('http://127.0.0.1:18790'), 3000);
    } catch (error: any) {
      setServiceStatus('idle');
      showToast(`启动失败: ${error?.error || error}`, 'error');
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
    } catch {
      setServiceStatus('idle');
      showToast('停止失败', 'error');
    }
  };

  const handleNavigate = async (key: string) => {
    const feature = getFeatureDefinition(key);

    if (feature?.requiresLicense && !isAuthorized) {
      showToast('请先输入授权码完成在线激活', 'info');
      setCurrentPage('license');
      return;
    }

    if (feature?.action.type === 'external') {
      open(feature.action.url);
      return;
    }

    if (feature?.action.type === 'dialog') {
      setActiveDialog(feature.action.dialog);
      return;
    }

    if (feature?.action.type === 'command' && feature.action.command === 'update') {
      try {
        const resp = await updateApi.check();
        if (resp.hasUpdate) {
          showToast(`发现新版本 ${resp.current} -> ${resp.latest}`, 'info');
          if (confirm(`当前: ${resp.current}\n最新: ${resp.latest}\n是否更新？`)) {
            appendLog('[更新] 开始更新...\n');
            const updateResp = await updateApi.do();
            showToast(updateResp.success ? `更新成功: ${updateResp.current_version}` : '更新失败', updateResp.success ? 'success' : 'error');
          }
        } else {
          showToast(`已是最新版本 ${resp.current}`, 'info');
        }
      } catch {
        showToast('检查更新失败', 'error');
      }
      return;
    }

    setCurrentPage(key);
  };

  return (
    <ThemeProvider>
      <DynamicTitle />
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-surface text-text">
        <WindowTitlebar />
        <div className="flex min-h-0 flex-1 overflow-hidden bg-surface">
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
          <main className="relative flex-1 overflow-hidden bg-surface">
            {renderFeaturePage(currentPage)}
          </main>
        </div>

        <ToastContainer />
        {activeDialog === 'api' && <ModernApiConfigDialog onClose={() => setActiveDialog(null)} onSaved={refreshApiConfigured} />}
        {activeDialog === 'feishu' && <FeishuConfigDialog onClose={() => setActiveDialog(null)} />}
        {activeDialog === 'weixin' && <WeixinConfigDialog onClose={() => setActiveDialog(null)} />}
      </div>
    </ThemeProvider>
  );
}
