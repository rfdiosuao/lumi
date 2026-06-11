import React from 'react';
import {
  Activity,
  BellOff,
  ChevronLeft,
  ChevronRight,
  Cpu,
  FileText,
  Gauge,
  Layers3,
  Maximize2,
  Minus,
  Phone,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Webhook,
  X,
} from 'lucide-react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { Button, cx } from './ui';
import { usePreviewStore, type PreviewSettings } from '../store/appStore';
import type { RouteKey } from '../types';
import { isTauriRuntime, resolveBridgeBaseUrl } from '../api/client';

const NAV_ITEMS: Array<{ key: RouteKey; label: string; desc: string; icon: typeof Gauge }> = [
  { key: 'dashboard', label: '启动器', desc: '开机总览', icon: Gauge },
  { key: 'service', label: '服务 / CLI', desc: '启动、日志、终端', icon: SquareTerminal },
  { key: 'license', label: '授权内测', desc: '授权码与成员状态', icon: ShieldCheck },
  { key: 'integrations', label: '平台对接', desc: '飞书 / 微信 / Webhook', icon: Webhook },
  { key: 'studio', label: '图像 / 视频', desc: '生成任务入口', icon: Sparkles },
  { key: 'phone', label: '手机控制台', desc: 'APKClaw 桥接', icon: Phone },
  { key: 'desktop', label: '桌面自动化', desc: 'Luminode 控制', icon: Cpu },
  { key: 'skills', label: 'Skills 工作区', desc: '能力模块管理', icon: Layers3 },
  { key: 'diagnostics', label: '环境检测', desc: '检测与修复', icon: Activity },
  { key: 'settings', label: '统一设置', desc: '密钥与连接', icon: Settings2 },
];

const ROUTE_COPY: Record<RouteKey, { eyebrow: string; title: string }> = {
  dashboard: { eyebrow: 'Windows 启动器', title: 'OpenClaw 启动器总览' },
  service: { eyebrow: '运行时 / CLI', title: '启动核心服务，查看日志与 CLI 状态' },
  license: { eyebrow: '授权内测', title: '授权码、成员状态与发卡入口' },
  integrations: { eyebrow: '平台对接', title: '飞书、微信、钉钉与 Webhook 的统一接入窗口' },
  studio: { eyebrow: '生成任务', title: '图像 / 视频生成任务' },
  phone: { eyebrow: 'APKClaw 桥接', title: '手机控制台，只作控制星桥' },
  desktop: { eyebrow: '桌面自动化', title: 'lumi 桌面控制台' },
  skills: { eyebrow: 'Skills 工作区', title: 'Skills 管理与工作区状态' },
  diagnostics: { eyebrow: '环境检测', title: '启动前环境检测与修复' },
  settings: { eyebrow: '统一设置', title: '统一配置密钥、桥接和控制端' },
};

function getBridgeLabel(settings: PreviewSettings): string {
  const bridgeBaseUrl = resolveBridgeBaseUrl(settings.bridgeBaseUrl);
  if (bridgeBaseUrl) return '真实桥接已配置';
  if (settings.transportMode === 'mock') return '预览星图';
  if (isTauriRuntime()) return '星河内置航道';
  return '待接入星桥';
}

