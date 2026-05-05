import React, { useState, useEffect } from 'react';
import { Button, Input, TextArea, Select, Loading, showToast, FieldLabel } from '../common';
import { imageApi, videoApi, configApi } from '../../services/api';
import { useLogStore } from '../../stores/logStore';
import { Scene } from '../../types';

const VIEW_KEYS: { key: 'front' | 'side' | 'back'; label: string }[] = [
  { key: 'front', label: '正面' },
  { key: 'side', label: '侧面' },
  { key: 'back', label: '背面' },
];

const CHECK_KEYS: { key: 'productStable' | 'logoClear' | 'sellingPoint' | 'frameFlowGood' | 'cropReady'; label: string }[] = [
  { key: 'productStable', label: '产品不变形' },
  { key: 'logoClear', label: 'Logo / 包装清晰' },
  { key: 'sellingPoint', label: '卖点一眼可懂' },
  { key: 'frameFlowGood', label: '首尾帧连贯' },
  { key: 'cropReady', label: '构图适合投放' },
];

const DURATION_OPTIONS = ['3', '5', '8', '10'];
const RATIO_OPTIONS = ['9:16', '16:9', '1:1', '4:3'];
const CAMERA_OPTIONS = ['缓慢推进', '平移', '环绕', '静物特写', '拉远'];

const defaultScene = (): Scene => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  title: '开场钩子',
  sellingPoint: '3 秒讲清产品亮点',
  duration: '5',
  ratio: '9:16',
  camera: '缓慢推进',
  prompt: '产品置于干净桌面，光线明亮，画面突出产品核心卖点，小广告视频开场镜头',
  negative: '低清晰度，变形，杂乱背景，错误文字，手指遮挡，品牌错乱',
  firstFrame: null,
  lastFrame: null,
  video: null,
  checks: { productStable: false, logoClear: false, sellingPoint: false, frameFlowGood: false, cropReady: false },
  productViews: { front: null, side: null, back: null },
  candidates: [],
});

interface StoryboardProject {
  title: string;
  scenes: Scene[];
  productViews: { front: string | null; side: string | null; back: string | null };
}

const defaultProject = (): StoryboardProject => ({
  title: 'U盘小广告视频',
  productViews: { front: null, side: null, back: null },
  scenes: [defaultScene()],
});

