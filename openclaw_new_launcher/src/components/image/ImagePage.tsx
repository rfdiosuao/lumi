import React, { useState } from 'react';
import { Button, Input, TextArea, Select, Loading, showToast, FieldLabel } from '../common';
import { imageApi, configApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const SIZES = ['1024x1024', '1024x1536', '1536x1024', '512x512'];

export const ImagePage: React.FC = () => {
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [prompt, setPrompt] = useState('');
  const [size, setSize] = useState('1024x1024');
  const [editImage, setEditImage] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [tripleGenerating, setTripleGenerating] = useState(false);
  const [resultImage, setResultImage] = useState<string | null>(null);
  const [tripleResults, setTripleResults] = useState<(string | null)[]>([null, null, null]);
  const [tripleStatus, setTripleStatus] = useState('');

  const appendLog = useLogStore((s) => s.append);

  const loadConfig = async () => {
    try {
      const resp = await configApi.read('imgapi_config.json', {});
      const data = resp.data as any;
      if (data?.baseUrl) setBaseUrl(data.baseUrl);
      if (data?.apiKey) setApiKey(data.apiKey);
    } catch (e) {
      appendLog('[生图] 配置加载失败: ' + e + '\n');
    }
  };

  React.useEffect(() => { loadConfig(); }, []);

  const saveConfig = async () => {
    try {
      await configApi.write('imgapi_config.json', { baseUrl, apiKey });
    } catch (e) {
      appendLog('[生图] 配置保存失败: ' + e + '\n');
    }
  };

  const handleGenerate = async () => {
    if (!baseUrl || !prompt) {
      showToast('请填写中转站地址和提示词', 'error');
      return;
    }
    setGenerating(true);
    setResultImage(null);
    try {
      await saveConfig();
      const resp = await imageApi.generate({ baseUrl, apiKey, prompt, size, count: 1, editImagePath: editImage || undefined });
      if (resp.images?.[0]) {
        setResultImage(`data:image/png;base64,${resp.images[0]}`);
        showToast('图片生成成功', 'success');
        appendLog('[生图] 单图生成成功\n');
      }
    } catch (e: any) {
      showToast(e?.error || '生成失败', 'error');
      appendLog(`[生图] 失败: ${e?.error}\n`);
    } finally {
      setGenerating(false);
    }
  };

  const TRIPLE_PROMPTS = [
    { label: '主图', prefix: 'product photography, hero shot, studio lighting, clean background, professional product photo' },
    { label: '白底图', prefix: 'pure white background, clean product photography, studio lighting, commercial product shot on white' },
    { label: '详情图', prefix: 'product detail closeup, high quality product photography, texture detail, professional lighting' },
  ];

  const handleTripleGenerate = async () => {
    if (!baseUrl || !prompt) {
      showToast('请填写中转站地址和提示词', 'error');
      return;
    }
    setTripleGenerating(true);
    setTripleResults([null, null, null]);
    await saveConfig();

    for (let i = 0; i < 3; i++) {
      setTripleStatus(`生成中: ${i + 1}/3 - ${TRIPLE_PROMPTS[i].label}`);
      try {
        const fullPrompt = `${prompt}\n${TRIPLE_PROMPTS[i].prefix}`;
        const resp = await imageApi.generate({ baseUrl, apiKey, prompt: fullPrompt, size, count: 1 });
        if (resp.images?.[0]) {
          setTripleResults((prev) => { const n = [...prev]; n[i] = `data:image/png;base64,${resp.images[0]}`; return n; });
        }
      } catch (e: any) {
        setTripleResults((prev) => { const n = [...prev]; n[i] = `error:${e?.error}`; return n; });
      }
    }
    setTripleStatus('');
    showToast('三图生成完成', 'success');
  };

  const handlePickImage = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          setEditImage(ev.target?.result as string);
        };
        reader.readAsDataURL(file);
      }
    };
    input.click();
  };

  return (
    <div className="flex flex-col h-full bg-surface overflow-y-auto">
      <div className="flex-shrink-0 px-8 py-6 border-b border-border bg-surface">
        <h1 className="text-xl font-semibold text-text">AI 生图</h1>
        <p className="text-sm text-text-muted mt-1">生成或编辑图片</p>
      </div>

      {/* Form Card */}
      <div className="px-8 py-6">
        <div className="bg-surface-alt rounded-lg border border-border p-6 max-w-3xl">
          <div className="space-y-4">
            <div>
              <FieldLabel text="中转站地址" required />
              <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://..." />
            </div>
            <div>
              <FieldLabel text="API Key" />
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
            </div>
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <FieldLabel text="尺寸" />
                <Select value={size} onChange={(e) => setSize(e.target.value)} className="w-full">
                  {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </div>
              <Button onClick={handlePickImage} variant="quiet">
                {editImage ? '已选图片' : '上传原图'}
              </Button>
              {editImage && (
                <Button onClick={() => setEditImage(null)} variant="quiet">清除</Button>
              )}
            </div>
            <div>
              <FieldLabel text="提示词" required />
              <TextArea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} placeholder="描述你想要生成的图片..." />
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 mt-4">
          <Button onClick={handleGenerate} variant="primary" disabled={generating}>
            {generating ? '生成中...' : '生成图片'}
          </Button>
          <Button onClick={handleTripleGenerate} variant="success" disabled={tripleGenerating}>
            {tripleGenerating ? tripleStatus : '一键三图'}
          </Button>
        </div>

        {/* Result Area */}
        <div className="mt-8">
          {generating && <Loading text="正在生成图片..." />}
          {resultImage && (
            <div className="border border-border rounded-lg overflow-hidden inline-block max-w-lg">
              <img src={resultImage} alt="Generated" className="max-w-full" />
            </div>
          )}
        </div>

        {/* Triple Results */}
        {tripleGenerating && tripleResults.some(r => r) && (
          <div className="mt-6 grid grid-cols-3 gap-4">
            {TRIPLE_PROMPTS.map((tpl, i) => (
              <div key={i} className="border border-border rounded-lg p-4 bg-surface-alt">
                <p className="text-sm font-medium text-text mb-2">{tpl.label}</p>
                {tripleResults[i]?.startsWith('data:') ? (
                  <img src={tripleResults[i]!} alt={tpl.label} className="w-full rounded" />
                ) : tripleResults[i]?.startsWith('error:') ? (
                  <p className="text-xs text-status-danger">{tripleResults[i]?.slice(6)}</p>
                ) : (
                  <div className="w-full aspect-square bg-surface-alt border border-border rounded flex items-center justify-center">
                    <Loading text="生成中..." />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {!resultImage && !generating && !tripleGenerating && (
          <div className="mt-8 text-center text-text-muted text-sm py-12">
            生成结果将显示在这里
          </div>
        )}
      </div>
    </div>
  );
};
