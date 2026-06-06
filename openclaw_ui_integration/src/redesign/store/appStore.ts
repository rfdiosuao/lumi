import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { RouteKey, ToastMessage, TransportMode } from '../types';

export interface PreviewSettings {
  transportMode: TransportMode;
  bridgeBaseUrl: string;
  bridgeToken: string;
  proxyTarget: string;
  openaiProxy: string;
  phoneBaseUrl: string;
  phoneToken: string;
}

interface AppState {
  route: RouteKey;
  sidebarCollapsed: boolean;
  selectedPhoneId: string | null;
  settings: PreviewSettings;
  toasts: ToastMessage[];
  navigate: (route: RouteKey) => void;
  toggleSidebar: () => void;
  setSelectedPhoneId: (id: string | null) => void;
  updateSettings: (patch: Partial<PreviewSettings>) => void;
  pushToast: (toast: Omit<ToastMessage, 'id'>) => void;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
}

const DEFAULT_SETTINGS: PreviewSettings = {
  transportMode: 'live',
  bridgeBaseUrl: '',
  bridgeToken: '',
  proxyTarget: '',
  openaiProxy: '',
  phoneBaseUrl: '',
  phoneToken: '',
};

const TOAST_DEDUPE_WINDOW_MS = 3000;

function safeId() {
  return `toast_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function toastCreatedAt(id: string): number {
  const value = Number(id.split('_')[1]);
  return Number.isFinite(value) ? value : 0;
}

export const usePreviewStore = create<AppState>()(
  persist(
    (set) => ({
      route: 'dashboard',
      sidebarCollapsed: false,
      selectedPhoneId: null,
      settings: DEFAULT_SETTINGS,
      toasts: [],
      navigate: (route) => set({ route }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSelectedPhoneId: (selectedPhoneId) => set({ selectedPhoneId }),
      updateSettings: (patch) => set((state) => ({ settings: { ...state.settings, ...patch } })),
      pushToast: (toast) =>
        set((state) => {
          const now = Date.now();
          const duplicate = state.toasts.some(
            (item) =>
              item.tone === toast.tone &&
              item.title === toast.title &&
              (item.detail || '') === (toast.detail || '') &&
              now - toastCreatedAt(item.id) < TOAST_DEDUPE_WINDOW_MS,
          );
          if (duplicate) return state;
          return { toasts: [...state.toasts, { id: safeId(), ...toast }].slice(-5) };
        }),
      dismissToast: (id) =>
        set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
      clearToasts: () => set({ toasts: [] }),
    }),
    {
      name: 'openclaw-redesign-live',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        route: state.route,
        sidebarCollapsed: state.sidebarCollapsed,
        selectedPhoneId: state.selectedPhoneId,
        settings: state.settings,
      }),
    }
  )
);