export function Shell({ children }: { children: React.ReactNode }) {
  const route = usePreviewStore((state) => state.route);
  const navigate = usePreviewStore((state) => state.navigate);
  const settings = usePreviewStore((state) => state.settings);
  const toggleSidebar = usePreviewStore((state) => state.toggleSidebar);
  const sidebarCollapsed = usePreviewStore((state) => state.sidebarCollapsed);
  const toasts = usePreviewStore((state) => state.toasts);
  const dismissToast = usePreviewStore((state) => state.dismissToast);
  const clearToasts = usePreviewStore((state) => state.clearToasts);

  const handleWindowAction = React.useCallback(async (action: 'minimize' | 'toggleMaximize' | 'close') => {
    if (!isTauriRuntime()) return;
    const currentWindow = getCurrentWindow();
    if (action === 'minimize') await currentWindow.minimize();
    else if (action === 'toggleMaximize') await currentWindow.toggleMaximize();
    else await currentWindow.close();
  }, []);

  React.useEffect(() => {
    if (!toasts.length) return;
    const timers = toasts.map((toast) =>
      window.setTimeout(() => {
        dismissToast(toast.id);
      }, 4000)
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [toasts, dismissToast]);

  return (
    <div className={cx('app-shell', sidebarCollapsed && 'app-shell-sidebar-collapsed')}>
      <aside className={cx('sidebar', sidebarCollapsed && 'sidebar-collapsed')}>
        <div className="brand-block" data-tauri-drag-region>
          <div className="brand-copy">
            <div className="brand-title" data-tauri-drag-region>OpenClaw</div>
            <div className="brand-subtitle" data-tauri-drag-region>满舱清梦压星河</div>
          </div>
        </div>

        <div className="sidebar-toolbar">
          <Button
            variant="quiet"
            icon={sidebarCollapsed ? ChevronRight : ChevronLeft}
            className="sidebar-toggle-button"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
            aria-label={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          >
            {sidebarCollapsed ? '' : '收起侧栏'}
          </Button>
        </div>

        <nav className="nav-list" aria-label="OpenClaw preview navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = route === item.key;
            return (
              <button
                key={item.key}
                type="button"
                className={cx('nav-item', active && 'nav-item-active')}
                onClick={() => navigate(item.key)}
              >
                <Icon size={16} />
                <span className="nav-item-text">
                  <span className="nav-item-label">{item.label}</span>
                  <span className="nav-item-desc">{item.desc}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-foot-title">星河航标</div>
          <div className="sidebar-foot-value">/{route}</div>
          <div className="sidebar-foot-note">
            桥接 {getBridgeLabel(settings)}<br />
            手机 {settings.phoneBaseUrl ? '控制星桥已绑定' : '只作控制星桥'}
          </div>
        </div>
      </aside>

      <div className="shell-main">
        <header className="topbar" data-tauri-drag-region>
          <div className="topbar-left" data-tauri-drag-region>
            <div className="topbar-kicker" data-tauri-drag-region>{ROUTE_COPY[route]?.eyebrow || 'Preview'}</div>
            <div className="topbar-title" data-tauri-drag-region>{ROUTE_COPY[route]?.title || 'OpenClaw preview'}</div>
          </div>
          <div className="topbar-right">
            <Button type="button" variant="quiet" icon={BellOff} onClick={clearToasts}>
              清除提示
            </Button>
            <div className="window-controls" aria-label="窗口控制">
              <Button
                type="button"
                variant="quiet"
                icon={Minus}
                className="window-control-button"
                onClick={() => void handleWindowAction('minimize')}
                title="最小化"
                aria-label="最小化"
              />
              <Button
                type="button"
                variant="quiet"
                icon={Maximize2}
                className="window-control-button"
                onClick={() => void handleWindowAction('toggleMaximize')}
                title="最大化 / 还原"
                aria-label="最大化或还原"
              />
              <Button
                type="button"
                variant="quiet"
                icon={X}
                className="window-control-button window-control-close"
                onClick={() => void handleWindowAction('close')}
                title="关闭"
                aria-label="关闭"
              />
            </div>
          </div>
        </header>

        <main className="page-wrap">{children}</main>
      </div>

      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={cx('toast', `toast-${toast.tone}`)}>
            <div>
              <div className="toast-title">{toast.title}</div>
              {toast.detail ? <div className="toast-detail">{toast.detail}</div> : null}
            </div>
            <button type="button" className="icon-button" onClick={() => dismissToast(toast.id)} aria-label="关闭提示">
              <FileText size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
