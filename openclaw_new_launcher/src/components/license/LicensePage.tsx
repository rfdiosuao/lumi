import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-shell';
import { BusyOverlay, showToast } from '../common';
import {
  accountApi,
  licenseApi,
  parseErrorText,
  type AccountSnapshot,
  type AccountSubscriptionSnapshot,
} from '../../services/api';
import { accountCacheUsable, loadCachedAccount, saveCachedAccount } from '../../services/startupCache';
import { useAppStore } from '../../stores/appStore';
import { APP_DISPLAY_NAME } from '../../version';

const DEFAULT_BASE_URL = 'https://api.heang.top';
const DEFAULT_ACCOUNT_CENTER_URL = `${DEFAULT_BASE_URL}/wallet`;

type AuthMode = 'email' | 'password' | 'register';

const SUBSCRIPTION_PLANS = [
  {
    name: '入门版',
    quota: '基础额度 $8',
    bonus: 'Bonus 每天刷新 $0.5',
    price: '$5.07 / 月',
    tone: 'border-border',
  },
  {
    name: '进阶版',
    quota: '基础额度 $18',
    bonus: 'Bonus 每天刷新 $1.2',
    price: '$10.15 / 月',
    tone: 'border-accent/45',
  },
  {
    name: '高级版',
    quota: '基础额度 $125',
    bonus: 'Bonus 每天刷新 $8',
    price: '$50.74 / 月',
    tone: 'border-[#C9A24A]/55',
  },
  {
    name: '专业版',
    quota: '基础额度 $300',
    bonus: 'Bonus 每天刷新 $25',
    price: '$101.47 / 月',
    tone: 'border-status-danger/45',
  },
];

function errorMessage(error: unknown): string {
  const friendly = parseErrorText(error);
  if (friendly) return friendly;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    if (typeof record.error === 'string') return record.error;
    if (typeof record.message === 'string') return record.message;
  }
  return '请求失败，请稍后重试';
}

function modelTotal(account: AccountSnapshot | null): number {
  const models = account?.models || {};
  return (models.text?.length || 0) + (models.image?.length || 0) + (models.video?.length || 0);
}

