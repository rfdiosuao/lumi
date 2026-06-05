import React from 'react';
import { Command } from '@tauri-apps/plugin-shell';
import { Copy, ExternalLink, RefreshCcw, Save } from 'lucide-react';
import { Button, Chip, Field, Input, Panel, SectionHeader, Select, TextArea } from '../components/ui';
import { loadSettingsSnapshot, readConfigValue, saveAuthProfiles, writeConfigValue } from '../api/adapters';
import { makeCommandOptions, resolvePortableBasePath } from '../api/runtimeCommand';
import { maskSecret } from '../lib/format';
import { displayPhoneBaseUrl, normalizeOrCleanPhoneBaseUrl } from '../lib/phoneUrl';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

type GatewayForm = {
  baseUrl: string;
  apiKey: string;
  model: string;
};

type ImageForm = {
  baseUrl: string;
  apiKey: string;
  model: string;
};

type VideoForm = {
  providerId: string;
  apiBase: string;
  apiKey: string;
  model: string;
};

const AUTH_PROFILES_PATH = 'data/.openclaw/agents/main/agent/auth-profiles.json';
const IMAGE_CONFIG_PATH = 'imgapi_config.json';
const VIDEO_CONFIG_PATH = 'videoapi_config.json';
const OPENCLAW_CONFIG_PATH = 'data/.openclaw/openclaw.json';
const OPENAI_CODEX_MANUAL_LOGIN_COMMAND = [
  "$env:OPENCLAW_HOME=(Join-Path $PWD 'data')",
  "$env:OPENCLAW_STATE_DIR=(Join-Path $PWD 'data\\.openclaw')",
  "$env:OPENCLAW_CONFIG_PATH=(Join-Path $env:OPENCLAW_STATE_DIR 'openclaw.json')",
  '$env:OPENCLAW_CONFIG=$env:OPENCLAW_CONFIG_PATH',
  "$env:OPENCLAW_GATEWAY_PORT='18790'",
  "$env:NO_COLOR='1'",
  "$env:Path=(Join-Path $PWD 'node')+';'+(Join-Path $PWD 'node_modules\\.bin')+';'+$env:Path",
  '.\\node\\node.exe .\\node_modules\\openclaw\\openclaw.mjs models auth login --provider openai --method oauth --set-default',
].join('; ');

