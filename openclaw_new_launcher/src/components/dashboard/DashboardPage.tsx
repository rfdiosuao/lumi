import React, { useEffect, useState, useCallback } from 'react';
import { useAppStore } from '../../stores/appStore';
import { useTheme } from '../../hooks/useTheme';
import { processApi, configApi, skillsApi, systemApi } from '../../services/api';
import { showToast } from '../common';

interface StatusCard {
  key: string;
  label: string;
  status: 'ok' | 'warn' | 'off' | 'loading';
  detail: string;
  icon: string;
}

interface QuickAction {
  key: string;
  label: string;
  desc: string;
  icon: string;
  accent?: boolean;
}

const STATUS_STYLES: Record<string, { dot: string; glow: string }> = {
  ok: {
    dot: 'bg-status-success',
    glow: 'shadow-[0_0_12px_rgba(63,224,143,0.6)]',
  },
  warn: {
    dot: 'bg-status-warning',
    glow: 'shadow-[0_0_12px_rgba(255,180,84,0.5)]',
  },
  off: {
    dot: 'bg-text-subtle',
    glow: '',
  },
  loading: {
    dot: 'bg-accent',
    glow: 'shadow-[0_0_12px_rgba(214,180,106,0.5)]',
  },
};

const AUTH_PROFILES_PATH = 'data/.openclaw/agents/main/agent/auth-profiles.json';
const LARK_PLUGIN_PATH = 'data/.openclaw/extensions/openclaw-lark';
const WEIXIN_PLUGIN_PATH = 'data/.openclaw/extensions/openclaw-weixin';

function hasConfiguredApiProfile(data: unknown): boolean {
  const providers = (data as any)?.models?.providers;
  if (!providers || typeof providers !== 'object') return false;
  return Object.values(providers).some((provider: any) => {
    const apiKey = String(provider?.apiKey || '').trim();
    const baseUrl = String(provider?.baseUrl || provider?.url || '').trim();
    return apiKey.length > 0 && baseUrl.length > 0;
  });
}