export const StoryboardPage: React.FC = () => {
  const [project, setProject] = useState<StoryboardProject>(defaultProject);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [candidates, setCandidates] = useState<string[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<number | null>(null);
  const [generatingCandidates, setGeneratingCandidates] = useState(false);
  const [generatingVideo, setGeneratingVideo] = useState(false);
  const [candidateStatus, setCandidateStatus] = useState('');
  const [videoStatus, setVideoStatus] = useState('');
  const [saved, setSaved] = useState(false);

  const appendLog = useLogStore((s) => s.append);

  const currentScene = project.scenes[currentIndex] || project.scenes[0];

  // Load project on mount
  useEffect(() => {
    (async () => {
      try {
        const resp = await configApi.read('data/.openclaw/storyboard_project.json', null);
        if (resp.data && Array.isArray((resp.data as any).scenes)) {
          setProject(resp.data as StoryboardProject);
        }
      } catch (e) {
        appendLog('[分镜] 配置加载失败: ' + e + '\n');
      }
    })();
  }, []);

  const updateScene = (updates: Partial<Scene>) => {
    setProject((prev) => {
      const scenes = [...prev.scenes];
      scenes[currentIndex] = { ...scenes[currentIndex], ...updates };
      return { ...prev, scenes };
    });
  };

  const updateProductView = (key: 'front' | 'side' | 'back', value: string | null) => {
    setProject((prev) => ({
      ...prev,
      productViews: { ...prev.productViews, [key]: value },
    }));
  };

  const saveProject = async () => {
    try {
      await configApi.write('data/.openclaw/storyboard_project.json', project);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      showToast('项目已保存', 'success');
    } catch (e: any) {
      showToast('保存失败: ' + (e?.error || e), 'error');
    }
  };

  const handleFileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (ev) => resolve(ev.target?.result as string);
      reader.readAsDataURL(file);
    });

  const handlePickProductView = async (key: 'front' | 'side' | 'back') => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const dataUrl = await handleFileToBase64(file);
        updateProductView(key, dataUrl);
      }
    };
    input.click();
  };

  const handlePickFrame = async (slot: 'firstFrame' | 'lastFrame') => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const dataUrl = await handleFileToBase64(file);
        updateScene({ [slot]: dataUrl });
      }
    };
    input.click();
  };

  const addScene = () => {
    const newScene = defaultScene();
    newScene.id = String(Date.now());
    newScene.title = `镜头 ${project.scenes.length + 1}`;
    newScene.prompt = '产品清晰可见，画面简洁，突出一个卖点，适合短视频广告';
    setProject((prev) => ({ ...prev, scenes: [...prev.scenes, newScene] }));
    setCurrentIndex(project.scenes.length);
    setCandidates([]);
    setSelectedCandidate(null);
  };

  const duplicateScene = () => {
    if (!currentScene) return;
    const copy: Scene = {
      ...currentScene,
      id: String(Date.now()),
      title: `${currentScene.title} 副本`,
      checks: { ...currentScene.checks },
      productViews: { ...currentScene.productViews },
      candidates: [],
    };
    setProject((prev) => {
      const scenes = [...prev.scenes];
      scenes.splice(currentIndex + 1, 0, copy);
      return { ...prev, scenes };
    });
    setCurrentIndex(currentIndex + 1);
    setCandidates([]);
    setSelectedCandidate(null);
  };

  const deleteScene = () => {
    if (project.scenes.length <= 1) {
      showToast('至少保留一个镜头', 'info');
      return;
    }
    if (!confirm('确定删除当前镜头？')) return;
    setProject((prev) => {
      const scenes = [...prev.scenes];
      scenes.splice(currentIndex, 1);
      return { ...prev, scenes };
    });
    setCurrentIndex(Math.max(0, currentIndex - 1));
    setCandidates([]);
    setSelectedCandidate(null);
  };

  const selectScene = (index: number) => {
    setCurrentIndex(index);
    setCandidates([]);
    setSelectedCandidate(null);
  };

  const composeCandidatePrompt = () => {
    const scene = currentScene;
    const productBits: string[] = [];
    for (const v of VIEW_KEYS) {
      if (project.productViews[v.key]) productBits.push(v.label);
    }
    const productContext = productBits.length > 0
      ? `参考产品${productBits.join('、')}三视图，保持产品外观一致。`
      : '保持产品主体稳定一致。';
    return (
      `${productContext}\n` +
      `广告镜头：${scene.title}\n` +
      `卖点：${scene.sellingPoint}\n` +
      `运镜：${scene.camera}\n` +
      `画面：${scene.prompt}\n` +
      `要求：商业广告关键帧，主体清晰，构图完整，适合${scene.ratio}短视频投放。\n` +
      `避免：${scene.negative}`
    );
  };

  const handleGenerateCandidates = async () => {
    const imgConfig = (await configApi.read('imgapi_config.json', {})).data as any;
    const baseUrl = imgConfig?.baseUrl || '';
    const apiKey = imgConfig?.apiKey || '';
    if (!baseUrl) {
      showToast('请先在 AI 生图页面配置中转站地址', 'error');
      return;
    }
    setGeneratingCandidates(true);
    setCandidates([]);
    setSelectedCandidate(null);
    setCandidateStatus('正在生成九宫格...');
    try {
      const prompt = composeCandidatePrompt();
      const resp = await imageApi.generate({ baseUrl, apiKey, prompt, size: '1024x1024', count: 9 });
      if (resp.images && resp.images.length > 0) {
        const imgs = resp.images.map((b64: string) => `data:image/png;base64,${b64}`);
        setCandidates(imgs);
        setCandidateStatus(`已生成 ${imgs.length} 张候选`);
        showToast('九宫格生成完成', 'success');
        appendLog('[分镜九宫格] 生成成功\n');
      }
    } catch (e: any) {
      const msg = e?.error || '生成失败';
      setCandidateStatus(`失败：${msg}`);
      appendLog(`[分镜九宫格] ${msg}\n`);
      showToast(msg, 'error');
    } finally {
      setGeneratingCandidates(false);
    }
  };

  const handleAssignCandidate = (slot: 'firstFrame' | 'lastFrame') => {
    if (selectedCandidate === null || selectedCandidate >= candidates.length) {
      showToast('请先点击选择一张候选图', 'info');
      return;
    }
    updateScene({ [slot]: candidates[selectedCandidate] });
    showToast(`已设为${slot === 'firstFrame' ? '首帧' : '尾帧'}`, 'success');
  };

  const handleGenerateVideo = async () => {
    if (!currentScene?.firstFrame) {
      showToast('请先为当前镜头设置首帧', 'error');
      return;
    }
    const videoConfig = (await configApi.read('video_config.json', {})).data as any;
    const dashKey = videoConfig?.dashKey || '';
    if (!dashKey) {
      showToast('请先在 AI 视频页面配置 DashScope API Key', 'error');
      return;
    }
    setGeneratingVideo(true);
    setVideoStatus('正在生成镜头视频...');
    try {
      const prompt = composeCandidatePrompt();
      const resp = await videoApi.generate({
        dashKey,
        prompt,
        mode: 'i2v',
        resolution: '720P',
        duration: parseInt(currentScene.duration || '5', 10),
        ratio: currentScene.ratio || '9:16',
        imagePath: currentScene.firstFrame,
      });
      if (resp.video) {
        const videoUrl = `data:video/mp4;base64,${resp.video}`;
        updateScene({ video: videoUrl });
        setVideoStatus('视频已生成');
        showToast('视频生成成功', 'success');
        appendLog('[分镜视频] 生成成功\n');
      }
    } catch (e: any) {
      const msg = e?.error || '生成失败';
      setVideoStatus(`失败：${msg}`);
      appendLog(`[分镜视频] ${msg}\n`);
      showToast(msg, 'error');
    } finally {
      setGeneratingVideo(false);
    }
  };

  const s = currentScene;
  if (!s) return null;

  return (
    <div className="flex flex-col h-full bg-surface overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-8 py-4 border-b border-border bg-surface flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">广告视频工作台</h1>
          <p className="text-sm text-text-muted mt-1">分镜 / 三视图 / 首尾帧 / 九宫格</p>
        </div>
        <Button onClick={saveProject} variant="primary">
          {saved ? '已保存' : '保存项目'}
        </Button>
      </div>

      {/* Three-column body */}
      <div className="flex-1 flex gap-3 px-4 py-4 overflow-hidden">
        {/* LEFT: Scene list */}
        <div className="w-52 flex-shrink-0 bg-surface-alt rounded-lg border border-border flex flex-col">
          <div className="px-3 py-2">
            <div className="text-xs text-text-subtle font-medium">分镜列表</div>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {project.scenes.map((scene, i) => (
              <button
                key={scene.id}
                onClick={() => selectScene(i)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm mb-1 transition-colors cursor-pointer ${
                  i === currentIndex
                    ? 'bg-accent text-accent-ink'
                    : 'text-text hover:bg-surface'
                }`}
              >
                <div className="truncate font-medium">{String(i + 1).padStart(2, '0')}  {scene.title}</div>
              </button>
            ))}
          </div>
          <div className="px-2 pb-3 flex gap-1.5">
            <Button onClick={addScene} variant="quiet" className="flex-1 text-xs px-2 py-1">新增</Button>
            <Button onClick={duplicateScene} variant="quiet" className="flex-1 text-xs px-2 py-1">复制</Button>
            <Button onClick={deleteScene} variant="danger" className="flex-1 text-xs px-2 py-1">删除</Button>
          </div>
        </div>

        {/* CENTER: Product views + frames + candidates */}
        <div className="flex-1 flex flex-col gap-3 overflow-y-auto min-w-0">
          {/* Product three views */}
          <div className="bg-surface-alt rounded-lg border border-border p-4">
            <div className="text-xs text-text-subtle font-medium mb-3">产品三视图</div>
            <div className="grid grid-cols-3 gap-3">
              {VIEW_KEYS.map((v) => (
                <div key={v.key} className="flex flex-col items-center">
                  <div
                    className="w-full aspect-video bg-surface border border-border rounded flex items-center justify-center cursor-pointer hover:border-accent transition-colors overflow-hidden"
                    onClick={() => handlePickProductView(v.key)}
                  >
                    {project.productViews[v.key] ? (
                      <img src={project.productViews[v.key]!} alt={v.label} className="w-full h-full object-contain" />
                    ) : (
                      <span className="text-text-muted text-sm">{v.label}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* First/last frames */}
          <div className="bg-surface-alt rounded-lg border border-border p-4">
            <div className="text-xs text-text-subtle font-medium mb-3">首尾帧</div>
            <div className="grid grid-cols-2 gap-3">
              {([
                { slot: 'firstFrame' as const, label: '首帧' },
                { slot: 'lastFrame' as const, label: '尾帧' },
              ]).map(({ slot, label }) => (
                <div key={slot} className="flex flex-col">
                  <div
                    className="w-full h-28 bg-surface border border-border rounded flex items-center justify-center cursor-pointer hover:border-accent transition-colors overflow-hidden"
                    onClick={() => handlePickFrame(slot)}
                  >
                    {s[slot] ? (
                      <img src={s[slot]!} alt={label} className="w-full h-full object-contain" />
                    ) : (
                      <span className="text-text-muted text-sm">{label}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 3x3 candidate grid */}
          <div className="bg-surface-alt rounded-lg border border-border p-4 flex-shrink-0">
            <div className="text-xs text-text-subtle font-medium mb-3">九宫格候选</div>
            <div className="flex gap-3 items-center mb-3">
              <Button onClick={handleGenerateCandidates} variant="primary" disabled={generatingCandidates} className="text-xs px-3 py-1.5">
                {generatingCandidates ? '生成中...' : '生成九宫格'}
              </Button>
              <Button onClick={() => handleAssignCandidate('firstFrame')} variant="quiet" disabled={selectedCandidate === null} className="text-xs px-3 py-1.5">设为首帧</Button>
              <Button onClick={() => handleAssignCandidate('lastFrame')} variant="quiet" disabled={selectedCandidate === null} className="text-xs px-3 py-1.5">设为尾帧</Button>
              {candidateStatus && (
                <span className="text-xs text-text-muted">{candidateStatus}</span>
              )}
            </div>
            {generatingCandidates && candidates.length === 0 ? (
              <div className="grid grid-cols-3 gap-2">
                {Array.from({ length: 9 }).map((_, i) => (
                  <div key={i} className="aspect-video bg-surface border border-border rounded flex items-center justify-center">
                    <Loading text="" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {Array.from({ length: 9 }).map((_, i) => (
                  <div
                    key={i}
                    className={`aspect-video bg-surface border rounded flex items-center justify-center cursor-pointer overflow-hidden transition-colors ${
                      i === selectedCandidate ? 'border-accent ring-2 ring-accent/30' : 'border-border hover:border-accent/50'
                    }`}
                    onClick={() => i < candidates.length && setSelectedCandidate(i)}
                  >
                    {i < candidates.length ? (
                      <img src={candidates[i]} alt={`候选 ${i + 1}`} className="w-full h-full object-contain" />
                    ) : (
                      <span className="text-text-subtle text-lg">{i + 1}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: Scene parameters */}
        <div className="w-72 flex-shrink-0 bg-surface-alt rounded-lg border border-border flex flex-col overflow-y-auto">
          <div className="px-4 py-3">
            <div className="text-xs text-text-subtle font-medium mb-3">镜头参数</div>
            <div className="space-y-3">
              <div>
                <FieldLabel text="镜头标题" />
                <Input value={s.title} onChange={(e) => updateScene({ title: e.target.value })} />
              </div>
              <div>
                <FieldLabel text="卖点" />
                <Input value={s.sellingPoint} onChange={(e) => updateScene({ sellingPoint: e.target.value })} />
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <FieldLabel text="时长" />
                  <Select value={s.duration} onChange={(e) => updateScene({ duration: e.target.value })} className="w-full">
                    {DURATION_OPTIONS.map((d) => <option key={d} value={d}>{d}s</option>)}
                  </Select>
                </div>
                <div className="flex-1">
                  <FieldLabel text="比例" />
                  <Select value={s.ratio} onChange={(e) => updateScene({ ratio: e.target.value })} className="w-full">
                    {RATIO_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </Select>
                </div>
              </div>
              <div>
                <FieldLabel text="运镜" />
                <Select value={s.camera} onChange={(e) => updateScene({ camera: e.target.value })} className="w-full">
                  {CAMERA_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </div>
              <div>
                <FieldLabel text="画面提示词" />
                <TextArea value={s.prompt} onChange={(e) => updateScene({ prompt: e.target.value })} rows={4} />
              </div>
              <div>
                <FieldLabel text="负面词" />
                <TextArea value={s.negative} onChange={(e) => updateScene({ negative: e.target.value })} rows={2} />
              </div>

              {/* Quality checks */}
              <div className="pt-2 border-t border-border">
                <div className="text-xs text-text-subtle font-medium mb-2">质量检查</div>
                <div className="space-y-1">
                  {CHECK_KEYS.map((c) => (
                    <label key={c.key} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={s.checks[c.key]}
                        onChange={(e) => updateScene({ checks: { ...s.checks, [c.key]: e.target.checked } })}
                        className="w-4 h-4 rounded accent-accent"
                      />
                      <span className="text-xs text-text-muted">{c.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Video actions */}
              <div className="pt-2 border-t border-border flex flex-col gap-2">
                <div className="flex gap-2">
                  <Button onClick={saveProject} variant="quiet" className="flex-1 text-xs px-2 py-1.5">保存镜头</Button>
                  <Button onClick={handleGenerateVideo} variant="primary" disabled={generatingVideo} className="flex-1 text-xs px-2 py-1.5">
                    {generatingVideo ? '生成中...' : '生成镜头视频'}
                  </Button>
                </div>
                {videoStatus && (
                  <p className={`text-xs ${videoStatus.includes('成功') ? 'text-status-success' : videoStatus.includes('生成') ? 'text-accent' : 'text-status-danger'}`}>
                    {videoStatus}
                  </p>
                )}
                {generatingVideo && <Loading text="正在生成视频..." />}
                {s.video && !generatingVideo && (
                  <div className="mt-1">
                    <video src={s.video} controls className="w-full rounded border border-border" />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
