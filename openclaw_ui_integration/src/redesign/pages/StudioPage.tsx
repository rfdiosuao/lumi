import React from 'react';
import { Film, ImagePlus, RefreshCcw, Settings2, Upload, X } from 'lucide-react';
import { Button, Chip, EmptyState, Field, Input, InlineState, Panel, SectionHeader, Select, Tabs, TextArea } from '../components/ui';
import { generateImage, generateVideo, loadStudioSnapshot, requestPhoneData } from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import type { ImageResult, VideoResult } from '../types';
import { usePreviewStore } from '../store/appStore';

type StudioTab = 'image' | 'video';

const IMAGE_SIZE_OPTIONS = [
  { value: '1024x1024', label: '1:1 · 1024x1024' },
  { value: '1536x1024', label: '3:2 · 1536x1024' },
  { value: '1024x1536', label: '2:3 · 1024x1536' },
  { value: '1792x1024', label: '16:9 · 1792x1024' },
  { value: '1024x1792', label: '9:16 · 1024x1792' },
];

const VIDEO_MODE_OPTIONS = [
  { value: 't2v', label: '文生视频' },
  { value: 'i2v', label: '图生视频' },
];

const VIDEO_RESOLUTION_OPTIONS = [
  { value: '480P', label: '480P' },
  { value: '720P', label: '720P' },
  { value: '1080P', label: '1080P' },
];

const VIDEO_RATIO_OPTIONS = [
  { value: '16:9', label: '16:9 横屏' },
  { value: '9:16', label: '9:16 竖屏' },
  { value: '1:1', label: '1:1 方图' },
  { value: '4:3', label: '4:3 标准' },
  { value: '3:4', label: '3:4 竖版' },
  { value: '21:9', label: '21:9 宽银幕' },
];