export const DashboardPage: React.FC = () => {
  const {
    serviceRunning,
    serviceStatus,
    isAuthorized,
    setCurrentPage,
  } = useAppStore();

  const { theme } = useTheme();
  const [apiConfigured, setApiConfigured] = useState<boolean | null>(null);
  const [larkInstalled, setLarkInstalled] = useState<boolean | null>(null);
  const [weixinInstalled, setWeixinInstalled] = useState<boolean | null>(null);
  const [skillsCount, setSkillsCount] = useState<number>(0);
  const [bridgeMode, setBridgeMode] = useState<string>('FastAPI');
  const [greetingTime, setGreetingTime] = useState('');

  const refreshStatus = useCallback(async () => {
    try {
      const resp = await configApi.read(AUTH_PROFILES_PATH, { models: { providers: {} } });
      setApiConfigured(hasConfiguredApiProfile(resp.data));
    } catch {
      setApiConfigured(false);
    }

    try {
      const larkResp = await configApi.read(LARK_PLUGIN_PATH, null);
      setLarkInstalled(larkResp.data !== null && larkResp.data !== undefined);
    } catch {
      setLarkInstalled(false);
    }

    try {
      const weixinResp = await configApi.read(WEIXIN_PLUGIN_PATH, null);
      setWeixinInstalled(weixinResp.data !== null && weixinResp.data !== undefined);
    } catch {
      setWeixinInstalled(false);
    }

    try {
      const skillsResp = await skillsApi.list();
      const enabled = skillsResp.skills?.filter((s) => s.enabled).length ?? 0;
      setSkillsCount(enabled);
    } catch {
      setSkillsCount(0);
    }

    try {
      await systemApi.info();
      setBridgeMode('FastAPI');
    } catch {
      setBridgeMode('Legacy');
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const hour = new Date().getHours();
    if (hour < 6) setGreetingTime('夜深了');
    else if (hour < 12) setGreetingTime('早上好');
    else if (hour < 14) setGreetingTime('中午好');
    else if (hour < 18) setGreetingTime('下午好');
    else setGreetingTime('晚上好');
  }, [refreshStatus]);

  const statusCards: StatusCard[] = [
    {
      key: 'service',
      label: 'OpenClaw 服务',
      status: serviceRunning ? 'ok' : serviceStatus === 'starting' ? 'loading' : 'off',
      detail: serviceRunning ? '运行中' : serviceStatus === 'starting' ? '启动中' : '未启动',
      icon: '⬡',
    },
    {
      key: 'bridge',
      label: 'Bridge 引擎',
      status: serviceRunning ? 'ok' : 'off',
      detail: bridgeMode,
      icon: '◈',
    },
    {
      key: 'license',
      label: '授权状态',
      status: isAuthorized ? 'ok' : 'warn',
      detail: isAuthorized ? '已授权' : '未授权',
      icon: '◇',
    },
    {
      key: 'api',
      label: 'API 配置',
      status: apiConfigured === null ? 'loading' : apiConfigured ? 'ok' : 'warn',
      detail: apiConfigured === null ? '检测中' : apiConfigured ? '已配置' : '未配置',
      icon: '⬢',
    },
    {
      key: 'lark',
      label: '飞书机器人',
      status: larkInstalled === null ? 'loading' : larkInstalled ? 'ok' : 'off',
      detail: larkInstalled === null ? '检测中' : larkInstalled ? '已安装' : '未安装',
      icon: '▣',
    },
    {
      key: 'weixin',
      label: '微信机器人',
      status: weixinInstalled === null ? 'loading' : weixinInstalled ? 'ok' : 'off',
      detail: weixinInstalled === null ? '检测中' : weixinInstalled ? '已安装' : '未安装',
      icon: '▤',
    },
    {
      key: 'skills',
      label: 'Skills 扩展',
      status: skillsCount > 0 ? 'ok' : 'off',
      detail: `${skillsCount} 个已启用`,
      icon: '⬩',
    },
  ];

  const quickActions: QuickAction[] = [
    { key: 'terminal', label: '服务日志', desc: '查看控制台', icon: '▸' },
    { key: 'storyboard', label: '广告视频', desc: '分镜工作台', icon: '▦', accent: true },
    { key: 'image', label: 'AI 生图', desc: '创作图片', icon: '◎', accent: true },
    { key: 'video', label: 'AI 视频', desc: '生成视频', icon: '▶', accent: true },
    { key: 'skills', label: 'Skills', desc: '扩展中心', icon: '⬩' },
    { key: 'license', label: '授权码', desc: '激活管理', icon: '◇' },
  ];

  const handleQuickAction = (key: string) => {
    if (key === 'storyboard' || key === 'image' || key === 'video') {
      if (!isAuthorized) {
        showToast('请先完成授权', 'info');
        setCurrentPage('license');
        return;
      }
    }
    setCurrentPage(key);
  };

  const handleStartService = async () => {
    if (!isAuthorized) {
      showToast('请先完成授权', 'info');
      setCurrentPage('license');
      return;
    }
    try {
      await processApi.start();
      showToast('服务启动中...', 'success');
    } catch (error: any) {
      showToast(`启动失败: ${error?.error || error}`, 'error');
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border bg-surface px-8 py-6">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.28em] text-accent">
              {theme.brand.terminal_header}
            </div>
            <h1 className="mt-1.5 text-2xl font-black tracking-wide text-text">
              {greetingTime}，欢迎回来
            </h1>
            <p className="mt-1 text-sm text-text-subtle">
              {theme.brand.name} · {theme.brand.subtitle}
            </p>
          </div>
          {!serviceRunning && (
            <button
              onClick={handleStartService}
              disabled={serviceStatus === 'starting'}
              className="rounded-2xl bg-accent px-6 py-3 text-sm font-black text-accent-ink shadow-[0_16px_44px_rgba(214,180,106,0.22)] transition-all hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-55"
            >
              {serviceStatus === 'starting' ? '启动中...' : '启动核心服务'}
            </button>
          )}
          {serviceRunning && (
            <div className="flex items-center gap-2 rounded-2xl border border-status-success/30 bg-status-success/10 px-5 py-3">
              <span className="h-2.5 w-2.5 rounded-full bg-status-success shadow-[0_0_10px_rgba(63,224,143,0.6)]" />
              <span className="text-sm font-bold text-status-success">服务运行中</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8">
        <div className="mb-8">
          <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">
            系统状态
          </div>
          <div className="grid grid-cols-4 gap-3">
            {statusCards.map((card, index) => {
              const style = STATUS_STYLES[card.status];
              return (
                <div
                  key={card.key}
                  className="group relative overflow-hidden rounded-2xl border border-border bg-surface-alt/60 p-4 transition-all hover:border-border-strong hover:bg-surface-alt"
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  <div className="pointer-events-none absolute -right-4 -top-4 text-5xl font-black text-accent/[0.06] transition-colors group-hover:text-accent/[0.12]">
                    {card.icon}
                  </div>
                  <div className="relative">
                    <div className="mb-3 flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${style.dot} ${style.glow} transition-all`} />
                      <span className="text-xs font-medium text-text-muted">{card.label}</span>
                    </div>
                    <div className="text-sm font-bold text-text">{card.detail}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mb-8">
          <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">
            快捷入口
          </div>
          <div className="grid grid-cols-3 gap-3">
            {quickActions.map((action) => (
              <button
                key={action.key}
                onClick={() => handleQuickAction(action.key)}
                className={`group relative flex items-center gap-4 overflow-hidden rounded-2xl border p-4 text-left transition-all ${
                  action.accent
                    ? 'border-accent/25 bg-accent/[0.06] hover:border-accent/50 hover:bg-accent/[0.12]'
                    : 'border-border bg-surface-alt/60 hover:border-border-strong hover:bg-surface-alt'
                }`}
              >
                <div
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border text-lg font-black transition-all ${
                    action.accent
                      ? 'border-accent/40 bg-accent/20 text-accent group-hover:border-accent/60 group-hover:bg-accent/30'
                      : 'border-border bg-surface-deep text-text-subtle group-hover:border-border-strong group-hover:text-text'
                  }`}
                >
                  {action.icon}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-bold text-text">{action.label}</div>
                  <div className="text-xs text-text-subtle">{action.desc}</div>
                </div>
                <div className="pointer-events-none absolute -right-1 bottom-0 text-3xl font-black text-accent/[0.04] transition-colors group-hover:text-accent/[0.1]">
                  →
                </div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-text-subtle">
            关于
          </div>
          <div className="rounded-2xl border border-border bg-surface-alt/40 p-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-border-strong bg-surface-alt shadow-[0_0_30px_rgba(214,180,106,0.12)]">
                <span className="text-2xl font-black text-accent">L</span>
              </div>
              <div>
                <div className="text-base font-black tracking-wide text-text">{theme.brand.name}</div>
                <div className="text-sm text-text-muted">{theme.brand.subtitle}</div>
                <div className="mt-1 text-xs text-text-subtle">
                  {theme.name} · v2.0.1
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