function displayValue(value: unknown, fallback = '暂无'): string {
  if (value === undefined || value === null || value === '') return fallback;
  return String(value);
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

function subscriptionUsage(subscription: AccountSubscriptionSnapshot | null): string {
  const usage = subscription?.usage;
  if (!usage || typeof usage !== 'object') return '暂无';
  const used = displayValue(usage.usedQuota, '');
  const count = displayValue(usage.requestCount, '');
  if (used && count) return `${used} / ${count} 次`;
  return used || count || '暂无';
}

function formatTime(value?: string): string {
  if (!value) return '暂无';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function accountProfile(account: AccountSnapshot | null) {
  if (!account?.loggedIn) return null;
  return {
    licensee: account.account || 'LOOM User',
    edition: account.plan || 'account',
    gatewayBaseUrl: account.gatewayBaseUrl,
    gatewayDefaultModel: account.selectedModels?.text || account.models?.text?.[0],
    managedBy: account.source || 'newapi_account',
  };
}

async function openExternalUrl(url: string): Promise<void> {
  try {
    await open(url);
  } catch {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

function isLocalSubscriptionUrl(url: string): boolean {
  try {
    const parsed = new URL(url, DEFAULT_BASE_URL);
    return ['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(parsed.hostname) || parsed.protocol === 'file:';
  } catch {
    return true;
  }
}

function safeSubscriptionUrl(url: string): string {
  const candidate = String(url || '').trim() || DEFAULT_ACCOUNT_CENTER_URL;
  if (isLocalSubscriptionUrl(candidate)) return '';
  try {
    const parsed = new URL(candidate, DEFAULT_BASE_URL);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return '';
    if (parsed.hostname === 'api.heang.top' && parsed.pathname.replace(/\/+$/, '') === '/topup') {
      return DEFAULT_ACCOUNT_CENTER_URL;
    }
    return parsed.toString();
  } catch {
    return '';
  }
}

export const LicensePage: React.FC = () => {
  const cachedAccount = useRef<AccountSnapshot | null>(loadCachedAccount());
  const hasCachedAccount = accountCacheUsable(cachedAccount.current);
  const [account, setAccount] = useState<AccountSnapshot | null>(() => cachedAccount.current);
  const [subscription, setSubscription] = useState<AccountSubscriptionSnapshot | null>(() => cachedAccount.current?.subscription || null);
  const [authMode, setAuthMode] = useState<AuthMode>('email');
  const [loginName, setLoginName] = useState('');
  const [email, setEmail] = useState('');
  const [emailCode, setEmailCode] = useState('');
  const [password, setPassword] = useState('');
  const [legacyCode, setLegacyCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(() => !hasCachedAccount);
  const [statusText, setStatusText] = useState('');
  const { setAuthorized, setLicenseInfo, setCurrentPage } = useAppStore();

  const loggedIn = Boolean(account?.loggedIn);
  const totalModels = modelTotal(account);
  const modelHint = useMemo(() => {
    const selected = account?.selectedModels?.text;
    if (selected) return selected;
    return account?.models?.text?.slice(0, 3).join(' / ') || '登录后同步';
  }, [account]);
  const purchaseUrl = subscription?.purchaseUrl || account?.purchaseUrl || DEFAULT_ACCOUNT_CENTER_URL;
  const subscriptionUrl = useMemo(() => safeSubscriptionUrl(purchaseUrl), [purchaseUrl]);
  const accountStateText = loading ? '读取中' : loggedIn ? '已登录' : '未登录';

  const applyAccount = useCallback((next: AccountSnapshot | null) => {
    cachedAccount.current = next;
    saveCachedAccount(next);
    setAccount(next);
    setSubscription(next?.subscription || null);
    const profile = accountProfile(next);
    setLicenseInfo(profile as any);
    setAuthorized(Boolean(profile));
  }, [setAuthorized, setLicenseInfo]);

  const refresh = useCallback(async (options: { background?: boolean } = {}) => {
    if (!options.background) setLoading(true);
    try {
      const resp = await accountApi.current();
      applyAccount(resp.account || null);
      setStatusText('');
    } catch (error) {
      const cached = loadCachedAccount();
      applyAccount(cached || null);
      setStatusText(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [applyAccount]);

  useEffect(() => {
    if (accountCacheUsable(cachedAccount.current)) {
      applyAccount(cachedAccount.current);
      setStatusText('');
      setLoading(false);
      void refresh({ background: true });
      return;
    }
    void refresh();
  }, [applyAccount, refresh]);

  const loadSubscription = async (quiet = false) => {
    if (!quiet) setBusy(true);
    try {
      const resp = await accountApi.subscription();
      setSubscription(resp.subscription || null);
      if (!quiet) {
        setStatusText(resp.subscription?.message || '订阅信息已更新');
        showToast('订阅信息已更新', 'success');
      }
    } catch (error) {
      const message = errorMessage(error);
      if (!quiet) {
        setStatusText(message);
        showToast(message || '订阅信息获取失败', 'error');
      }
    } finally {
      if (!quiet) setBusy(false);
    }
  };

  const sendEmailCode = async () => {
    const targetEmail = email.trim();
    if (!targetEmail) {
      showToast('请输入邮箱', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在发送邮箱验证码...');
    try {
      await accountApi.sendEmailCode({
        email: targetEmail,
        baseUrl: DEFAULT_BASE_URL,
        purpose: authMode === 'register' ? 'register' : 'login',
      });
      setStatusText('验证码已发送，请查看邮箱');
      showToast('验证码已发送', 'success');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '验证码发送失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const finishLogin = async (next: AccountSnapshot | null, message: string) => {
    applyAccount(next);
    setPassword('');
    setEmailCode('');
    setStatusText(message);
    showToast(message, 'success');
    await loadSubscription(true);
  };

  const handlePasswordLogin = async () => {
    const name = loginName.trim();
    if (!name || !password.trim()) {
      showToast('请输入中转站账号和密码', 'error');
      return;
    }

    setBusy(true);
    setStatusText('正在登录中转站并同步模型...');
    try {
      const loginPayload = name.includes('@')
        ? { email: name, password, baseUrl: DEFAULT_BASE_URL }
        : { username: name, password, baseUrl: DEFAULT_BASE_URL };
      const resp = await accountApi.login(loginPayload);
      await finishLogin(resp.account || null, '登录成功，模型已同步');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '登录失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleEmailCodeLogin = async () => {
    if (!email.trim() || !emailCode.trim()) {
      showToast('请输入邮箱和验证码', 'error');
      return;
    }

    setBusy(true);
    setStatusText('正在验证邮箱并同步模型...');
    try {
      const resp = await accountApi.loginWithEmailCode({
        email: email.trim(),
        code: emailCode.trim(),
        baseUrl: DEFAULT_BASE_URL,
      });
      await finishLogin(resp.account || null, '登录成功，模型已同步');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '验证码登录失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async () => {
    if (!email.trim() || !emailCode.trim() || !password.trim()) {
      showToast('请输入邮箱、验证码和密码', 'error');
      return;
    }
    if (password.trim().length < 6) {
      showToast('密码至少 6 位', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在注册并同步模型...');
    try {
      const resp = await accountApi.register({
        email: email.trim(),
        password: password.trim(),
        code: emailCode.trim(),
        baseUrl: DEFAULT_BASE_URL,
      });
      await finishLogin(resp.account || null, '注册成功，模型已同步');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '注册失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const syncModels = async () => {
    setBusy(true);
    setStatusText('正在同步模型...');
    try {
      const resp = await accountApi.sync();
      applyAccount(resp.account || null);
      setStatusText('模型已同步');
      showToast('模型已同步', 'success');
      await loadSubscription(true);
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '同步失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleLegacyActivate = async () => {
    const code = legacyCode.trim();
    if (!code) {
      showToast('请输入旧授权码', 'error');
      return;
    }
    setBusy(true);
    setStatusText('正在激活旧授权码...');
    try {
      const resp = await licenseApi.activate(code);
      setLicenseInfo(resp.license as any);
      setAuthorized(true);
      setLegacyCode('');
      setStatusText('旧授权码已激活');
      showToast('旧授权码已激活', 'success');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '授权码激活失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setBusy(true);
    setStatusText('正在退出中转站账号...');
    try {
      await accountApi.logout();
      applyAccount(null);
      setSubscription(null);
      setStatusText('已退出账号');
      showToast('已退出中转站账号', 'info');
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '退出失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleOpenSubscription = async () => {
    if (!loggedIn) {
      const message = '请先登录中转站账号，再打开订阅页';
      setStatusText(message);
      showToast(message, 'info');
      return;
    }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      const message = '当前网络不可用，请联网后再打开订阅页';
      setStatusText(message);
      showToast(message, 'error');
      return;
    }
    if (!subscriptionUrl) {
      const message = '订阅页地址不可用，请刷新账号后重试';
      setStatusText(message);
      showToast(message, 'error');
      return;
    }
    await openExternalUrl(subscriptionUrl);
    setStatusText('订阅页已在浏览器打开');
    showToast('订阅页已在浏览器打开', 'success');
  };

  const continueAsGuest = () => {
    setAuthorized(false);
    setLicenseInfo(null);
    showToast('已进入访客模式。安装和手机演示可浏览，模型同步需要登录。', 'info');
    setCurrentPage('dashboard');
  };

  const busyTitle = '正在处理账号请求';

  if (loggedIn) {
    return (
      <div
        data-account-subscription-page
        data-white-label-layout="account-subscription"
        className="loom-white-page flex h-full flex-col overflow-hidden bg-surface text-text"
      >
        <BusyOverlay
          active={busy}
          title={busyTitle}
          detail={`${APP_DISPLAY_NAME} 正在连接中转站。`}
        />

        <header className="shrink-0 border-b border-border px-8 py-7">
          <div className="text-sm font-black text-accent">模型账号</div>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-[34px] font-black leading-tight text-text">账号与订阅</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
                保持登录状态，统一同步模型、余额、订阅和 Agent 配置。
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loading || busy}
                className="h-10 rounded-[10px] border border-border bg-surface-alt px-4 text-sm font-black text-text transition hover:border-accent/50 disabled:opacity-55"
              >
                刷新账号
              </button>
              <button
                type="button"
                onClick={() => setCurrentPage('models')}
                className="h-10 rounded-[10px] bg-accent px-4 text-sm font-black text-accent-ink transition hover:bg-accent-hover"
              >
                模型选择
              </button>
            </div>
          </div>
        </header>

        <main className="loom-account-main min-h-0 flex-1 overflow-y-auto px-8 py-7">
          <div className="loom-account-layout grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
            <section className="space-y-5">
              <div className="rounded-[18px] border border-border bg-surface p-5 shadow-[0_18px_60px_rgba(5,35,29,0.08)]">
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-[14px] border border-border bg-surface-alt">
                    <img src="/logo.png" alt="LOOM" className="h-full w-full object-contain" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-black text-accent">已登录</div>
                    <div className="mt-1 truncate text-xl font-black text-text" title={account?.account || ''}>
                      {account?.account || '中转站账号'}
                    </div>
                    <div className="mt-2 text-sm text-text-muted">
                      {account?.plan || 'default'} · {totalModels ? `${totalModels} 个模型` : '模型待同步'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <GhostTile label="余额" value={displayValue(subscription?.balance, usageValue(account, ['quota', 'remainQuota', 'remainingQuota']))} />
                <GhostTile label="套餐" value={displayValue(subscription?.plan, account?.plan || '暂无')} />
                <GhostTile label="用量" value={subscriptionUsage(subscription)} />
                <GhostTile label="到期" value={formatTime(subscription?.expiresAt)} />
              </div>

              <div className="rounded-[18px] border border-border bg-surface p-5">
                <div className="text-sm font-black text-text">当前模型</div>
                <InfoRow label="默认文本模型" value={modelHint} />
                <InfoRow label="最近同步" value={formatTime(account?.lastOnlineAt)} />
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={syncModels}
                    disabled={busy}
                    className="h-11 rounded-[10px] bg-accent text-sm font-black text-accent-ink transition hover:bg-accent-hover disabled:opacity-55"
                  >
                    同步模型
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSubscription(false)}
                    disabled={busy}
                    className="h-11 rounded-[10px] border border-border bg-surface-alt text-sm font-black text-text transition hover:border-accent/50 disabled:opacity-55"
                  >
                    刷新订阅
                  </button>
                  <button
                    type="button"
                    onClick={handleOpenSubscription}
                    className="col-span-2 h-11 rounded-[10px] bg-accent text-sm font-black text-accent-ink transition hover:bg-accent-hover"
                  >
                    打开订阅页
                  </button>
                  <button
                    type="button"
                    onClick={() => loadSubscription(false)}
                    disabled={busy}
                    className="col-span-2 h-10 rounded-[10px] border border-border bg-surface-alt text-sm font-black text-text-muted transition hover:border-accent/50 hover:text-text"
                  >
                    刷新订阅信息
                  </button>
                  <button
                    type="button"
                    onClick={logout}
                    disabled={busy}
                    className="col-span-2 h-10 rounded-[10px] border border-border bg-surface text-sm font-black text-text-muted transition hover:border-status-danger/50 hover:text-status-danger disabled:opacity-55"
                  >
                    退出登录
                  </button>
                </div>
              </div>
            </section>

            <section
              data-native-subscription-dashboard
              data-subscription-external-fallback
              className="min-h-[560px] overflow-hidden rounded-[18px] border border-border bg-surface shadow-[0_18px_60px_rgba(5,35,29,0.08)]"
            >
              <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                  <h2 className="text-lg font-black text-text">账户与余额</h2>
                  <p className="mt-1 text-xs leading-5 text-text-muted">充值、消耗记录与 API 密钥由中转站同步；购买与支付在浏览器完成。</p>
                </div>
                <button
                  type="button"
                  onClick={() => loadSubscription(false)}
                  disabled={busy}
                  className="h-9 rounded-[10px] border border-border bg-surface-alt px-4 text-xs font-black text-text transition hover:border-accent/50 disabled:opacity-55"
                >
                  刷新余额
                </button>
              </div>
              <div className="space-y-6 px-6 py-6">
                <div className="grid gap-4 md:grid-cols-5">
                  <MetricTile label="可用余额" value={displayValue(subscription?.balance, usageValue(account, ['quota', 'remainQuota', 'remainingQuota']))} accent />
                  <MetricTile label="累计消耗" value={displayValue(subscription?.usage?.usedQuota, usageValue(account, ['usedQuota', 'used', 'quotaUsed']))} />
                  <MetricTile label="请求次数" value={displayValue(subscription?.usage?.requestCount, usageValue(account, ['requestCount', 'requests']))} />
                  <MetricTile label="我的邀请码" value={displayValue(subscription?.inviteCode || subscription?.invitationCode || subscription?.referralCode, usageValue(account, ['inviteCode', 'invitationCode', 'referralCode'], '登录后查看'))} />
                  <MetricTile label="当前套餐" value={displayValue(subscription?.plan, account?.plan || '暂无')} />
                </div>

                <div>
                  <div className="mb-3 flex items-end justify-between gap-3">
                    <div>
                      <div className="text-sm font-black text-text">套餐方案</div>
                      <div className="mt-1 text-xs text-text-muted">开通 VIP 会员，按周期自动重置额度，并解锁更高用量与模型权限。</div>
                    </div>
                    <button
                      type="button"
                      onClick={handleOpenSubscription}
                      disabled={!subscriptionUrl}
                      className="h-10 rounded-[10px] bg-accent px-4 text-sm font-black text-accent-ink transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
                    >
                      打开订阅页
                    </button>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    {SUBSCRIPTION_PLANS.map((plan) => (
                      <div
                        key={plan.name}
                        className={`rounded-[14px] border ${plan.tone} bg-surface-alt/50 p-4`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-base font-black text-text">{plan.name}</div>
                          {subscription?.plan === plan.name ? (
                            <span className="rounded-full bg-accent/12 px-2 py-1 text-[11px] font-black text-accent">当前</span>
                          ) : null}
                        </div>
                        <div className="mt-4 text-2xl font-black text-text">{plan.price}</div>
                        <div className="mt-4 space-y-2 text-xs font-bold leading-5 text-text-muted">
                          <div>{plan.quota}</div>
                          <div>{plan.bonus}</div>
                          <div>解锁更高用量与模型权限</div>
                        </div>
                        <button
                          type="button"
                          onClick={handleOpenSubscription}
                          disabled={!subscriptionUrl}
                          className="mt-5 h-10 w-full rounded-[10px] bg-accent text-xs font-black text-accent-ink transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
                        >
                          微信开通 VIP
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <InfoPanel label="到期时间" value={formatTime(subscription?.expiresAt)} />
                  <InfoPanel label="默认文本模型" value={modelHint} />
                  <InfoPanel label="购买入口" value={subscriptionUrl ? '浏览器打开' : '地址不可用'} />
                </div>
              </div>
            </section>
          </div>

          {statusText ? (
            <div className="mt-5 rounded-[12px] border border-border bg-surface-alt px-4 py-3 text-sm leading-6 text-text-muted">
              {statusText}
            </div>
          ) : null}
        </main>
      </div>
    );
  }

  return (
    <div className="relative h-full overflow-hidden bg-app-bg text-text">
      <BusyOverlay
        active={busy}
        title={busyTitle}
        detail={`${APP_DISPLAY_NAME} 正在连接中转站。`}
      />

      <div className="absolute inset-0 opacity-80">
        <div className="mx-auto grid h-full max-w-[1160px] grid-cols-[minmax(0,1fr)_360px] gap-7 px-8 py-7 blur-[1px]">
          <section className="min-w-0">
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">模型账号</div>
            <h1 className="mt-2 text-[38px] font-black leading-tight text-text">中转站登录</h1>
            <div className="mt-8 grid grid-cols-2 gap-4">
              <GhostTile label="账号" value={accountStateText} />
              <GhostTile label="模型" value={totalModels ? `${totalModels} 个` : '待同步'} />
              <GhostTile label="余额" value={displayValue(subscription?.balance, usageValue(account, ['quota', 'remainQuota', 'remainingQuota']))} />
              <GhostTile label="来源" value="api.heang.top" />
            </div>
            <div className="mt-7 rounded-[22px] border border-border/70 bg-surface-alt/45 p-6">
              <div className="text-sm font-black text-text">演示版能力</div>
              <div className="mt-4 grid grid-cols-3 gap-3">
                <SoftPill>安装器</SoftPill>
                <SoftPill>手机控制</SoftPill>
                <SoftPill>模型同步</SoftPill>
              </div>
            </div>
          </section>

          <aside className="rounded-[22px] border border-border/70 bg-surface-alt/35 p-5">
            <div className="text-sm font-black text-text">当前状态</div>
            <InfoRow label="账号" value={account?.account || '访客'} />
            <InfoRow label="订阅" value={displayValue(subscription?.plan, account?.plan || '暂无')} />
            <InfoRow label="最近同步" value={formatTime(account?.lastOnlineAt)} />
          </aside>
        </div>
      </div>

      <div className="absolute inset-0 bg-[#1c211c]/45 backdrop-blur-[2px]" />

      <div className="relative z-10 flex h-full items-center justify-center px-6 py-8">
        <section className="w-full max-w-[440px] rounded-[18px] border border-[#2C332C] bg-[#14140F]/96 p-8 text-[#F6F2E8] shadow-[0_34px_100px_rgba(0,0,0,0.42)]">
          <div className="mb-7 flex items-start justify-between gap-4">
            <div className="flex min-w-0 gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[12px] border border-[#31554B] bg-[#0B2F2A]">
                <img src="/logo.png" alt={APP_DISPLAY_NAME} className="h-full w-full object-contain" />
              </div>
              <div className="min-w-0">
                <h1 className="text-[24px] font-black leading-tight">{APP_DISPLAY_NAME}</h1>
                <p className="mt-2 text-sm leading-6 text-[#AAA59A]">
                  登录后同步模型、余额与智能体配置。
                </p>
                <p className="mt-3 inline-flex rounded-full border border-[#1E7A63]/45 bg-[#0B6B57]/16 px-3 py-1 text-xs font-black text-[#BFF7E7]">
                  新用户注册即送 10 元体验额度
                </p>
              </div>
            </div>
            <button
              type="button"
              className="shrink-0 text-2xl leading-none text-[#9D978C] transition hover:text-[#F6F2E8]"
              onClick={() => setCurrentPage('dashboard')}
              aria-label="关闭登录页"
            >
              ×
            </button>
          </div>

          <div className="space-y-4">
              <div className="grid grid-cols-3 gap-2 rounded-[11px] border border-[#302B23] bg-[#100F0B] p-1">
                <ModeButton active={authMode === 'email'} onClick={() => setAuthMode('email')}>验证码登录</ModeButton>
                <ModeButton active={authMode === 'password'} onClick={() => setAuthMode('password')}>密码登录</ModeButton>
                <ModeButton active={authMode === 'register'} onClick={() => setAuthMode('register')}>邮箱注册</ModeButton>
              </div>

              {authMode === 'email' ? (
                <>
                  <label className="block">
                    <span className="mb-2 block text-xs font-bold text-[#A9A397]">邮箱</span>
                    <input
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                      placeholder="请输入中转站邮箱"
                      autoComplete="email"
                    />
                  </label>
                  <div className="grid grid-cols-[minmax(0,1fr)_112px] gap-2">
                    <label className="block min-w-0">
                      <span className="mb-2 block text-xs font-bold text-[#A9A397]">邮箱验证码</span>
                      <input
                        value={emailCode}
                        onChange={(event) => setEmailCode(event.target.value)}
                        className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                        placeholder="6 位验证码"
                        autoComplete="one-time-code"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={sendEmailCode}
                      disabled={busy}
                      className="mt-[22px] h-11 rounded-[9px] border border-[#31554B] bg-[#10201B] text-sm font-black text-[#CDEFE4] transition hover:border-[#0B6B57] disabled:opacity-55"
                    >
                      发送验证码
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleEmailCodeLogin}
                    disabled={busy}
                    className="h-11 w-full rounded-[9px] bg-[#0B6B57] text-sm font-black text-[#F5FFF9] shadow-[0_16px_30px_rgba(11,107,87,0.26)] transition hover:bg-[#0E7B64] disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    {busy ? '验证中...' : '验证并登录'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setAuthMode('register')}
                    className="w-full text-center text-sm font-bold text-[#A9A397] transition hover:text-[#F6F2E8]"
                  >
                    还没有账户？注册
                  </button>
                </>
              ) : authMode === 'password' ? (
                <>
                  <label className="block">
                    <span className="mb-2 block text-xs font-bold text-[#A9A397]">用户名或邮箱</span>
                    <input
                      value={loginName}
                      onChange={(event) => setLoginName(event.target.value)}
                      className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                      placeholder="请输入中转站账号"
                      autoComplete="username"
                    />
                  </label>
                  <PasswordInput
                    value={password}
                    autoComplete="current-password"
                    onChange={setPassword}
                    onEnter={handlePasswordLogin}
                  />
                  <button
                    type="button"
                    onClick={handlePasswordLogin}
                    disabled={busy}
                    className="h-11 w-full rounded-[9px] bg-[#0B6B57] text-sm font-black text-[#F5FFF9] shadow-[0_16px_30px_rgba(11,107,87,0.26)] transition hover:bg-[#0E7B64] disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    {busy ? '登录中...' : '登录'}
                  </button>
                </>
              ) : (
                <>
                  <label className="block">
                    <span className="mb-2 block text-xs font-bold text-[#A9A397]">邮箱</span>
                    <input
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                      placeholder="请输入邮箱"
                      autoComplete="email"
                    />
                  </label>
                  <div className="grid grid-cols-[minmax(0,1fr)_112px] gap-2">
                    <label className="block min-w-0">
                      <span className="mb-2 block text-xs font-bold text-[#A9A397]">验证码</span>
                      <input
                        value={emailCode}
                        onChange={(event) => setEmailCode(event.target.value)}
                        className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                        placeholder="邮箱验证码"
                        autoComplete="one-time-code"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={sendEmailCode}
                      disabled={busy}
                      className="mt-[22px] h-11 rounded-[9px] border border-[#31554B] bg-[#10201B] text-sm font-black text-[#CDEFE4] transition hover:border-[#0B6B57] disabled:opacity-55"
                    >
                      发送验证码
                    </button>
                  </div>
                  <PasswordInput
                    value={password}
                    autoComplete="new-password"
                    onChange={setPassword}
                    onEnter={handleRegister}
                  />
                  <button
                    type="button"
                    onClick={handleRegister}
                    disabled={busy}
                    className="h-11 w-full rounded-[9px] bg-[#0B6B57] text-sm font-black text-[#F5FFF9] shadow-[0_16px_30px_rgba(11,107,87,0.26)] transition hover:bg-[#0E7B64] disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    注册并登录，领取 10 元
                  </button>
                </>
              )}

              <button
                type="button"
                onClick={continueAsGuest}
                className="mt-5 w-full rounded-[10px] border border-[#3A3327] bg-[#15130E] px-4 py-3 text-sm font-black text-[#F6F2E8] transition hover:border-[#0B6B57]/60 hover:bg-[#10201B]"
              >
                暂不登录，继续以访客身份浏览
              </button>
              <button
                type="button"
                onClick={handleOpenSubscription}
                className="w-full text-center text-sm font-bold text-[#A9A397] transition hover:text-[#F6F2E8]"
              >
                打开订阅页
              </button>

              <details className="rounded-[10px] border border-[#302B23] bg-[#10100C] px-3 py-2 text-sm">
                <summary className="cursor-pointer select-none font-bold text-[#A9A397]">旧授权码</summary>
                <div className="mt-3 grid grid-cols-[minmax(0,1fr)_84px] gap-2">
                  <input
                    value={legacyCode}
                    onChange={(event) => setLegacyCode(event.target.value)}
                    className="h-10 min-w-0 rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                    placeholder="输入授权码"
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={handleLegacyActivate}
                    disabled={busy}
                    className="h-10 rounded-[9px] border border-[#31554B] bg-[#10201B] text-sm font-black text-[#CDEFE4] transition hover:border-[#0B6B57] disabled:opacity-55"
                  >
                    激活
                  </button>
                </div>
              </details>
          </div>

          {statusText ? (
            <div className="mt-5 rounded-[10px] border border-[#3A3327] bg-[#10130F] px-3 py-2 text-sm leading-6 text-[#BBB5A9]">
              {statusText}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
};

const ModeButton: React.FC<{ active: boolean; onClick: () => void; children: React.ReactNode }> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      'h-9 rounded-[8px] text-xs font-black transition',
      active ? 'bg-[#0B6B57] text-[#F5FFF9]' : 'text-[#A9A397] hover:bg-[#171A14] hover:text-[#F6F2E8]',
    ].join(' ')}
  >
    {children}
  </button>
);

const PasswordInput: React.FC<{
  value: string;
  autoComplete: string;
  onChange: (value: string) => void;
  onEnter: () => void;
}> = ({ value, autoComplete, onChange, onEnter }) => (
  <label className="block">
    <span className="mb-2 block text-xs font-bold text-[#A9A397]">密码</span>
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
      placeholder="请输入密码"
      type="password"
      autoComplete={autoComplete}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onEnter();
      }}
    />
  </label>
);

const GhostTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="min-w-0 rounded-[18px] border border-border/70 bg-surface-alt/35 p-4">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className="mt-2 truncate text-xl font-black text-text" title={value}>{value}</div>
  </div>
);

const MetricTile: React.FC<{ label: string; value: string; accent?: boolean }> = ({ label, value, accent }) => (
  <div className={['min-w-0 rounded-[14px] border bg-surface-alt/40 p-4', accent ? 'border-accent/45' : 'border-border'].join(' ')}>
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className="mt-2 truncate text-[22px] font-black text-text" title={value}>{value}</div>
  </div>
);

const InfoPanel: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="min-w-0 rounded-[14px] border border-border bg-surface-alt/35 px-4 py-3">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className="mt-1 truncate text-sm font-black text-text" title={value}>{value}</div>
  </div>
);

const SoftPill: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="rounded-full border border-border/70 bg-surface/45 px-3 py-2 text-center text-xs font-black text-text-muted">
    {children}
  </span>
);

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="mt-4 border-t border-border/60 pt-4">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className="mt-2 truncate text-sm font-bold text-text" title={value}>{value}</div>
  </div>
);
