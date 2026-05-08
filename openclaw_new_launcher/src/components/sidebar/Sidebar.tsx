import React from 'react';
import logoImg from '../../assets/logo.png';
import { BrandLogo } from '../common';
import { useTheme } from '../../hooks/useTheme';
import { DEFAULT_NAV_ITEMS, normalizeNavItems } from '../../theme/default';
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
  if (!isAuthorized) return 'bg-status-danger shadow-[0_0_10px_rgba(255,77,109,0.6)]';
  if (serviceRunning || isApiConfigured) return 'bg-status-success shadow-[0_0_10px_rgba(63,224,143,0.6)]';
  return 'bg-status-warning shadow-[0_0_10px_rgba(255,180,84,0.5)]';
}

const NavButton: React.FC<{
  item: NavItem;
  isActive: boolean;
  onClick: () => void;
}> = ({ item, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`group relative w-full overflow-hidden rounded-xl px-3 py-2.5 text-left transition-all duration-150 ${
      isActive
        ? 'border border-border-strong bg-accent-soft text-text'
        : 'border border-transparent text-text-muted hover:border-border hover:bg-hover hover:text-text'
    } ${item.accent ? 'font-medium' : ''}`}
  >
    {isActive && (
      <span className="absolute bottom-2 left-0 top-2 w-[2.5px] rounded-r bg-accent shadow-[0_0_12px_rgba(214,180,106,0.7)]" />
    )}
    <div className="flex items-center gap-3">
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-[9px] font-bold tracking-wider transition-all ${
          isActive
            ? 'border-border-strong bg-accent/20 text-accent'
            : 'border-border bg-surface-alt text-text-subtle group-hover:border-border-strong group-hover:text-text'
        }`}
      >
        {item.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold leading-tight">{item.label}</div>
        {item.desc && <div className="mt-0.5 truncate text-[11px] text-text-subtle">{item.desc}</div>}
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
  const { theme, navItems, themeMode, toggleTheme, logoUrl } = useTheme();
  const items = React.useMemo(() => normalizeNavItems(navItems.length > 0 ? navItems : DEFAULT_NAV_ITEMS), [navItems]);
  const brandLogo = logoUrl || logoImg;

  const groups = React.useMemo(() => {
    const groupSet = new Set(items.map((item) => item.group));
    return Array.from(groupSet);
  }, [items]);

  return (
    <aside className="relative z-10 flex h-full w-[260px] shrink-0 flex-col border-r border-border bg-app-sidebar">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_50%_40%_at_20%_0%,rgba(214,180,106,0.14),transparent),linear-gradient(180deg,rgba(255,255,255,0.025),transparent_50%)]" />

      <div className="relative flex shrink-0 items-center gap-3 px-5 py-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border-strong bg-surface-alt shadow-[0_0_24px_rgba(214,180,106,0.12)]">
          <BrandLogo src={brandLogo} fallbackSrc={logoImg} alt="Lumi" className="h-7 w-7 rounded-lg object-contain" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-black tracking-wide text-text">{theme.brand.name}</div>
          <div className="mt-0.5 truncate text-[11px] text-text-subtle">{theme.brand.subtitle}</div>
        </div>
      </div>

      <div className="relative shrink-0 px-4 pb-3">
        <button
          onClick={onStart}
          disabled={serviceRunning || serviceStatus === 'starting'}
          className="w-full rounded-xl bg-accent px-4 py-2.5 text-[13px] font-black text-accent-ink shadow-[0_12px_36px_rgba(214,180,106,0.18)] transition-all hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
        >
          {serviceStatus === 'starting' ? '启动中...' : serviceRunning ? '服务已运行' : '启动核心服务'}
        </button>
      </div>

      <nav className="relative flex-1 overflow-y-auto px-3 pb-3">
        {groups.map((group) => {
          const groupItems = items.filter((item) => item.group === group);
          return (
            <section key={group} className="mb-3">
              <div className="px-3 pb-1.5 pt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-text-subtle">{group}</div>
              <div className="space-y-1">
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

      <div className="relative shrink-0 border-t border-border p-3">
        <div className="mb-2.5 grid grid-cols-[1fr_38px] gap-2">
          <button
            onClick={onStop}
            disabled={!serviceRunning && serviceStatus !== 'starting'}
            className="rounded-xl border border-status-danger/30 bg-status-danger/8 px-3 py-2 text-[13px] font-bold text-status-danger transition-all hover:bg-status-danger/16 disabled:cursor-not-allowed disabled:opacity-40"
          >
            停止服务
          </button>
          <button
            onClick={toggleTheme}
            className="flex h-[38px] w-[38px] items-center justify-center rounded-xl border border-border bg-surface-alt text-sm font-black text-accent transition-all hover:border-border-strong hover:bg-hover"
            title={themeMode === 'dark' ? '切换浅色风格' : '切换深色风格'}
            aria-label={themeMode === 'dark' ? '切换浅色风格' : '切换深色风格'}
          >
            {themeMode === 'dark' ? '☀' : '☾'}
          </button>
        </div>
        <div className="rounded-xl border border-border bg-surface-alt/60 p-2.5">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <span className="text-[11px] font-medium text-text-muted">系统状态</span>
            <span className="text-[9px] uppercase tracking-[0.22em] text-text-subtle">LUMI</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusTone(serviceRunning, isAuthorized, isApiConfigured)}`} />
            <span className="truncate text-[11px] font-medium text-text">{statusLabel(serviceRunning, serviceStatus, isAuthorized, isApiConfigured)}</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
