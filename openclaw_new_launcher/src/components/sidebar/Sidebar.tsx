import React from 'react';
import logoImg from '../../assets/logo.png';
import { useTheme } from '../../hooks/useTheme';
import { DEFAULT_NAV_ITEMS } from '../../theme/default';
import type { NavItem } from '../../types/theme';

interface SidebarProps {
  activePage: string;
  serviceRunning: boolean;
  serviceStatus: string;
  isAuthorized: boolean;
  isApiConfigured: boolean;
  onNavigate: (key: string) => void;
  onStart: () => void;
  onStop: () => void;
}

function statusLabel(serviceRunning: boolean, serviceStatus: string, isAuthorized: boolean, isApiConfigured: boolean): string {
  if (!isAuthorized) return '未授权';
  if (serviceRunning) return '服务运行中';
  if (serviceStatus === 'starting') return '启动中';
  if (serviceStatus === 'stopping') return '停止中';
  if (isApiConfigured) return 'API 已配置';
  return '未配置 API';
}

function statusTone(serviceRunning: boolean, isAuthorized: boolean, isApiConfigured: boolean): string {
  if (!isAuthorized) return 'bg-status-danger shadow-[0_0_12px_rgba(255,77,109,0.65)]';
  if (serviceRunning || isApiConfigured) return 'bg-status-success shadow-[0_0_12px_rgba(22,199,132,0.65)]';
  return 'bg-status-warning shadow-[0_0_12px_rgba(245,158,11,0.55)]';
}

const NavButton: React.FC<{
  item: NavItem;
  isActive: boolean;
  onClick: () => void;
}> = ({ item, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`group relative w-full overflow-hidden rounded-lg px-3 py-3 text-left transition-all ${
      isActive
        ? 'border border-border-strong bg-accent-soft text-text shadow-[0_0_24px_rgba(157,78,221,0.18)]'
        : 'border border-transparent text-text-muted hover:border-border hover:bg-white/5 hover:text-text'
    } ${item.accent ? 'font-medium' : ''}`}
  >
    {isActive && (
      <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-accent shadow-[0_0_14px_rgba(157,78,221,0.9)]" />
    )}
    <div className="flex items-center gap-3">
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-[10px] font-bold tracking-wide ${
          isActive
            ? 'border-border-strong bg-white/10 text-accent-ink'
            : 'border-white/10 bg-white/[0.03] text-text-subtle group-hover:text-text-muted'
        }`}
      >
        {item.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold">{item.label}</div>
        {item.desc && <div className="mt-0.5 truncate text-xs text-text-subtle">{item.desc}</div>}
      </div>
    </div>
  </button>
);

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  serviceRunning,
  serviceStatus,
  isAuthorized,
  isApiConfigured,
  onNavigate,
  onStart,
  onStop,
}) => {
  const { theme, navItems } = useTheme();
  const items = navItems.length > 0 ? navItems : DEFAULT_NAV_ITEMS;
  const brandName = theme.brand.name;
  const brandSubtitle = theme.brand.subtitle;

  const groups = React.useMemo(() => {
    const groupSet = new Set(items.map((item) => item.group));
    return Array.from(groupSet);
  }, [items]);

  return (
    <aside className="relative z-10 flex h-full w-[286px] shrink-0 flex-col border-r border-white/10 bg-app-sidebar/95">
      <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_30%_0%,rgba(157,78,221,0.24),transparent_62%)] pointer-events-none" />

      <div className="relative flex shrink-0 items-center gap-3 px-5 py-6">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-white/5 shadow-[0_0_28px_rgba(157,78,221,0.18)]">
          <img src={logoImg} alt="Logo" className="h-9 w-9 rounded-lg object-contain" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-base font-bold tracking-wide text-text">{brandName}</div>
          <div className="mt-0.5 truncate text-xs text-text-muted">{brandSubtitle}</div>
        </div>
      </div>

      <div className="relative shrink-0 px-4 pb-4">
        <button
          onClick={onStart}
          disabled={serviceRunning || serviceStatus === 'starting'}
          className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-bold text-white shadow-[0_0_28px_rgba(157,78,221,0.30)] transition-all hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
        >
          {serviceStatus === 'starting' ? '启动中...' : serviceRunning ? '服务已运行' : '启动核心服务'}
        </button>
      </div>

      <nav className="relative flex-1 overflow-y-auto px-3 pb-3">
        {groups.map((group) => {
          const groupItems = items.filter((item) => item.group === group);
          return (
            <section key={group} className="mb-4">
              <div className="px-3 pb-2 pt-1 text-[11px] font-bold uppercase tracking-[0.16em] text-text-subtle">{group}</div>
              <div className="space-y-1.5">
                {groupItems.map((item) => (
                  <NavButton
                    key={item.key}
                    item={item}
                    isActive={activePage === item.key}
                    onClick={() => onNavigate(item.key)}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </nav>

      <div className="relative shrink-0 border-t border-white/10 p-4">
        <button
          onClick={onStop}
          disabled={!serviceRunning && serviceStatus !== 'starting'}
          className="mb-3 w-full rounded-xl border border-status-danger/30 bg-status-danger/10 px-4 py-2.5 text-sm font-bold text-status-danger transition-all hover:bg-status-danger/20 disabled:cursor-not-allowed disabled:opacity-45"
        >
          停止服务
        </button>
        <div className="rounded-xl border border-white/10 bg-white/[0.035] p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-text-muted">系统状态</span>
            <span className="text-[10px] uppercase tracking-[0.18em] text-text-subtle">OpenClaw</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusTone(serviceRunning, isAuthorized, isApiConfigured)}`} />
            <span className="truncate text-xs font-medium text-text">{statusLabel(serviceRunning, serviceStatus, isAuthorized, isApiConfigured)}</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
