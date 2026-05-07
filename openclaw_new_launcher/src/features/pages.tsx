import React from 'react';
import { TerminalPage } from '../components/terminal/TerminalPage';
import { LicensePage } from '../components/license/LicensePage';
import { ImagePage } from '../components/image/ImagePage';
import { VideoPage } from '../components/video/VideoPage';
import { StoryboardPage } from '../components/storyboard/StoryboardPage';
import { DiagnosticsPage } from '../components/diagnostics/DiagnosticsPage';

const PAGE_COMPONENTS: Record<string, React.ComponentType> = {
  terminal: TerminalPage,
  license: LicensePage,
  image: ImagePage,
  video: VideoPage,
  storyboard: StoryboardPage,
  diagnostics: DiagnosticsPage,
};

export function getFeaturePage(key: string): React.ComponentType {
  return PAGE_COMPONENTS[key] || TerminalPage;
}

export function renderFeaturePage(key: string): React.ReactNode {
  const Page = getFeaturePage(key);
  return <Page />;
}
