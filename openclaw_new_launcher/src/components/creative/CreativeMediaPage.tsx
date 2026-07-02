import React from 'react';
import { Button, FieldLabel, Input, Select, TextArea, showToast } from '../common';
import {
  imageApi,
  jobApi,
  mediaApi,
  parseErrorText,
  videoApi,
  type BridgeJob,
  type MediaConfigSnapshot,
} from '../../services/api';
import type { VideoProviderId } from '../../types';

type CreativeTab = 'image' | 'video';

type ImageResult = {
  images?: string[];
  files?: Array<{ path?: string; directory?: string; filename?: string; size?: number; mime?: string }>;
  count?: number;
};

type VideoResult = {
  video?: string;
  mime?: string;
  path?: string;
  directory?: string;
  filename?: string;
  size?: number;
};

let rememberedCreativeJobs: Partial<Record<CreativeTab, string>> = {};

function jobDone(job: BridgeJob | null): boolean {
  return Boolean(job && ['succeeded', 'success', 'completed', 'complete'].includes(String(job.status || '').toLowerCase()));
}

function jobFailed(job: BridgeJob | null): boolean {
  return Boolean(job && ['failed', 'error', 'cancelled', 'canceled'].includes(String(job.status || '').toLowerCase()));
}

function friendlyError(error: unknown, fallback: string): string {
  return parseErrorText(error) || fallback;
}

function imagePayload(state: {
  imageBaseUrl: string;
  imageApiKey: string;
  imageModel: string;
  imageSize: string;
  imageCount: number;
}) {
  return {
    baseUrl: state.imageBaseUrl.trim(),
    apiKey: state.imageApiKey.trim(),
    model: state.imageModel.trim(),
    size: state.imageSize,
    count: state.imageCount,
  };
}

function videoPayload(state: {
  videoProvider: VideoProviderId;
  videoBaseUrl: string;
  videoApiKey: string;
  videoModel: string;
  videoResolution: string;
  videoDuration: number;
  videoRatio: string;
}) {
  return {
    providerId: state.videoProvider,
    apiBase: state.videoBaseUrl.trim(),
    apiKey: state.videoApiKey.trim(),
    dashKey: state.videoApiKey.trim(),
    model: state.videoModel.trim(),
    mode: 't2v',
    resolution: state.videoResolution,
    duration: state.videoDuration,
    ratio: state.videoRatio,
  };
}

