import React from 'react';
import { getCurrentWindow } from '@tauri-apps/api/window';
import logoImg from '../../assets/logo.png';
import { useTheme } from '../../hooks/useTheme';

const appWindow = getCurrentWindow();

const WindowButton: React.FC<{
  label: string;
  title: string;
  danger?: boolean;
  onClick: () => void;
}> = ({ label, title, danger, onClick }) => (
  <button
    type="button"
    title={title}
    aria-label={title}
    onClick={(event) => {
      event.stopPropagation();
      onClick();
    }}
    className={`flex h-8 w-10 items-center justify-center rounded-md text-sm font-semibold transition-colors ${
      danger
        ? 'text-text-muted hover:bg-status-danger hover:text-white'
        : 'text-text-muted hover:bg-hover hover:text-text'
    }`}
  >
    {label}
  </button>
);

export const WindowTitlebar: React.FC = () => {
  const { brandName, brandSubtitle, themeMode } = useTheme();
  const isDark = themeMode === 'dark';

  const toggleMaximize = () => {
    appWindow.toggleMaximize().catch(() => {});
  };

  return (
    <div
      data-tauri-drag-region
      onDoubleClick={toggleMaximize}
      className={`flex h-10 shrink-0 items-center justify-between border-b px-3 ${
        isDark
          ? 'border-white/10 bg-[#080A16]/95 text-slate-100'
          : 'border-border bg-surface/95 text-text'
      }`}
    >
      <div data-tauri-drag-region className="flex min-w-0 items-center gap-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-md border border-border bg-white/60">
          <img src={logoImg} alt="" className="h-4 w-4 object-contain" />
        </div>
        <div data-tauri-drag-region className="truncate text-xs font-semibold">
          {brandName}
        </div>
        <div data-tauri-drag-region className="hidden truncate text-xs text-text-subtle sm:block">
          {brandSubtitle}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <WindowButton title="最小化" label="-" onClick={() => appWindow.minimize()} />
        <WindowButton title="最大化/还原" label="□" onClick={toggleMaximize} />
        <WindowButton title="关闭" label="×" danger onClick={() => appWindow.close()} />
      </div>
    </div>
  );
};
