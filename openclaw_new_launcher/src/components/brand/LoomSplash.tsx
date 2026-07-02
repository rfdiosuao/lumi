import React from 'react';
import { LumingWordmarkImage } from './LoomBrand';

const MIN_SPLASH_DURATION_MS = 4400;
const MAX_SPLASH_DURATION_MS = 10000;
const MOTION_READY_EVENT = 'loom-motion-ready';
const MOTION_READY_NONCE = 'loom-motion-20260630-v1';

export const LoomSplash: React.FC = () => {
  const [motionReady, setMotionReady] = React.useState(false);
  const [minElapsed, setMinElapsed] = React.useState(false);
  const [visible, setVisible] = React.useState(true);
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);

  React.useEffect(() => {
    const minTimer = window.setTimeout(() => setMinElapsed(true), MIN_SPLASH_DURATION_MS);
    const fallbackTimer = window.setTimeout(() => setVisible(false), MAX_SPLASH_DURATION_MS);
    return () => {
      window.clearTimeout(minTimer);
      window.clearTimeout(fallbackTimer);
    };
  }, []);

  React.useEffect(() => {
    const handleMotionReady = (event: MessageEvent) => {
      if (
        event.source === iframeRef.current?.contentWindow &&
        event.data?.type === MOTION_READY_EVENT &&
        event.data?.source === 'loom-motion-vector-v1' &&
        event.data?.nonce === MOTION_READY_NONCE
      ) {
        setMotionReady(true);
      }
    };
    window.addEventListener('message', handleMotionReady);
    return () => {
      window.removeEventListener('message', handleMotionReady);
    };
  }, []);

  React.useEffect(() => {
    if (motionReady && minElapsed) {
      const timer = window.setTimeout(() => setVisible(false), 220);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [motionReady, minElapsed]);

  if (!visible) return null;

  return (
    <div
      data-loom-splash
      className="loom-splash fixed inset-0 z-[99990] flex items-center justify-center bg-[#071b24] text-[#dffaff]"
      aria-label="LOOM 麓鸣启动中"
    >
      <div className="flex flex-col items-center">
        <div className="loom-splash-orbit relative h-[268px] w-[268px] rounded-[34px] bg-[#071b24] p-0 shadow-[0_34px_90px_rgba(0,0,0,0.34)]">
          <div className="h-full w-full overflow-hidden rounded-[34px] bg-[#071b24]">
            <iframe
              ref={iframeRef}
              title="LOOM 麓鸣启动动画"
              src={`/loom-motion/logo_motion_vector-v1.html?embed=1&loop=1&motion=calm&v=20260630-v1&nonce=${MOTION_READY_NONCE}`}
              className="h-full w-full border-0"
              sandbox="allow-scripts"
              loading="eager"
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
