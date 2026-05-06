import React from 'react';
import { useLogStore } from '../../stores/logStore';
import { useTheme } from '../../hooks/useTheme';

export const TerminalPage: React.FC = () => {
  const lines = useLogStore((s) => s.lines);
  const { theme } = useTheme();
  const containerRef = React.useRef<HTMLPreElement>(null);
  const userAtBottom = React.useRef(true);
  const logLines = lines.split('\n').filter(Boolean);

  React.useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (el) {
      userAtBottom.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey && (e.key === 'c' || e.key === 'C' || e.key === 'a' || e.key === 'A')) {
      return;
    }
    e.preventDefault();
  };

  const highlightLine = (line: string) => {
    if (line.includes('[Error]')) return <span className="text-status-danger">{line}</span>;
    if (line.includes('[WARN]') || line.includes('[Warning]')) return <span className="text-status-warning">{line}</span>;
    if (line.includes('[INFO]') || line.includes('[OpenClaw]')) return <span className="text-terminal-text">{line}</span>;
    return <span className="text-terminal-label">{line}</span>;
  };

  return (
    <div className="flex h-full flex-col bg-transparent">
      <div className="flex h-[64px] shrink-0 items-center border-b border-white/10 bg-terminal-header/80 px-6 backdrop-blur-xl">
        <div className="mr-5 flex items-center gap-2">
          <div className="h-3 w-3 rounded-full bg-status-danger shadow-[0_0_10px_rgba(255,77,109,0.65)]" />
          <div className="h-3 w-3 rounded-full bg-status-warning shadow-[0_0_10px_rgba(245,158,11,0.55)]" />
          <div className="h-3 w-3 rounded-full bg-status-success shadow-[0_0_10px_rgba(22,199,132,0.55)]" />
        </div>
        <span className="text-lg font-bold tracking-wide text-terminal-label">{theme.brand.terminal_header}</span>
        <span className="ml-3 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-terminal-labelMuted">
          127.0.0.1:18790
        </span>
      </div>

      <div className="flex-1 p-6">
        <div className="h-full overflow-hidden rounded-2xl border border-border bg-black/30 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.02),0_18px_50px_rgba(0,0,0,0.22)]">
          <div className="flex h-10 items-center justify-between border-b border-white/10 bg-white/[0.035] px-4">
            <span className="text-xs font-bold uppercase tracking-[0.18em] text-text-subtle">Live Output</span>
            <span className="text-xs text-text-muted">{logLines.length} lines</span>
          </div>
          <pre
            ref={containerRef}
            className="h-[calc(100%-40px)] overflow-auto p-5 font-mono text-sm leading-relaxed text-terminal-text"
            onKeyDown={handleKeyDown}
            onScroll={handleScroll}
          >
            {logLines.map((line, i) => (
              <div key={i}>{highlightLine(line)}</div>
            ))}
            {lines.length === 0 && (
              <span className="text-terminal-labelMuted">等待服务启动...</span>
            )}
          </pre>
        </div>
      </div>
    </div>
  );
};
