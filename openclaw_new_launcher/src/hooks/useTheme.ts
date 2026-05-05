import { useAppStore } from '../stores/appStore';
import type { ThemeConfig } from '../types/theme';
import { DEFAULT_THEME, DEFAULT_NAV_ITEMS } from '../theme/default';
import { applyThemeToDOM } from '../providers/ThemeProvider';

export function useTheme() {
  const { themeConfig, setThemeConfig, navItems, setNavItems } = useAppStore();

  const current = themeConfig ?? DEFAULT_THEME;
  const currentNavItems = navItems.length > 0 ? navItems : DEFAULT_NAV_ITEMS;

  const applyTheme = (config: ThemeConfig) => {
    setThemeConfig(config);
    applyThemeToDOM(config);
  };

  const resetTheme = () => {
    setThemeConfig(null);
    setNavItems(DEFAULT_NAV_ITEMS);
    applyThemeToDOM(DEFAULT_THEME);
  };

  return {
    theme: current,
    navItems: currentNavItems,
    isCustom: themeConfig !== null && themeConfig.name !== DEFAULT_THEME.name,
    brandName: current.brand.name,
    brandSubtitle: current.brand.subtitle,
    applyTheme,
    resetTheme,
  };
}
