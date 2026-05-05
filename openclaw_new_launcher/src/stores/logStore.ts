import { create } from 'zustand';

interface LogState {
  lines: string;
  append: (text: string) => void;
  clear: () => void;
}

export const useLogStore = create<LogState>((set) => ({
  lines: '',
  append: (text: string) => set((state) => {
    const newLines = state.lines + text;
    // Cap at 100KB to prevent memory issues
    const maxLen = 100000;
    if (newLines.length > maxLen) {
      const truncated = newLines.slice(-maxLen);
      const firstNewline = truncated.indexOf('\n');
      return { lines: firstNewline >= 0 ? truncated.slice(firstNewline + 1) : truncated };
    }
    return { lines: newLines };
  }),
  clear: () => set({ lines: '' }),
}));
