import React from 'react';
import { create } from 'zustand';

// === Button ===
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'success' | 'quiet' | 'default';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({ variant = 'default', children, className = '', ...props }) => {
  const base = 'px-4 py-2 rounded-lg font-medium transition-all cursor-pointer text-sm disabled:opacity-50 disabled:cursor-not-allowed';
  const variants: Record<string, string> = {
    primary: 'bg-accent hover:bg-accent-hover text-white shadow-[0_0_22px_rgba(157,78,221,0.28)]',
    danger: 'bg-status-danger/15 hover:bg-status-danger/25 text-status-danger border border-status-danger/30',
    success: 'bg-status-success/15 hover:bg-status-success/25 text-status-success border border-status-success/30 shadow-[0_0_18px_rgba(22,199,132,0.18)]',
    quiet: 'bg-white/5 hover:bg-white/10 text-text-muted border border-border',
    default: 'bg-surface-alt/80 hover:bg-hover text-text border border-border',
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
};

// === Input ===
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input: React.FC<InputProps> = ({ className = '', ...props }) => (
  <input
    className={`w-full px-3 py-2 rounded-lg border border-border bg-input text-text text-sm placeholder:text-text-subtle focus:outline-none focus:ring-2 focus:ring-accent/35 focus:border-border-strong ${className}`}
    {...props}
  />
);

// === TextArea ===
export interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const TextArea: React.FC<TextAreaProps> = ({ className = '', ...props }) => (
  <textarea
    className={`w-full px-3 py-2 rounded-lg border border-border bg-input text-text text-sm placeholder:text-text-subtle focus:outline-none focus:ring-2 focus:ring-accent/35 focus:border-border-strong resize-y ${className}`}
    {...props}
  />
);

// === Select ===
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const Select: React.FC<SelectProps> = ({ className = '', children, ...props }) => (
  <select
    className={`px-3 py-2 rounded-lg border border-border bg-input text-text text-sm focus:outline-none focus:ring-2 focus:ring-accent/35 focus:border-border-strong appearance-none ${className}`}
    {...props}
  >
    {children}
  </select>
);

// === Modal ===
export const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative bg-surface/95 rounded-lg shadow-[0_24px_80px_rgba(0,0,0,0.55),0_0_32px_rgba(157,78,221,0.16)] border border-border w-full max-w-lg mx-4 p-6 max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-text">{title}</h2>
            <button onClick={onClose} className="text-text-muted hover:text-text text-xl leading-none">&times;</button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

// === Toast ===
let toastId = 0;

interface ToastItem {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info';
}

const toastStore = create<{
  toasts: ToastItem[];
  addToast: (message: string, type: 'success' | 'error' | 'info') => void;
  removeToast: (id: number) => void;
}>((set) => ({
  toasts: [],
  addToast: (message: string, type: 'success' | 'error' | 'info') => {
    const id = ++toastId;
    set((state: { toasts: ToastItem[] }) => ({
      toasts: [...state.toasts, { id, message, type }],
    }));
    window.setTimeout(() => {
      toastStore.getState().removeToast(id);
    }, 3000);
  },
  removeToast: (id: number) =>
    set((state: { toasts: ToastItem[] }) => ({
      toasts: state.toasts.filter((t: ToastItem) => t.id !== id),
    })),
}));

export const useToastStore = toastStore;

export const ToastContainer: React.FC = () => {
  const toasts = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.removeToast);
  const colors: Record<string, string> = {
    success: 'bg-status-success',
    error: 'bg-status-danger',
    info: 'bg-accent',
  };
  return (
    <div className="fixed top-5 right-5 z-[100] space-y-2">
      {toasts.map((t) => (
        <div key={t.id} className={`${colors[t.type]} text-white px-4 py-3 rounded-lg shadow-[0_16px_40px_rgba(0,0,0,0.38)] border border-white/10 text-sm flex items-center gap-3`}>
          <span>{t.message}</span>
          <button onClick={() => removeToast(t.id)} className="opacity-70 hover:opacity-100">&times;</button>
        </div>
      ))}
    </div>
  );
};

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  toastStore.getState().addToast(message, type);
}

// === Brand Logo ===
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

// === Loading ===
export const Loading: React.FC<{ text?: string }> = ({ text = '加载中...' }) => (
  <div className="flex flex-col items-center justify-center py-12 gap-3">
    <div className="w-8 h-8 border-4 border-accent border-t-transparent rounded-full animate-spin" />
    <span className="text-text-muted text-sm">{text}</span>
  </div>
);

// === Section Label ===
export const SectionLabel: React.FC<{ text: string }> = ({ text }) => (
  <div className="text-xs text-text-subtle font-medium px-3 py-1 mt-2">{text}</div>
);

// === Field Label ===
export const FieldLabel: React.FC<{ text: string; required?: boolean }> = ({ text, required }) => (
  <label className="text-xs text-text-muted mb-1 block">
    {text}{required && <span className="text-status-danger ml-1">*</span>}
  </label>
);
