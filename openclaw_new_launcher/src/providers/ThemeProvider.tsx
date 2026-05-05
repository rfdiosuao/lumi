import React, { useEffect, useRef, useCallback } from 'react';
import { DEFAULT_THEME, applyThemeToCssVars } from '../theme/default';
import { useAppStore } from '../stores/appStore';
import { themeApi } from '../services/api';

const applyThemeToDOM = applyThemeToCssVars;

export { applyThemeToDOM };

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { themeConfig, setThemeConfig, setNavItems } = useAppStore();
  const loadedRef = useRef(false);

  const loadTheme = useCallback(async () => {
    try {
      const resp = await themeApi.current();
      if (resp.theme) {
        setThemeConfig(resp.theme);
        const respNavItems = (resp.theme as any).navItems;
        if (Array.isArray(respNavItems) && respNavItems.length > 0) {
          setNavItems(respNavItems);
        }
      }
    } catch {
      applyThemeToDOM(DEFAULT_THEME);
    }
  }, [setThemeConfig, setNavItems]);

  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadTheme();
    }
  }, [loadTheme]);

  useEffect(() => {
    if (themeConfig) {
      applyThemeToDOM(themeConfig);
    }
  }, [themeConfig]);

  (window as any).__reloadTheme = loadTheme;

  return <>{children}</>;
};
