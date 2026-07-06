import React from 'react';
import { APP_DISPLAY_NAME } from '../../version';

const LOGO_SRC = '/loom-motion/logo.svg';
const LUMING_WORDMARK_DARK_SRC = '/loom-motion/luming-wordmark.png';
const LUMING_WORDMARK_LIGHT_SRC = '/loom-motion/luming-wordmark-light.png';
const LUMING_WORDMARK_GOLD_SRC = '/loom-motion/luming-wordmark-gold.png';

export const LoomLogoMark: React.FC<{ className?: string }> = ({ className = '' }) => (
  <span
    className={`loom-logo-mark relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[8px] bg-[#071b24] ${className}`}
    aria-hidden="true"
  >
    <img src={LOGO_SRC} alt="" className="h-full w-full max-w-none object-contain" draggable={false} />
  </span>
);

export const LoomWordmark: React.FC<{ className?: string; title?: string }> = ({ className = '', title = APP_DISPLAY_NAME }) => (
  <svg
    className={`loom-wordmark ${className}`}
    viewBox="0 0 154 42"
    role="img"
    aria-label={title}
  >
    <title>{title}</title>
    <g fill="currentColor">
      <path d="M5 5h8v25h20v7H5V5Z" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M54 4c-11.2 0-19 7-19 17s7.8 17 19 17 19-7 19-17S65.2 4 54 4Zm0 7.4c6.1 0 10.4 4 10.4 9.6S60.1 30.6 54 30.6 43.6 26.6 43.6 21 47.9 11.4 54 11.4Z"
      />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M94 4c-11.2 0-19 7-19 17s7.8 17 19 17 19-7 19-17S105.2 4 94 4Zm0 7.4c6.1 0 10.4 4 10.4 9.6S100.1 30.6 94 30.6 83.6 26.6 83.6 21 87.9 11.4 94 11.4Z"
      />
      <path d="M116 37V5h8.1l8.9 14.5L141.9 5H150v32h-8V18.9l-7.2 11.2h-3.6L124 18.9V37h-8Z" />
    </g>
    <path d="M38 40h71" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.34" />
    <path d="M54 40h40" stroke="#0B4A3E" strokeWidth="2.2" strokeLinecap="round" opacity="0.72" />
  </svg>
);

export const LumingWordmarkImage: React.FC<{
  className?: string;
  tone?: 'dark' | 'light' | 'gold';
}> = ({ className = '', tone = 'dark' }) => {
  const src =
    tone === 'light'
      ? LUMING_WORDMARK_LIGHT_SRC
      : tone === 'gold'
        ? LUMING_WORDMARK_GOLD_SRC
        : LUMING_WORDMARK_DARK_SRC;
  return (
    <img
      src={src}
      alt={APP_DISPLAY_NAME}
      className={`luming-wordmark select-none object-contain ${className}`}
      draggable={false}
    />
  );
};

export const LoomTitleLockup: React.FC<{
  title?: string;
  subtitle?: string;
  className?: string;
  wordmarkTone?: 'dark' | 'light' | 'gold';
}> = ({ title = APP_DISPLAY_NAME, subtitle, className = '', wordmarkTone = 'dark' }) => {
  const titleClass = wordmarkTone === 'dark' ? 'text-text' : 'text-white';
  const subtitleClass = wordmarkTone === 'dark' ? 'text-text-subtle' : 'text-white/60';

  return (
    <div className={`flex min-w-0 items-center gap-2.5 ${className}`}>
      <LoomLogoMark className="h-7 w-7 shadow-[0_8px_22px_rgba(3,30,38,0.22)]" />
      <div className="min-w-0">
        <div className={`truncate text-[15px] font-black leading-tight ${titleClass}`}>{title}</div>
        {subtitle ? (
          <div className={`mt-0.5 truncate text-[10px] font-semibold ${subtitleClass}`}>
            {subtitle}
          </div>
        ) : null}
      </div>
    </div>
  );
};
