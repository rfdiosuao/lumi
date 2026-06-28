import React from 'react';
import { BusyOverlay, Button, Input, Select, showToast } from '../common';
import { accountApi, parseErrorText, wireApi, type AccountSnapshot } from '../../services/api';
import { useAppStore } from '../../stores/appStore';

type SourceMode = 'off' | 'managed' | 'custom';

function firstChoice(values?: string[], preferred?: string): string {
  if (preferred && values?.includes(preferred)) return preferred;
  return values?.[0] || '';
}

const ModelSelect: React.FC<{
  label: string;
  value: string;
  values?: string[];
  disabled?: boolean;
  onChange: (value: string) => void;
}> = ({ label, value, values = [], disabled, onChange }) => (
  <label className="block">
    <div className="mb-2 text-xs font-bold text-text-muted">{label}</div>
    <Select
      className="w-full"
      value={value}
      disabled={disabled || values.length === 0}
      onChange={(event) => onChange(event.target.value)}
    >
      {values.length === 0 ? <option value="">暂无可用模型</option> : null}
      {values.map((model) => (
        <option key={model} value={model}>{model}</option>
      ))}
    </Select>
  </label>
);

export const ModelsPage: React.FC = () => {
  const [account, setAccount] = React.useState<AccountSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [textModel, setTextModel] = React.useState('');
  const [imageModel, setImageModel] = React.useState('');
  const [videoModel, setVideoModel] = React.useState('');
  const [sourceMode, setSourceMode] = React.useState<SourceMode>('managed');
  const [customProvider, setCustomProvider] = React.useState('OpenAI 兼容');
  const [customBaseUrl, setCustomBaseUrl] = React.useState('');
  const [customApiKey, setCustomApiKey] = React.useState('');
  const [customTextModel, setCustomTextModel] = React.useState('');
  const [customImageModel, setCustomImageModel] = React.useState('');
  const [customPhoneModel, setCustomPhoneModel] = React.useState('');
  const [customVideoModel, setCustomVideoModel] = React.useState('');
  const setCurrentPage = useAppStore((state) => state.setCurrentPage);

  const applyAccount = React.useCallback((next: AccountSnapshot | null) => {
    setAccount(next);
    setTextModel(firstChoice(next?.models?.text, next?.selectedModels?.text));
    setImageModel(firstChoice(next?.models?.image, next?.selectedModels?.image));
    setVideoModel(firstChoice(next?.models?.video, next?.selectedModels?.videoDraft));
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const resp = await accountApi.current();
      applyAccount(resp.account || null);
    } catch (error: any) {
      showToast(parseErrorText(error) || '读取模型失败', 'error');
    } finally {
      setLoading(false);
    }
  }, [applyAccount]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const syncModels = async () => {
    setBusy(true);
    try {
      const resp = await accountApi.sync();
      applyAccount(resp.account || null);
      showToast('模型已同步', 'success');
    } catch (error: any) {
      showToast(parseErrorText(error) || '同步失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const saveSelection = async () => {
    setBusy(true);
    try {
      const resp = await accountApi.selectModels({
        textModel,
        imageModel,
        videoModel,
      });
      applyAccount(resp.account || null);
      showToast('模型选择已保存', 'success');
    } catch (error: any) {
      showToast(parseErrorText(error) || '保存失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const applyCustomProvider = async () => {
    if (!customBaseUrl.trim() || !customApiKey.trim() || !customTextModel.trim()) {
      showToast('请填写 Provider URL、API Key 和默认文本模型', 'error');
      return;
    }
    setBusy(true);
    try {
      await wireApi.custom({
        provider: customProvider.trim() || 'OpenAI 兼容',
        baseUrl: customBaseUrl.trim(),
        apiKey: customApiKey.trim(),
        textModel: customTextModel.trim(),
        imageModel: customImageModel.trim(),
        phoneModel: customPhoneModel.trim(),
        videoModel: customVideoModel.trim(),
      });
      setCustomApiKey('');
      showToast('第三方模型配置已应用', 'success');
    } catch (error: any) {
      showToast(parseErrorText(error) || '应用第三方配置失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const loggedIn = Boolean(account?.loggedIn);
  const total =
    (account?.models?.text?.length || 0) +
    (account?.models?.image?.length || 0) +
    (account?.models?.video?.length || 0);

  const busyOverlayTitle = loading
    ? '正在读取模型'
    : sourceMode === 'custom'
      ? '正在应用第三方配置'
      : '正在同步模型';

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <BusyOverlay
        active={loading || busy}
        title={busyOverlayTitle}
        detail="LOOM 正在读取或写入模型配置。"
      />
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="flex items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">模型</div>
            <h1 className="mt-2 text-[30px] font-black leading-tight text-text">模型选择</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-border/70 bg-surface-alt/50 px-3 py-2 text-xs font-bold text-text">
              {loggedIn ? `${total} 个模型` : '未登录'}
            </span>
            <Button variant="quiet" onClick={refresh} disabled={loading || busy}>刷新</Button>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-[20px] border border-border/80 bg-surface-alt/30 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-text">模型来源</h2>
                <p className="mt-1 text-sm text-text-muted">托管账号可一键配置，也可以接入自己的第三方 OpenAI 兼容接口。</p>
              </div>
              <div className="flex rounded-[14px] border border-border/80 bg-surface/35 p-1">
                <SourceModeButton active={sourceMode === 'off'} onClick={() => setSourceMode('off')}>关闭</SourceModeButton>
                <SourceModeButton active={sourceMode === 'managed'} onClick={() => setSourceMode('managed')}>一键配置</SourceModeButton>
                <SourceModeButton active={sourceMode === 'custom'} onClick={() => setSourceMode('custom')}>自定义</SourceModeButton>
              </div>
            </div>

            {sourceMode === 'off' ? (
              <div className="mt-6 rounded-[16px] border border-border/70 bg-surface/35 p-5 text-sm leading-6 text-text-muted">
                已关闭模型来源配置。启动器不会改动本地 Provider，已存在的配置保持原样。
              </div>
            ) : sourceMode === 'custom' ? (
              <div className="mt-6 grid gap-5">
                <div className="rounded-[16px] border border-status-warning/30 bg-status-warning/10 p-4 text-sm leading-6 text-status-warning">
                  使用陌生的第三方 API Key 需谨慎。API Key 只交给本地 Bridge 写入配置，不会显示在页面、日志或文档里。
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="block">
                    <div className="mb-2 text-xs font-bold text-text-muted">Provider</div>
                    <Input value={customProvider} onChange={(event) => setCustomProvider(event.target.value)} placeholder="OpenAI 兼容" />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs font-bold text-text-muted">默认文本模型</div>
                    <Input value={customTextModel} onChange={(event) => setCustomTextModel(event.target.value)} placeholder="例如 gpt-4o、claude-3-5-sonnet" />
                  </label>
                  <label className="block md:col-span-2">
                    <div className="mb-2 text-xs font-bold text-text-muted">自定义 URL</div>
                    <Input value={customBaseUrl} onChange={(event) => setCustomBaseUrl(event.target.value)} placeholder="https://example.com/v1" />
                  </label>
                  <label className="block md:col-span-2">
                    <div className="mb-2 text-xs font-bold text-text-muted">API Key</div>
                    <Input type="password" value={customApiKey} onChange={(event) => setCustomApiKey(event.target.value)} placeholder="sk-..." autoComplete="off" />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs font-bold text-text-muted">图像模型</div>
                    <Input value={customImageModel} onChange={(event) => setCustomImageModel(event.target.value)} placeholder="可选，例如 gpt-image-1" />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs font-bold text-text-muted">手机模型</div>
                    <Input value={customPhoneModel} onChange={(event) => setCustomPhoneModel(event.target.value)} placeholder="可选，默认跟随文本模型" />
                  </label>
                  <label className="block md:col-span-2">
                    <div className="mb-2 text-xs font-bold text-text-muted">视频模型草案</div>
                    <Input value={customVideoModel} onChange={(event) => setCustomVideoModel(event.target.value)} placeholder="可选，仅保存草案，不切换视频 provider" />
                  </label>
                </div>
                <div>
                  <Button variant="primary" onClick={applyCustomProvider} disabled={busy || loading}>
                    {busy ? '处理中...' : '应用第三方配置'}
                  </Button>
                </div>
              </div>
            ) : !loggedIn ? (
              <div className="mt-6 rounded-[16px] border border-border/80 bg-surface/35 p-5">
                <h3 className="text-base font-black text-text">需要登录中转站账号</h3>
                <p className="mt-2 text-sm leading-6 text-text-muted">登录后可一键同步文本、图像和手机模型。视频模型只作为草案展示，不会自动切换视频通道。</p>
                <Button className="mt-5" variant="primary" onClick={() => setCurrentPage('license')}>前往登录</Button>
              </div>
            ) : (
              <div className="mt-6 grid gap-5">
                <ModelSelect label="默认文本模型" value={textModel} values={account?.models?.text} disabled={busy} onChange={setTextModel} />
                <ModelSelect label="默认图像模型" value={imageModel} values={account?.models?.image} disabled={busy} onChange={setImageModel} />
                <ModelSelect label="视频模型草案" value={videoModel} values={account?.models?.video} disabled={busy} onChange={setVideoModel} />
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" onClick={saveSelection} disabled={busy || loading}>
                    {busy ? '处理中...' : '保存选择'}
                  </Button>
                  <Button variant="quiet" onClick={syncModels} disabled={busy || loading}>
                    同步模型
                  </Button>
                </div>
                <div className="rounded-[16px] border border-status-warning/30 bg-status-warning/10 p-4 text-sm text-status-warning">
                  视频模型仅保存为草案选择，不会写入视频 provider 或 API Key 配置。
                </div>
              </div>
            )}
          </section>

          <aside className="space-y-4">
            <SummaryPanel title="文本" values={account?.models?.text} selected={textModel || customTextModel} />
            <SummaryPanel title="图像" values={account?.models?.image} selected={imageModel || customImageModel} />
            <SummaryPanel title="视频" values={account?.models?.video} selected={videoModel || customVideoModel} />
          </aside>
        </div>
      </div>
    </div>
  );
};

const SourceModeButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }> = ({ active, className = '', ...props }) => (
  <button
    type="button"
    className={`rounded-[11px] px-4 py-2 text-sm font-black transition ${
      active ? 'bg-accent text-accent-ink shadow-[0_10px_22px_rgba(8,60,49,0.18)]' : 'text-text-muted hover:bg-hover hover:text-text'
    } ${className}`}
    {...props}
  />
);

const SummaryPanel: React.FC<{ title: string; values?: string[]; selected: string }> = ({ title, values = [], selected }) => (
  <div className="rounded-[20px] border border-border/80 bg-surface-alt/30 p-5">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-base font-black text-text">{title}</h2>
      <span className="rounded-full border border-border/70 bg-surface/35 px-3 py-1 text-xs font-bold text-text-muted">
        {values.length}
      </span>
    </div>
    <div className="mt-3 truncate text-sm font-bold text-text" title={selected || '暂无'}>{selected || '暂无'}</div>
    <div className="mt-3 space-y-1">
      {values.slice(0, 6).map((model) => (
        <div key={model} className="truncate text-xs text-text-muted" title={model}>{model}</div>
      ))}
    </div>
  </div>
);