export function SettingsPage() {
  const storeSettings = usePreviewStore((state) => state.settings);
  const updateSettings = usePreviewStore((state) => state.updateSettings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadSettingsSnapshot(storeSettings), [storeSettings]);
  const [authProfiles, setAuthProfiles] = React.useState<any>({});
  const [imageConfig, setImageConfig] = React.useState<any>({});
  const [videoConfig, setVideoConfig] = React.useState<any>({});
  const [openclawConfig, setOpenclawConfig] = React.useState<any>({});
  const [gatewayForm, setGatewayForm] = React.useState<GatewayForm>({ baseUrl: '', apiKey: '', model: 'gpt-4o' });
  const [imageForm, setImageForm] = React.useState<ImageForm>({ baseUrl: '', apiKey: '', model: 'gpt-image-2' });
  const [videoForm, setVideoForm] = React.useState<VideoForm>({ providerId: 'agnes', apiBase: 'https://apihub.agnes-ai.com/v1', apiKey: '', model: 'agnes-video-v2.0' });
  const [codexLoginRunning, setCodexLoginRunning] = React.useState(false);
  const [jsonDrafts, setJsonDrafts] = React.useState({
    authProfiles: '{}',
    imageConfig: '{}',
    videoConfig: '{}',
    openclawConfig: '{}',
  });

  // 表单只首次填充:避免后续任意一次 loadConfigs 重跑(如 storeSettings 变化)把用户
  // 正在编辑的网关地址/主模型等内容还原,表现为"打不进字/改了又跳回去"。
  const formsSeededRef = React.useRef(false);

  const loadConfigs = React.useCallback(async () => {
    try {
      const [auth, image, video, openclaw] = await Promise.all([
        readConfigValue(storeSettings, AUTH_PROFILES_PATH, { models: { providers: {} } }),
        readConfigValue(storeSettings, IMAGE_CONFIG_PATH, {}),
        readConfigValue(storeSettings, VIDEO_CONFIG_PATH, {}),
        readConfigValue(storeSettings, OPENCLAW_CONFIG_PATH, {}),
      ]);
      const nextAuth = auth || {};
      const nextImage = image || {};
      const nextVideo = video || {};
      const nextOpenclaw = openclaw || {};
      const gateway = formFromAuthProfiles(nextAuth);
      setAuthProfiles(nextAuth);
      setImageConfig(nextImage);
      setVideoConfig(nextVideo);
      setOpenclawConfig(nextOpenclaw);
      // 仅首次填充可编辑表单/草稿;之后保留用户输入,不被重载冲掉。
      if (!formsSeededRef.current) {
        formsSeededRef.current = true;
        setGatewayForm(gateway);
        setImageForm({
          baseUrl: stringValue(nextImage.baseUrl) || gateway.baseUrl,
          apiKey: stringValue(nextImage.apiKey),
          model: stringValue(nextImage.model) || 'gpt-image-2',
        });
        const loadedVideoBase = stringValue(nextVideo.apiBase) || stringValue(nextVideo.baseUrl) || gateway.baseUrl;
        const loadedVideoModel = stringValue(nextVideo.model);
        const loadedVideoProvider = inferVideoProviderId(nextVideo.providerId, loadedVideoBase, loadedVideoModel);
        setVideoForm({
          providerId: loadedVideoProvider,
          apiBase: loadedVideoBase || videoProviderDefaults(loadedVideoProvider).apiBase,
          apiKey: stringValue(nextVideo.apiKey) || stringValue(nextVideo.dashKey) || stringValue(nextImage.apiKey),
          model: loadedVideoModel || videoProviderDefaults(loadedVideoProvider).model,
        });
        setJsonDrafts({
          authProfiles: formatJson(nextAuth),
          imageConfig: formatJson(nextImage),
          videoConfig: formatJson(nextVideo),
          openclawConfig: formatJson(nextOpenclaw),
        });
      }
    } catch {
      setAuthProfiles({});
      setImageConfig({});
      setVideoConfig({});
      setOpenclawConfig({});
      setJsonDrafts({ authProfiles: '{}', imageConfig: '{}', videoConfig: '{}', openclawConfig: '{}' });
    }
  }, [storeSettings]);

  React.useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  const handleOpenAiCodexLogin = React.useCallback(async () => {
    if (codexLoginRunning) return;
    setCodexLoginRunning(true);
    try {
      const cwd = await resolvePortableBasePath(storeSettings);
      const args = ['scripts/openclaw-auth-terminal.mjs', 'openai-browser'];
      const options = makeCommandOptions(cwd);
      let result;

      try {
        result = await Command.create('openclaw-auth-openai-browser', args, options).execute();
      } catch {
        result = await Command.create('openclaw-auth-openai-browser-node-exe', args, options).execute();
      }

      if (result.code === 0) {
        pushToast({
          tone: 'ok',
          title: 'OpenAI Codex 登录已打开',
          detail: '会打开一个 PowerShell 登录窗口，并自动弹出 OpenAI 网页。若窗口没出现，请复制备用命令手动执行。',
        });
      } else {
        pushToast({
          tone: 'danger',
          title: 'OpenAI Codex 登录启动失败',
          detail: commandResultDetail(result),
        });
      }
    } catch (err) {
      pushToast({ tone: 'danger', title: 'OpenAI Codex 登录启动失败', detail: String(err) });
    } finally {
      setCodexLoginRunning(false);
    }
  }, [codexLoginRunning, pushToast, storeSettings]);

  const handleCopyOpenAiCodexCommand = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(OPENAI_CODEX_MANUAL_LOGIN_COMMAND);
      pushToast({
        tone: 'ok',
        title: '登录命令已复制',
        detail: '在 OpenClawFiles 目录打开 PowerShell 后粘贴执行。',
      });
    } catch (err) {
      pushToast({ tone: 'danger', title: '复制失败', detail: String(err) });
    }
  }, [pushToast]);

  const handleSaveConfigs = async () => {
    const nextAuth = withPrimaryProvider(authProfiles, gatewayForm);
    const nextImage = {
      ...(imageConfig || {}),
      gatewayMode: (imageConfig || {}).gatewayMode || 'manual',
      baseUrl: imageForm.baseUrl.trim(),
      apiKey: imageForm.apiKey.trim(),
      model: imageForm.model.trim() || 'gpt-image-2',
    };
    const nextVideo = {
      ...(videoConfig || {}),
      gatewayMode: (videoConfig || {}).gatewayMode || 'manual',
      providerId: inferVideoProviderId(videoForm.providerId, videoForm.apiBase, videoForm.model),
      apiBase: videoForm.apiBase.trim(),
      apiKey: videoForm.apiKey.trim(),
      model: videoForm.model.trim(),
    };
    const nextOpenclaw = sanitizeOpenClawConfig(openclawConfig);

    try {
      await Promise.all([
        saveAuthProfiles(storeSettings, nextAuth),
        writeConfigValue(storeSettings, IMAGE_CONFIG_PATH, nextImage),
        writeConfigValue(storeSettings, VIDEO_CONFIG_PATH, nextVideo),
        writeConfigValue(storeSettings, OPENCLAW_CONFIG_PATH, nextOpenclaw),
      ]);
      setAuthProfiles(nextAuth);
      setImageConfig(nextImage);
      setVideoConfig(nextVideo);
      setOpenclawConfig(nextOpenclaw);
      setJsonDrafts({
        authProfiles: formatJson(nextAuth),
        imageConfig: formatJson(nextImage),
        videoConfig: formatJson(nextVideo),
        openclawConfig: formatJson(nextOpenclaw),
      });
      pushToast({ tone: 'ok', title: '设置已保存', detail: '网关、图像、视频和启动器配置已写入对应文件。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '保存失败', detail: String(err) });
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">统一设置</div>
          <h1>所有密钥和连接参数，只放在这一个设置页。</h1>
          <p>旧的模型配置、图像生成、视频生成、桥接地址和手机控制台参数都从这里维护，业务页面只读取结果。</p>
        </div>
        <div className="hero-actions">
          <Button variant="primary" icon={RefreshCcw} onClick={() => { refresh(); loadConfigs(); }}>
            刷新
          </Button>
          <Button variant="secondary" icon={Save} onClick={handleSaveConfigs}>
            保存设置
          </Button>
        </div>
      </section>

      <section className="content-grid content-grid-settings">
        <Panel className="surface-panel">
          <SectionHeader
            eyebrow="启动器连接"
            title="启动器连接"
            subtitle="控制预览版如何连接桥接服务，以及手机控制台如何连接 APKClaw。"
            action={<Chip tone={storeSettings.transportMode === 'live' ? 'ok' : storeSettings.transportMode === 'mock' ? 'warn' : 'neutral'}>{transportLabel(storeSettings.transportMode)}</Chip>}
          />
          <div className="form-grid">
            <Field label="连接模式">
              <Select value={storeSettings.transportMode} onChange={(event) => updateSettings({ transportMode: event.target.value as any })}>
                <option value="live">真实接口</option>
                <option value="auto">自动选择</option>
              </Select>
            </Field>
            <Field label="桥接地址">
              <Input value={storeSettings.bridgeBaseUrl} onChange={(event) => updateSettings({ bridgeBaseUrl: event.target.value })} placeholder="例如 /api 或 http://127.0.0.1:18791" />
            </Field>
            <Field label="桥接令牌">
              <Input type="password" value={storeSettings.bridgeToken} onChange={(event) => updateSettings({ bridgeToken: event.target.value })} placeholder="示例：桥接令牌" />
            </Field>
            <Field label="代理目标">
              <Input value={storeSettings.proxyTarget} onChange={(event) => updateSettings({ proxyTarget: event.target.value })} placeholder="http://127.0.0.1:18791" />
            </Field>
            <Field label="手机控制台地址">
              <Input
                value={displayPhoneBaseUrl(storeSettings.phoneBaseUrl)}
                onChange={(event) => updateSettings({ phoneBaseUrl: event.target.value })}
                onBlur={(event) => updateSettings({ phoneBaseUrl: normalizeOrCleanPhoneBaseUrl(event.target.value) })}
                placeholder="192.168.1.137:9527"
              />
            </Field>
            <Field label="手机令牌">
              <Input type="password" value={storeSettings.phoneToken} onChange={(event) => updateSettings({ phoneToken: event.target.value })} placeholder="示例：Bearer 令牌" />
            </Field>
          </div>
        </Panel>

        <Panel className="surface-panel surface-panel-wide">
          <SectionHeader
            eyebrow="统一密钥"
            title="模型、图像、视频密钥"
            subtitle="字段分别映射到 auth-profiles.json、imgapi_config.json、videoapi_config.json，不改后端字段。"
            action={<Chip tone={gatewayForm.apiKey || imageForm.apiKey || videoForm.apiKey ? 'ok' : 'warn'}>{gatewayForm.apiKey || imageForm.apiKey || videoForm.apiKey ? '已配置' : '缺少密钥'}</Chip>}
          />
          <div className="settings-card-grid">
            <section className="settings-card">
              <div className="settings-card-title">OpenAI Codex 账号</div>
              <p className="settings-card-copy">点击后会打开 PowerShell 登录窗口，OpenClaw 会自动弹出 OpenAI/ChatGPT 网页授权。这个窗口需要保留到授权写入完成。</p>
              <div className="settings-card-actions">
                <Button
                  variant="primary"
                  icon={ExternalLink}
                  onClick={handleOpenAiCodexLogin}
                  disabled={codexLoginRunning}
                  className="settings-card-action"
                >
                  {codexLoginRunning ? '正在打开...' : '打开网页登录'}
                </Button>
                <Button
                  variant="secondary"
                  icon={Copy}
                  onClick={handleCopyOpenAiCodexCommand}
                  className="settings-card-action"
                >
                  复制备用命令
                </Button>
              </div>
              <div className="settings-login-command">
                <span>PowerShell 备用命令</span>
                <code>{OPENAI_CODEX_MANUAL_LOGIN_COMMAND}</code>
              </div>
              <div className="settings-card-note">如果没有弹出终端：进入 OpenClaw.exe 同级的 OpenClawFiles 目录，打开 PowerShell，粘贴备用命令。授权完成后重启核心服务让模型登录生效。</div>
            </section>

            <section className="settings-card">
              <div className="settings-card-title">主模型网关</div>
              <Field label="模型地址">
                <Input value={gatewayForm.baseUrl} onChange={(event) => setGatewayForm((state) => ({ ...state, baseUrl: event.target.value }))} placeholder="https://api.example.com/v1" />
              </Field>
              <Field label="模型密钥" hint={maskSecret(gatewayForm.apiKey)}>
                <Input type="password" value={gatewayForm.apiKey} onChange={(event) => setGatewayForm((state) => ({ ...state, apiKey: event.target.value }))} placeholder="示例：sk-..." />
              </Field>
              <Field label="主模型">
                <Input value={gatewayForm.model} onChange={(event) => setGatewayForm((state) => ({ ...state, model: event.target.value }))} placeholder="gpt-4o" />
              </Field>
            </section>

            <section className="settings-card">
              <div className="settings-card-title">图像生成</div>
              <Field label="图像地址">
                <Input value={imageForm.baseUrl} onChange={(event) => setImageForm((state) => ({ ...state, baseUrl: event.target.value }))} placeholder="https://api.example.com/v1" />
              </Field>
              <Field label="图像密钥" hint={maskSecret(imageForm.apiKey)}>
                <Input type="password" value={imageForm.apiKey} onChange={(event) => setImageForm((state) => ({ ...state, apiKey: event.target.value }))} placeholder="示例：图像密钥" />
              </Field>
              <Field label="图像模型">
                <Input value={imageForm.model} onChange={(event) => setImageForm((state) => ({ ...state, model: event.target.value }))} placeholder="gpt-image-2" />
              </Field>
            </section>

            <section className="settings-card">
              <div className="settings-card-title">视频生成</div>
              <div className="form-grid form-grid-tight">
                <Field label="服务商">
                  <Select
                    value={videoForm.providerId}
                    onChange={(event) => {
                      const providerId = event.target.value;
                      const defaults = videoProviderDefaults(providerId);
                      setVideoForm((state) => ({
                        ...state,
                        providerId,
                        apiBase: state.apiBase.trim() && state.providerId === providerId ? state.apiBase : defaults.apiBase,
                        model: defaults.model || state.model,
                      }));
                    }}
                  >
                    <option value="agnes">Agnes Video V2.0</option>
                    <option value="dashscope">DashScope / 快乐马</option>
                    <option value="seedance">火山引擎 Seedance</option>
                    <option value="custom">自定义兼容服务</option>
                  </Select>
                </Field>
                <Field label="模型">
                  <Input value={videoForm.model} onChange={(event) => setVideoForm((state) => ({ ...state, model: event.target.value }))} placeholder="happyhorse-1.0-t2v" />
                </Field>
              </div>
              <Field label="视频地址">
                <Input value={videoForm.apiBase} onChange={(event) => setVideoForm((state) => ({ ...state, apiBase: event.target.value }))} placeholder="https://apihub.agnes-ai.com/v1" />
              </Field>
              <Field label="视频密钥" hint={maskSecret(videoForm.apiKey)}>
                <Input type="password" value={videoForm.apiKey} onChange={(event) => setVideoForm((state) => ({ ...state, apiKey: event.target.value }))} placeholder="示例：视频密钥" />
              </Field>
            </section>
          </div>
        </Panel>

        <Panel className="surface-panel">
          <SectionHeader eyebrow="配置文件" title="本页会写入的配置文件" subtitle="只写现有配置文件，不改后端路径、字段名和鉴权逻辑。" />
          <div className="path-list">
            {data?.configPaths.map((item) => (
              <div key={item.key} className="path-card">
                <strong>{item.key}</strong>
                <span>{item.path}</span>
                <Chip tone={item.writable ? 'ok' : 'warn'}>{item.writable ? '可写' : '只读'}</Chip>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="surface-panel">
          <SectionHeader eyebrow="环境变量" title="相关环境变量" subtitle="用于核对配置来源，密钥仍然脱敏显示。" />
          <details className="settings-details">
            <summary>展开环境变量</summary>
            <div className="env-list">
              {data?.env.map((item) => (
                <div key={item.key} className="env-row">
                  <strong>{item.key}</strong>
                  <span>{item.value}</span>
                  <Chip tone={item.value === '未设置' || item.value.includes('未') ? 'warn' : 'ok'}>{item.note}</Chip>
                </div>
              ))}
            </div>
          </details>
        </Panel>

        <Panel className="surface-panel surface-panel-wide">
          <SectionHeader eyebrow="高级" title="原始 JSON 快照" subtitle="日常只改上面的结构化表单；JSON 保留给排查和迁移时查看。" />
          <details className="settings-details">
            <summary>展开 JSON 编辑器</summary>
            <div className="form-grid">
              <Field label="模型配置">
                <TextArea rows={9} value={jsonDrafts.authProfiles} onChange={(event) => {
                  setJsonDrafts((state) => ({ ...state, authProfiles: event.target.value }));
                  const parsed = parseJson(event.target.value, authProfiles);
                  setAuthProfiles(parsed);
                  setGatewayForm(formFromAuthProfiles(parsed));
                }} />
              </Field>
              <Field label="图像配置">
                <TextArea rows={9} value={jsonDrafts.imageConfig} onChange={(event) => {
                  setJsonDrafts((state) => ({ ...state, imageConfig: event.target.value }));
                  const parsed = parseJson(event.target.value, imageConfig);
                  setImageConfig(parsed);
                  setImageForm({
                    baseUrl: stringValue(parsed.baseUrl),
                    apiKey: stringValue(parsed.apiKey),
                    model: stringValue(parsed.model) || 'gpt-image-2',
                  });
                }} />
              </Field>
              <Field label="视频配置">
                <TextArea rows={9} value={jsonDrafts.videoConfig} onChange={(event) => {
                  setJsonDrafts((state) => ({ ...state, videoConfig: event.target.value }));
                  const parsed = parseJson(event.target.value, videoConfig);
                  setVideoConfig(parsed);
                  setVideoForm({
                    providerId: inferVideoProviderId(parsed.providerId, parsed.apiBase || parsed.baseUrl, parsed.model),
                    apiBase: stringValue(parsed.apiBase) || stringValue(parsed.baseUrl),
                    apiKey: stringValue(parsed.apiKey) || stringValue(parsed.dashKey),
                    model: stringValue(parsed.model) || videoProviderDefaults(parsed.providerId).model,
                  });
                }} />
              </Field>
              <Field label="OpenClaw 配置">
                <TextArea rows={9} value={jsonDrafts.openclawConfig} onChange={(event) => {
                  setJsonDrafts((state) => ({ ...state, openclawConfig: event.target.value }));
                  setOpenclawConfig(parseJson(event.target.value, openclawConfig));
                }} />
              </Field>
            </div>
          </details>
        </Panel>
      </section>

      {loading ? <Panel className="panel-loading">正在读取设置快照...</Panel> : null}
      {error ? <Panel className="panel-error">{error}</Panel> : null}
    </div>
  );
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function formatJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function parseJson(value: string, fallback: unknown = {}) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function cloneRecord(value: any): any {
  return JSON.parse(JSON.stringify(value || {}));
}

function formFromAuthProfiles(value: any): GatewayForm {
  const source = value && typeof value === 'object' ? value : {};
  const providers = source.models?.providers && typeof source.models.providers === 'object'
    ? source.models.providers
    : {};
  const primaryKey = source.models?.primary && providers[source.models.primary]
    ? source.models.primary
    : Object.keys(providers)[0];
  const provider = primaryKey ? providers[primaryKey] || {} : {};
  const models = Array.isArray(provider.models) ? provider.models : [];
  const firstModel = models
    .map((item: any) => typeof item === 'string' ? item : item?.id)
    .find(Boolean);
  return {
    baseUrl: stringValue(provider.baseUrl) || stringValue(provider.url),
    apiKey: stringValue(provider.apiKey),
    model: stringValue(firstModel) || stringValue(provider.model) || 'gpt-4o',
  };
}

function withPrimaryProvider(value: any, form: GatewayForm) {
  const next = cloneRecord(value);
  next.models = next.models || {};
  next.models.providers = next.models.providers || {};
  const primaryKey = next.models.primary && next.models.providers[next.models.primary]
    ? next.models.primary
    : Object.keys(next.models.providers)[0] || 'openclaw_gateway';
  next.models.primary = primaryKey;
  next.models.providers[primaryKey] = {
    ...(next.models.providers[primaryKey] || {}),
    id: primaryKey,
    name: next.models.providers[primaryKey]?.name || 'OpenClaw Gateway',
    baseUrl: form.baseUrl.trim(),
    apiKey: form.apiKey.trim(),
    models: form.model.trim() ? [form.model.trim()] : [],
  };
  return next;
}

function inferVideoProviderId(providerId: unknown, apiBase: unknown, model: unknown): string {
  const id = stringValue(providerId).toLowerCase();
  const base = stringValue(apiBase).toLowerCase();
  const modelId = stringValue(model).toLowerCase();
  if (id === 'agnes' || base.includes('agnes-ai.com') || modelId.startsWith('agnes-video')) return 'agnes';
  if (id === 'seedance' || base.includes('volces.com') || modelId.includes('seedance')) return 'seedance';
  if (id === 'custom') return 'custom';
  return id || 'dashscope';
}

function videoProviderDefaults(providerId: unknown) {
  const id = stringValue(providerId).toLowerCase();
  if (id === 'agnes') return { apiBase: 'https://apihub.agnes-ai.com/v1', model: 'agnes-video-v2.0' };
  if (id === 'seedance') return { apiBase: 'https://ark.cn-beijing.volces.com', model: 'doubao-seedance-2-0-pro-260215' };
  if (id === 'dashscope') return { apiBase: 'https://dashscope.aliyuncs.com/api/v1', model: 'happyhorse-1.0-t2v' };
  return { apiBase: '', model: '' };
}

function sanitizeOpenClawConfig(value: any) {
  const next = cloneRecord(value);
  delete next.launcherPreview;
  return next;
}

function commandResultDetail(result: { code?: number | null; stdout?: string; stderr?: string } | undefined) {
  const detail = [result?.stderr, result?.stdout].filter(Boolean).join('\n').trim();
  return detail || `退出码：${result?.code ?? 'unknown'}`;
}

function transportLabel(value: string) {
  const map: Record<string, string> = {
    mock: '预览模式',
    auto: '自动选择',
    live: '真实接口',
  };
  return map[value] || value;
}
