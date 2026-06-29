import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BusyOverlay, showToast } from '../common';
import { accountApi, parseErrorText, type AccountSnapshot } from '../../services/api';
import { useAppStore } from '../../stores/appStore';

const DEFAULT_BASE_URL = 'https://api.heang.top';

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

function accountProfile(account: AccountSnapshot | null) {
  if (!account?.loggedIn) return null;
  return {
    licensee: account.account || 'LOOM User',
    edition: account.plan || 'account',
    gatewayBaseUrl: account.gatewayBaseUrl,
    gatewayDefaultModel: account.models?.text?.[0],
    managedBy: account.source || 'newapi_account',
  };
}

export const LicensePage: React.FC = () => {
  const [account, setAccount] = useState<AccountSnapshot | null>(null);
  const [loginName, setLoginName] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [statusText, setStatusText] = useState('');
  const { setAuthorized, setLicenseInfo, setCurrentPage } = useAppStore();

  const loggedIn = Boolean(account?.loggedIn);
  const totalModels = modelTotal(account);
  const modelHint = useMemo(() => account?.models?.text?.slice(0, 3).join(' / ') || '登录后同步', [account]);

  const applyAccount = useCallback((next: AccountSnapshot | null) => {
    setAccount(next);
    const profile = accountProfile(next);
    setLicenseInfo(profile as any);
    setAuthorized(Boolean(profile));
  }, [setAuthorized, setLicenseInfo]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await accountApi.current();
      applyAccount(resp.account || null);
      setStatusText('');
    } catch (error) {
      applyAccount(null);
      setStatusText(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [applyAccount]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleLogin = async () => {
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
      if (!remember) {
        showToast('已登录。本机仍会保持本次会话，退出可清除账号状态。', 'info');
      }
      setPassword('');
      applyAccount(resp.account || null);
      setStatusText('登录成功，模型已同步');
      showToast('中转站登录成功', 'success');
      window.setTimeout(() => setCurrentPage('dashboard'), 650);
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '登录失败', 'error');
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
    } catch (error) {
      const message = errorMessage(error);
      setStatusText(message);
      showToast(message || '同步失败', 'error');
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

  const continueAsGuest = () => {
    setAuthorized(false);
    setLicenseInfo(null);
    showToast('已进入访客模式。安装和手机演示可浏览，模型同步需要登录。', 'info');
    setCurrentPage('dashboard');
  };

  const showUnavailable = (label: string) => {
    showToast(`${label}请在中转站网页完成，演示版只保留启动器内登录。`, 'info');
  };

  const busyTitle = loading ? '正在读取账号状态' : '正在处理登录';

  return (
    <div className="relative h-full overflow-hidden bg-app-bg text-text">
      <BusyOverlay
        active={loading || busy}
        title={busyTitle}
        detail="LOOM 正在连接中转站和本地 Bridge。"
      />

      <div className="absolute inset-0 opacity-80">
        <div className="mx-auto grid h-full max-w-[1160px] grid-cols-[minmax(0,1fr)_360px] gap-7 px-8 py-7 blur-[1px]">
          <section className="min-w-0">
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">模型账号</div>
            <h1 className="mt-2 text-[38px] font-black leading-tight text-text">中转站登录</h1>
            <div className="mt-8 grid grid-cols-2 gap-4">
              <GhostTile label="账号" value={loggedIn ? '已登录' : '未登录'} />
              <GhostTile label="模型" value={totalModels ? `${totalModels} 个` : '待同步'} />
              <GhostTile label="余额" value={usageValue(account, ['quota', 'remainQuota', 'remainingQuota'])} />
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
            <InfoRow label="订阅" value={account?.plan || '暂无'} />
            <InfoRow label="最近同步" value={formatTime(account?.lastOnlineAt)} />
          </aside>
        </div>
      </div>

      <div className="absolute inset-0 bg-[#1c211c]/45 backdrop-blur-[2px]" />

      <div className="relative z-10 flex h-full items-center justify-center px-6 py-8">
        <section className="w-full max-w-[420px] rounded-[18px] border border-[#2C332C] bg-[#14140F]/96 p-8 text-[#F6F2E8] shadow-[0_34px_100px_rgba(0,0,0,0.42)]">
          <div className="mb-7 flex items-start justify-between gap-4">
            <div className="flex min-w-0 gap-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-[12px] border border-[#31554B] bg-[#0B2F2A]">
                <img src="/logo.png" alt="LOOM" className="h-full w-full object-contain" />
              </div>
              <div className="min-w-0">
                <h1 className="text-[24px] font-black leading-tight">麓鸣</h1>
                <p className="mt-2 text-sm leading-6 text-[#AAA59A]">
                  登录后解锁一键配置、智能体管理与模型同步。
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

          {loggedIn ? (
            <LoggedInPanel
              account={account}
              modelHint={modelHint}
              totalModels={totalModels}
              busy={busy}
              onSync={syncModels}
              onLogout={logout}
              onModels={() => setCurrentPage('models')}
            />
          ) : (
            <div className="space-y-4">
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

              <label className="block">
                <span className="mb-2 block text-xs font-bold text-[#A9A397]">密码</span>
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-11 w-full rounded-[9px] border border-[#3A3327] bg-[#12100B] px-3 text-sm text-[#F6F2E8] outline-none transition placeholder:text-[#615B52] focus:border-[#1E7A63] focus:ring-2 focus:ring-[#1E7A63]/25"
                  placeholder="请输入密码"
                  type="password"
                  autoComplete="current-password"
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void handleLogin();
                  }}
                />
              </label>

              <div className="flex items-center justify-between gap-3 text-sm">
                <label className="flex cursor-pointer select-none items-center gap-2 text-[#A9A397]">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(event) => setRemember(event.target.checked)}
                    className="h-4 w-4 accent-[#0B6B57]"
                  />
                  记住登录状态
                </label>
                <button type="button" className="font-bold text-[#2CA883] hover:text-[#52C9A5]" onClick={() => showUnavailable('找回密码')}>
                  忘记密码?
                </button>
              </div>

              <button
                type="button"
                onClick={handleLogin}
                disabled={busy}
                className="h-11 w-full rounded-[9px] bg-[#0B6B57] text-sm font-black text-[#F5FFF9] shadow-[0_16px_30px_rgba(11,107,87,0.26)] transition hover:bg-[#0E7B64] disabled:cursor-not-allowed disabled:opacity-55"
              >
                {busy ? '登录中...' : '登录'}
              </button>

              <div className="text-center text-sm text-[#A9A397]">
                还没有账号?
                <button type="button" className="ml-2 font-bold text-[#2CA883] hover:text-[#52C9A5]" onClick={() => showUnavailable('注册账号')}>
                  注册
                </button>
              </div>

              <button
                type="button"
                onClick={continueAsGuest}
                className="mt-8 w-full rounded-[10px] border border-[#3A3327] bg-[#15130E] px-4 py-3 text-sm font-black text-[#F6F2E8] transition hover:border-[#0B6B57]/60 hover:bg-[#10201B]"
              >
                暂不登录，继续以访客身份浏览
              </button>
              <p className="text-center text-xs leading-5 text-[#777166]">
                访客可查看安装与手机演示；模型同步和一键配置需要登录。
              </p>
            </div>
          )}

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

const LoggedInPanel: React.FC<{
  account: AccountSnapshot | null;
  modelHint: string;
  totalModels: number;
  busy: boolean;
  onSync: () => void;
  onLogout: () => void;
  onModels: () => void;
}> = ({ account, modelHint, totalModels, busy, onSync, onLogout, onModels }) => (
  <div className="space-y-5">
    <div className="rounded-[12px] border border-[#284B40] bg-[#0D221D] p-4">
      <div className="text-xs font-bold text-[#8FB8A8]">已登录</div>
      <div className="mt-2 truncate text-lg font-black" title={account?.account || ''}>
        {account?.account || '中转站账号'}
      </div>
      <div className="mt-2 text-sm text-[#A9A397]">
        {account?.plan || '默认计划'} · {totalModels ? `${totalModels} 个模型` : '模型待同步'}
      </div>
    </div>

    <div className="space-y-2 text-sm">
      <DarkInfo label="余额" value={usageValue(account, ['quota', 'remainQuota', 'remainingQuota'])} />
      <DarkInfo label="默认模型" value={modelHint} />
      <DarkInfo label="最近同步" value={formatTime(account?.lastOnlineAt)} />
    </div>

    <div className="grid grid-cols-2 gap-3">
      <button
        type="button"
        onClick={onSync}
        disabled={busy}
        className="h-11 rounded-[9px] bg-[#0B6B57] text-sm font-black text-[#F5FFF9] transition hover:bg-[#0E7B64] disabled:opacity-55"
      >
        同步模型
      </button>
      <button
        type="button"
        onClick={onModels}
        className="h-11 rounded-[9px] border border-[#3A3327] bg-[#15130E] text-sm font-black text-[#F6F2E8] transition hover:border-[#0B6B57]/60"
      >
        模型选择
      </button>
      <button
        type="button"
        onClick={onLogout}
        disabled={busy}
        className="col-span-2 h-11 rounded-[9px] border border-[#3A3327] bg-[#15130E] text-sm font-black text-[#F6F2E8] transition hover:border-[#8B4B42]/70 hover:bg-[#271714] disabled:opacity-55"
      >
        退出登录
      </button>
    </div>
  </div>
);

const GhostTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="min-w-0 rounded-[18px] border border-border/70 bg-surface-alt/35 p-4">
    <div className="text-xs font-bold text-text-subtle">{label}</div>
    <div className="mt-2 truncate text-xl font-black text-text" title={value}>{value}</div>
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

const DarkInfo: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-4 border-b border-[#302B23] py-2 last:border-b-0">
    <span className="shrink-0 text-[#8C8579]">{label}</span>
    <span className="min-w-0 truncate text-right font-bold text-[#F6F2E8]" title={value}>{value}</span>
  </div>
);
