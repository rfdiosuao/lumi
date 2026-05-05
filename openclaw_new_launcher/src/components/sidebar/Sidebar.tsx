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

const NavButton: React.FC<{
  item: NavItem;
  isActive: boolean;
  onClick: () => void;
}> = ({ item, isActive, onClick }) => (
  <button
    onClick={onClick}
    className={`w-full text-left px-3 py-2 rounded-md transition-colors cursor-pointer flex items-center gap-3 ${
      isActive
        ? 'bg-accent-soft text-accent-ink'
        : 'text-text hover:bg-surface-alt'
    } ${item.accent ? 'font-medium' : ''}`}
  >
    <span className={`w-1 h-4 rounded-full flex-shrink-0 ${isActive ? 'bg-accent' : 'bg-transparent'}`} />
    <div className="min-w-0 flex-1">
      <div className="text-sm truncate">{item.label}</div>
      {item.desc && <div className={`text-xs truncate ${isActive ? 'text-accent-ink/70' : 'text-text-muted'}`}>{item.desc}</div>}
    </div>
  </button>
);

export const Sidebar: React.FC<SidebarProps> = ({
  activePage, serviceRunning, serviceStatus, isAuthorized,
  onNavigate, onStart, onStop,
}) => {
  const { theme, navItems } = useTheme();
  const items = navItems.length > 0 ? navItems : DEFAULT_NAV_ITEMS;
  const brandName = theme.brand.name;
  const brandSubtitle = theme.brand.subtitle;

  const groups = React.useMemo(() => {
    const groupSet = new Set(items.map((i) => i.group));
    return Array.from(groupSet);
  }, [items]);

  const statusColor = !isAuthorized
    ? 'bg-status-danger'
    : serviceRunning
    ? 'bg-status-success'
    : 'bg-status-warning';

  return (
    <div className="w-[280px] flex-shrink-0 bg-app-sidebar border-r border-border flex flex-col h-full">
      <div className="px-5 py-5 flex items-center gap-3 flex-shrink-0">
        <img src={logoImg} alt="Logo" className="w-12 h-12 rounded-xl flex-shrink-0" />
        <div className="min-w-0">
          <div className="text-base font-semibold text-text">{brandName}</div>
          <div className="text-xs text-text-muted">{brandSubtitle}</div>
        </div>
      </div>

      <div className="px-4 pb-3 flex-shrink-0">
        <button
          onClick={onStart}
          disabled={serviceRunning || serviceStatus === 'starting'}
          className="w-full bg-accent hover:bg-accent-hover text-white px-4 py-3 rounded-lg text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {serviceStatus === 'starting' ? '启动中...' : '启动服务'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-3">
        {groups.map((group) => {
          const groupItems = items.filter((i) => i.group === group);
          return (
            <div key={group}>
              <div className="text-xs text-text-subtle font-medium px-3 py-1 mt-2">{group}</div>
              {groupItems.map((item) => (
                <div key={item.key} className="py-0.5">
                  <NavButton
                    item={item}
                    isActive={activePage === item.key}
                    onClick={() => onNavigate(item.key)}
                  />
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="px-4 pb-4 pt-2 border-t border-border flex-shrink-0">
        <button
          onClick={onStop}
          disabled={!serviceRunning && serviceStatus !== 'starting'}
          className="w-full bg-status-danger/10 hover:bg-status-danger/20 text-status-danger px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer mb-3 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          停止服务
        </button>
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusColor}`} />
          <span className="text-xs text-text-muted">{
            !isAuthorized ? '未授权' : serviceRunning ? '服务运行中' : serviceStatus === 'idle' ? '未配置' : serviceStatus
          }</span>
          {isAuthorized && (
            <span className="text-xs text-text-muted">
              {serviceStatus === 'idle' ? 'API ' : ''}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
