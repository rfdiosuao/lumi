import React, { Suspense } from 'react';
import { DashboardPage } from '../components/dashboard/DashboardPage';
import { Loading } from '../components/common';

// Only the default landing page (dashboard) is eager. Every other page is
// code-split via React.lazy so the launcher's first paint no longer has to
// parse/execute the entire app bundle (e.g. the ~2.8k-line PhoneControlPage,
// storyboard, publish, video) before the console appears.
function lazyNamed(
  loader: () => Promise<Record<string, unknown>>,
  name: string,
): React.ComponentType {
  return React.lazy(async () => ({ default: (await loader())[name] as React.ComponentType }));
}

const TerminalPage = lazyNamed(() => import('../components/terminal/TerminalPage'), 'TerminalPage');
const LicensePage = lazyNamed(() => import('../components/license/LicensePage'), 'LicensePage');
const ImagePage = lazyNamed(() => import('../components/image/ImagePage'), 'ImagePage');
const VideoPage = lazyNamed(() => import('../components/video/VideoPage'), 'VideoPage');
const StoryboardPage = lazyNamed(() => import('../components/storyboard/StoryboardPage'), 'StoryboardPage');
const DiagnosticsPage = lazyNamed(() => import('../components/diagnostics/DiagnosticsPage'), 'DiagnosticsPage');
const SkillsPage = lazyNamed(() => import('../components/skills/SkillsPage'), 'SkillsPage');
const PhoneControlPage = lazyNamed(() => import('../components/phone/PhoneControlPage'), 'PhoneControlPage');
const DesktopAgentPage = lazyNamed(() => import('../components/desktop/DesktopAgentPage'), 'DesktopAgentPage');
const PublishPage = lazyNamed(() => import('../components/publish/PublishPage'), 'PublishPage');

const PAGE_COMPONENTS: Record<string, React.ComponentType> = {
  dashboard: DashboardPage,
  terminal: TerminalPage,
  license: LicensePage,
  image: ImagePage,
  video: VideoPage,
  storyboard: StoryboardPage,
  diagnostics: DiagnosticsPage,
  skills: SkillsPage,
  phone: PhoneControlPage,
  publish: PublishPage,
  desktop: DesktopAgentPage,
};

export function getFeaturePage(key: string): React.ComponentType {
  return PAGE_COMPONENTS[key] || TerminalPage;
}

export function renderFeaturePage(key: string): React.ReactNode {
  const Page = getFeaturePage(key);
  return (
    <Suspense fallback={<div className="flex h-full w-full items-center justify-center"><Loading /></div>}>
      <Page />
    </Suspense>
  );
}
