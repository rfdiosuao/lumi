import type { NavItem, ThemeConfig } from '../types/theme';
import { DEFAULT_FEATURE_NAV_ITEMS, normalizeFeatureNavItems } from '../features/registry';

type ThemeColors = ThemeConfig['colors'];

export type BuiltinThemeMode = 'light' | 'dark';

export const THEME_MODE_STORAGE_KEY = 'lumi_theme_mode';

const BASE_FONTS: ThemeConfig['fonts'] = {
  display: ['Microsoft YaHei UI', 21, 'bold'],
  title: ['Microsoft YaHei UI', 14, 'bold'],
  section: ['Microsoft YaHei UI', 10, 'bold'],
  body: ['Microsoft YaHei UI', 10, 'normal'],
  small: ['Microsoft YaHei UI', 9, 'normal'],
  mono: ['Consolas', 10, 'normal'],
};

export const DEFAULT_NAV_ITEMS: NavItem[] = DEFAULT_FEATURE_NAV_ITEMS;

export const LIGHT_THEME: ThemeConfig = {
  name: '永浩科技浅色主题',
  colors: {
    app_bg: '#F3F4F6',
    sidebar_bg: '#F8FAFC',
    surface: '#FFFFFF',
    surface_alt: '#F8FAFC',
    surface_deep: '#1E293B',
    surface_deeper: '#0F172A',
    hover: '#EDEFF3',
    input: '#FFFFFF',
    border: '#DDE3EA',
    border_strong: '#B8C4D2',
    text: '#102033',
    text_muted: '#64748B',
    text_subtle: '#94A3B8',
    accent: '#2563EB',
    accent_hover: '#1D4ED8',
    accent_soft: '#E8EEFD',
    accent_ink: '#1E40AF',
    success: '#059669',
    warning: '#D97706',
    danger: '#DC2626',
    danger_hover: '#B91C1C',
    terminal_bg: '#0F172A',
    terminal_header: '#1E293B',
    terminal_text: '#34D399',
  },
  fonts: BASE_FONTS,
  brand: {
    name: '永浩科技',
    subtitle: '智能AI服务平台',
    app_user_model_id: 'YonghaoTech.Launcher',
    terminal_header: 'Service Console',
  },
  navItems: DEFAULT_NAV_ITEMS,
  window: {
    title: '永浩科技 - 智能AI服务平台',
    width: 1200,
    height: 800,
  },
};

export const DARK_THEME: ThemeConfig = {
  ...LIGHT_THEME,
  name: '永浩科技暗紫主题',
  colors: {
    app_bg: '#050510',
    sidebar_bg: '#090A18',
    surface: '#0B0D1A',
    surface_alt: '#111426',
    surface_deep: '#171B32',
    surface_deeper: '#070812',
    hover: '#1A1F38',
    input: '#0C1020',
    border: 'rgba(157, 78, 221, 0.24)',
    border_strong: 'rgba(0, 212, 255, 0.38)',
    text: '#F4F7FB',
    text_muted: '#A8B0C3',
    text_subtle: '#66708B',
    accent: '#9D4EDD',
    accent_hover: '#B76BFF',
    accent_soft: 'rgba(157, 78, 221, 0.18)',
    accent_ink: '#F5EAFF',
    success: '#16C784',
    warning: '#F59E0B',
    danger: '#FF4D6D',
    danger_hover: '#FF6B84',
    terminal_bg: '#050510',
    terminal_header: '#101328',
    terminal_text: '#00F5D4',
  },
};

export const DEFAULT_THEME = LIGHT_THEME;

export function getStoredThemeMode(): BuiltinThemeMode {
  if (typeof window === 'undefined') return 'light';
  try {
    return window.localStorage.getItem(THEME_MODE_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function persistThemeMode(mode: BuiltinThemeMode): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_MODE_STORAGE_KEY, mode);
    document.documentElement.dataset.themeMode = mode;
    document.documentElement.style.colorScheme = mode;
  } catch {
    // ignore storage failures
  }
}

export function getBuiltinTheme(mode: BuiltinThemeMode): ThemeConfig {
  return mode === 'dark' ? DARK_THEME : LIGHT_THEME;
}

export function normalizeNavItems(items?: NavItem[]): NavItem[] {
  return normalizeFeatureNavItems(items);
}

export function buildRuntimeTheme(baseTheme: ThemeConfig | null | undefined, mode: BuiltinThemeMode): ThemeConfig {
  const palette = getBuiltinTheme(mode);
  const brand = baseTheme?.brand ? { ...palette.brand, ...baseTheme.brand } : palette.brand;
  const windowConfig = baseTheme?.window ? { ...palette.window, ...baseTheme.window } : palette.window;
  const modeColors = baseTheme?.modes?.[mode];
  const colors = {
    ...palette.colors,
    ...(modeColors ?? baseTheme?.colors ?? {}),
  };

  return {
    ...palette,
    name: baseTheme?.name ?? palette.name,
    colors,
    modes: baseTheme?.modes,
    brand,
    window: windowConfig,
    fonts: { ...palette.fonts, ...(baseTheme?.fonts ?? {}) },
    navItems: normalizeNavItems(baseTheme?.navItems),
  };
}

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

export function bootstrapThemeFromStorage(): void {
  if (typeof document === 'undefined') return;
  const mode = getStoredThemeMode();
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.style.colorScheme = mode;
  applyThemeToCssVars(getBuiltinTheme(mode));
}