export function StudioPage() {
  const settings = usePreviewStore((state) => state.settings);
  const navigate = usePreviewStore((state) => state.navigate);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadStudioSnapshot(settings), [settings]);
  const [tab, setTab] = React.useState<StudioTab>('image');
  const [imagePrompt, setImagePrompt] = React.useState('一个安静、克制、有玻璃质感的 OpenClaw 启动器界面，冷光、清晰排版、舒适的背景');
  const [imageSize, setImageSize] = React.useState('1024x1024');
  const [imageCount, setImageCount] = React.useState(1);
  const [imageEditPath, setImageEditPath] = React.useState('');
  const [imageReferenceName, setImageReferenceName] = React.useState('');
  const [videoPrompt, setVideoPrompt] = React.useState('OpenClaw 启动器的轻微镜头运动，玻璃面板缓慢浮现，动效克制');
  const [videoMode, setVideoMode] = React.useState('t2v');
  const [videoResolution, setVideoResolution] = React.useState('720P');
  const [videoDuration, setVideoDuration] = React.useState(5);
  const [videoRatio, setVideoRatio] = React.useState('16:9');
  const [videoImagePath, setVideoImagePath] = React.useState('');
  const [videoReferenceName, setVideoReferenceName] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [selectedImage, setSelectedImage] = React.useState<ImageResult | null>(null);
  const [selectedVideo, setSelectedVideo] = React.useState<VideoResult | null>(null);
  const [imageHistory, setImageHistory] = React.useState<ImageResult[]>([]);
  const [videoHistory, setVideoHistory] = React.useState<VideoResult[]>([]);
  const imageReferenceInputRef = React.useRef<HTMLInputElement>(null);
  const videoReferenceInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!data) return;
    if (!imageHistory.length && data.imageHistory.length) setImageHistory(data.imageHistory);
    if (!videoHistory.length && data.videoHistory.length) setVideoHistory(data.videoHistory);
    if (!selectedImage && data.imageHistory.length) setSelectedImage(data.imageHistory[0]);
    if (!selectedVideo && data.videoHistory.length) setSelectedVideo(data.videoHistory[0]);
  }, [data, imageHistory.length, videoHistory.length, selectedImage, selectedVideo]);

  const importImagesToPhone = React.useCallback(async (result: ImageResult) => {
    const phoneBaseUrl = settings.phoneBaseUrl.trim();
    const phoneToken = settings.phoneToken.trim();
    if (!phoneBaseUrl || !phoneToken || !result.previewUrls.length) return 0;

    let imported = 0;
    for (let index = 0; index < result.previewUrls.length; index += 1) {
      const dataUrl = result.previewUrls[index];
      if (!dataUrl.startsWith('data:image/')) continue;
      await requestPhoneData(
        settings,
        { baseUrl: phoneBaseUrl, token: phoneToken },
        '/api/lumi/media/import_image',
        'POST',
        {
          dataUrl,
          album: 'OpenClaw',
          filename: result.files[index]?.filename || 'openclaw-image-' + Date.now() + '-' + (index + 1) + '.png',
        },
      );
      imported += 1;
    }
    return imported;
  }, [settings]);

  const importVideoToPhone = React.useCallback(async (result: VideoResult) => {
    const phoneBaseUrl = settings.phoneBaseUrl.trim();
    const phoneToken = settings.phoneToken.trim();
    const dataUrl = result.previewUrl;
    if (!phoneBaseUrl || !phoneToken || !dataUrl.startsWith('data:video/')) return false;

    await requestPhoneData(
      settings,
      { baseUrl: phoneBaseUrl, token: phoneToken },
      '/api/lumi/media/import_video',
      'POST',
      {
        dataUrl,
        album: 'OpenClaw',
        filename: result.file?.filename || 'openclaw-video-' + Date.now() + '.mp4',
      },
    );
    return true;
  }, [settings]);

  const handleGenerateImage = async () => {
    const baseUrl = data?.imageDefaults.baseUrl.trim() || '';
    const apiKey = data?.imageDefaults.apiKey.trim() || '';
    if (!baseUrl || !apiKey) {
      pushToast({ tone: 'danger', title: '缺少图像网关', detail: '请到统一设置里填写图像生成 API。' });
      return;
    }
    setBusy(true);
    try {
      const result = await generateImage(settings, {
        baseUrl,
        apiKey,
        prompt: imagePrompt.trim(),
        size: imageSize,
        count: imageCount,
        editImagePath: imageEditPath.trim() || undefined,
        model: data?.imageDefaults.model,
      });
      setSelectedImage(result.data);
      setImageHistory((history) => [result.data, ...history].slice(0, 6));
      pushToast({ tone: 'ok', title: '图像已生成', detail: String(result.data.count) + ' 个结果' });
      try {
        const imported = await importImagesToPhone(result.data);
        if (imported) {
          pushToast({ tone: 'ok', title: '已导入手机相册', detail: 'Pictures/OpenClaw · ' + imported + ' 张' });
        }
      } catch (err) {
        pushToast({ tone: 'warn', title: '手机相册导入失败', detail: String(err) });
      }
    } catch (err) {
      pushToast({ tone: 'danger', title: '图像生成失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateVideo = async () => {
    const apiBase = data?.videoDefaults.apiBase.trim() || '';
    const apiKey = data?.videoDefaults.apiKey.trim() || '';
    const model = data?.videoDefaults.model.trim() || '';
    const providerId = inferVideoProviderId(data?.videoDefaults.providerId || '', apiBase, model);
    if (!apiBase || !apiKey) {
      pushToast({ tone: 'danger', title: '缺少视频网关', detail: '请到统一设置里填写视频生成 API。' });
      return;
    }
    setBusy(true);
    try {
      const result = await generateVideo(settings, {
        providerId,
        apiBase,
        model: model || (providerId === 'agnes' ? 'agnes-video-v2.0' : ''),
        dashKey: apiKey,
        prompt: videoPrompt.trim(),
        mode: videoMode,
        resolution: videoResolution,
        duration: videoDuration,
        ratio: videoRatio,
        imagePath: videoImagePath.trim() || undefined,
      });
      setSelectedVideo(result.data);
      setVideoHistory((history) => [result.data, ...history].slice(0, 6));
      void importVideoToPhone(result.data)
        .then((imported) => {
          if (imported) {
            pushToast({ tone: 'ok', title: '视频已导入手机', detail: 'Movies/OpenClaw · ' + (result.data.file?.filename || 'openclaw-video.mp4') });
          }
        })
        .catch((err) => {
          pushToast({ tone: 'warn', title: '手机视频导入失败', detail: String(err) });
        });
      pushToast({ tone: 'ok', title: '视频已生成', detail: result.data.file?.filename || '预览已就绪' });
    } catch (err) {
      pushToast({ tone: 'danger', title: '视频生成失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleReferenceFile = async (event: React.ChangeEvent<HTMLInputElement>, kind: 'image' | 'video') => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await readFileAsDataUrl(file);
      if (kind === 'image') {
        setImageEditPath(dataUrl);
        setImageReferenceName(file.name);
      } else {
        setVideoImagePath(dataUrl);
        setVideoReferenceName(file.name);
        setVideoMode('i2v');
      }
    } catch (err) {
      pushToast({ tone: 'danger', title: '参考图读取失败', detail: String(err) });
    } finally {
      input.value = '';
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">生成任务</div>
          <h1>图像和视频生成保留，但密钥不再散落在页面里。</h1>
          <p>这里只做任务提交和结果预览；网关、模型和密钥统一从设置页读取。</p>
        </div>
        <div className="hero-actions">
          <Button variant="primary" icon={RefreshCcw} onClick={refresh}>刷新默认值</Button>
          <Button variant="secondary" icon={Settings2} onClick={() => navigate('settings')}>打开设置</Button>
          <Chip tone={data?.source === 'live' ? 'ok' : 'warn'}>{sourceLabel(data?.source || 'mock')}</Chip>
        </div>
      </section>

      <section className="content-grid content-grid-studio">
        <Panel className="surface-panel">
          <SectionHeader
            eyebrow="网关"
            title="已解析的默认配置"
            subtitle="这些值来自统一设置和配置文件，不在当前页面临时改写。"
          />
          {loading ? (
            <div className="panel-loading-inline">正在读取生成配置...</div>
          ) : error ? (
            <InlineState tone="danger" title="生成配置读取失败" description={error} />
          ) : data ? (
            <div className="detail-stack">
              {tab === 'image' ? (
                <>
                  <div className="detail-row"><span className="detail-label">图像地址</span><span className="detail-value">{data.imageDefaults.baseUrl || '暂无'}</span></div>
                  <div className="detail-row"><span className="detail-label">图像密钥</span><span className="detail-value">{data.imageDefaults.apiKeyMasked}</span></div>
                  <div className="detail-row"><span className="detail-label">图像模型</span><span className="detail-value">{data.imageDefaults.model || 'gpt-image-2'}</span></div>
                </>
              ) : (
                <>
                  <div className="detail-row"><span className="detail-label">视频地址</span><span className="detail-value">{data.videoDefaults.apiBase || '暂无'}</span></div>
                  <div className="detail-row"><span className="detail-label">视频密钥</span><span className="detail-value">{data.videoDefaults.apiKeyMasked}</span></div>
                  <div className="detail-row"><span className="detail-label">视频模型</span><span className="detail-value">{data.videoDefaults.model || 'agnes-video-v2.0'}</span></div>
                </>
              )}
              <div className="detail-row"><span className="detail-label">服务商</span><span className="detail-value">{inferVideoProviderId(data.videoDefaults.providerId, data.videoDefaults.apiBase, data.videoDefaults.model)}</span></div>
              <div className="detail-row"><span className="detail-label">来源</span><span className="detail-value">{data.gateway.mode}</span></div>
            </div>
          ) : null}
        </Panel>

        <Panel className="surface-panel surface-panel-wide">
          <SectionHeader
            eyebrow="工作台"
            title="图像 / 视频工作台"
            subtitle="提示词、参数、结果预览和设置跳转分开，便于排错。"
            action={
              <Tabs
                value={tab}
                onChange={(value) => setTab(value as StudioTab)}
                items={[
                  { key: 'image', label: '图像' },
                  { key: 'video', label: '视频' },
                ]}
              />
            }
          />

          {tab === 'image' ? (
            <div className="studio-layout">
              <div className="studio-form">
                <Field label="提示词" hint="映射到 /api/image/generate.prompt">
                  <TextArea rows={7} value={imagePrompt} onChange={(event) => setImagePrompt(event.target.value)} />
                </Field>
                <div className="form-grid">
                  <Field label="尺寸">
                    <Select value={imageSize} onChange={(event) => setImageSize(event.target.value)}>
                      {IMAGE_SIZE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </Select>
                  </Field>
                  <Field label="数量">
                    <Input type="number" min={1} max={4} value={imageCount} onChange={(event) => setImageCount(Number(event.target.value) || 1)} />
                  </Field>
                </div>
                <Field label="参考图" hint="可选，选择本地图片后自动转为 data URL">
                  <input
                    ref={imageReferenceInputRef}
                    type="file"
                    accept="image/*"
                    className="visually-hidden-file"
                    onChange={(event) => void handleReferenceFile(event, 'image')}
                  />
                  <div className="upload-row">
                    <Button type="button" variant="secondary" icon={Upload} onClick={() => imageReferenceInputRef.current?.click()}>选择图片</Button>
                    {imageReferenceName ? <Chip tone="ok" className="upload-chip">{imageReferenceName}</Chip> : <span className="upload-hint">未选择参考图</span>}
                    {imageEditPath ? <Button type="button" variant="quiet" icon={X} onClick={() => { setImageEditPath(''); setImageReferenceName(''); }}>清除</Button> : null}
                  </div>
                </Field>
                <div className="button-row">
                  <Button variant="primary" icon={ImagePlus} onClick={handleGenerateImage} disabled={busy}>生成图像</Button>
                </div>
              </div>

              <div className="studio-preview">
                <SectionHeader eyebrow="结果" title="图像结果" subtitle="最新结果在上方，历史结果在下方。" />
                {selectedImage ? (
                  <div className="result-grid">
                    {selectedImage.previewUrls.map((url, index) => (
                      <button type="button" key={url + index} className="result-card" onClick={() => setSelectedImage(selectedImage)}>
                        <img src={url} alt={'generated-' + index} />
                        <div className="result-meta">
                          <span>{selectedImage.size}</span>
                          <span>{selectedImage.files[index]?.filename || '图像 ' + (index + 1)}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="暂无图像" description="生成后会显示在预览区。" />
                )}
                {imageHistory.length ? (
                  <div className="history-strip">
                    {imageHistory.map((item, index) => (
                      <button key={item.prompt + '-' + index} type="button" className="history-card" onClick={() => setSelectedImage(item)}>
                        <img src={item.previewUrls[0]} alt={item.prompt} />
                        <span>{item.files[0]?.filename || '结果 ' + (index + 1)}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="studio-layout">
              <div className="studio-form">
                <Field label="提示词" hint="映射到 /api/video/generate.prompt">
                  <TextArea rows={7} value={videoPrompt} onChange={(event) => setVideoPrompt(event.target.value)} />
                </Field>
                <div className="form-grid">
                  <Field label="模式">
                    <Select value={videoMode} onChange={(event) => setVideoMode(event.target.value)}>
                      {VIDEO_MODE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </Select>
                  </Field>
                  <Field label="分辨率">
                    <Select value={videoResolution} onChange={(event) => setVideoResolution(event.target.value)}>
                      {VIDEO_RESOLUTION_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </Select>
                  </Field>
                  <Field label="时长">
                    <Input type="number" min={1} max={30} value={videoDuration} onChange={(event) => setVideoDuration(Number(event.target.value) || 5)} />
                  </Field>
                  <Field label="比例">
                    <Select value={videoRatio} onChange={(event) => setVideoRatio(event.target.value)}>
                      {VIDEO_RATIO_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </Select>
                  </Field>
                </div>
                <Field label="参考图" hint="可选，选择后自动切换为图生视频">
                  <input
                    ref={videoReferenceInputRef}
                    type="file"
                    accept="image/*"
                    className="visually-hidden-file"
                    onChange={(event) => void handleReferenceFile(event, 'video')}
                  />
                  <div className="upload-row">
                    <Button type="button" variant="secondary" icon={Upload} onClick={() => videoReferenceInputRef.current?.click()}>选择图片</Button>
                    {videoReferenceName ? <Chip tone="ok" className="upload-chip">{videoReferenceName}</Chip> : <span className="upload-hint">未选择参考图</span>}
                    {videoImagePath ? <Button type="button" variant="quiet" icon={X} onClick={() => { setVideoImagePath(''); setVideoReferenceName(''); }}>清除</Button> : null}
                  </div>
                </Field>
                <div className="button-row">
                  <Button variant="primary" icon={Film} onClick={handleGenerateVideo} disabled={busy}>生成视频</Button>
                </div>
              </div>

              <div className="studio-preview">
                <SectionHeader eyebrow="结果" title="视频结果" subtitle="真实模式返回 mp4；Agnes 视频会自动按任务接口轮询。" />
                {selectedVideo ? (
                  <div className="video-preview-shell">
                    {selectedVideo.mime.startsWith('video/') ? (
                      <video controls src={selectedVideo.previewUrl} className="video-preview" />
                    ) : (
                      <img src={selectedVideo.previewUrl} alt={selectedVideo.prompt} className="video-preview" />
                    )}
                    <div className="result-meta-grid">
                      <div><span>模式</span><strong>{selectedVideo.mode}</strong></div>
                      <div><span>分辨率</span><strong>{selectedVideo.resolution}</strong></div>
                      <div><span>时长</span><strong>{selectedVideo.duration}s</strong></div>
                      <div><span>比例</span><strong>{selectedVideo.ratio}</strong></div>
                      <div><span>Mime</span><strong>{selectedVideo.mime}</strong></div>
                      <div><span>文件</span><strong>{selectedVideo.file?.filename || '预览图'}</strong></div>
                    </div>
                  </div>
                ) : (
                  <EmptyState title="暂无视频" description="生成后会显示在这里。" />
                )}
                {videoHistory.length ? (
                  <div className="history-strip">
                    {videoHistory.map((item, index) => (
                      <button key={item.prompt + '-' + index} type="button" className="history-card" onClick={() => setSelectedVideo(item)}>
                        {item.mime.startsWith('video/') ? <video src={item.previewUrl} muted /> : <img src={item.previewUrl} alt={item.prompt} />}
                        <span>{item.file?.filename || '片段 ' + (index + 1)}</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </Panel>
      </section>
    </div>
  );
}

function inferVideoProviderId(providerId: string, apiBase: string, model: string) {
  const id = providerId.trim().toLowerCase();
  const base = apiBase.trim().toLowerCase();
  const modelId = model.trim().toLowerCase();
  if (id === 'agnes' || base.includes('agnes-ai.com') || modelId.startsWith('agnes-video')) return 'agnes';
  if (id === 'seedance' || base.includes('volces.com') || modelId.includes('seedance')) return 'seedance';
  if (id === 'custom') return 'custom';
  return 'dashscope';
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('file_read_failed'));
    reader.readAsDataURL(file);
  });
}

function sourceLabel(value: string) {
  const map: Record<string, string> = {
    mock: '预览',
    live: '真实接口',
    mixed: '混合',
  };
  return map[value] || value;
}
