import { create } from 'zustand';
import { type License } from '../types';
import { type ThemeConfig, type NavItem } from '../types/theme';
import {
  DEFAULT_NAV_ITEMS,
  type BuiltinThemeMode,
  getBuiltinTheme,
  getStoredThemeMode,
} from '../theme/default';
import { licenseApi } from '../services/api';

interface AppState {
  currentPage: string;
  serviceRunning: boolean;
  serviceStatus: 'idle' | 'starting' | 'running' | 'stopping' | 'stopped';
  isAuthorized: boolean;
  isLicenseChecking: boolean;
  licenseInfo: License | null;
  apiConfigured: boolean;
  themeConfig: ThemeConfig | null;
  themeMode: BuiltinThemeMode;
  navItems: NavItem[];

  setCurrentPage: (page: string) => void;
  setServiceRunning: (running: boolean) => void;
  setServiceStatus: (status: AppState['serviceStatus']) => void;
  setAuthorized: (authorized: boolean) => void;
  setLicenseInfo: (info: License | null) => void;
  setApiConfigured: (configured: boolean) => void;
  setLicenseChecking: (checking: boolean) => void;
  setThemeConfig: (config: ThemeConfig | null) => void;
  setThemeMode: (mode: BuiltinThemeMode) => void;
  setNavItems: (items: NavItem[]) => void;
  checkLicense: () => Promise<void>;
}

const initialThemeMode = getStoredThemeMode();

export const useAppStore = create<AppState>((set) => ({
  currentPage: 'dashboard',
  serviceRunning: false,
  serviceStatus: 'idle',
  isAuthorized: false,
  isLicenseChecking: true,
  licenseInfo: null,
  apiConfigured: false,
  themeConfig: getBuiltinTheme(initialThemeMode),
  themeMode: initialThemeMode,
  navItems: DEFAULT_NAV_ITEMS,

  setCurrentPage: (currentPage) => set({ currentPage }),
  setServiceRunning: (serviceRunning) => set({ serviceRunning }),
  setServiceStatus: (serviceStatus) => set({ serviceStatus }),
  setAuthorized: (isAuthorized) => {
    if (!isAuthorized) {
      try { localStorage.removeItem('openclaw_auth'); } catch { /* ignore */ }
    }
    set({ isAuthorized, isLicenseChecking: false });
  },
  setLicenseInfo: (licenseInfo) => {
    set({ licenseInfo });
  },
  setApiConfigured: (apiConfigured) => set({ apiConfigured }),
  setThemeConfig: (themeConfig) => set({ themeConfig }),
  setThemeMode: (themeMode) => set({ themeMode }),
  setNavItems: (navItems) => set({ navItems }),
  setLicenseChecking: (val: boolean) => set({ isLicenseChecking: val }),
  checkLicense: async () => {
    set({ isLicenseChecking: true });
    try {
      const resp = await licenseApi.current();
      if (resp.license && typeof resp.license === 'object') {
        set({ isAuthorized: true, licenseInfo: resp.license as License, isLicenseChecking: false });
      } else {
        set({ isAuthorized: false, licenseInfo: null, isLicenseChecking: false });
        try { localStorage.removeItem('openclaw_auth'); } catch { /* ignore */ }
      }
    } catch {
      set({ isAuthorized: false, licenseInfo: null, isLicenseChecking: false });
      try { localStorage.removeItem('openclaw_auth'); } catch { /* ignore */ }
    }
  },
}));
