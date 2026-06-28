import React from 'react';
import {
  jobApi,
  parseErrorText,
  phoneApi,
  type BridgeJob,
  type PhoneConfigSnapshot,
  type PhoneDeviceSummary,
} from '../../services/api';
import { Button, Input, TextArea, showToast } from '../common';

type CliResult = {
  success?: boolean;
  stdout?: string;
  stderr?: string;
  code?: number | string;
  message?: string;
  error?: string;
  wire?: {
    models?: {
      phone?: string;
      text?: string;
    };
  };
  syncResults?: Array<{ target?: string; ok?: boolean; error?: string }>;
};

const PHONE_JOB_LABELS = new Set([
  '手机 Agent',
  '多设备',
  '手机视觉',
  '手机录屏',
  '手机设备',
  '手机连接',
  '手机截图',
  '读取屏幕',
  '手机最近任务',
  '手机模型同步',
]);
const DEFAULT_READ_PROMPT = '只读取当前手机屏幕，不要点击、输入或滑动。请用中文返回当前页面名称和三个可见内容。';

function statusLabel(status: string): string {
  const key = String(status || '').toLowerCase();
  if (key === 'queued') return '排队中';
  if (key === 'running') return '执行中';
  if (['succeeded', 'success', 'completed', 'complete'].includes(key)) return '已完成';
  if (['failed', 'error'].includes(key)) return '失败';
  return status || '-';
}

function jobTone(status: string): string {
  const key = String(status || '').toLowerCase();
  if (['succeeded', 'success', 'completed', 'complete'].includes(key)) return 'border-status-success/30 bg-status-success/10 text-status-success';
  if (['failed', 'error'].includes(key)) return 'border-status-danger/30 bg-status-danger/10 text-status-danger';
  if (['queued', 'running'].includes(key)) return 'border-accent/30 bg-accent/10 text-accent';
  return 'border-border/70 bg-surface/35 text-text-muted';
}

function parseJsonMaybe(text?: string): any {
  const value = String(text || '').trim();
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function isDoneStatus(status: string): boolean {
  return ['succeeded', 'success', 'completed', 'complete'].includes(String(status || '').toLowerCase());
}

function isFailedStatus(status: string): boolean {
  return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status || '').toLowerCase());
}

function friendlyPhoneText(input?: string): string {
  const text = String(input || '').trim();
  if (!text) return '';
  if (/No APKClaw devices are configured/i.test(text)) {
    return '未配置手机设备。请先在手机配置中添加 APKClaw 地址和令牌，然后重新检测。';
  }
  if (/Missing phone URL/i.test(text)) {
    return '缺少手机连接地址。请先配置 APKClaw 手机地址，或确认运行时配置已同步。';
  }
  if (/Missing phone token/i.test(text)) {
    return '缺少手机连接令牌。请先配置 APKClaw 手机令牌，或重新完成手机配对。';
  }
  if (/Unknown APKClaw device id/i.test(text)) {
    return '未找到指定手机设备。请刷新设备列表后重新选择。';
  }
  if (/fetch failed|ECONNREFUSED|ETIMEDOUT|timed out|network/i.test(text)) {
    return '手机连接失败。请确认手机端 APKClaw 已启动，并且电脑与手机在同一网络。';
  }
  return text;
}

async function waitForPhoneJob(jobId: string, timeoutMs = 4 * 60 * 1000): Promise<BridgeJob<CliResult>> {
  const deadline = Date.now() + timeoutMs;
  let lastJob: BridgeJob<CliResult> | null = null;
  while (Date.now() < deadline) {
    const resp = await jobApi.get(jobId) as { job: BridgeJob<CliResult> };
    lastJob = resp.job;
    if (isDoneStatus(lastJob.status) || isFailedStatus(lastJob.status)) return lastJob;
    await new Promise((resolve) => window.setTimeout(resolve, 1300));
  }
  throw { error: lastJob?.progress?.message || lastJob?.message || '手机任务超时，请检查手机连接状态。' };
}

