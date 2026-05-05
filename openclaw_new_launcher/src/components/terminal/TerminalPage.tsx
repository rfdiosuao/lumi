import React from 'react';
import { useLogStore } from '../../stores/logStore';
import { useTheme } from '../../hooks/useTheme';

export const TerminalPage: React.FC = () => {
  const lines = useLogStore((s) => s.lines);
  const { theme } = useTheme();
  const containerRef = React.useRef<HTMLPreElement>(null);
  const userAtBottom = React.useRef(true);

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
    <div className="flex flex-col h-full bg-terminal-bg">
      {/* Terminal Header */}
      <div className="flex items-center h-[58px] bg-terminal-header px-6 flex-shrink-0">
        <div className="flex items-center gap-2 mr-4">
          <div className="w-3 h-3 rounded-full bg-status-danger" />
          <div className="w-3 h-3 rounded-full bg-status-warning" />
          <div className="w-3 h-3 rounded-full bg-status-success" />
        </div>
        <span className="text-terminal-label font-medium">{theme.brand.terminal_header}</span>
        <span className="text-terminal-labelMuted text-sm ml-3">127.0.0.1:18790</span>
      </div>

      {/* Log Area */}
      <pre
        ref={containerRef}
        className="flex-1 font-mono text-sm p-6 overflow-auto text-terminal-text leading-relaxed"
        onKeyDown={handleKeyDown}
        onScroll={handleScroll}
      >
        {lines.split('\n').filter(Boolean).map((line, i) => (
          <div key={i}>{highlightLine(line)}</div>
        ))}
        {lines.length === 0 && (
          <span className="text-terminal-labelMuted">等待服务启动...</span>
        )}
      </pre>
    </div>
  );
};
