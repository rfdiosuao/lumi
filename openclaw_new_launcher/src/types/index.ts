// === Process ===
export interface ProcessStatus {
  running: boolean;
  pid: number | null;
}

// === License ===
export interface License {
  licensee: string;
  edition: string;
  expires: string | null;
  features: string[];
  installId: string;
  deviceId?: string;
  signature: string;
}

export interface LicenseState {
  license: License | null;
  authorized: boolean;
}

// === Image ===
export interface ImageConfig {
  baseUrl: string;
  apiKey: string;
}

// === Video ===
export interface VideoConfig {
  providerId: VideoProviderId;
  apiBase: string;
  model: string;
  dashKey: string;
}

export type VideoProviderId = 'dashscope' | 'seedance' | 'custom';

export type VideoMode = 't2v' | 'i2v';

export interface VideoGenerationParams {
  prompt: string;
  mode: VideoMode;
  providerId?: VideoProviderId;
  apiBase?: string;
  model?: string;
  resolution?: string;
  duration?: number;
  ratio?: string;
  image_path?: string;
}

// === Storyboard ===
export interface SceneCheck {
  productStable: boolean;
  logoClear: boolean;
  sellingPoint: boolean;
  frameFlowGood: boolean;
  cropReady: boolean;
}

export interface Scene {
  id: string;
  title: string;
  sellingPoint: string;
  duration: string;
  ratio: string;
  camera: string;
  prompt: string;
  negative: string;
  candidatePrompt: string;
  referenceImage: string | null;
  firstFrame: string | null;
  lastFrame: string | null;
  video: string | null;
  checks: SceneCheck;
  productViews: {
    front: string | null;
    side: string | null;
    back: string | null;
  };
  candidates: string[];
}

export interface StoryboardProject {
  scenes: Scene[];
  productName: string;
  productDescription: string;
}

// === Provider ===
export interface Provider {
  name: string;
  url: string;
  models: string[];
}

// === Update ===
export interface UpdateInfo {
  current: string;
  latest: string;
  hasUpdate: boolean;
}

// === API Response ===
export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  [key: string]: unknown;
}
