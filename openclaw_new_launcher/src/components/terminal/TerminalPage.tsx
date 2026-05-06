import React from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Button, showToast } from '../common';
import { useLogStore } from '../../stores/logStore';
import { useTheme } from '../../hooks/useTheme';

export const TerminalPage: React.FC = () => {
  const lines = useLogStore((s) => s.lines);
  const clearLogs = useLogStore((s) => s.clear);
  const { theme, themeMode } = useTheme();
  const isLight = themeMode === 'light';
  const containerRef = React.useRef<HTMLPreElement>(null);
  const [exporting, setExporting] = React.useState(false);
  const [lastExportPath, setLastExportPath] = React.useState('');
  const logLines = lines.split('\n').filter(Boolean);

  const scrollToBottom = React.useCallback((smooth = false) => {
    const el = containerRef.current;
    if (!el) return;
    const top = Math.max(0, el.scrollHeight - el.clientHeight);
    if (smooth) {
      el.scrollTo({ top, behavior: 'smooth' });
    } else {
      el.scrollTop = top;
    }
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey && (e.key === 'c' || e.key === 'C' || e.key === 'a' || e.key === 'A')) {
      return;
    }
    e.preventDefault();
  };

  const highlightLine = (line: string) => {
    if (line.includes('[Error]') || line.includes('Error:') || line.includes('failed')) {
      return <span className={isLight ? 'text-[#B91C1C]' : 'text-[#F87171]'}>{line}</span>;
    }
    if (line.includes('[WARN]') || line.includes('[Warning]') || line.includes('warning')) {
      return <span className={isLight ? 'text-[#B45309]' : 'text-[#FBBF24]'}>{line}</span>;
    }
    if (line.includes('[OpenClaw]')) {
      return <span className={isLight ? 'text-[#047857]' : 'text-[#00F5D4]'}>{line}</span>;
    }
    if (line.includes('[Bridge]')) {
      return <span className={isLight ? 'text-[#1D4ED8]' : 'text-[#93C5FD]'}>{line}</span>;
    }
    return <span className={isLight ? 'text-slate-800' : 'text-slate-100'}>{line}</span>;
  };

  const handleJumpToBottom = () => {
    requestAnimationFrame(() => scrollToBottom(true));
    showToast('已跳到底部', 'info');
  };

  const handleExport = async () => {
    if (!lines.trim()) {
      showToast('当前没有可导出的日志', 'info');
      return;
    }
    setExporting(true);
    try {
      const path = await invoke<string>('export_log', { content: lines });
      setLastExportPath(path);
      showToast(`日志已导出：${path}`, 'success');
    } catch (error: any) {
      showToast(`导出日志失败：${error?.error || error}`, 'error');
    } finally {
      setExporting(false);
    }
  };

  const handleOpenLogDir = async () => {
    if (!lastExportPath) {
      showToast('请先导出日志', 'info');
      return;
    }
    const directory = lastExportPath.replace(/[\\/][^\\/]+$/, '');
    try {
      await invoke('open_path', { path: directory });
      showToast(`已打开目录：${directory}`, 'info');
    } catch (error: any) {
      showToast(`打开目录失败：${error?.error || error}`, 'error');
    }
  };

  return (
    <div className="flex h-full flex-col bg-transparent">
      <div className={`flex h-[64px] shrink-0 items-center justify-between border-b px-6 ${
        isLight ? 'border-border bg-surface' : 'border-white/10 bg-[#101328]'
      }`}>
        <div className="flex items-center">
          <div className="mr-5 flex items-center gap-2">
            <div className="h-3 w-3 rounded-full bg-status-danger shadow-[0_0_10px_rgba(255,77,109,0.65)]" />
            <div className="h-3 w-3 rounded-full bg-status-warning shadow-[0_0_10px_rgba(245,158,11,0.55)]" />
            <div className="h-3 w-3 rounded-full bg-status-success shadow-[0_0_10px_rgba(22,199,132,0.55)]" />
          </div>
          <span className={`text-lg font-bold tracking-wide ${isLight ? 'text-text' : 'text-slate-100'}`}>
            {theme.brand.terminal_header}
          </span>
          <span className={`ml-3 rounded-full border px-3 py-1 text-xs ${
            isLight ? 'border-border bg-surface-alt text-text-muted' : 'border-white/10 bg-white/5 text-slate-300'
          }`}>
            127.0.0.1:18790
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="quiet" className="px-3 py-1.5 text-xs" onClick={handleJumpToBottom}>
            跳到底部
          </Button>
          <Button variant="quiet" className="px-3 py-1.5 text-xs" onClick={handleExport} disabled={exporting}>
            {exporting ? '导出中...' : '导出日志'}
          </Button>
          {lastExportPath && (
            <Button variant="quiet" className="px-3 py-1.5 text-xs" onClick={handleOpenLogDir}>
              打开目录
            </Button>
          )}
          <Button variant="danger" className="px-3 py-1.5 text-xs" onClick={clearLogs}>
            清空
          </Button>
        </div>
      </div>

      <div className="flex-1 p-6">
        <div className={`h-full overflow-hidden rounded-2xl border shadow-[0_18px_50px_rgba(15,23,42,0.14)] ${
          isLight ? 'border-border bg-white' : 'border-slate-700 bg-[#080C18]'
        }`}>
          <div className={`flex h-10 items-center justify-between border-b px-4 ${
            isLight ? 'border-border bg-surface-alt' : 'border-slate-700 bg-[#111827]'
          }`}>
            <span className={`text-xs font-bold uppercase tracking-[0.18em] ${isLight ? 'text-accent' : 'text-[#93C5FD]'}`}>Live Output</span>
            <span className={`text-xs ${isLight ? 'text-text-muted' : 'text-slate-300'}`}>{logLines.length} lines</span>
          </div>
          <pre
            ref={containerRef}
            className={`h-[calc(100%-40px)] overflow-y-scroll overflow-x-auto p-5 font-mono text-sm leading-relaxed ${
              isLight ? 'bg-white text-slate-800' : 'bg-[#080C18] text-slate-100'
            }`}
            onKeyDown={handleKeyDown}
          >
            {logLines.map((line, i) => (
              <div key={i}>{highlightLine(line)}</div>
            ))}
            {lines.length === 0 && (
              <span className={isLight ? 'text-text-muted' : 'text-slate-400'}>等待服务启动...</span>
            )}
          </pre>
        </div>
      </div>
    </div>
  );
};