function firstResultText(job: BridgeJob<CliResult> | null): string {
  const result = job?.result;
  if (result?.wire?.models?.phone) {
    const failed = result.syncResults?.find((item) => item.ok === false);
    if (failed) return friendlyPhoneText(failed.error || result.error || '手机模型同步失败');
    return `手机模型已同步：${result.wire.models.phone}`;
  }
  if (result?.message) return friendlyPhoneText(result.message);
  const parsed = parseJsonMaybe(result?.stdout);
  if (parsed?.final?.result?.summary) return String(parsed.final.result.summary);
  if (parsed?.final?.result?.text) return String(parsed.final.result.text);
  if (parsed?.final?.summary) return String(parsed.final.summary);
  if (parsed?.filePath || parsed?.path) {
    return '截图已保存，可在诊断日志中查看。';
  }
  if (parsed?.rows?.length) {
    return parsed.rows
      .slice(0, 3)
      .map((row: any) => row.summary || row.error || row.status || row.taskId || '')
      .filter(Boolean)
      .join('\n');
  }
  if (parsed?.devices?.length) {
    return parsed.devices
      .map((device: any) => `${device.selected ? '* ' : ''}${device.name || device.id || 'Android'}：${device.configured ? '已配置' : '未配置'}`)
      .join('\n');
  }
  if (parsed?.results?.length) {
    return parsed.results
      .map((item: any) => `${item.device?.name || item.device?.id || '设备'}：${item.ok === false ? '连接失败' : '在线'}`)
      .join('\n');
  }
  return friendlyPhoneText(result?.stdout || result?.stderr || job?.error || job?.message || '');
}

function screenshotPath(job: BridgeJob<CliResult> | null): string {
  const parsed = parseJsonMaybe(job?.result?.stdout);
  return String(parsed?.filePath || parsed?.path || '');
}

function phoneJobs(jobs: BridgeJob[]): BridgeJob[] {
  return jobs.filter((job) => PHONE_JOB_LABELS.has(String(job.label || '')));
}

function selectedPhoneDevice(snapshot?: PhoneConfigSnapshot): PhoneDeviceSummary | null {
  const devices = snapshot?.devices || [];
  return devices.find((device) => device.id && device.id === snapshot?.selectedDeviceId) || devices[0] || null;
}

const Metric: React.FC<{ label: string; value: string; tone?: 'ok' | 'warn' | 'neutral' }> = ({ label, value, tone = 'neutral' }) => (
  <div className="border-t border-border/70 py-4">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className={`mt-2 truncate text-xl font-black ${
      tone === 'ok' ? 'text-status-success' : tone === 'warn' ? 'text-status-warning' : 'text-text'
    }`} title={value}>
      {value}
    </div>
  </div>
);

