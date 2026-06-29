import React, { useEffect, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-shell';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { Sidebar } from './components/sidebar/Sidebar';
import { WindowTitlebar } from './components/window/WindowTitlebar';
import { ConfirmDialogHost, ToastContainer, showConfirm, showToast } from './components/common';
import { useAppStore } from './stores/appStore';
import { useLogStore } from './stores/logStore';
import { processApi, logApi, parseErrorText, updateApi } from './services/api';
import { detectApiConfigured } from './services/apiStatus';
import { ThemeProvider } from './providers/ThemeProvider';
import { useTheme } from './hooks/useTheme';
import { getFeatureDefinition } from './features/registry';
import { renderFeaturePage } from './features/pages';
import { SetupGate } from './components/SetupGate';
import { LoomSplash } from './components/brand/LoomSplash';

const NAV_PARENT_BY_PAGE: Record<string, string> = {
  models: 'license',
  diagnostics: 'capabilities',
  settings: 'settings',
  terminal: 'capabilities',
};

function formatError(error: unknown): string {
  const friendly = parseErrorText(error);
  if (friendly) return friendly;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const value = error as { error?: unknown; message?: unknown };
    if (typeof value.error === 'string') return value.error;
    if (typeof value.message === 'string') return value.message;
    try {
      return JSON.stringify(error);
    } catch {
      return String(error);
    }
  }
  return String(error);
}

function safeCurrentWindow() {
  try {
    return getCurrentWindow();
  } catch {
    return null;
  }
}

function DynamicTitle() {
  const { windowTitle } = useTheme();

  useEffect(() => {
    document.title = windowTitle;
    safeCurrentWindow()?.setTitle(windowTitle).catch(() => {});
  }, [windowTitle]);

  return null;
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
  const replaceLog = useLogStore((s) => s.replace);
  const [apiConfigured, setApiConfigured] = useState(false);
  const logInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const logOffset = useRef(0);

  const refreshApiConfigured = React.useCallback(async () => {
    setApiConfigured(await detectApiConfigured());
  }, []);

  const startLogPolling = () => {
    if (logInterval.current) return;
    logInterval.current = setInterval(async () => {
      try {
        const resp = await logApi.get(logOffset.current);
        logOffset.current = resp.offset ?? logOffset.current;
        if (resp.reset) {
          replaceLog(resp.log || '');
        } else if (resp.log) {
          appendLog(resp.log);
        }
      } catch (error) {
        appendLog(`[日志轮询] 错误: ${formatError(error)}\n`);
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

  // Reflect an already-running core service when the launcher is reopened, so
  // status and log polling don't require the user to hit "start" again.
  useEffect(() => {
    let cancelled = false;
    processApi.status().then((status) => {
      if (!cancelled && status.running) {
        setServiceRunning(true);
        setServiceStatus('running');
      }
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [setServiceRunning, setServiceStatus]);

  // Keep log polling in sync with service state (covers the service already
  // running on launch, not just the in-session start button).
  useEffect(() => {
    if (serviceRunning) startLogPolling();
    else stopLogPolling();
    return () => stopLogPolling();
    // startLogPolling/stopLogPolling are stable closures over refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceRunning]);

  useEffect(() => {
    const resetOffset = () => {
      logOffset.current = 0;
    };
    window.addEventListener('openclaw:logs-cleared', resetOffset);
    return () => window.removeEventListener('openclaw:logs-cleared', resetOffset);
  }, []);

  useEffect(() => {
    const feature = getFeatureDefinition(currentPage);
    const allowedWithoutLicense =
      ['license', 'diagnostics'].includes(currentPage) || !feature?.requiresLicense;
    if (!isLicenseChecking && !isAuthorized && !allowedWithoutLicense) {
      setCurrentPage('license');
    }
  }, [currentPage, isAuthorized, isLicenseChecking, setCurrentPage]);

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
      showToast('请先邮箱登录，或输入授权码完成授权', 'info');
      setCurrentPage('license');
      return;
    }

    if (feature?.action.type === 'external') {
      open(feature.action.url);
      return;
    }

    if (feature?.action.type === 'command' && feature.action.command === 'update') {
      try {
        const resp = await updateApi.check();
        if (resp.hasUpdate) {
          showToast(`发现新版本 ${resp.current} -> ${resp.latest}`, 'info');
          const ok = await showConfirm({
            title: '发现新版本',
            message: `当前版本：${resp.current}\n最新版本：${resp.latest}\n是否现在更新？`,
            confirmText: '立即更新',
          });
          if (ok) {
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

  const currentFeature = getFeatureDefinition(currentPage);
  const canOpenCurrentPage = !currentFeature?.requiresLicense || isAuthorized || isLicenseChecking;
  const visiblePage = canOpenCurrentPage ? currentPage : 'license';
  const activeNavPage = NAV_PARENT_BY_PAGE[visiblePage] || visiblePage;

  return (
    <ThemeProvider>
      <DynamicTitle />
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-surface text-text">
        <WindowTitlebar />
        <div className="flex min-h-0 flex-1 overflow-hidden bg-surface">
          <Sidebar
            activePage={activeNavPage}
            serviceRunning={serviceRunning}
            serviceStatus={serviceStatus}
            isAuthorized={isAuthorized}
            isApiConfigured={apiConfigured}
            onNavigate={handleNavigate}
            onStop={handleStop}
          />
          <main className="relative flex-1 overflow-hidden bg-surface">
            {renderFeaturePage(visiblePage)}
          </main>
        </div>

        <ToastContainer />
        <ConfirmDialogHost />
        <LoomSplash />
        <SetupGate />
      </div>
    </ThemeProvider>
  );
}
