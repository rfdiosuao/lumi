import React, { useState } from 'react';
import { convertFileSrc, invoke } from '@tauri-apps/api/core';
import { Button, FieldLabel, Input, Loading, Select, TextArea, showToast } from '../common';
import { videoApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const RESOLUTIONS = ['720P', '1080P'];
const DURATIONS = [5, 10];
const RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4'];

type GeneratedVideo = {
  previewUrl: string;
  downloadUrl: string;
  blobUrl?: string;
  mime: string;
  size: number;
  path?: string;
  directory?: string;
  filename?: string;
};

function createVideoBlobUrl(base64: string, mime = 'video/mp4') {
  const cleanBase64 = base64.includes(',') ? base64.split(',').pop() || '' : base64;
  const binary = atob(cleanBase64);
  const chunkSize = 32768;
  const chunks: BlobPart[] = [];

  for (let offset = 0; offset < binary.length; offset += chunkSize) {
    const slice = binary.slice(offset, offset + chunkSize);
    const bytes = new Uint8Array(slice.length);
    for (let i = 0; i < slice.length; i += 1) {
      bytes[i] = slice.charCodeAt(i);
    }
    chunks.push(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  }

  const blob = new Blob(chunks, { type: mime });
  return { url: URL.createObjectURL(blob), size: blob.size };
}

function createGeneratedVideo(resp: {
  video?: string;
  mime?: string;
  size?: number;
  path?: string;
  directory?: string;
  filename?: string;
}): GeneratedVideo {
  const mime = resp.mime || 'video/mp4';
  const blobVideo = resp.video ? createVideoBlobUrl(resp.video, mime) : null;
  const previewUrl = resp.path ? convertFileSrc(resp.path) : blobVideo?.url || '';

  if (!previewUrl) {
    throw { error: '生成成功但没有可预览的视频地址' };
  }

  return {
    previewUrl,
    downloadUrl: blobVideo?.url || previewUrl,
    blobUrl: blobVideo?.url,
    mime,
    size: resp.size || blobVideo?.size || 0,
    path: resp.path,
    directory: resp.directory,
    filename: resp.filename,
  };
}

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export const VideoPage: React.FC = () => {
  const [dashKey, setDashKey] = useState('');
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState<'t2v' | 'i2v'>('t2v');
  const [resolution, setResolution] = useState('720P');
  const [duration, setDuration] = useState(5);
  const [ratio, setRatio] = useState('16:9');
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState('');
  const [resultVideo, setResultVideo] = useState<GeneratedVideo | null>(null);
  const [videoError, setVideoError] = useState('');

  const appendLog = useLogStore((s) => s.append);

  React.useEffect(() => () => {
    if (resultVideo?.blobUrl) {
      URL.revokeObjectURL(resultVideo.blobUrl);
    }
  }, [resultVideo?.blobUrl]);

  const handlePickImage = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (readerEvent) => {
        const dataUrl = readerEvent.target?.result as string;
        setImageBase64(dataUrl);
        setImagePreview(dataUrl);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  };

  const handleGenerate = async () => {
    const cleanDashKey = dashKey.trim();
    const cleanPrompt = prompt.trim();
    if (!cleanDashKey || !cleanPrompt) {
      showToast('请填写 DashScope API Key 和提示词', 'error');
      return;
    }
    if (mode === 'i2v' && !imageBase64) {
      showToast('图生视频需要上传参考图', 'error');
      return;
    }

    setGenerating(true);
    setResultVideo(null);
    setVideoError('');
    setProgress('正在提交任务...');

    try {
      const resp = await videoApi.generate({
        dashKey: cleanDashKey,
        prompt: cleanPrompt,
        mode,
        resolution,
        duration,
        ratio,
        imagePath: mode === 'i2v' ? imageBase64 || undefined : undefined,
      });

      if (!resp.video) {
        throw { error: '生成成功但没有返回视频数据' };
      }

      const result = createGeneratedVideo(resp);
      setResultVideo(result);

      const savedMessage = resp.path ? `视频生成成功，已保存到：${resp.path}` : '视频生成成功';
      showToast(savedMessage, 'success');
      appendLog(`[视频] 生成成功，大小 ${formatBytes(result.size)}${resp.path ? `，保存路径：${resp.path}` : ''}\n`);
    } catch (error: any) {
      const message = error?.error || '生成失败';
      showToast(message, 'error');
      appendLog(`[视频] 生成失败: ${message}\n`);
    } finally {
      setGenerating(false);
      setProgress('');
    }
  };

  const handleOpenVideoDir = async () => {
    if (!resultVideo?.directory) {
      showToast('暂无保存目录', 'info');
      return;
    }
    try {
      await invoke('open_path', { path: resultVideo.directory });
      showToast(`已打开目录：${resultVideo.directory}`, 'info');
    } catch (error: any) {
      showToast(`打开目录失败：${error?.error || error}`, 'error');
    }
  };

  const handleDownloadClick = () => {
    if (resultVideo?.path) {
      showToast(`视频已保存到：${resultVideo.path}`, 'info');
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-surface">
      <div className="shrink-0 border-b border-border bg-surface px-8 py-6">
        <h1 className="text-xl font-semibold text-text">AI 视频</h1>
        <p className="mt-1 text-sm text-text-muted">文生视频 / 图生视频</p>
      </div>

      <div className="px-8 py-6">
        <div className="max-w-3xl rounded-lg border border-border bg-surface-alt p-6">
          <div className="space-y-4">
            <div>
              <FieldLabel text="DashScope API Key" required />
              <Input
                type="password"
                value={dashKey}
                onChange={(event) => setDashKey(event.target.value)}
                placeholder="每次启动后需手动填写，不会保存到本地"
                autoComplete="off"
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setMode('t2v')}
                className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${mode === 't2v' ? 'bg-accent text-white' : 'border border-border bg-surface text-text'}`}
              >
                文生视频
              </button>
              <button
                onClick={() => setMode('i2v')}
                className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${mode === 'i2v' ? 'bg-accent text-white' : 'border border-border bg-surface text-text'}`}
              >
                图生视频
              </button>
            </div>

            <div>
              <FieldLabel text="提示词" required />
              <TextArea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                rows={4}
                placeholder="描述你想要生成的视频..."
              />
            </div>

            {mode === 'i2v' && (
              <div>
                <FieldLabel text="首帧图片" />
                <div className="flex items-center gap-3">
                  <Button onClick={handlePickImage} variant="quiet">
                    {imageBase64 ? '已选择图片' : '选择图片'}
                  </Button>
                  {imagePreview && <img src={imagePreview} alt="preview" className="h-16 w-16 rounded object-cover" />}
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-4">
              <div>
                <FieldLabel text="分辨率" />
                <Select value={resolution} onChange={(event) => setResolution(event.target.value)} className="w-full">
                  {RESOLUTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
                </Select>
              </div>
              <div>
                <FieldLabel text="时长" />
                <Select value={duration} onChange={(event) => setDuration(Number(event.target.value))} className="w-full">
                  {DURATIONS.map((item) => <option key={item} value={item}>{item}秒</option>)}
                </Select>
              </div>
              <div>
                <FieldLabel text="比例" />
                <Select value={ratio} onChange={(event) => setRatio(event.target.value)} className="w-full">
                  {RATIOS.map((item) => <option key={item} value={item}>{item}</option>)}
                </Select>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex gap-3">
          <Button onClick={handleGenerate} variant="primary" disabled={generating}>
            {generating ? '生成中...' : '生成视频'}
          </Button>
        </div>

        {generating && <Loading text={progress || '正在生成视频...'} />}

        {resultVideo && (
          <div className="mt-8 max-w-3xl">
            <video
              key={resultVideo.previewUrl}
              controls
              preload="metadata"
              className="aspect-video w-full rounded-lg border border-border bg-black"
              onError={() => setVideoError('视频已生成并保存，但当前播放器无法读取本地预览。请点击下载视频或打开保存目录查看。')}
            >
              <source src={resultVideo.previewUrl} type={resultVideo.mime || 'video/mp4'} />
            </video>

            <div className="mt-3 space-y-2 text-sm text-text-muted">
              <div>大小：{formatBytes(resultVideo.size)}</div>
              {resultVideo.path && <div className="break-all">保存路径：{resultVideo.path}</div>}
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
              <a
                href={resultVideo.downloadUrl}
                download={resultVideo.filename || `lumi-video-${Date.now()}.mp4`}
                onClick={handleDownloadClick}
                className="text-accent hover:underline"
              >
                下载视频
              </a>
              {resultVideo.directory && (
                <button onClick={handleOpenVideoDir} className="text-accent hover:underline">
                  打开保存目录
                </button>
              )}
            </div>

            {videoError && (
              <div className="mt-3 rounded-md border border-status-danger/30 bg-status-danger/10 px-4 py-3 text-sm text-status-danger">
                {videoError}
              </div>
            )}
          </div>
        )}

        {!resultVideo && !generating && (
          <div className="mt-8 py-12 text-center text-sm text-text-muted">
            生成结果将显示在这里
          </div>
        )}
      </div>
    </div>
  );
};
