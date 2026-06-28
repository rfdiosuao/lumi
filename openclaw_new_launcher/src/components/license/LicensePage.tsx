import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { open } from '@tauri-apps/plugin-shell';
import { BusyOverlay, Button, Input, showToast } from '../common';
import { accountApi, licenseApi, parseErrorText, wireApi, type AccountSnapshot } from '../../services/api';
import { useAppStore } from '../../stores/appStore';

const ACTIVATION_CODE_LABEL_KEY = 'openclaw_activation_code_label';
const DEFAULT_BASE_URL = 'https://api.heang.top';
const LOGIN_PATH = '/sign-in';

type AuthMode = 'web' | 'license';

function activationCodeLabelFromCode(value: string): string {
  const last8 = value.replace(/[^a-z0-9]/gi, '').toUpperCase().slice(-8);
  return last8.length === 8 ? `${last8.slice(0, 4)}-${last8.slice(4)}` : last8;
}

function activationCodeLabelFromLicense(license: unknown): string {
  const data = license && typeof license === 'object' ? license as Record<string, unknown> : {};
  const explicit = String(data.activationCodeLabel || data.codeLabel || '').trim();
  if (explicit) return explicit;
  const last8 = String(data.activationCodeLast8 || '').trim();
  return last8 ? activationCodeLabelFromCode(last8) : '';
}

function errorMessage(error: unknown): string {
  const friendly = parseErrorText(error);
  if (friendly) return friendly;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    if (typeof record.error === 'string') return record.error;
    if (typeof record.message === 'string') return record.message;
  }
  return '请求失败';
}

function modelTotal(account: AccountSnapshot | null): number {
  const models = account?.models || {};
  return (models.text?.length || 0) + (models.image?.length || 0) + (models.video?.length || 0);
}

