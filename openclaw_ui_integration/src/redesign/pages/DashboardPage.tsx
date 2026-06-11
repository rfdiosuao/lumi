import {
  ArrowRight,
  Cpu,
  ExternalLink,
  Gauge,
  Layers3,
  Phone,
  RefreshCcw,
  Server,
  Settings2,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button, Chip, EmptyState, InlineState, Panel, SectionHeader, StatTile } from '../components/ui';
import { formatDateTime } from '../lib/format';
import { loadDashboardSnapshot, startProcess, stopProcess } from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

export function DashboardPage() {
  const settings = usePreviewStore((state) => state.settings);
  const navigate = usePreviewStore((state) => state.navigate);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadDashboardSnapshot(settings), [settings]);

  const service = data?.service;
  const license = data?.license;
  const diagnostics = data?.diagnostics;
  const skills = data?.skills;
  const gateway = data?.gateway;
  const enabledSkills = skills?.skills.filter((item) => item.enabled).length ?? 0;
  const skillsMeta = skills?.skills.length ? `已启用 ${enabledSkills}` : '按需加载';
  const startupStage = toCnState(service?.startupStage || '待命');
  const environmentState = diagnostics?.summary.total ? toCnState(diagnostics.summary.status) : '按需检测';

  const primaryTiles = [
    {
      icon: Gauge,
      title: '启动核心服务',
      desc: '运行时、日志与 CLI 先就绪。',
      meta: service?.running ? '运行中' : '待启动',
      tone: service?.running ? 'ok' : 'warn',
      featured: true,
      route: 'service' as const,
    },
    {
      icon: Settings2,
      title: '统一设置',
      desc: '模型、图像、视频与桥接参数统一收纳。',
      meta: gateway?.hasGateway ? '已配置' : '待配置',
      tone: gateway?.hasGateway ? 'ok' : 'warn',
      featured: true,
      route: 'settings' as const,
    },
    {
      icon: Cpu,
      title: '桌面 RPA',
      desc: '保留自动回复能力，作为桌面操作中枢。',
      meta: '自动回复',
      tone: 'neutral' as const,
      featured: true,
      route: 'desktop' as const,
    },
    {
      icon: Phone,
      title: '手机控制台',
      desc: '仅作 APKClaw 轻量桥接，不承担启动职责。',
      meta: '辅助桥接',
      tone: 'neutral' as const,
      featured: true,
      route: 'phone' as const,
    },
  ] as const;

  const secondaryTiles = [
    {
      icon: Layers3,
      title: 'Skills 工作区',
      desc: '安装、启用和查看本地能力模块。',
      meta: skillsMeta,
      tone: 'ok' as const,
      route: 'skills' as const,
    },
    {
      icon: ShieldCheck,
      title: '授权内测',
      desc: '授权码、成员租约和邀请制内测入口。',
      meta: license?.authorized ? displayEdition(license.edition) : '未授权',
      tone: license?.authorized ? 'ok' : 'warn',
      route: 'license' as const,
    },
    {
      icon: TriangleAlert,
      title: '环境检测',
      desc: '检查启动前的运行环境与可修复项。',
      meta: diagnostics?.summary.status || 'warn',
      tone: diagnostics?.summary.status === 'ok' ? 'ok' : diagnostics?.summary.status === 'fail' ? 'danger' : 'warn',
      route: 'diagnostics' as const,
    },
    {
      icon: Sparkles,
      title: '图像 / 视频',
      desc: '图像与视频生成的密钥统一从设置读取。',
      meta: '统一密钥',
      tone: 'neutral' as const,
      route: 'studio' as const,
    },
  ] as const;

  const handleStart = async () => {
    try {
      await startProcess(settings);
      pushToast({ tone: 'ok', title: '核心服务已启动', detail: '桥接端已接收启动指令。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '启动失败', detail: String(err) });
    }
  };

  // Open the OpenClaw web console in the system browser. Uses the shell plugin
  // in the desktop app (so it opens the real browser, not the app webview) and
  // falls back to window.open in the web preview.
  const handleOpenConsole = async () => {
    const url = 'http://127.0.0.1:18790';
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
    } catch {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleStop = async () => {
    try {
      await stopProcess(settings);
      pushToast({ tone: 'warn', title: '核心服务已停止', detail: '启动器回到待启动状态。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '停止失败', detail: String(err) });
    }
  };

  return (
    <div className="page-grid page-grid-dashboard">
      <section className="launcher-hero">
        <div className="launcher-hero-copy">
          <div className="eyebrow">OpenClaw 开源启动器</div>
          <h1>满船清梦压星河，偷捧时间煮酒喝。</h1>
          <p>先让核心服务稳定升空，再进入工作区处理 CLI、RPA、Skills 与生成任务。</p>
          <div className="hero-mini-signals">
            <Chip tone={service?.running ? 'ok' : 'warn'}>{service?.running ? '核心运行中' : '核心待启动'}</Chip>
            <Chip tone={gateway?.hasGateway ? 'ok' : 'warn'}>{gateway?.hasGateway ? '接口已配置' : '需要设置接口'}</Chip>
          </div>
        </div>
        <div className="launcher-hero-actions hero-action-card">
          <div className="hero-action-label">当前状态</div>
          <div className="hero-action-value">{service?.running ? '运行中' : '待启动'}</div>
          <div className="hero-action-note">{service?.running ? `PID ${service?.pid ?? '未知'}` : startupStage || '准备启动'}</div>
          <div className="hero-action-buttons">
            {service?.running ? (
              <Button variant="danger" icon={Server} onClick={handleStop}>
                停止核心
              </Button>
            ) : (
              <Button variant="success" icon={Server} onClick={handleStart}>
                启动核心
              </Button>
            )}
            <Button
              variant="secondary"
              icon={ExternalLink}
              onClick={handleOpenConsole}
              disabled={!service?.running}
              title={service?.running ? '在浏览器打开 127.0.0.1:18790' : '启动核心后可打开'}
            >
              打开网页
            </Button>
            <Button variant="quiet" icon={RefreshCcw} onClick={refresh}>
              刷新
            </Button>
          </div>
        </div>
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取启动器状态...</Panel>
      ) : error ? (
        <Panel className="panel-error">
          <InlineState tone="danger" title="启动器状态读取失败" description={error} />
        </Panel>
      ) : data ? (
        <>
          <section className="stats-grid">
            <StatTile
              label="核心服务"
              value={service?.running ? '运行中' : '待启动'}
              hint={service?.running ? `PID ${service?.pid ?? '未知'}` : startupStage || '可以启动'}
              tone={service?.running ? 'ok' : 'warn'}
            />
            <StatTile
              label="授权内测"
              value={license?.authorized ? '已授权' : '未授权'}
              hint={license?.licensee || '需要授权码'}
              tone={license?.authorized ? 'ok' : 'warn'}
            />
            <StatTile
              label="接口网关"
              value={gateway?.hasGateway ? '已配置' : '未配置'}
              hint={gateway?.baseUrl || '进入统一设置'}
              tone={gateway?.hasGateway ? 'ok' : 'warn'}
            />
            <StatTile
              label="环境"
              value={environmentState}
              hint={diagnostics?.summary.total ? `${diagnostics.summary.ok}/${diagnostics.summary.total} 项通过` : '进入环境检测运行'}
              tone={diagnostics?.summary.status === 'ok' ? 'ok' : diagnostics?.summary.status === 'warn' ? 'warn' : 'danger'}
            />
          </section>

          <section className="launch-stack">
            <div className="launch-group">
              <div className="launch-group-head">
                <div className="eyebrow">主要入口</div>
                <h2>首页只放最常用的入口。</h2>
                <p>核心服务与统一设置放在前面，桌面 RPA 和手机控制台保持独立。</p>
              </div>
              <div className="launcher-grid launcher-grid-primary">
                {primaryTiles.map((tile) => (
                  <LauncherTile
                    key={tile.title}
                    icon={tile.icon}
                    title={tile.title}
                    desc={tile.desc}
                    meta={tile.meta}
                    tone={tile.tone}
                    featured={tile.featured}
                    onClick={() => navigate(tile.route)}
                  />
                ))}
              </div>
            </div>

            <div className="launch-group launch-group-secondary">
              <div className="launch-group-head">
                <div className="eyebrow">能力区</div>
                <h2>完整能力收纳在后方。</h2>
                <p>Skills、授权、环境检测与图像视频都可进入，但不抢首页重心。</p>
              </div>
              <div className="launcher-grid launcher-grid-secondary">
                {secondaryTiles.map((tile) => (
                  <LauncherTile
                    key={tile.title}
                    icon={tile.icon}
                    title={tile.title}
                    desc={tile.desc}
                    meta={tile.meta}
                    tone={tile.tone}
                    onClick={() => navigate(tile.route)}
                  />
                ))}
              </div>
            </div>
          </section>

          <section className="content-grid content-grid-dashboard-bottom">
            <Panel className="surface-panel">
              <SectionHeader eyebrow="CLI / 日志" title="运行摘要" subtitle="保留原来的日志与 CLI 入口，首页只展示最短摘要。" />
              {data.recentLogs.length ? (
                <div className="log-list">
                  {data.recentLogs.map((line, index) => (
                    <div key={index} className="log-line">
                      {line}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="暂无日志" description="启动核心服务或刷新后，这里会显示最近输出。" />
              )}
            </Panel>

            <Panel className="surface-panel">
              <SectionHeader eyebrow="信号" title="状态摘要" subtitle="只保留判断启动与生成是否可用的关键信号。" />
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">桥接来源</span><span className="detail-value">{toCnState(service?.source || 'mock')}</span></div>
                <div className="detail-row"><span className="detail-label">主题</span><span className="detail-value">{data.themeName}</span></div>
                <div className="detail-row"><span className="detail-label">图像密钥</span><span className="detail-value">{gateway?.imageApiKeyMasked || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">视频密钥</span><span className="detail-value">{gateway?.videoApiKeyMasked || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">刷新时间</span><span className="detail-value">{formatDateTime(Date.now())}</span></div>
              </div>
            </Panel>
          </section>
        </>
      ) : null}
    </div>
  );
}

function LauncherTile({
  icon: Icon,
  title,
  desc,
  meta,
  tone,
  featured = false,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  desc: string;
  meta: string;
  tone: 'ok' | 'warn' | 'danger' | 'neutral';
  featured?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`launcher-tile ${featured ? 'launcher-tile-featured' : ''}`} onClick={onClick}>
      <span className="launcher-tile-icon"><Icon size={18} /></span>
      <span className="launcher-tile-copy">
        <span className="launcher-tile-title">{title}</span>
        <span className="launcher-tile-desc">{desc}</span>
      </span>
      <span className={`launcher-tile-meta chip chip-${tone}`}>{toCnState(meta)}</span>
      <ArrowRight size={16} />
    </button>
  );
}

function toCnState(value: string) {
  const lower = String(value || '').toLowerCase();
  const map: Record<string, string> = {
    idle: '待命',
    warn: '警告',
    ok: '正常',
    fail: '失败',
    running: '运行中',
    stopped: '已停止',
    mock: '预览',
    live: '真实接口',
  };
  return map[lower] || value;
}

function displayEdition(value?: string) {
  if (!value) return '已授权';
  if (value === 'Pro') return '专业版';
  if (value === 'Free') return '免费版';
  return value;
}
