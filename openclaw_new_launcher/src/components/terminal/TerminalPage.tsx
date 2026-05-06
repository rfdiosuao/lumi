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
  const [followTail, setFollowTail] = React.useState(true);
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

  React.useLayoutEffect(() => {
    if (followTail) {
      scrollToBottom(false);
    }
  }, [lines, followTail, scrollToBottom]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    setFollowTail(el.scrollTop + el.clientHeight >= el.scrollHeight - 80);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey && (e.key === 'c' || e.key === 'C' || e.key === 'a' || e.key === 'A')) {
      return;
    }
    e.preventDefault();
  };

  const highlightLine = (line: string) => {
    if (line.includes('[Error]') || line.includes('Error:') || line.includes('failed')) {
      return <span className="text-[#F87171]">{line}</span>;
    }
    if (line.includes('[WARN]') || line.includes('[Warning]') || line.includes('warning')) {
      return <span className="text-[#FBBF24]">{line}</span>;
    }
    if (line.includes('[OpenClaw]')) {
      return <span className="text-[#00F5D4]">{line}</span>;
    }
    if (line.includes('[Bridge]')) {
      return <span className="text-[#93C5FD]">{line}</span>;
    }
    return <span className="text-slate-100">{line}</span>;
  };

  const handleJumpToBottom = () => {
    setFollowTail(true);
    scrollToBottom(true);
    window.setTimeout(() => scrollToBottom(false), 180);
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
          <Button variant={followTail ? 'success' : 'quiet'} className="px-3 py-1.5 text-xs" onClick={handleJumpToBottom}>
            跟随底部
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
        <div className="h-full overflow-hidden rounded-2xl border border-slate-700 bg-[#080C18] shadow-[0_18px_50px_rgba(15,23,42,0.28)]">
          <div className="flex h-10 items-center justify-between border-b border-slate-700 bg-[#111827] px-4">
            <span className="text-xs font-bold uppercase tracking-[0.18em] text-[#93C5FD]">Live Output</span>
            <span className="text-xs text-slate-300">{logLines.length} lines</span>
          </div>
          <pre
            ref={containerRef}
            className="h-[calc(100%-40px)] overflow-y-scroll overflow-x-auto bg-[#080C18] p-5 font-mono text-sm leading-relaxed text-slate-100"
            onKeyDown={handleKeyDown}
            onScroll={handleScroll}
          >
            {logLines.map((line, i) => (
              <div key={i}>{highlightLine(line)}</div>
            ))}
            {lines.length === 0 && (
              <span className="text-slate-400">等待服务启动...</span>
            )}
          </pre>
        </div>
      </div>
    </div>
  );
};
