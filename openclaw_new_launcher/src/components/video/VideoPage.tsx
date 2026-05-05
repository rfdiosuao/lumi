import React, { useState } from 'react';
import { Button, Input, TextArea, Select, Loading, showToast, FieldLabel } from '../common';
import { videoApi, configApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const RESOLUTIONS = ['720P', '1080P'];
const DURATIONS = [5, 10];
const RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4'];

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
  const [resultVideo, setResultVideo] = useState<string | null>(null);

  const appendLog = useLogStore((s) => s.append);

  const loadConfig = async () => {
    try {
      const resp = await configApi.read('video_config.json', {});
      const data = resp.data as any;
      if (data?.dashKey) setDashKey(data.dashKey);
    } catch (e) {
      appendLog('[视频] 配置加载失败: ' + e + '\n');
    }
  };

  React.useEffect(() => { loadConfig(); }, []);

  const handlePickImage = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const dataUrl = ev.target?.result as string;
          setImageBase64(dataUrl);
          setImagePreview(dataUrl);
        };
        reader.readAsDataURL(file);
      }
    };
    input.click();
  };

  const handleGenerate = async () => {
    if (!dashKey || !prompt) {
      showToast('请填写 API Key 和提示词', 'error');
      return;
    }
    if (mode === 'i2v' && !imageBase64) {
      showToast('图生视频需要上传参考图', 'error');
      return;
    }

    setGenerating(true);
    setResultVideo(null);
    setProgress('正在提交任务...');

    try {
      // Save config
      await configApi.write('video_config.json', { dashKey });

      const resp = await videoApi.generate({
        dashKey,
        prompt,
        mode,
        resolution,
        duration,
        ratio,
        imagePath: mode === 'i2v' ? imageBase64 || undefined : undefined,
      });

      if (resp.video) {
        setResultVideo(`data:video/mp4;base64,${resp.video}`);
        showToast('视频生成成功', 'success');
        appendLog('[生视频] 生成成功\n');
      }
    } catch (e: any) {
      showToast(e?.error || '生成失败', 'error');
      appendLog(`[生视频] 失败: ${e?.error}\n`);
    } finally {
      setGenerating(false);
      setProgress('');
    }
  };

  return (
    <div className="flex flex-col h-full bg-surface overflow-y-auto">
      <div className="flex-shrink-0 px-8 py-6 border-b border-border bg-surface">
        <h1 className="text-xl font-semibold text-text">AI 视频</h1>
        <p className="text-sm text-text-muted mt-1">文生视频 / 图生视频</p>
      </div>

      <div className="px-8 py-6">
        <div className="bg-surface-alt rounded-lg border border-border p-6 max-w-3xl">
          <div className="space-y-4">
            <div>
              <FieldLabel text="DashScope API Key" required />
              <Input type="password" value={dashKey} onChange={(e) => setDashKey(e.target.value)} placeholder="sk-..." />
            </div>

            {/* Mode Toggle */}
            <div className="flex gap-3">
              <button
                onClick={() => setMode('t2v')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${mode === 't2v' ? 'bg-accent text-white' : 'bg-surface text-text border border-border'}`}
              >
                文生视频
              </button>
              <button
                onClick={() => setMode('i2v')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${mode === 'i2v' ? 'bg-accent text-white' : 'bg-surface text-text border border-border'}`}
              >
                图生视频
              </button>
            </div>

            <div>
              <FieldLabel text="提示词" required />
              <TextArea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} placeholder="描述你想要生成的视频..." />
            </div>

            {mode === 'i2v' && (
              <div>
                <FieldLabel text="首帧图片" />
                <div className="flex gap-3 items-center">
                  <Button onClick={handlePickImage} variant="quiet">
                    {imageBase64 ? '已选图片' : '选择图片'}
                  </Button>
                  {imagePreview && <img src={imagePreview} alt="preview" className="w-16 h-16 object-cover rounded" />}
                </div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-4">
              <div>
                <FieldLabel text="分辨率" />
                <Select value={resolution} onChange={(e) => setResolution(e.target.value)} className="w-full">
                  {RESOLUTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </Select>
              </div>
              <div>
                <FieldLabel text="时长" />
                <Select value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="w-full">
                  {DURATIONS.map((d) => <option key={d} value={d}>{d}秒</option>)}
                </Select>
              </div>
              <div>
                <FieldLabel text="比例" />
                <Select value={ratio} onChange={(e) => setRatio(e.target.value)} className="w-full">
                  {RATIOS.map((r) => <option key={r} value={r}>{r}</option>)}
                </Select>
              </div>
            </div>
          </div>
        </div>

        <div className="flex gap-3 mt-4">
          <Button onClick={handleGenerate} variant="primary" disabled={generating}>
            {generating ? '生成中...' : '生成视频'}
          </Button>
        </div>

        {generating && <Loading text={progress || '正在生成视频...'} />}

        {resultVideo && (
          <div className="mt-8">
            <video src={resultVideo} controls className="max-w-2xl rounded-lg border border-border" />
          </div>
        )}

        {!resultVideo && !generating && (
          <div className="mt-8 text-center text-text-muted text-sm py-12">
            生成结果将显示在这里
          </div>
        )}
      </div>
    </div>
  );
};