const JobRow: React.FC<{ job: BridgeJob<CliResult>; onSelect: () => void }> = ({ job, onSelect }) => (
  <button
    type="button"
    onClick={onSelect}
    className="w-full border-t border-border/60 py-3 text-left transition hover:border-border-strong"
  >
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-black text-text">{job.label || job.kind || job.id}</div>
        <div className="mt-1 truncate text-xs text-text-muted">{job.progress?.message || job.message || job.id}</div>
      </div>
      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${jobTone(job.status)}`}>
        {statusLabel(job.status)}
      </span>
    </div>
  </button>
);

const LockedCard: React.FC<{ title: string; desc: string }> = ({ title, desc }) => (
  <div className="border-t border-border/60 py-3">
    <div className="flex items-center justify-between gap-3">
      <div>
        <div className="text-sm font-black text-text">{title}</div>
        <div className="mt-1 text-xs leading-5 text-text-muted">{desc}</div>
      </div>
      <span className="shrink-0 rounded-full border border-status-warning/30 bg-status-warning/10 px-3 py-1 text-xs font-bold text-status-warning">
        暂未开放
      </span>
    </div>
  </div>
);

export const PhoneDemoPage: React.FC = () => {
  const [jobs, setJobs] = React.useState<BridgeJob[]>([]);
  const [busy, setBusy] = React.useState('');
  const [lastJob, setLastJob] = React.useState<BridgeJob<CliResult> | null>(null);
  const [prompt, setPrompt] = React.useState(DEFAULT_READ_PROMPT);
  const [deviceSummary, setDeviceSummary] = React.useState('未检测');
  const [connectionSummary, setConnectionSummary] = React.useState('未检测');
  const [lastScreenshotPath, setLastScreenshotPath] = React.useState('');
  const [selectedDeviceId, setSelectedDeviceId] = React.useState('phone-1');
  const [deviceName, setDeviceName] = React.useState('Android Phone');
  const [phoneUrl, setPhoneUrl] = React.useState('');
  const [phoneToken, setPhoneToken] = React.useState('');
  const [tokenAvailable, setTokenAvailable] = React.useState(false);
  const canUsePhone = Boolean(phoneUrl.trim() && (tokenAvailable || phoneToken.trim()));

  const refreshJobs = React.useCallback(async () => {
    try {
      const resp = await jobApi.list(40);
      setJobs(phoneJobs(resp.jobs || []));
    } catch {
      // Recent jobs are helpful but not required for the page to load.
    }
  }, []);

  const applyPhoneConfig = React.useCallback((snapshot: PhoneConfigSnapshot) => {
    const selected = selectedPhoneDevice(snapshot);
    setSelectedDeviceId(snapshot.selectedDeviceId || selected?.id || 'phone-1');
    setDeviceName(selected?.name || selected?.id || 'Android Phone');
    setPhoneUrl(selected?.baseUrl || '');
    setTokenAvailable(Boolean(selected?.tokenAvailable));
    setPhoneToken('');
    if (snapshot.devices?.length) {
      setDeviceSummary(`${snapshot.devices.length} 台 / ${selected?.name || selected?.id || '已配置'}`);
    } else {
      setDeviceSummary('未配置设备');
    }
  }, []);

  const loadPhoneConfig = React.useCallback(async () => {
    try {
      const snapshot = await phoneApi.config();
      applyPhoneConfig(snapshot);
    } catch (error: any) {
      showToast(parseErrorText(error) || '读取手机连接配置失败', 'error');
    }
  }, [applyPhoneConfig]);

  React.useEffect(() => {
    void loadPhoneConfig();
    void refreshJobs();
    const timer = window.setInterval(refreshJobs, 2200);
    return () => window.clearInterval(timer);
  }, [loadPhoneConfig, refreshJobs]);

  const runPhone = React.useCallback(async (
    key: string,
    submit: () => Promise<unknown>,
    onDone?: (job: BridgeJob<CliResult>) => void,
  ) => {
    setBusy(key);
    try {
      const submitted = await submit() as { jobId?: string; job?: BridgeJob<CliResult> };
      const jobId = submitted.jobId || submitted.job?.id;
      if (!jobId) throw new Error('手机任务提交失败');
      showToast('手机任务已提交', 'success');
      const done = await waitForPhoneJob(jobId);
      setLastJob(done);
      onDone?.(done);
      await refreshJobs();
      if (isFailedStatus(done.status)) {
        showToast(firstResultText(done) || '手机任务执行失败，请检查手机连接和诊断日志', 'error');
        return done;
      }
      return done;
    } catch (error: any) {
      showToast(parseErrorText(error) || '手机任务执行失败，请检查手机连接和诊断日志', 'error');
      await refreshJobs();
      return null;
    } finally {
      setBusy('');
    }
  }, [refreshJobs]);

  const saveDeviceAndDetect = async () => {
    const cleanUrl = phoneUrl.trim();
    const cleanName = deviceName.trim() || 'Android Phone';
    const cleanToken = phoneToken.trim();
    if (!cleanUrl) {
      showToast('请输入 APKClaw 手机地址', 'error');
      return;
    }
    if (!cleanToken && !tokenAvailable) {
      showToast('请输入 APKClaw 连接令牌', 'error');
      return;
    }
    setBusy('config');
    try {
      const snapshot = await phoneApi.saveDevice({
        id: selectedDeviceId || cleanName || 'phone-1',
        name: cleanName,
        baseUrl: cleanUrl,
        token: cleanToken,
        selectedDeviceId: selectedDeviceId || 'phone-1',
      });
      applyPhoneConfig(snapshot);
      setPhoneToken('');
      showToast('手机连接配置已保存', 'success');
      await checkConnection();
    } catch (error: any) {
      showToast(friendlyPhoneText(parseErrorText(error)) || '保存手机连接配置失败', 'error');
    } finally {
      setBusy('');
    }
  };

  const refreshDevices = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机地址和连接令牌', 'info');
      return;
    }
    await runPhone('devices', () => phoneApi.devices(), (job) => {
      const parsed = parseJsonMaybe(job.result?.stdout);
      const count = Array.isArray(parsed?.devices) ? parsed.devices.length : 0;
      const selected = parsed?.devices?.find?.((device: any) => device.selected) || parsed?.devices?.[0];
      setDeviceSummary(count ? `${count} 台 / ${selected?.name || selected?.id || '已配置'}` : '未配置设备');
    });
  };

  const checkConnection = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机地址和连接令牌', 'info');
      return;
    }
    await runPhone('status', () => phoneApi.status(), (job) => {
      const parsed = parseJsonMaybe(job.result?.stdout);
      const text = firstResultText(job);
      const ok =
        parsed?.ok === true ||
        parsed?.success === true ||
        parsed?.results?.some?.((item: any) => item?.ok !== false);
      setConnectionSummary(ok ? '已连接' : text || '检测完成');
    });
  };

  const captureFrame = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机地址和连接令牌', 'info');
      return;
    }
    await runPhone('frame', () => phoneApi.screenshot(), (job) => {
      const path = screenshotPath(job);
      setLastScreenshotPath(path ? '已保存' : '截图已完成');
    });
  };

  const readScreen = async () => {
    if (!canUsePhone) {
      showToast('请先保存手机地址和连接令牌', 'info');
      return;
    }
    const text = prompt.trim() || DEFAULT_READ_PROMPT;
    await runPhone('read', () => phoneApi.read({ prompt: text }));
  };

  const syncPhoneModel = async () => {
    await runPhone('syncModel', () => phoneApi.syncModel(), (job) => {
      const model = job.result?.wire?.models?.phone;
      if (model) showToast(`手机模型已同步：${model}`, 'success');
    });
  };

  const loadHistory = async () => {
    await runPhone('history', () => phoneApi.history());
  };

  const lastText = firstResultText(lastJob);

  return (
    <div className="h-full overflow-y-auto bg-app-bg">
      <div className="mx-auto flex w-full max-w-[1220px] flex-col gap-7 px-8 py-7">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">手机控制</div>
            <h1 className="mt-2 text-[36px] font-black leading-tight text-text">手机演示台</h1>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="quiet" onClick={refreshJobs}>刷新任务</Button>
            <Button variant="primary" onClick={checkConnection} disabled={Boolean(busy) || !canUsePhone}>
              {busy === 'status' ? '检测中...' : '检测连接'}
            </Button>
          </div>
        </header>

        <section className="grid gap-x-8 gap-y-2 md:grid-cols-3">
          <Metric label="设备" value={deviceSummary} tone={deviceSummary.includes('未') ? 'warn' : 'ok'} />
          <Metric label="连接" value={connectionSummary} tone={connectionSummary.includes('已连接') ? 'ok' : 'warn'} />
          <Metric label="最近截图" value={lastScreenshotPath ? '已保存' : '暂无'} tone={lastScreenshotPath ? 'ok' : 'neutral'} />
        </section>

        <section className="border-t border-border/70 pt-7">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">演示流程</div>
              <h2 className="mt-1 text-2xl font-black text-text">检测设备、截图、读取屏幕</h2>
            </div>
            <span className="rounded-full border border-border/70 bg-surface-alt/40 px-3 py-1 text-xs font-bold text-text-muted">
              APKClaw 安全协议
            </span>
          </div>

          <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-8">
              <section className="border-t border-border/70 pt-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-black text-text">手机连接配置</h2>
                    <p className="mt-1 text-xs leading-5 text-text-muted">
                      只保存本机连接信息；连接令牌不会回显到界面。
                    </p>
                  </div>
                  <Button variant="quiet" onClick={loadPhoneConfig} disabled={Boolean(busy)}>
                    读取配置
                  </Button>
                </div>
                <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)_220px]">
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">设备名称</span>
                    <Input
                      value={deviceName}
                      onChange={(event) => setDeviceName(event.target.value)}
                      placeholder="Android Phone"
                      disabled={Boolean(busy)}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">手机地址</span>
                    <Input
                      value={phoneUrl}
                      onChange={(event) => setPhoneUrl(event.target.value)}
                      placeholder="http://手机IP:端口"
                      disabled={Boolean(busy)}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-bold text-text-subtle">连接令牌</span>
                    <Input
                      type="password"
                      value={phoneToken}
                      onChange={(event) => setPhoneToken(event.target.value)}
                      placeholder={tokenAvailable ? '已保存，留空沿用' : 'APKClaw Token'}
                      disabled={Boolean(busy)}
                    />
                  </label>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button variant="primary" onClick={saveDeviceAndDetect} disabled={Boolean(busy)}>
                    {busy === 'config' || busy === 'status' ? '保存检测中...' : '保存并检测'}
                  </Button>
                  <span className="text-xs font-bold text-text-subtle">
                    {tokenAvailable ? '令牌已保存' : '未保存令牌'}
                  </span>
                </div>
              </section>

              <section className="border-t border-border/70 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-sm font-black text-text">模型同步</div>
                    <p className="mt-1 text-xs leading-5 text-text-muted">
                      登录中转站或配置第三方 Provider 后，一键写入手机 Agent 模型配置。
                    </p>
                  </div>
                  <Button variant="primary" onClick={syncPhoneModel} disabled={Boolean(busy)}>
                    {busy === 'syncModel' ? '同步中...' : '同步模型到手机'}
                  </Button>
                </div>
              </section>

              <section className="grid gap-x-6 gap-y-4 md:grid-cols-3">
                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">设备连接状态</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">读取已保存设备并检查当前连接。</p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button variant="primary" onClick={refreshDevices} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'devices' ? '读取中...' : '刷新设备'}
                    </Button>
                    <Button variant="quiet" onClick={checkConnection} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'status' ? '检测中...' : '检测连接'}
                    </Button>
                  </div>
                </div>

                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">截图 / 读取屏幕</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">优先走只读能力，避免演示时误操作手机。</p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button variant="primary" onClick={captureFrame} disabled={Boolean(busy) || !canUsePhone}>
                      {busy === 'frame' ? '截图中...' : '截图'}
                    </Button>
                    <Button variant="quiet" onClick={loadHistory} disabled={Boolean(busy)}>
                      {busy === 'history' ? '读取中...' : '读取历史'}
                    </Button>
                  </div>
                </div>

                <div className="border-t border-border/70 pt-4">
                  <div className="text-sm font-black text-text">任务状态</div>
                  <p className="mt-1 text-xs leading-5 text-text-muted">最近任务会保留在右侧，切页后再回来也能查看。</p>
                  <Button className="mt-4" variant="quiet" onClick={refreshJobs} disabled={Boolean(busy)}>
                    刷新任务
                  </Button>
                </div>
              </section>

              <section className="border-t border-border/70 pt-6">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">简单只读任务</h2>
                  <span className="text-xs font-bold text-text-subtle">observe</span>
                </div>
                <TextArea
                  rows={4}
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={DEFAULT_READ_PROMPT}
                />
                <Button className="mt-3" variant="primary" onClick={readScreen} disabled={Boolean(busy) || !canUsePhone}>
                  {busy === 'read' ? '读取中...' : '执行只读任务'}
                </Button>
              </section>

              <section className="border-t border-border/70 pt-6">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">任务结果</h2>
                  {lastJob ? (
                    <span className={`rounded-full border px-3 py-1 text-xs font-bold ${jobTone(lastJob.status)}`}>
                      {statusLabel(lastJob.status)}
                    </span>
                  ) : null}
                </div>
                {lastText ? (
                  <pre className="whitespace-pre-wrap break-words border-t border-border/60 pt-4 text-sm leading-7 text-text-muted">
                    {lastText}
                  </pre>
                ) : (
                  <div className="border-t border-border/60 pt-4 text-sm text-text-muted">
                    点击上方按钮后，这里会显示设备状态、截图结果或屏幕读取结果。
                  </div>
                )}
              </section>
            </div>

            <aside className="border-t border-border/70 pt-6 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
              <section>
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="text-lg font-black text-text">最近任务</h2>
                  <Button variant="quiet" onClick={refreshJobs}>刷新</Button>
                </div>
                <div>
                  {jobs.length ? jobs.slice(0, 8).map((job) => (
                    <JobRow key={job.id} job={job as BridgeJob<CliResult>} onSelect={() => setLastJob(job as BridgeJob<CliResult>)} />
                  )) : (
                    <div className="border-t border-border/60 py-3 text-sm text-text-muted">暂无手机任务</div>
                  )}
                </div>
              </section>

              <section className="mt-8">
                <h2 className="text-lg font-black text-text">暂未开放</h2>
                <div className="mt-2">
                  <LockedCard title="自动化模板" desc="演示版不开放复杂流程编排。" />
                  <LockedCard title="定时任务" desc="避免现场后台任务影响演示。" />
                </div>
              </section>
            </aside>
          </div>
        </section>
      </div>
    </div>
  );
};
