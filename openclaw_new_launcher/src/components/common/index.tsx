import React from 'react';
import { createPortal } from 'react-dom';
import { create } from 'zustand';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'success' | 'quiet' | 'default';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({ variant = 'default', children, className = '', ...props }) => {
  const base = 'px-4 py-2 rounded-xl font-semibold transition-all cursor-pointer text-sm disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-alt/60 disabled:text-text-subtle disabled:shadow-none';
  const variants: Record<string, string> = {
    primary: 'border border-[#0B4A3E]/45 bg-[#0B4A3E] text-[#F5FFF9] shadow-[0_12px_28px_rgba(8,60,49,0.20)] hover:border-[#146650]/60 hover:bg-[#12604F]',
    danger: 'bg-status-danger/12 hover:bg-status-danger/22 text-status-danger border border-status-danger/35',
    success: 'bg-status-success/14 hover:bg-status-success/24 text-status-success border border-status-success/35 shadow-[0_0_18px_rgba(63,224,143,0.16)]',
    quiet: 'bg-surface-alt/70 hover:bg-hover text-text-muted hover:text-text border border-border',
    default: 'bg-surface-alt/85 hover:bg-hover text-text border border-border',
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
};

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input: React.FC<InputProps> = ({ className = '', ...props }) => (
  <input
    className={`w-full rounded-xl border border-border bg-input px-3 py-2 text-sm text-text placeholder:text-text-subtle focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-accent/30 ${className}`}
    {...props}
  />
);

export interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const TextArea: React.FC<TextAreaProps> = ({ className = '', ...props }) => (
  <textarea
    className={`w-full resize-y rounded-xl border border-border bg-input px-3 py-2 text-sm text-text placeholder:text-text-subtle focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-accent/30 ${className}`}
    {...props}
  />
);

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select: React.FC<SelectProps> = ({ className = '', children, ...props }) => (
  <select
    className={`rounded-xl border border-border bg-input px-3 py-2 text-sm text-text focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-accent/30 ${className}`}
    {...props}
  >
    {children}
  </select>
);

export const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-md" />
      <div
        className="relative mx-4 max-h-[82vh] w-full max-w-lg overflow-auto rounded-2xl border border-border bg-surface/95 p-6 shadow-[0_28px_90px_rgba(0,0,0,0.56),0_0_34px_rgba(11,74,62,0.12)]"
        onClick={(event) => event.stopPropagation()}
      >
        {title && (
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-bold text-text">{title}</h2>
            <button onClick={onClose} className="text-2xl leading-none text-text-muted hover:text-text">&times;</button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

type ConfirmTone = 'default' | 'danger';

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: ConfirmTone;
}

interface ConfirmRequest extends Required<ConfirmOptions> {
  id: number;
  resolve: (value: boolean) => void;
}

let confirmId = 0;

const confirmStore = create<{
  request: ConfirmRequest | null;
  open: (options: ConfirmOptions) => Promise<boolean>;
  settle: (value: boolean) => void;
}>((set, get) => ({
  request: null,
  open: (options) => new Promise<boolean>((resolve) => {
    const current = get().request;
    if (current) current.resolve(false);
    set({
      request: {
        id: ++confirmId,
        title: options.title || '请确认',
        message: options.message,
        confirmText: options.confirmText || '确定',
        cancelText: options.cancelText || '取消',
        tone: options.tone || 'default',
        resolve,
      },
    });
  }),
  settle: (value) => {
    const current = get().request;
    if (!current) return;
    current.resolve(value);
    set({ request: null });
  },
}));

export function showConfirm(options: string | ConfirmOptions): Promise<boolean> {
  const normalized = typeof options === 'string' ? { message: options } : options;
  return confirmStore.getState().open(normalized);
}

export const ConfirmDialogHost: React.FC = () => {
  const request = confirmStore((state) => state.request);
  const settle = confirmStore((state) => state.settle);
  if (!request) return null;

  return (
    <div className="fixed inset-0 z-[99970] flex items-center justify-center px-5" role="dialog" aria-modal="true" aria-labelledby={`confirm-title-${request.id}`}>
      <button
        type="button"
        aria-label="取消"
        className="absolute inset-0 h-full w-full bg-[#061017]/55 backdrop-blur-[2px]"
        onClick={() => settle(false)}
      />
      <div className="relative w-full max-w-[440px] rounded-[18px] border border-border bg-surface/98 p-5 shadow-[0_30px_90px_rgba(5,25,22,0.28)]">
        <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-full ${
          request.tone === 'danger'
            ? 'border border-status-danger/25 bg-status-danger/12 text-status-danger'
            : 'border border-[#0B4A3E]/20 bg-[#0B4A3E]/10 text-[#0B4A3E]'
        }`}>
          <span className="text-lg font-black">{request.tone === 'danger' ? '!' : '?'}</span>
        </div>
        <h2 id={`confirm-title-${request.id}`} className="text-lg font-black text-text">{request.title}</h2>
        <p className="mt-2 whitespace-pre-line text-sm leading-6 text-text-muted">{request.message}</p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="quiet" onClick={() => settle(false)}>{request.cancelText}</Button>
          <Button variant={request.tone === 'danger' ? 'danger' : 'primary'} onClick={() => settle(true)}>
            {request.confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
};

let toastId = 0;
const TOAST_TTL_MS = 3200;
const TOAST_DEDUPE_WINDOW_MS = 1800;
const MAX_VISIBLE_TOASTS = 3;

interface ToastItem {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
  createdAt: number;
}

const toastStore = create<{
  toasts: ToastItem[];
  addToast: (message: string, type: 'success' | 'error' | 'info') => void;
  removeToast: (id: number) => void;
}>((set) => ({
  toasts: [],
  addToast: (message: string, type: 'success' | 'error' | 'info') => {
    const now = Date.now();
    let scheduledId: number | null = null;
    let shouldSchedule = false;

    const id = ++toastId;
    set((state) => ({
      toasts: (() => {
        const duplicate = state.toasts.find(
          (toast) => toast.type === type && toast.message === message && now - toast.createdAt < TOAST_DEDUPE_WINDOW_MS
        );
        if (duplicate) return state.toasts;

        scheduledId = id;
        shouldSchedule = true;
        return [...state.toasts, { id, message, type, createdAt: now }].slice(-MAX_VISIBLE_TOASTS);
      })(),
    }));

    if (shouldSchedule && scheduledId !== null) {
      window.setTimeout(() => {
        toastStore.getState().removeToast(scheduledId as number);
      }, TOAST_TTL_MS);
    }
  },
  removeToast: (id: number) =>
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    })),
}));

export const useToastStore = toastStore;

export const ToastContainer: React.FC = () => {
  const toasts = useToastStore((state) => state.toasts);
  const removeToast = useToastStore((state) => state.removeToast);
  const colors: Record<string, string> = {
    success: 'bg-status-success text-[#04140D]',
    error: 'bg-status-danger text-white',
    info: 'border border-[#0B4A3E]/35 bg-[#0B4A3E] text-[#F5FFF9]',
  };
  return (
    <div className="pointer-events-none fixed right-5 top-5 z-[100] flex w-[min(560px,calc(100vw-2.5rem))] flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`${colors[toast.type]} toast-enter pointer-events-auto flex items-center gap-3 rounded-xl border border-white/15 px-4 py-3 text-sm font-semibold shadow-[0_18px_44px_rgba(0,0,0,0.42)]`}
        >
          <span className="min-w-0 flex-1 break-words">{toast.message}</span>
          <button onClick={() => removeToast(toast.id)} className="opacity-70 hover:opacity-100">&times;</button>
        </div>
      ))}
    </div>
  );
};

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  toastStore.getState().addToast(message, type);
}

export const BrandLogo: React.FC<{
  src?: string;
  fallbackSrc: string;
  alt?: string;
  className?: string;
}> = ({ src, fallbackSrc, alt = '', className = '' }) => {
  const [activeSrc, setActiveSrc] = React.useState(src || fallbackSrc);
  const fallbackUsedRef = React.useRef(false);

  React.useEffect(() => {
    fallbackUsedRef.current = false;
    setActiveSrc(src || fallbackSrc);
  }, [src, fallbackSrc]);

  return (
    <img
      src={activeSrc}
      alt={alt}
      className={className}
      onError={() => {
        if (fallbackUsedRef.current) return;
        fallbackUsedRef.current = true;
        setActiveSrc(fallbackSrc);
      }}
      draggable={false}
    />
  );
};

export const Loading: React.FC<{ text?: string }> = ({ text = '加载中...' }) => (
  <div className="flex flex-col items-center justify-center gap-3 py-12">
    <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#0B4A3E] border-t-transparent" />
    <span className="text-sm text-text-muted">{text}</span>
  </div>
);

export const BusyOverlay: React.FC<{
  active: boolean;
  title?: string;
  detail?: string;
}> = ({
  active,
  title = '正在处理',
  detail = '请稍候，LOOM 正在完成当前操作。',
}) => {
  if (!active) return null;

  const overlay = (
    <div
      data-busy-overlay
      role="status"
      aria-live="polite"
      className="pointer-events-auto fixed inset-0 z-[99940] flex items-center justify-center bg-[#071916]/64 px-6"
    >
      <div
        data-busy-overlay-card
        className="flex min-w-[260px] max-w-[360px] max-h-[min(80vh,420px)] flex-col items-center overflow-auto rounded-[18px] border border-[#0B4A3E]/18 bg-surface/98 px-6 py-5 text-center shadow-[0_24px_72px_rgba(5,35,29,0.22)]"
      >
        <span className="loom-busy-ring" aria-hidden="true" />
        <div className="mt-4 text-base font-black text-text">{title}</div>
        {detail ? <div className="mt-1 max-w-full whitespace-pre-wrap break-words text-xs leading-5 text-text-muted">{detail}</div> : null}
      </div>
    </div>
  );

  if (typeof document === 'undefined') return overlay;
  return createPortal(overlay, document.body);
};

export const SectionLabel: React.FC<{ text: string }> = ({ text }) => (
  <div className="mt-2 px-3 py-1 text-xs font-semibold text-text-subtle">{text}</div>
);

export const FieldLabel: React.FC<{ text: string; required?: boolean }> = ({ text, required }) => (
  <label className="mb-1 block text-xs font-medium text-text-muted">
    {text}{required && <span className="ml-1 text-status-danger">*</span>}
  </label>
);
