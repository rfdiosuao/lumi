import React from 'react';
import { LumingWordmarkImage } from './LoomBrand';

const MIN_SPLASH_DURATION_MS = 2400;
const MAX_SPLASH_DURATION_MS = 5200;

export const LoomSplash: React.FC = () => {
  const [logoReady, setLogoReady] = React.useState(false);
  const [minElapsed, setMinElapsed] = React.useState(false);
  const [visible, setVisible] = React.useState(true);

  React.useEffect(() => {
    const minTimer = window.setTimeout(() => setMinElapsed(true), MIN_SPLASH_DURATION_MS);
    const fallbackTimer = window.setTimeout(() => setVisible(false), MAX_SPLASH_DURATION_MS);
    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(fallbackTimer);
    };
  }, []);

  React.useEffect(() => {
    if (logoReady && minElapsed) {
      const timer = window.setTimeout(() => setVisible(false), 220);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [logoReady, minElapsed]);

  if (!visible) return null;

  return (
    <div
      data-loom-splash
      className="loom-splash fixed inset-0 z-[99990] flex items-center justify-center bg-[#071b24] text-[#dffaff]"
      aria-label="LOOM 麓鸣启动中"
    >
      <div className="flex flex-col items-center">
        <div className="loom-splash-orbit relative h-[232px] w-[232px] rounded-[32px] bg-[#071b24] p-1 shadow-[0_34px_90px_rgba(0,0,0,0.34)]">
          <div className="h-full w-full overflow-hidden rounded-[28px] bg-[#071b24]">
            <iframe
              title="LOOM 麓鸣启动动画"
              src="/loom-motion/logo_motion_single.html?qa=1"
              className="h-full w-full border-0"
              sandbox="allow-scripts"
              onLoad={() => setLogoReady(true)}
            />
          </div>
        </div>
        <LumingWordmarkImage tone="light" className="mt-6 h-[106px] w-[168px] opacity-95" />
        <div className="mt-1 text-sm font-bold text-[#dffaff]">正在启动 LOOM</div>
        <div className="loom-splash-dots mt-4 flex items-center gap-1.5" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>
  );
};