function usageValue(account: AccountSnapshot | null, keys: string[], fallback = '暂无'): string {
  const usage = account?.usage;
  if (!usage || typeof usage !== 'object') return fallback;
  for (const key of keys) {
    const value = usage[key];
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return fallback;
}

function formatTime(value?: string): string {
  if (!value) return '暂无';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function normalizeBaseUrl(value: string): string {
  const text = String(value || '').trim() || DEFAULT_BASE_URL;
  return text.replace(/\/+$/, '').replace(/\/v1$/i, '');
}

function loginPageUrl(value: string): string {
  return `${normalizeBaseUrl(value)}${LOGIN_PATH}`;
}

export const LicensePage: React.FC = () => {
  const [mode, setMode] = useState<AuthMode>('web');
  const [code, setCode] = useState('');
  const [account, setAccount] = useState<AccountSnapshot | null>(null);
  const [loginEmail, setLoginEmail] = useState('');
  const [emailCode, setEmailCode] = useState('');
  const [emailCodeSent, setEmailCodeSent] = useState(false);
  const [accountPassword, setAccountPassword] = useState('');
  const [accountBaseUrl, setAccountBaseUrl] = useState(DEFAULT_BASE_URL);
  const [bindTicket, setBindTicket] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [statusText, setStatusText] = useState('');
  const [wireStatus, setWireStatus] = useState('');
  const [cardSite, setCardSite] = useState<{ enabled?: boolean; label?: string; url?: string } | null>(null);
  const { isAuthorized, licenseInfo, setAuthorized, setLicenseInfo, setCurrentPage } = useAppStore();

  const accountLoggedIn = Boolean(account?.loggedIn);
  const accountModelTotal = modelTotal(account);

  const applyAuthSnapshot = useCallback((nextAccount: AccountSnapshot | null, nextLicense: unknown, gatewayProfile?: unknown) => {
    setAccount(nextAccount);
    const effectiveProfile = nextLicense || gatewayProfile || (nextAccount?.loggedIn ? {
      licensee: nextAccount.account || 'NewAPI Account',
      edition: nextAccount.plan || 'account',
      gatewayBaseUrl: nextAccount.gatewayBaseUrl,
      gatewayDefaultModel: nextAccount.models?.text?.[0],
      managedBy: nextAccount.source || 'newapi_account',
    } : null);
    setLicenseInfo(effectiveProfile as any);
    setAuthorized(Boolean(nextAccount?.loggedIn || effectiveProfile));
  }, [setAuthorized, setLicenseInfo]);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setStatusText('');
    try {
      const [accountResp, licenseResp, clientResp] = await Promise.allSettled([
        accountApi.current(),
        licenseApi.current(),
        licenseApi.clientConfig(),
      ]);
      const nextAccount = accountResp.status === 'fulfilled' ? accountResp.value.account || null : null;
      const nextLicense = licenseResp.status === 'fulfilled' ? licenseResp.value.license : null;
      const gatewayProfile = licenseResp.status === 'fulfilled' ? (licenseResp.value as any).gatewayProfile : null;
      const site = clientResp.status === 'fulfilled' ? clientResp.value.cardSite : null;
      setCardSite(site?.enabled && site.url ? site : null);
      applyAuthSnapshot(nextAccount, nextLicense, gatewayProfile);
      if (accountResp.status === 'rejected') setStatusText(errorMessage(accountResp.reason));
    } finally {
      setLoading(false);
    }
  }, [applyAuthSnapshot]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  const handleSendEmailCode = async () => {
    if (!loginEmail.trim()) {
      showToast('请输入中转站注册邮箱', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在发送邮箱验证码...');
    try {
      await accountApi.sendEmailCode({
        email: loginEmail.trim(),
        baseUrl: normalizeBaseUrl(accountBaseUrl),
      });
      setEmailCodeSent(true);
      setStatusText('验证码已发送，请查看邮箱');
      showToast('验证码已发送', 'success');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('验证码发送失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleEmailCodeLogin = async () => {
    if (!loginEmail.trim() || !emailCode.trim()) {
      showToast('请输入邮箱和验证码', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在登录并同步托管模型...');
    try {
      const resp = await accountApi.loginWithEmailCode({
        email: loginEmail.trim(),
        code: emailCode.trim(),
        baseUrl: normalizeBaseUrl(accountBaseUrl),
      });
      setEmailCode('');
      setEmailCodeSent(false);
      applyAuthSnapshot(resp.account || null, null);
      setStatusText('中转站账号已登录，模型已同步');
      showToast('登录成功，模型已同步', 'success');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('验证码登录失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleAccountLogin = async () => {
    if (!loginEmail.trim() || !accountPassword.trim()) {
      showToast('请输入邮箱和密码', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在登录并同步模型...');
    try {
      const resp = await accountApi.login({
        email: loginEmail.trim(),
        password: accountPassword,
        baseUrl: normalizeBaseUrl(accountBaseUrl),
      });
      setAccountPassword('');
      applyAuthSnapshot(resp.account || null, null);
      setStatusText('邮箱已登录，模型已同步');
      showToast('邮箱已登录', 'success');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('邮箱登录失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleBindTicket = async () => {
    if (!bindTicket.trim()) {
      showToast('请输入网站绑定码', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在绑定网站账号...');
    try {
      const resp = await accountApi.bindTicket({
        ticket: bindTicket.trim(),
        baseUrl: normalizeBaseUrl(accountBaseUrl),
      });
      setBindTicket('');
      applyAuthSnapshot(resp.account || null, null);
      setStatusText('网站账号已绑定');
      showToast('网站账号已绑定', 'success');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('网站绑定失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleAccountSync = async () => {
    setBusy(true);
    setStatusText('正在同步模型...');
    try {
      const resp = await accountApi.sync();
      applyAuthSnapshot(resp.account || null, null);
      setStatusText('模型已同步');
      setWireStatus('运行配置已同步');
      showToast('模型已同步', 'success');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('同步失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleWireVerify = async () => {
    setBusy(true);
    setWireStatus('正在验证运行配置...');
    try {
      const result = await wireApi.verify();
      const targets = result.targets || {};
      const failed = Object.entries(targets).filter(([, item]) => !item?.ok).map(([key]) => key);
      setWireStatus(result.ok ? '运行配置验证通过' : `需要处理：${failed.join(' / ') || '运行配置未完成'}`);
      showToast(result.ok ? '运行配置验证通过' : '运行配置需要处理', result.ok ? 'success' : 'error');
    } catch (error) {
      setWireStatus(errorMessage(error));
      showToast('验证失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleWireRollback = async () => {
    if (!confirm('确定回滚到上一次模型同步配置吗？账号不会退出。')) return;
    setBusy(true);
    setWireStatus('正在回滚运行配置...');
    try {
      const result = await wireApi.rollback();
      setWireStatus(`已回滚到 ${result.wire?.models?.text || '上一组模型配置'}`);
      showToast('运行配置已回滚', 'success');
      await refreshAll();
    } catch (error) {
      setWireStatus(errorMessage(error));
      showToast('回滚失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleAccountLogout = async () => {
    setBusy(true);
    setStatusText('正在退出账号...');
    try {
      await accountApi.logout();
      await refreshAll();
      setStatusText('账号已退出');
      showToast('账号已退出', 'info');
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('退出失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenNewApiLogin = async () => {
    const url = loginPageUrl(accountBaseUrl);
    setStatusText('已打开中转站网页登录页；登录后请在网站生成绑定码，再回到 LOOM 绑定并同步模型。');
    try {
      await open(url);
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleActivate = async () => {
    if (!code.trim()) {
      showToast('请输入授权码', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在激活授权码...');
    try {
      const resp = await licenseApi.activate(code.trim());
      const license = resp.license;
      if (!license || typeof license !== 'object') {
        setStatusText('激活失败：服务器返回了无效许可证');
        showToast('激活失败', 'error');
        return;
      }
      const codeLabel = activationCodeLabelFromLicense(license) || activationCodeLabelFromCode(code);
      if (codeLabel) {
        try { localStorage.setItem(ACTIVATION_CODE_LABEL_KEY, codeLabel); } catch { /* ignore */ }
      }
      applyAuthSnapshot(account, license);
      setStatusText(`激活成功：${(license as any).licensee || 'LOOM User'}`);
      showToast('授权已激活', 'success');
      setTimeout(() => setCurrentPage('dashboard'), 600);
    } catch (error) {
      setStatusText(errorMessage(error));
      showToast('激活失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenCardSite = async () => {
    const url = String(cardSite?.url || '').trim();
    if (!url) {
      showToast('授权页面未配置', 'info');
      return;
    }
    try {
      await open(url);
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const activationCodeLabel = activationCodeLabelFromLicense(licenseInfo) || (() => {
    try { return localStorage.getItem(ACTIVATION_CODE_LABEL_KEY) || ''; } catch { return ''; }
  })();
  const statusTone = statusText.includes('成功') || statusText.includes('已') ? 'text-status-success' : statusText ? 'text-status-danger' : 'text-text-muted';
  const modelHint = useMemo(() => account?.models?.text?.slice(0, 4).join(' / ') || (licenseInfo as any)?.gatewayDefaultModel || '暂无', [account, licenseInfo]);

  const busyOverlayTitle = loading ? '正在读取账号状态' : '正在同步中转站';

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <BusyOverlay
        active={loading || busy}
        title={busyOverlayTitle}
        detail="LOOM 正在处理账号、模型和本地配置。"
      />
      <header className="shrink-0 border-b border-border/70 bg-surface px-8 py-7">
        <div className="flex items-end justify-between gap-6">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">账号</div>
            <h1 className="mt-2 text-[30px] font-black leading-tight text-text">中转站登录</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className={`rounded-full border px-3 py-2 text-xs font-black ${
              accountLoggedIn || isAuthorized
                ? 'border-status-success/30 bg-status-success/10 text-status-success'
                : 'border-status-warning/30 bg-status-warning/10 text-status-warning'
            }`}>
              {accountLoggedIn ? '邮箱已登录' : isAuthorized ? '已授权' : '未接入'}
            </span>
            <Button onClick={refreshAll} variant="quiet" disabled={busy || loading}>刷新</Button>
          </div>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
        <section className="mb-6 grid grid-cols-4 gap-3">
          <StatusTile label="邮箱" value={accountLoggedIn ? '已登录' : '未登录'} hint={account?.account || 'NewAPI'} tone={accountLoggedIn ? 'ok' : 'warn'} />
          <StatusTile label="订阅" value={account?.plan || '暂无'} hint={account?.status || '登录后同步'} tone={accountLoggedIn ? 'ok' : 'neutral'} />
          <StatusTile label="余额" value={usageValue(account, ['quota', 'remainQuota', 'remainingQuota'])} hint={`已用 ${usageValue(account, ['usedQuota', 'used_quota'], '0')}`} tone={accountLoggedIn ? 'ok' : 'neutral'} />
          <StatusTile label="模型" value={accountModelTotal ? `${accountModelTotal}` : '暂无'} hint={modelHint} tone={accountModelTotal ? 'ok' : 'neutral'} />
        </section>

        <section className="grid grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)] gap-5">
          <div className="rounded-[20px] border border-border/80 bg-surface-alt/30 p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <div className="text-[10px] font-bold tracking-[0.24em] text-text-subtle">登录</div>
                <h2 className="mt-1 text-lg font-black text-text">接入方式</h2>
              </div>
              <div className="flex rounded-[14px] border border-border/80 bg-surface/35 p-1">
                <ModeButton active={mode === 'web'} onClick={() => setMode('web')}>网页登录</ModeButton>
                <ModeButton active={mode === 'license'} onClick={() => setMode('license')}>授权码</ModeButton>
              </div>
            </div>

            {mode === 'web' ? (
              <div className="grid gap-4">
                <Field label="中转站地址">
                  <Input value={accountBaseUrl} onChange={(event) => setAccountBaseUrl(event.target.value)} placeholder={DEFAULT_BASE_URL} />
                </Field>
                <div className="rounded-[18px] border border-accent/25 bg-accent/10 p-4">
                  <div className="text-sm font-black text-text">邮箱验证码登录</div>
                  <div className="mt-2 text-sm leading-6 text-text-muted">
                    输入中转站注册邮箱，收到验证码后即可登录并一键同步托管模型配置。
                  </div>
                  <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                    <Input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} placeholder="请输入中转站注册邮箱" autoComplete="email" inputMode="email" />
                    <Button onClick={handleSendEmailCode} variant="quiet" disabled={busy}>
                      {emailCodeSent ? '重新发送' : '发送验证码'}
                    </Button>
                    <Input value={emailCode} onChange={(event) => setEmailCode(event.target.value)} placeholder="输入邮箱验证码" autoComplete="one-time-code" inputMode="numeric" />
                    <Button onClick={handleEmailCodeLogin} variant="primary" disabled={busy}>
                      {busy ? '处理中...' : '登录并同步'}
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-3 pt-1">
                  <Button onClick={handleAccountSync} variant="quiet" disabled={busy || !accountLoggedIn}>
                    同步模型
                  </Button>
                  <Button onClick={handleAccountLogout} variant="quiet" disabled={busy || !accountLoggedIn}>
                    退出
                  </Button>
                </div>
                <details className="rounded-[16px] border border-border/70 bg-surface/35 p-4">
                  <summary className="cursor-pointer text-sm font-black text-text-muted">备用：网页登录 / 绑定码</summary>
                  <div className="mt-4 grid gap-4">
                    <div className="rounded-[14px] border border-border/70 bg-surface-alt/25 p-4">
                      <div className="text-sm font-black text-text">打开中转站网页</div>
                      <div className="mt-2 text-sm leading-6 text-text-muted">
                        如果邮箱验证码暂不可用，可在网页登录后生成绑定码，再回到启动器完成同步。
                      </div>
                      <Button className="mt-4" onClick={handleOpenNewApiLogin} variant="quiet" disabled={busy}>
                        打开中转站登录页
                      </Button>
                    </div>
                    <Field label="网站绑定码" hint="登录网站后生成">
                      <Input value={bindTicket} onChange={(event) => setBindTicket(event.target.value)} placeholder="粘贴中转站绑定码" autoComplete="off" />
                    </Field>
                    <div>
                      <Button onClick={handleBindTicket} variant="default" disabled={busy}>
                        {busy ? '处理中...' : '绑定并同步模型'}
                      </Button>
                    </div>
                  </div>
                </details>
                <details className="rounded-[16px] border border-border/70 bg-surface/35 p-4">
                  <summary className="cursor-pointer text-sm font-black text-text-muted">高级：邮箱密码直连</summary>
                  <div className="mt-4 grid gap-4">
                    <Field label="邮箱">
                      <Input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} placeholder="请输入中转站注册邮箱" autoComplete="email" inputMode="email" />
                    </Field>
                    <Field label="密码">
                      <Input value={accountPassword} onChange={(event) => setAccountPassword(event.target.value)} placeholder="中转站登录密码" type="password" autoComplete="current-password" />
                    </Field>
                    <div>
                      <Button onClick={handleAccountLogin} variant="quiet" disabled={busy}>
                        {busy ? '处理中...' : '登录并同步'}
                      </Button>
                    </div>
                  </div>
                </details>
              </div>
            ) : (
              <div className="grid gap-4">
                <Field label="授权码">
                  <Input
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    placeholder="输入授权码"
                    className="font-mono"
                  />
                </Field>
                <div className="flex flex-wrap gap-3 pt-1">
                  <Button onClick={handleActivate} variant="primary" disabled={busy}>
                    {busy ? '激活中...' : isAuthorized ? '重新激活' : '在线激活'}
                  </Button>
                  {cardSite?.url ? (
                    <Button onClick={handleOpenCardSite} variant="quiet">
                      {cardSite.label || '获取授权'}
                    </Button>
                  ) : null}
                </div>
              </div>
            )}

            {statusText ? (
              <div className={`mt-5 rounded-[16px] border border-border/70 bg-surface/35 p-4 text-sm font-semibold ${statusTone}`}>
                {statusText}
              </div>
            ) : null}
          </div>

          <div className="space-y-5">
            <Panel title="当前邮箱" badge={accountLoggedIn ? '已登录' : '未登录'}>
              {accountLoggedIn ? (
                <div className="space-y-3 text-sm">
                  <InfoRow label="邮箱" value={account?.account || '暂无'} />
                  <InfoRow label="用户 ID" value={account?.memberId || '暂无'} />
                  <InfoRow label="订阅" value={account?.plan || 'default'} />
                  <InfoRow label="余额" value={usageValue(account, ['quota', 'remainQuota', 'remainingQuota'])} />
                  <InfoRow label="已用" value={usageValue(account, ['usedQuota', 'used_quota'], '0')} />
                  <InfoRow label="网关" value={account?.gatewayBaseUrl || '暂无'} />
                  <InfoRow label="最近同步" value={formatTime(account?.lastOnlineAt)} />
                </div>
              ) : (
                <div className="text-sm leading-6 text-text-muted">访客模式可查看安装器；运行能力需要邮箱登录或授权码。</div>
              )}
            </Panel>

            <Panel title="模型同步" badge={accountModelTotal ? `${accountModelTotal} 个` : '暂无'}>
              <div className="space-y-3 text-sm">
                <ModelLine label="文本" values={account?.models?.text} />
                <ModelLine label="图像" values={account?.models?.image} />
                <ModelLine label="视频" values={account?.models?.video} />
              </div>
              <div className="mt-4">
                <Button variant="quiet" onClick={() => setCurrentPage('models')}>
                  模型来源
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-3">
                <Button variant="quiet" onClick={handleWireVerify} disabled={busy || !accountLoggedIn}>
                  验证同步
                </Button>
                <Button variant="quiet" onClick={handleWireRollback} disabled={busy || !accountLoggedIn}>
                  回滚同步
                </Button>
              </div>
              {wireStatus ? (
                <div className="mt-3 rounded-[14px] border border-border/70 bg-surface/35 p-3 text-xs font-bold text-text-muted">
                  {wireStatus}
                </div>
              ) : null}
              {account?.models?.video?.length ? (
                <div className="mt-4 rounded-[14px] border border-status-warning/30 bg-status-warning/10 p-3 text-xs text-status-warning">
                  视频模型只展示，不自动切换通道。
                </div>
              ) : null}
            </Panel>

            <Panel title="兼容授权" badge={isAuthorized && !accountLoggedIn ? '已激活' : '兼容'}>
              <div className="space-y-3 text-sm">
                <InfoRow label="授权码" value={activationCodeLabel || '暂无'} />
                <InfoRow label="客户" value={(licenseInfo as any)?.licensee || '暂无'} />
                <InfoRow label="版本" value={(licenseInfo as any)?.edition || (licenseInfo as any)?.plan || '暂无'} />
                <InfoRow label="到期" value={(licenseInfo as any)?.expires || (licenseInfo as any)?.expiresAt || '永久'} />
              </div>
            </Panel>
          </div>
        </section>
      </div>
    </div>
  );
};

const ModeButton: React.FC<{ active: boolean; onClick: () => void; children: React.ReactNode }> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded-[11px] px-4 py-2 text-xs font-black transition ${
      active ? 'bg-accent text-accent-ink' : 'text-text-muted hover:bg-surface-alt/70 hover:text-text'
    }`}
  >
    {children}
  </button>
);

const Field: React.FC<{ label: string; hint?: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <label className="block">
    <div className="mb-2 flex items-center gap-2 text-xs font-bold text-text-muted">
      <span>{label}</span>
      {hint ? <span className="text-text-subtle">{hint}</span> : null}
    </div>
    {children}
  </label>
);

const Panel: React.FC<{ title: string; badge?: string; children: React.ReactNode }> = ({ title, badge, children }) => (
  <div className="rounded-[20px] border border-border/80 bg-surface-alt/30 p-5">
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="text-lg font-black text-text">{title}</h2>
      {badge ? <span className="rounded-full border border-border/70 bg-surface/35 px-3 py-1 text-xs font-bold text-text-muted">{badge}</span> : null}
    </div>
    {children}
  </div>
);

const StatusTile: React.FC<{ label: string; value: string; hint: string; tone: 'ok' | 'warn' | 'neutral' }> = ({ label, value, hint, tone }) => {
  const toneClass = tone === 'ok' ? 'text-status-success' : tone === 'warn' ? 'text-status-warning' : 'text-text';
  return (
    <div className="min-w-0 rounded-[16px] border border-border/80 bg-surface-alt/30 p-4">
      <div className="text-xs font-bold text-text-subtle">{label}</div>
      <div className={`mt-2 truncate text-xl font-black ${toneClass}`} title={value}>{value}</div>
      <div className="mt-1 truncate text-xs text-text-muted" title={hint}>{hint}</div>
    </div>
  );
};

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-4 border-b border-border/50 pb-2 last:border-b-0 last:pb-0">
    <span className="shrink-0 text-text-subtle">{label}</span>
    <span className="min-w-0 truncate text-right font-semibold text-text" title={value}>{value}</span>
  </div>
);

const ModelLine: React.FC<{ label: string; values?: string[] }> = ({ label, values = [] }) => (
  <InfoRow label={label} value={values.length ? values.slice(0, 6).join(' / ') : '暂无'} />
);
