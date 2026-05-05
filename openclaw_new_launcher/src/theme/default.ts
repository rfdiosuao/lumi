import type { ThemeConfig, NavItem } from '../types/theme';

type ThemeColors = ThemeConfig['colors'];

export const DEFAULT_THEME: ThemeConfig = {
  name: '永浩科技主题',
  colors: {
    app_bg: '#F3F4F5',
    sidebar_bg: '#F9F9FA',
    surface: '#FFFFFF',
    surface_alt: '#F6F7F8',
    surface_deep: '#1C202A',
    surface_deeper: '#14171E',
    hover: '#EDEFF1',
    input: '#F6F7F8',
    border: '#DDDFE3',
    border_strong: '#C1C4CC',
    text: '#1E2A3A',
    text_muted: '#64748B',
    text_subtle: '#94A3B8',
    accent: '#1A56DB',
    accent_hover: '#1444AD',
    accent_soft: '#E4E8F0',
    accent_ink: '#0F327F',
    success: '#059669',
    warning: '#D97706',
    danger: '#DC2626',
    danger_hover: '#B91C1C',
    terminal_bg: '#0F172A',
    terminal_header: '#1E293B',
    terminal_text: '#34D399',
  },
  fonts: {
    display: ['Microsoft YaHei UI', 21, 'bold'],
    title: ['Microsoft YaHei UI', 14, 'bold'],
    section: ['Microsoft YaHei UI', 10, 'bold'],
    body: ['Microsoft YaHei UI', 10, 'normal'],
    small: ['Microsoft YaHei UI', 9, 'normal'],
    mono: ['Consolas', 10, 'normal'],
  },
  brand: {
    name: '永浩科技',
    subtitle: '智能AI服务平台',
    app_user_model_id: 'YonghaoTech.Launcher',
    terminal_header: 'Service Console',
  },
};

export const DEFAULT_NAV_ITEMS: NavItem[] = [
  { key: 'terminal', label: '服务日志', desc: '查看运行状态', icon: 'LOG', group: '工作台' },
  { key: 'storyboard', label: '广告视频', desc: '分镜/首尾帧/九宫格', icon: 'AD', group: '工作台', accent: true },
  { key: 'image', label: 'AI 生图', desc: '生成/编辑图片', icon: 'IMG', group: '工作台', accent: true },
  { key: 'video', label: 'AI 视频', desc: '文生/图生视频', icon: 'VID', group: '工作台', accent: true },
  { key: 'license', label: '授权码', desc: '在线激活解锁', icon: 'LIC', group: '配置' },
  { key: 'api', label: 'API 配置', desc: '设置模型密钥', icon: 'KEY', group: '配置' },
  { key: 'feishu', label: '飞书机器人', desc: '绑定消息通道', icon: 'BOT', group: '配置' },
  { key: 'web', label: '网页界面', desc: '打开本地控制台', icon: 'WEB', group: '维护' },
  { key: 'update', label: '检查更新', desc: '更新 OpenClaw', icon: 'UP', group: '维护' },
  { key: 'help', label: '帮助文档', desc: '查看使用说明', icon: 'DOC', group: '维护' },
];

const CSS_VAR_MAP: Record<keyof ThemeColors, string> = {
  app_bg: '--color-app-bg',
  sidebar_bg: '--color-sidebar-bg',
  surface: '--color-surface',
  surface_alt: '--color-surface-alt',
  surface_deep: '--color-surface-deep',
  surface_deeper: '--color-surface-deeper',
  hover: '--color-hover',
  input: '--color-input',
  border: '--color-border',
  border_strong: '--color-border-strong',
  text: '--color-text',
  text_muted: '--color-text-muted',
  text_subtle: '--color-text-subtle',
  accent: '--color-accent',
  accent_hover: '--color-accent-hover',
  accent_soft: '--color-accent-soft',
  accent_ink: '--color-accent-ink',
  success: '--color-success',
  warning: '--color-warning',
  danger: '--color-danger',
  danger_hover: '--color-danger-hover',
  terminal_bg: '--color-terminal-bg',
  terminal_header: '--color-terminal-header',
  terminal_text: '--color-terminal-text',
};

export function applyThemeToCssVars(theme: ThemeConfig): void {
  const root = document.documentElement;
  const colors = theme.colors;
  for (const [key, cssVar] of Object.entries(CSS_VAR_MAP)) {
    const value = colors[key as keyof ThemeColors];
    if (value) {
      root.style.setProperty(cssVar, value);
    }
  }
  root.style.setProperty('--font-display', theme.fonts.display[0]);
  root.style.setProperty('--font-mono', theme.fonts.mono[0]);
  root.style.setProperty('--brand-name', theme.brand.name);
  root.style.setProperty('--brand-subtitle', theme.brand.subtitle);
}