export const CreativeMediaPage: React.FC = () => {
  const [tab, setTab] = React.useState<CreativeTab>('image');
  const [config, setConfig] = React.useState<MediaConfigSnapshot | null>(null);
  const [loadingConfig, setLoadingConfig] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [activeJobs, setActiveJobs] = React.useState<Record<CreativeTab, BridgeJob | null>>({ image: null, video: null });
  const [imageResult, setImageResult] = React.useState<ImageResult | null>(null);
  const [videoResult, setVideoResult] = React.useState<VideoResult | null>(null);
  const pollRefs = React.useRef<Record<CreativeTab, number | null>>({ image: null, video: null });

  const [imageBaseUrl, setImageBaseUrl] = React.useState('https://api.heang.top/v1');
  const [imageApiKey, setImageApiKey] = React.useState('');
  const [imageModel, setImageModel] = React.useState('');
  const [imageSize, setImageSize] = React.useState('1024x1024');
  const [imageCount, setImageCount] = React.useState(1);
  const [imagePrompt, setImagePrompt] = React.useState('商务产品海报，米白深绿，界面清晰。');

  const [videoProvider, setVideoProvider] = React.useState<VideoProviderId>('dashscope');
  const [videoBaseUrl, setVideoBaseUrl] = React.useState('');
  const [videoApiKey, setVideoApiKey] = React.useState('');
  const [videoModel, setVideoModel] = React.useState('');
  const [videoResolution, setVideoResolution] = React.useState('720P');
  const [videoDuration, setVideoDuration] = React.useState(5);
  const [videoRatio, setVideoRatio] = React.useState('16:9');
  const [videoPrompt, setVideoPrompt] = React.useState('商务科技短片，多设备协同工作。');

  const activeJob = activeJobs[tab];
  const imageRunning = Boolean(activeJobs.image && !jobDone(activeJobs.image) && !jobFailed(activeJobs.image));
  const videoRunning = Boolean(activeJobs.video && !jobDone(activeJobs.video) && !jobFailed(activeJobs.video));
  const generationRunning = tab === 'image' ? imageRunning : videoRunning;
  const activeMessage = String(activeJob?.progress?.message || activeJob?.message || '生成中');

  const setKindJob = React.useCallback((kind: CreativeTab, job: BridgeJob | null) => {
    setActiveJobs((current) => ({ ...current, [kind]: job }));
  }, []);

  const applyConfig = React.useCallback((snapshot: MediaConfigSnapshot | null) => {
    if (!snapshot) return;
    setConfig(snapshot);
    if (snapshot.image?.baseUrl) setImageBaseUrl(snapshot.image.baseUrl);
    if (snapshot.image?.model) setImageModel(snapshot.image.model);
    if (snapshot.image?.size) setImageSize(snapshot.image.size);
    if (snapshot.image?.count) setImageCount(snapshot.image.count);
    if (snapshot.video?.providerId && ['dashscope', 'seedance', 'custom'].includes(String(snapshot.video.providerId))) {
      setVideoProvider(String(snapshot.video.providerId) as VideoProviderId);
    }
    if (snapshot.video?.apiBase) setVideoBaseUrl(snapshot.video.apiBase);
    if (snapshot.video?.model) setVideoModel(snapshot.video.model);
    if (snapshot.video?.resolution) setVideoResolution(snapshot.video.resolution);
    if (snapshot.video?.duration) setVideoDuration(snapshot.video.duration);
    if (snapshot.video?.ratio) setVideoRatio(snapshot.video.ratio);
  }, []);

  const refreshConfig = React.useCallback(async () => {
    setLoadingConfig(true);
    try {
      const response = await mediaApi.config();
      applyConfig(response.config);
    } catch (error) {
      showToast(friendlyError(error, '读取创作配置失败'), 'error');
    } finally {
      setLoadingConfig(false);
    }
  }, [applyConfig]);

  const stopPolling = React.useCallback((kind?: CreativeTab) => {
    const kinds: CreativeTab[] = kind ? [kind] : ['image', 'video'];
    kinds.forEach((item) => {
      if (pollRefs.current[item] !== null) {
        window.clearInterval(pollRefs.current[item] as number);
        pollRefs.current[item] = null;
      }
    });
  }, []);

  const applyFinishedJob = React.useCallback((job: BridgeJob, kind: CreativeTab) => {
    if (kind === 'image') {
      setImageResult((job.result || null) as ImageResult | null);
    } else {
      setVideoResult((job.result || null) as VideoResult | null);
    }
    delete rememberedCreativeJobs[kind];
  }, []);

  const pollJob = React.useCallback((jobId: string, kind: CreativeTab) => {
    stopPolling(kind);
    const tick = async () => {
      try {
        const { job } = await jobApi.get(jobId);
        setKindJob(kind, job);
        if (jobDone(job)) {
          stopPolling(kind);
          applyFinishedJob(job, kind);
          showToast(kind === 'image' ? '图片生成完成' : '视频生成完成', 'success');
        } else if (jobFailed(job)) {
          stopPolling(kind);
          delete rememberedCreativeJobs[kind];
          showToast(job.error || job.message || '生成失败', 'error');
        }
      } catch (error) {
        stopPolling(kind);
        showToast(friendlyError(error, '读取生成状态失败'), 'error');
      }
    };
    void tick();
    pollRefs.current[kind] = window.setInterval(tick, 1300);
  }, [applyFinishedJob, setKindJob, stopPolling]);

  React.useEffect(() => {
    void refreshConfig();
    (Object.entries(rememberedCreativeJobs) as Array<[CreativeTab, string]>).forEach(([kind, id]) => {
      if (id) pollJob(id, kind);
    });
    return () => stopPolling();
  }, [pollJob, refreshConfig, stopPolling]);

  const saveConfig = async () => {
    setSaving(true);
    try {
      const response = await mediaApi.saveConfig({
        image: imagePayload({ imageBaseUrl, imageApiKey, imageModel, imageSize, imageCount }),
        video: videoPayload({ videoProvider, videoBaseUrl, videoApiKey, videoModel, videoResolution, videoDuration, videoRatio }),
      });
      applyConfig(response.config);
      setImageApiKey('');
      setVideoApiKey('');
      showToast('创作配置已保存', 'success');
    } catch (error) {
      showToast(friendlyError(error, '保存创作配置失败'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const testConfig = async () => {
    setTesting(true);
    try {
      const response = await mediaApi.testConfig({
        kind: tab,
        image: imagePayload({ imageBaseUrl, imageApiKey, imageModel, imageSize, imageCount }),
        video: videoPayload({ videoProvider, videoBaseUrl, videoApiKey, videoModel, videoResolution, videoDuration, videoRatio }),
      });
      if (response.config) applyConfig(response.config);
      showToast(response.message || (response.ok ? '配置可用' : '配置未完整'), response.ok ? 'success' : 'error');
    } catch (error) {
      showToast(friendlyError(error, '测试配置失败'), 'error');
    } finally {
      setTesting(false);
    }
  };

  const submitImage = async () => {
    if (!imagePrompt.trim()) {
      showToast('请先填写图片提示词', 'error');
      return;
    }
    const optimistic: BridgeJob = {
      id: `pending_image_${Date.now()}`,
      kind: 'image',
      label: '图片生成',
      status: 'queued',
      message: '生成中',
      progress: { message: '正在提交图片生成任务', phase: 'submitting' },
    };
    setTab('image');
    setKindJob('image', optimistic);
    setImageResult(null);
    try {
      const params = imagePayload({ imageBaseUrl, imageApiKey, imageModel, imageSize, imageCount });
      await mediaApi.saveConfig({ image: params });
      const { jobId, job } = await imageApi.submit({ ...params, prompt: imagePrompt.trim() });
      rememberedCreativeJobs.image = jobId;
      setKindJob('image', job);
      pollJob(jobId, 'image');
    } catch (error) {
      delete rememberedCreativeJobs.image;
      setKindJob('image', { ...optimistic, status: 'failed', error: friendlyError(error, '图片生成提交失败') });
      showToast(friendlyError(error, '图片生成提交失败'), 'error');
    }
  };

  const submitVideo = async () => {
    if (!videoPrompt.trim()) {
      showToast('请先填写视频提示词', 'error');
      return;
    }
    const optimistic: BridgeJob = {
      id: `pending_video_${Date.now()}`,
      kind: 'video',
      label: '视频生成',
      status: 'queued',
      message: '生成中',
      progress: { message: '正在提交视频生成任务', phase: 'submitting' },
    };
    setTab('video');
    setKindJob('video', optimistic);
    setVideoResult(null);
    try {
      const params = videoPayload({ videoProvider, videoBaseUrl, videoApiKey, videoModel, videoResolution, videoDuration, videoRatio });
      await mediaApi.saveConfig({ video: params });
      const { jobId, job } = await videoApi.submit({ ...params, prompt: videoPrompt.trim() });
      rememberedCreativeJobs.video = jobId;
      setKindJob('video', job);
      pollJob(jobId, 'video');
    } catch (error) {
      delete rememberedCreativeJobs.video;
      setKindJob('video', { ...optimistic, status: 'failed', error: friendlyError(error, '视频生成提交失败') });
      showToast(friendlyError(error, '视频生成提交失败'), 'error');
    }
  };

  const copyPath = async (path?: string) => {
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      showToast('路径已复制', 'success');
    } catch {
      showToast(path, 'info');
    }
  };

  return (
    <div data-creative-media-page className="flex h-full flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-border px-8 py-7">
        <div className="text-sm font-black text-accent">创作</div>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[34px] font-black leading-tight text-text">生图 / 生视频</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">接入自己的模型服务，提交生成任务，并持续查看进度与结果。</p>
          </div>
          <div className="flex rounded-[14px] border border-border bg-surface-alt/60 p-1">
            <button
              data-creative-tab-image
              type="button"
              onClick={() => setTab('image')}
              className={`rounded-[10px] px-5 py-2 text-sm font-black transition ${tab === 'image' ? 'bg-accent text-accent-ink shadow-[0_12px_28px_rgba(8,60,49,0.18)]' : 'text-text-muted hover:text-text'}`}
            >
              生图
            </button>
            <button
              data-creative-tab-video
              type="button"
              onClick={() => setTab('video')}
              className={`rounded-[10px] px-5 py-2 text-sm font-black transition ${tab === 'video' ? 'bg-accent text-accent-ink shadow-[0_12px_28px_rgba(8,60,49,0.18)]' : 'text-text-muted hover:text-text'}`}
            >
              生视频
            </button>
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="rounded-[18px] border border-border bg-surface-alt/35 p-5 xl:order-2">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-black text-text">自定义 API</h2>
                <p className="mt-1 text-xs leading-5 text-text-muted">
                  {loadingConfig ? '正在读取配置...' : 'API Key 只写入本地配置，页面不会回显。'}
                </p>
              </div>
              <span className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-black text-text-muted">
                {tab === 'image' ? (config?.image?.hasApiKey ? '生图已配置' : '生图未配置') : (config?.video?.hasApiKey ? '视频已配置' : '视频未配置')}
              </span>
            </div>

            <details data-creative-config-details className="rounded-[14px] border border-border/70 bg-surface/55 p-4">
              <summary className="cursor-pointer select-none text-sm font-black text-text">
                展开配置
              </summary>

            {tab === 'image' ? (
              <div className="mt-4 grid gap-3">
                <label>
                  <FieldLabel text="Base URL" />
                  <Input value={imageBaseUrl} onChange={(event) => setImageBaseUrl(event.target.value)} placeholder="https://api.heang.top/v1" />
                </label>
                <label>
                  <FieldLabel text="API Key" />
                  <Input type="password" value={imageApiKey} onChange={(event) => setImageApiKey(event.target.value)} placeholder={config?.image?.hasApiKey ? '已保存，留空继续使用' : 'sk-...'} autoComplete="off" />
                </label>
                <label>
                  <FieldLabel text="模型" />
                  <Input value={imageModel} onChange={(event) => setImageModel(event.target.value)} placeholder="留空使用当前默认模型" />
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label>
                    <FieldLabel text="尺寸" />
                    <Select value={imageSize} onChange={(event) => setImageSize(event.target.value)} className="w-full">
                      <option value="1024x1024">1024x1024</option>
                      <option value="1024x1536">1024x1536</option>
                      <option value="1536x1024">1536x1024</option>
                    </Select>
                  </label>
                  <label>
                    <FieldLabel text="数量" />
                    <Input type="number" min={1} max={9} value={imageCount} onChange={(event) => setImageCount(Number(event.target.value || 1))} />
                  </label>
                </div>
              </div>
            ) : (
              <div className="mt-4 grid gap-3">
                <label>
                  <FieldLabel text="Provider" />
                  <Select value={videoProvider} onChange={(event) => setVideoProvider(event.target.value as VideoProviderId)} className="w-full">
                    <option value="dashscope">DashScope</option>
                    <option value="seedance">Seedance</option>
                    <option value="custom">自定义 OpenAI 兼容</option>
                  </Select>
                </label>
                <label>
                  <FieldLabel text="API Base" />
                  <Input value={videoBaseUrl} onChange={(event) => setVideoBaseUrl(event.target.value)} placeholder="留空使用 provider 默认地址" />
                </label>
                <label>
                  <FieldLabel text="API Key" />
                  <Input type="password" value={videoApiKey} onChange={(event) => setVideoApiKey(event.target.value)} placeholder={config?.video?.hasApiKey ? '已保存，留空继续使用' : 'sk-...'} autoComplete="off" />
                </label>
                <label>
                  <FieldLabel text="模型" />
                  <Input value={videoModel} onChange={(event) => setVideoModel(event.target.value)} placeholder="留空使用 provider 默认模型" />
                </label>
                <div className="grid grid-cols-3 gap-3">
                  <label>
                    <FieldLabel text="清晰度" />
                    <Select value={videoResolution} onChange={(event) => setVideoResolution(event.target.value)} className="w-full">
                      <option value="480P">480P</option>
                      <option value="720P">720P</option>
                      <option value="1080P">1080P</option>
                    </Select>
                  </label>
                  <label>
                    <FieldLabel text="秒数" />
                    <Input type="number" min={1} max={30} value={videoDuration} onChange={(event) => setVideoDuration(Number(event.target.value || 5))} />
                  </label>
                  <label>
                    <FieldLabel text="比例" />
                    <Select value={videoRatio} onChange={(event) => setVideoRatio(event.target.value)} className="w-full">
                      <option value="16:9">16:9</option>
                      <option value="9:16">9:16</option>
                      <option value="1:1">1:1</option>
                    </Select>
                  </label>
                </div>
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-3">
              <Button variant="primary" onClick={saveConfig} disabled={saving || testing || generationRunning}>
                {saving ? '保存中...' : '保存配置'}
              </Button>
              <Button variant="quiet" onClick={testConfig} disabled={saving || testing || generationRunning}>
                {testing ? '检测中...' : '测试配置'}
              </Button>
            </div>
            </details>
          </section>

          <section className="rounded-[18px] border border-border bg-surface p-5 shadow-[0_18px_60px_rgba(5,35,29,0.08)] xl:order-1">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div>
                <h2 className="text-lg font-black text-text">{tab === 'image' ? '图片生成' : '视频生成'}</h2>
                <p className="mt-1 text-xs leading-5 text-text-muted">提交后会持续轮询本地任务状态，切页回来仍可继续查看。</p>
                <label className="mt-5 block">
                  <FieldLabel text="提示词" required />
                  <TextArea
                    value={tab === 'image' ? imagePrompt : videoPrompt}
                    onChange={(event) => (tab === 'image' ? setImagePrompt(event.target.value) : setVideoPrompt(event.target.value))}
                    rows={8}
                    placeholder="描述你想生成的画面..."
                  />
                </label>
                <div className="mt-4 flex flex-wrap gap-3">
                  {tab === 'image' ? (
                    <Button variant="primary" onClick={submitImage} disabled={imageRunning}>
                      {imageRunning ? '生成中...' : '生成图片'}
                    </Button>
                  ) : (
                    <Button variant="primary" onClick={submitVideo} disabled={videoRunning}>
                      {videoRunning ? '生成中...' : '生成视频'}
                    </Button>
                  )}
                  <Button variant="quiet" onClick={() => void refreshConfig()} disabled={generationRunning || loadingConfig}>
                    刷新配置
                  </Button>
                </div>
              </div>

              <div className="rounded-[16px] border border-border bg-surface-alt/35 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-black text-text">任务状态</span>
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${jobFailed(activeJob) ? 'bg-status-danger/12 text-status-danger' : generationRunning ? 'bg-accent-soft text-accent' : 'bg-surface text-text-muted'}`}>
                    {generationRunning ? '生成中' : jobFailed(activeJob) ? '失败' : jobDone(activeJob) ? '完成' : '待提交'}
                  </span>
                </div>
                <div className="mt-5 flex min-h-[178px] flex-col items-center justify-center rounded-[14px] border border-border/70 bg-surface/70 p-5 text-center">
                  {generationRunning ? (
                    <>
                      <div className="generationPulse relative h-16 w-16 rounded-full border border-accent/30 bg-accent-soft" />
                      <div className="mt-4 text-sm font-black text-text">{activeMessage}</div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border">
                        <div className="creative-progress-bar h-full w-2/3 rounded-full bg-accent" />
                      </div>
                    </>
                  ) : jobFailed(activeJob) ? (
                    <div className="text-sm leading-6 text-status-danger">{activeJob?.error || activeJob?.message || '生成失败'}</div>
                  ) : (
                    <div className="text-sm leading-6 text-text-muted">提交任务后会显示阶段状态。</div>
                  )}
                </div>
                {activeJob?.progress?.history?.length ? (
                  <div className="mt-4 max-h-28 space-y-2 overflow-auto text-xs leading-5 text-text-muted">
                    {activeJob.progress.history.slice(-5).map((entry, index) => (
                      <div key={`${entry.updatedAt || index}-${entry.message}`}>{entry.message}</div>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="mt-6 border-t border-border pt-5">
              <h3 className="text-base font-black text-text">结果</h3>
              {tab === 'image' ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  {imageResult?.images?.length ? imageResult.images.map((image, index) => (
                    <div key={index} className="overflow-hidden rounded-[14px] border border-border bg-surface-alt/40">
                      <img src={`data:image/png;base64,${image}`} alt={`LOOM generated ${index + 1}`} className="aspect-square w-full object-cover" />
                      <div className="flex items-center justify-between gap-3 px-3 py-2 text-xs text-text-muted">
                        <span className="truncate">{imageResult.files?.[index]?.filename || `image-${index + 1}.png`}</span>
                        <button type="button" className="font-black text-accent" onClick={() => void copyPath(imageResult.files?.[index]?.path)}>复制路径</button>
                      </div>
                    </div>
                  )) : (
                    <div className="rounded-[14px] border border-dashed border-border p-6 text-sm text-text-muted">暂无图片结果。</div>
                  )}
                </div>
              ) : (
                <div className="mt-4">
                  {videoResult?.video ? (
                    <div className="overflow-hidden rounded-[14px] border border-border bg-surface-alt/40">
                      <video src={`data:${videoResult.mime || 'video/mp4'};base64,${videoResult.video}`} controls className="aspect-video w-full bg-black" />
                      <div className="flex items-center justify-between gap-3 px-3 py-2 text-xs text-text-muted">
                        <span className="truncate">{videoResult.filename || 'loom-video.mp4'}</span>
                        <button type="button" className="font-black text-accent" onClick={() => void copyPath(videoResult.path)}>复制路径</button>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-[14px] border border-dashed border-border p-6 text-sm text-text-muted">暂无视频结果。</div>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};
