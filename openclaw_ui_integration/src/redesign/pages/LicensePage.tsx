import React from 'react';
import { BadgeCheck, ExternalLink, RefreshCcw, ShieldCheck } from 'lucide-react';
import { activateLicense, loadClientConfig, loadLicenseBundle, refreshMember, startProcess } from '../api/adapters';
import { Button, Chip, EmptyState, Field, Input, InlineState, Panel, SectionHeader, StatTile } from '../components/ui';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

export function LicensePage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const [licenseCode, setLicenseCode] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const { data, loading, error, refresh } = useAsync(async () => {
    const [bundle, clientConfig] = await Promise.all([loadLicenseBundle(settings), loadClientConfig(settings)]);
    return { ...bundle, clientConfig: clientConfig.data };
  }, [settings], { cacheKey: 'license' });

  const license = data?.license;
  const member = data?.member;
  const gateway = data?.gateway;
  const cardSite = data?.clientConfig?.cardSite;

  const handleActivateLicense = async () => {
    if (!licenseCode.trim()) {
      pushToast({ tone: 'danger', title: '缺少授权码', detail: '激活前需要输入授权码。' });
      return;
    }
    setBusy(true);
    try {
      await activateLicense(settings, licenseCode.trim());
      pushToast({ tone: 'ok', title: '授权已激活', detail: licenseCode.trim() });
      refresh();
      // 授权成功后自动拉起核心服务,免去用户再手动点一次「启动」。运行时层在
      // 首启时已无条件下载,通常此刻已就绪;若仍在初始化则提示稍后手动启动。
      try {
        await startProcess(settings);
        pushToast({ tone: 'ok', title: '核心服务启动中', detail: '授权已生效,正在拉起 OpenClaw 运行时。' });
      } catch {
        pushToast({ tone: 'warn', title: '已授权,服务待启动', detail: '运行时可能还在初始化,稍后可在「服务 / CLI」页手动启动。' });
      }
    } catch (err) {
      pushToast({ tone: 'danger', title: '激活失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshMember = async () => {
    setBusy(true);
    try {
      await refreshMember(settings);
      pushToast({ tone: 'ok', title: '成员信息已刷新', detail: '租约与用量已重新读取。' });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '刷新失败', detail: String(err) });
    } finally {
      setBusy(false);
    }
  };

  // window.open is a no-op inside the Tauri webview — use the shell opener so the
  // card site launches in the real browser, falling back to window.open in web preview.
  const openCardSite = async () => {
    if (!cardSite?.url) {
      pushToast({ tone: 'warn', title: '发卡网站未配置', detail: '服务端 client-config 未返回 cardSite.url。' });
      return;
    }
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(cardSite.url);
    } catch {
      window.open(cardSite.url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">授权内测</div>
          <h1>授权、成员状态和发卡入口集中管理。</h1>
        </div>
        <div className="hero-actions">
          <Button variant="primary" icon={RefreshCcw} onClick={refresh}>
            刷新
          </Button>
          <Button variant="secondary" icon={ShieldCheck} onClick={handleRefreshMember} disabled={busy}>
            刷新成员
          </Button>
        </div>
      </section>

      <section className="stats-grid">
        <StatTile label="授权" value={license?.authorized ? '已激活' : '未激活'} hint={license?.licensee || '暂无所有者'} tone={license?.authorized ? 'ok' : 'warn'} />
        <StatTile label="成员" value={memberStatusLabel(member?.status)} hint={member?.memberId || '暂无成员'} tone={member?.status === 'active' ? 'ok' : 'warn'} />
        <StatTile label="网关" value={gateway?.hasGateway ? '已配置' : '缺失'} hint={gateway?.baseUrl || '暂无地址'} tone={gateway?.hasGateway ? 'ok' : 'warn'} />
        <StatTile label="发卡网站" value={cardSite?.enabled ? '服务端开启' : '关闭'} hint={cardSite?.url || '暂无地址'} tone={cardSite?.enabled ? 'ok' : 'neutral'} />
      </section>

      {loading ? (
        <Panel className="panel-loading">正在读取授权信息...</Panel>
      ) : error ? (
        <Panel className="panel-error">
          <InlineState tone="danger" title="授权信息读取失败" description={error} />
        </Panel>
      ) : data ? (
        <section className="content-grid content-grid-license">
          <Panel className="surface-panel">
            <SectionHeader
              eyebrow="授权"
              title="当前授权"
              action={<Chip tone={license?.authorized ? 'ok' : 'warn'}>{sourceLabel(license?.rawHint || 'mock')}</Chip>}
            />
            {license?.authorized ? (
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">所有者</span><span className="detail-value">{license.licensee}</span></div>
                <div className="detail-row"><span className="detail-label">版本</span><span className="detail-value">{displayEdition(license.edition)}</span></div>
                <div className="detail-row"><span className="detail-label">到期</span><span className="detail-value">{license.expires}</span></div>
                <div className="detail-row"><span className="detail-label">安装 ID</span><span className="detail-value">{license.installId}</span></div>
                <div className="detail-row"><span className="detail-label">能力</span><span className="detail-value">{license.features.join(' / ') || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">网关</span><span className="detail-value">{license.gatewayBaseUrl || '暂无'}</span></div>
              </div>
            ) : (
              <EmptyState title="暂无授权" description="在右侧输入授权码激活。" />
            )}
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader
              eyebrow="激活"
              title="授权码"
            />
            <Field label="授权码" hint="OC-PRO-xxxx-xxxx">
              <Input value={licenseCode} onChange={(event) => setLicenseCode(event.target.value)} placeholder="OC-PRO-XXXX-XXXX-XXXX-XXXX" />
            </Field>
            <div className="button-row">
              <Button variant="primary" icon={BadgeCheck} onClick={handleActivateLicense} disabled={busy}>
                激活授权
              </Button>
              <Button variant="secondary" icon={RefreshCcw} onClick={handleRefreshMember} disabled={busy}>
                刷新成员
              </Button>
            </div>
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader
              eyebrow="成员"
              title="租约与用量"
              subtitle="只展示 /api/member/current 的成员状态、租约和额度，不增加新的成员激活业务。"
            />
            {member ? (
              <div className="detail-stack">
                <div className="detail-row"><span className="detail-label">状态</span><span className="detail-value">{memberStatusLabel(member.status)}</span></div>
                <div className="detail-row"><span className="detail-label">租约</span><span className="detail-value">{member.leaseId || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">成员 ID</span><span className="detail-value">{member.memberId || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">到期</span><span className="detail-value">{member.expiresAt || '暂无'}</span></div>
                <div className="detail-row"><span className="detail-label">续租</span><span className="detail-value">{member.renewAt || '暂无'}</span></div>
                <div className="quota-grid">
                  <div className="quota-box"><span>LLM</span><strong>{member.usage.llm}</strong></div>
                  <div className="quota-box"><span>图像</span><strong>{member.usage.image}</strong></div>
                  <div className="quota-box"><span>视频</span><strong>{member.usage.video}</strong></div>
                  <div className="quota-box"><span>月份</span><strong>{member.usage.month}</strong></div>
                </div>
              </div>
            ) : (
              <EmptyState title="暂无成员数据" description="刷新成员后会显示租约与用量；如果后端返回空数组或空字段，页面会保持空状态。" />
            )}
          </Panel>

          <Panel className="surface-panel">
            <SectionHeader
              eyebrow="网关 / 发卡"
              title="服务端配置映射"
              action={<Chip tone={cardSite?.enabled ? 'ok' : 'neutral'}>{cardSite?.enabled ? '服务端开启' : '未开启'}</Chip>}
            />
            <div className="detail-stack">
              <div className="detail-row"><span className="detail-label">主地址</span><span className="detail-value">{gateway?.baseUrl || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">图像地址</span><span className="detail-value">{gateway?.imageBaseUrl || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">视频地址</span><span className="detail-value">{gateway?.videoBaseUrl || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">模型密钥</span><span className="detail-value">{gateway?.apiKeyMasked || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">图像密钥</span><span className="detail-value">{gateway?.imageApiKeyMasked || '暂无'}</span></div>
              <div className="detail-row"><span className="detail-label">视频密钥</span><span className="detail-value">{gateway?.videoApiKeyMasked || '暂无'}</span></div>
            </div>
            {cardSite?.enabled && cardSite.url ? (
              <div className="button-row">
                <Button variant="quiet" icon={ExternalLink} onClick={openCardSite}>
                  {cardSite.label || '打开发卡网站'}
                </Button>
              </div>
            ) : (
              <EmptyState title="发卡网站未开启" description="服务端 client-config 没有返回可用的 cardSite.url。" />
            )}
          </Panel>
        </section>
      ) : null}
    </div>
  );
}

function sourceLabel(value: string) {
  const map: Record<string, string> = {
    mock: '预览',
    live: '真实接口',
    mixed: '混合',
  };
  return map[value] || value;
}

function displayEdition(value?: string) {
  if (!value) return '已授权';
  if (value === 'Pro') return '专业版';
  if (value === 'Free') return '免费版';
  return value;
}

function memberStatusLabel(value?: string) {
  if (!value) return '未激活';
  if (value === 'active') return '已激活';
  if (value === 'inactive') return '未激活';
  return value;
}
