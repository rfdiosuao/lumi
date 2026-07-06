import React from 'react';
import {
  acquisitionApi,
  feishuApi,
  parseErrorText,
  type AcquisitionDraft,
  type AcquisitionLead,
  type AcquisitionSnapshot,
  type AcquisitionTemplateStatus,
  type FeishuStatus,
} from '../../services/api';
import { Button, Input, TextArea, showToast } from '../common';

const EMPTY_SNAPSHOT: AcquisitionSnapshot = {
  schema: 'loom.customer_acquisition.v1',
  contentTasks: [],
  leads: [],
  customers: [],
  drafts: [],
  sop: [],
  logs: [],
  stats: {
    contentTasks: 0,
    leads: 0,
    customers: 0,
    draftsPending: 0,
    approvedDrafts: 0,
    pendingSync: 0,
  },
  outboundPolicy: ['draft_only', 'manual_confirm', 'whitelist', 'frequency_cap', 'audit_log'],
  integrations: {
    feishu: {
      cliInstalled: false,
      connected: false,
      pendingCount: 0,
      auth: { loggedIn: false, botReady: false },
      table: {},
      lastSync: {},
    },
  },
};

const PLATFORM_OPTIONS = [
  { id: 'douyin', label: '抖音' },
  { id: 'xiaohongshu', label: '小红书' },
  { id: 'wechat', label: '微信' },
  { id: 'manual', label: '手动导入' },
];

const SOURCE_STEPS = [
  { title: '手动导入', detail: '先接 CSV、评论 JSON、剪贴板线索，保证安全可控。', state: '已接入' },
  { title: '评论区导入', detail: '下一步接抖音/小红书评论读取，把意向留言沉淀成线索。', state: '待填能力' },
  { title: '私信会话导入', detail: '只读取和归档会话，不做无确认群发。', state: '待填能力' },
  { title: '搜索关键词任务', detail: '按行业、城市、痛点关键词生成采集任务。', state: '设计中' },
];

const FUNNEL_STEPS = [
  '获客任务',
  '线索来源',
  'AI 筛选',
  '飞书入表',
  '待确认触达',
  '日志复盘',
];

const CAPABILITY_CARDS = [
  {
    title: '自动找线索',
    detail: '从评论、会话、关键词和手动导入里发现潜在客户，把零散信息变成可跟进线索。',
    metric: '发现',
  },
  {
    title: 'AI 写话术',
    detail: '根据客户场景生成开场白、评论回复、私信草稿和下一步跟进建议。',
    metric: '开口',
  },
  {
    title: '沉淀客户池',
    detail: '把线索、客户阶段、跟进状态和负责人沉淀下来，避免漏跟进。',
    metric: '管理',
  },
  {
    title: '同步飞书线索表',
    detail: '自动把本地线索写入飞书，多维表格成为销售团队的统一客户池。',
    metric: '入表',
  },
  {
    title: '安全触达队列',
    detail: '真实评论、私信、加微和发布只进入待确认队列，默认不自动发送。',
    metric: '风控',
  },
];

function statusLabel(value: string): string {
  if (value === 'pending_manual_review') return '待人工确认';
  if (value === 'approved_pending_manual_send') return '已确认待手动触达';
  if (value === 'qualified') return '已筛选';
  if (value === 'needs_follow_up') return '待跟进';
  if (value === 'pending_sync') return '待同步飞书';
  if (value === 'sync_failed') return '同步失败';
  if (value === 'synced') return '已入飞书';
  return value || '待处理';
}

function feishuStatusLabel(status?: FeishuStatus): string {
  if (!status?.cliInstalled) return '未安装 CLI';
  if (!status?.auth?.loggedIn && !status?.auth?.botReady) return '未登录';
  if (!status?.table?.baseToken || !status?.table?.tableId) return '未绑定表格';
  return status.connected ? '已连接' : '待检查';
}

function latestPendingDraft(snapshot: AcquisitionSnapshot): AcquisitionDraft | null {
  return [...snapshot.drafts].reverse().find((draft) => draft.status === 'pending_manual_review') || null;
}

function latestLead(snapshot: AcquisitionSnapshot): AcquisitionLead | null {
  return snapshot.leads[snapshot.leads.length - 1] || null;
}

export const AcquisitionWorkbenchPage = () => {
  const [snapshot, setSnapshot] = React.useState<AcquisitionSnapshot>(EMPTY_SNAPSHOT);
  const [topic, setTopic] = React.useState('本地生活商家 AI 私域获客试跑');
  const [platform, setPlatform] = React.useState('douyin');
  const [target, setTarget] = React.useState('美业/家政/装修老板，正在找低成本获客方法');
  const [leadSummary, setLeadSummary] = React.useState('评论区用户询问如何用手机矩阵持续找客户，希望先看一份行业试跑方案。');
  const [knowledge, setKnowledge] = React.useState('先确认行业、城市、客单价、现在线索来源，再给出低风险试跑路径；不承诺效果，不诱导骚扰。');
  const [loading, setLoading] = React.useState(false);
  const [confirmingId, setConfirmingId] = React.useState('');
  const [feishuBusy, setFeishuBusy] = React.useState('');
  const [templateBusy, setTemplateBusy] = React.useState('');
  const [templateStatus, setTemplateStatus] = React.useState<AcquisitionTemplateStatus | null>(null);
  const [tableUrl, setTableUrl] = React.useState('');
  const [loginGuide, setLoginGuide] = React.useState<{ loginUrl?: string; userCode?: string; qrAscii?: string } | null>(null);

  const refreshTemplates = React.useCallback(async () => {
    try {
      setTemplateStatus(await acquisitionApi.templates());
    } catch {
      setTemplateStatus(null);
    }
  }, []);

  const refresh = React.useCallback(async () => {
    try {
      setSnapshot(await acquisitionApi.snapshot());
      void refreshTemplates();
    } catch (error) {
      showToast(parseErrorText(error) || '读取获客工作台失败', 'error');
    }
  }, [refreshTemplates]);

  React.useEffect(() => {
    void refresh();
    void refreshTemplates();
  }, [refresh, refreshTemplates]);

  const runDemo = async () => {
    if (!topic.trim() || !leadSummary.trim()) {
      showToast('请先填写获客任务和线索描述', 'info');
      return;
    }
    setLoading(true);
    try {
      const result = await acquisitionApi.runDemo({
        topic,
        platform,
        channel: platform === 'wechat' ? 'wechat' : 'comment',
        leadSummary: `${target.trim() ? `目标客户：${target.trim()}。` : ''}${leadSummary}`,
        knowledge,
      });
      setSnapshot(result.snapshot);
      showToast('已生成线索、AI 判断和跟进草稿', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '生成跟进草稿失败', 'error');
    } finally {
      setLoading(false);
    }
  };

  const confirmDraft = async (draftId: string) => {
    setConfirmingId(draftId);
    try {
      const result = await acquisitionApi.confirmDraft(draftId);
      setSnapshot(result.snapshot);
      showToast('草稿已人工确认，仍不会自动发送', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '确认草稿失败', 'error');
    } finally {
      setConfirmingId('');
    }
  };

  const refreshFeishu = async () => {
    setFeishuBusy('status');
    try {
      const feishu = await feishuApi.status();
      setSnapshot((current) => ({ ...current, integrations: { ...(current.integrations || {}), feishu } }));
      showToast('已刷新飞书状态', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '刷新飞书状态失败', 'error');
    } finally {
      setFeishuBusy('');
    }
  };

  const startFeishuLogin = async () => {
    setFeishuBusy('login');
    try {
      const guide = await feishuApi.login();
      setLoginGuide({ loginUrl: guide.loginUrl || guide.verificationUrl, userCode: guide.userCode, qrAscii: guide.qrAscii });
      showToast('请扫码或打开链接完成飞书登录', 'info');
    } catch (error) {
      showToast(parseErrorText(error) || '启动飞书扫码登录失败', 'error');
    } finally {
      setFeishuBusy('');
    }
  };

  const bindFeishuTable = async () => {
    if (!tableUrl.trim()) {
      showToast('请粘贴飞书线索表链接', 'info');
      return;
    }
    setFeishuBusy('bind');
    try {
      const result = await feishuApi.bindTable({ url: tableUrl, name: '麓鸣获客线索表' });
      const feishu = result.status || await feishuApi.status();
      setSnapshot((current) => ({ ...current, integrations: { ...(current.integrations || {}), feishu } }));
      showToast('已绑定飞书线索表', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '绑定飞书线索表失败', 'error');
    } finally {
      setFeishuBusy('');
    }
  };

  const testFeishuWrite = async () => {
    setFeishuBusy('test');
    try {
      await feishuApi.testWrite();
      await refresh();
      showToast('已提交飞书测试写入', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '飞书测试写入失败', 'error');
    } finally {
      setFeishuBusy('');
    }
  };

  const retryFeishuSync = async () => {
    setFeishuBusy('retry');
    try {
      await feishuApi.retrySync();
      await refresh();
      showToast('已重试同步本地缓存线索', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '重试同步失败', 'error');
    } finally {
      setFeishuBusy('');
    }
  };

  const saveTemplate = async () => {
    setTemplateBusy('save');
    try {
      const result = await acquisitionApi.saveTemplate({
        name: `${topic || '获客'}模板`,
        topic,
        industry: target.split(/[，,、/]/)[0] || '通用获客',
        platform,
        platforms: [platform],
        targetCustomer: target,
        keywords: [topic, target].filter(Boolean),
        leadRules: ['询价', '问方案', '问案例', '表达合作意向'],
        replyStyle: knowledge,
        knowledge,
      });
      setTemplateStatus(result.status || await acquisitionApi.templates());
      const uploaded = result.template?.uploadStatus === 'uploaded';
      showToast(uploaded ? '模板已沉淀并自动上传服务器' : '模板已沉淀，服务器未配置时会保留待上传', uploaded ? 'success' : 'info');
    } catch (error) {
      showToast(parseErrorText(error) || '沉淀模板失败', 'error');
    } finally {
      setTemplateBusy('');
    }
  };

  const retryTemplateUpload = async () => {
    setTemplateBusy('retry');
    try {
      const result = await acquisitionApi.retryTemplates();
      setTemplateStatus((result as { status?: AcquisitionTemplateStatus }).status || await acquisitionApi.templates());
      showToast('已重试上传待同步模板', 'success');
    } catch (error) {
      showToast(parseErrorText(error) || '重试上传模板失败', 'error');
    } finally {
      setTemplateBusy('');
    }
  };

  const pendingDraft = latestPendingDraft(snapshot);
  const latestDraft = snapshot.drafts[snapshot.drafts.length - 1] || null;
  const visibleDraft = pendingDraft || latestDraft;
  const lead = latestLead(snapshot);
  const feishu = snapshot.integrations?.feishu;
  const pendingSync = snapshot.stats.pendingSync || feishu?.pendingCount || 0;
  const templateStats = templateStatus?.stats || {};
  const latestTemplate = templateStatus?.templates?.[templateStatus.templates.length - 1];

  return (
    <div data-acquisition-workbench className="h-full overflow-auto bg-[#EEF2F5] text-[#18212A]">
      <div className="mx-auto flex min-h-full w-full max-w-[1380px] flex-col gap-4 px-5 py-4">
        <header className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-4 border-b border-[#CCD5DD] pb-4">
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-[#0F6B7A]">自动营销工作台 / AI PRIVATE TRAFFIC ACQUISITION</div>
            <h1 className="mt-1 text-[28px] font-black leading-9 text-[#111827]">多台手机矩阵，自动帮你发现潜在客户</h1>
            <p className="mt-2 max-w-[900px] text-sm font-semibold leading-6 text-[#5D6875]">
              适合本地商家和销售团队的 AI 私域获客助手：多台设备统一调度，自动发现线索、AI 判断意向、生成沟通话术、同步飞书线索表，再把真实触达放进人工确认队列。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {['本地生活', '招商加盟', '房产保险', '短视频获客', '私域运营'].map((item) => (
                <span key={item} className="rounded-[6px] border border-[#CBD5E1] bg-white px-2.5 py-1 text-[11px] font-black text-[#475569]">{item}</span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="quiet" onClick={() => void refresh()} className="!rounded-[8px]">刷新</Button>
            <Button variant="primary" onClick={() => void runDemo()} disabled={loading} className="!rounded-[8px]">
              {loading ? '生成中...' : '跑一条演示流'}
            </Button>
          </div>
        </header>

        <section data-acquisition-stats className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
          {[
            ['内容任务', snapshot.stats.contentTasks, '#0F6B7A'],
            ['线索池', snapshot.stats.leads, '#2563EB'],
            ['客户池', snapshot.stats.customers, '#4F46E5'],
            ['待确认草稿', snapshot.stats.draftsPending, '#B45309'],
            ['飞书待同步', pendingSync, '#BE123C'],
            ['已确认草稿', snapshot.stats.approvedDrafts, '#047857'],
          ].map(([label, value, color]) => (
            <div key={label} className="min-h-[74px] rounded-[8px] border border-[#D5DDE5] bg-white px-3 py-2">
              <div className="text-xs font-bold text-[#647181]">{label}</div>
              <div className="mt-1 text-2xl font-black" style={{ color: String(color) }}>{value}</div>
            </div>
          ))}
        </section>

        <section className="grid gap-2 md:grid-cols-5">
          {CAPABILITY_CARDS.map((item) => (
            <div key={item.title} className="min-h-[126px] rounded-[8px] border border-[#D5DDE5] bg-white p-3">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-black text-[#111827]">{item.title}</h2>
                <span className="rounded-[6px] bg-[#E0F2FE] px-2 py-1 text-[11px] font-black text-[#075985]">{item.metric}</span>
              </div>
              <p className="mt-2 text-xs font-semibold leading-5 text-[#647181]">{item.detail}</p>
            </div>
          ))}
        </section>

        <section className="grid gap-2 md:grid-cols-6">
          {FUNNEL_STEPS.map((step, index) => (
            <div key={step} className="rounded-[8px] border border-[#D5DDE5] bg-white px-3 py-2">
              <div className="text-[10px] font-black text-[#8A96A3]">STEP {index + 1}</div>
              <div className="mt-1 truncate text-sm font-black text-[#1F2937]">{step}</div>
            </div>
          ))}
        </section>

        <main className="grid min-h-[620px] grid-cols-1 gap-4 xl:grid-cols-[360px_minmax(420px,1fr)_360px]">
          <section data-marketing-mission-control className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
            <div className="text-[10px] font-black tracking-[0.18em] text-[#0F6B7A]">MISSION CONTROL</div>
            <h2 className="mt-1 text-base font-black">获客任务</h2>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="text-xs font-bold text-[#5D6875]">任务主题</span>
                <Input value={topic} onChange={(event) => setTopic(event.target.value)} className="mt-1 !rounded-[8px]" />
              </label>
              <label className="block">
                <span className="text-xs font-bold text-[#5D6875]">目标客户</span>
                <Input value={target} onChange={(event) => setTarget(event.target.value)} className="mt-1 !rounded-[8px]" />
              </label>
              <label className="block">
                <span className="text-xs font-bold text-[#5D6875]">平台</span>
                <select
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="mt-1 w-full rounded-[8px] border border-[#CBD5E1] bg-[#F8FAFC] px-3 py-2 text-sm font-semibold text-[#18212A] outline-none focus:border-[#0F6B7A]"
                >
                  {PLATFORM_OPTIONS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-bold text-[#5D6875]">线索发现/导入</span>
                <TextArea value={leadSummary} rows={4} onChange={(event) => setLeadSummary(event.target.value)} className="mt-1 !rounded-[8px]" />
              </label>
              <label className="block">
                <span className="text-xs font-bold text-[#5D6875]">SOP/知识库回复</span>
                <TextArea value={knowledge} rows={4} onChange={(event) => setKnowledge(event.target.value)} className="mt-1 !rounded-[8px]" />
              </label>
              <Button variant="primary" onClick={() => void runDemo()} disabled={loading} className="w-full !rounded-[8px]">
                {loading ? '生成中...' : '生成线索与跟进草稿'}
              </Button>
            </div>
          </section>

          <section className="flex min-h-0 flex-col gap-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <section data-lead-source-panel className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
                <h2 className="text-base font-black">线索来源</h2>
                <div className="mt-3 space-y-2">
                  {SOURCE_STEPS.map((item) => (
                    <div key={item.title} className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-black">{item.title}</div>
                        <span className="rounded-[6px] bg-[#E0F2FE] px-2 py-1 text-[11px] font-black text-[#075985]">{item.state}</span>
                      </div>
                      <div className="mt-1 text-xs font-semibold leading-5 text-[#647181]">{item.detail}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section data-ai-qualification-panel className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
                <h2 className="text-base font-black">AI 筛选</h2>
                <div className="mt-3 rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3">
                  <div className="text-xs font-black text-[#647181]">当前判断</div>
                  <div className="mt-2 text-sm font-bold leading-6 text-[#1F2937]">
                    {lead ? lead.summary : '生成演示流后，这里会展示客户需求摘要、意向等级和推荐跟进动作。'}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {['需求强度', '行业匹配', '可跟进', '需人工确认'].map((tag) => (
                      <span key={tag} className="rounded-[6px] border border-[#CBD5E1] bg-white px-2 py-1 text-[11px] font-black text-[#475569]">{tag}</span>
                    ))}
                  </div>
                </div>
                <div className="mt-3 rounded-[8px] border border-[#FDE68A] bg-[#FFFBEB] p-3 text-xs font-bold leading-5 text-[#854D0E]">
                  AI 只给判断和话术建议，不替用户承诺效果，也不绕过人工确认。
                </div>
              </section>
            </div>

            <section data-acquisition-lead-pool className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-black">线索池 / 客户池</h2>
                <span className="rounded-[6px] border border-[#CBD5E1] px-2 py-1 text-[11px] font-black text-[#475569]">
                  {snapshot.leads.length} leads
                </span>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <LeadColumn
                  title="潜在线索"
                  empty="线索会先进入这里，随后再入飞书。"
                  rows={snapshot.leads.slice(-4).reverse().map((item) => ({
                    id: item.leadId,
                    title: item.title,
                    body: item.summary,
                    meta: `${statusLabel(item.status)} / ${item.channel || 'manual'} / ${statusLabel(item.syncStatus || '')}`,
                  }))}
                />
                <LeadColumn
                  title="客户池"
                  empty="AI 筛选后的客户会沉淀到这里。"
                  rows={snapshot.customers.slice(-4).reverse().map((item) => ({
                    id: item.customerId,
                    title: item.name,
                    body: item.summary || '',
                    meta: statusLabel(item.stage),
                  }))}
                />
              </div>
            </section>

            <section data-acquisition-draft-review data-safe-outreach-queue className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-black">待确认触达</h2>
                  <p className="mt-1 text-xs font-semibold text-[#647181]">评论、私信、微信跟进只生成草稿；人工确认也不会自动发送。</p>
                </div>
                {visibleDraft ? <span className="rounded-[6px] bg-[#ECFDF5] px-2 py-1 text-[11px] font-black text-[#047857]">{statusLabel(visibleDraft.status)}</span> : null}
              </div>
              {visibleDraft ? (
                <div className="mt-3">
                  <div className="min-h-[112px] rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3 text-sm font-semibold leading-6 text-[#1F2937]">
                    {visibleDraft.body}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {visibleDraft.policy.map((item) => (
                      <span key={item} className="rounded-[6px] border border-[#CBD5E1] bg-white px-2 py-1 text-[11px] font-black text-[#475569]">{policyLabel(item)}</span>
                    ))}
                  </div>
                  <Button
                    variant="success"
                    onClick={() => void confirmDraft(visibleDraft.draftId)}
                    disabled={visibleDraft.status !== 'pending_manual_review' || confirmingId === visibleDraft.draftId}
                    className="mt-4 !rounded-[8px]"
                  >
                    {confirmingId === visibleDraft.draftId ? '确认中...' : '人工确认'}
                  </Button>
                </div>
              ) : (
                <div className="mt-3 rounded-[8px] border border-dashed border-[#CBD5E1] p-8 text-center text-sm font-bold text-[#647181]">还没有待确认草稿</div>
              )}
            </section>
          </section>

          <aside className="flex min-h-0 flex-col gap-4">
            <section data-template-cloud-panel className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-black">云端模板库</h2>
                  <div className="mt-1 text-xs font-semibold text-[#647181]">
                    {templateStatus?.cloud?.configured ? '服务器已配置，沉淀后自动上传' : '服务器未配置，模板会先进入待上传'}
                  </div>
                </div>
                <span className="rounded-[6px] bg-[#E0F2FE] px-2 py-1 text-[11px] font-black text-[#075985]">自动上传</span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs font-bold text-[#475569]">
                <div className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">总数：{templateStats.total || 0}</div>
                <div className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">待上传：{templateStats.pendingUpload || 0}</div>
                <div className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">已上传：{templateStats.uploaded || 0}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="primary" onClick={() => void saveTemplate()} disabled={Boolean(templateBusy)} className="!rounded-[8px] !px-3 !py-1.5 !text-xs">
                  {templateBusy === 'save' ? '沉淀中...' : '沉淀为模板并上传服务器'}
                </Button>
                <Button variant="quiet" onClick={() => void retryTemplateUpload()} disabled={Boolean(templateBusy)} className="!rounded-[8px] !px-3 !py-1.5 !text-xs">
                  重试待上传
                </Button>
              </div>
              <div className="mt-3 rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3 text-xs font-semibold leading-5 text-[#647181]">
                {latestTemplate ? (
                  <>
                    <div className="font-black text-[#1F2937]">{latestTemplate.name}</div>
                    <div>状态：{templateUploadLabel(latestTemplate.uploadStatus || '')}</div>
                    <div className="break-all">服务器：{latestTemplate.remote?.url || templateStatus?.cloud?.serverUrl || '待配置'}</div>
                  </>
                ) : (
                  <div>还没有沉淀模板。跑通一个获客任务后，可以把行业、关键词、筛选规则和话术风格保存成模板。</div>
                )}
              </div>
            </section>

            <section data-feishu-sync-panel data-acquisition-feishu-sync className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-black">飞书入表 / 连接飞书</h2>
                  <div className="mt-1 text-xs font-semibold text-[#647181]">状态：{feishuStatusLabel(feishu)}</div>
                </div>
                <Button variant="quiet" onClick={() => void refreshFeishu()} disabled={Boolean(feishuBusy)} className="!rounded-[8px] !px-2.5 !py-1.5 !text-xs">
                  检查
                </Button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-bold text-[#475569]">
                <div className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">CLI：{feishu?.cliInstalled ? '已安装' : '未安装'}</div>
                <div className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">登录：{feishu?.auth?.loggedIn ? '用户已登录' : feishu?.auth?.botReady ? 'Bot 可用' : '待扫码'}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="primary" onClick={() => void startFeishuLogin()} disabled={Boolean(feishuBusy)} className="!rounded-[8px] !px-3 !py-1.5 !text-xs">扫码登录</Button>
                <Button variant="quiet" onClick={() => void testFeishuWrite()} disabled={Boolean(feishuBusy)} className="!rounded-[8px] !px-3 !py-1.5 !text-xs">测试写入</Button>
                <Button variant="quiet" onClick={() => void retryFeishuSync()} disabled={Boolean(feishuBusy)} className="!rounded-[8px] !px-3 !py-1.5 !text-xs">重试同步</Button>
              </div>
              {loginGuide ? (
                <div className="mt-3 rounded-[8px] border border-[#BAE6FD] bg-[#F0F9FF] p-2 text-xs font-semibold leading-5 text-[#075985]">
                  <div className="break-all">登录链接：{loginGuide.loginUrl || '请查看飞书 CLI 输出'}</div>
                  <div>验证码：{loginGuide.userCode || '无'}</div>
                  {loginGuide.qrAscii ? <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[9px] leading-3">{loginGuide.qrAscii}</pre> : null}
                </div>
              ) : null}
              <label className="mt-3 block">
                <span className="text-xs font-bold text-[#5D6875]">绑定线索表</span>
                <Input value={tableUrl} onChange={(event) => setTableUrl(event.target.value)} placeholder="粘贴飞书多维表格链接" className="mt-1 !rounded-[8px]" />
              </label>
              <Button variant="success" onClick={() => void bindFeishuTable()} disabled={Boolean(feishuBusy)} className="mt-2 w-full !rounded-[8px] !py-1.5 !text-xs">绑定线索表</Button>
              <div className="mt-3 space-y-1.5 text-xs font-semibold text-[#647181]">
                <div>表格：{feishu?.table?.name || feishu?.table?.tableId || '未绑定'}</div>
                <div>最近同步：{feishu?.lastSync?.syncStatus ? statusLabel(feishu.lastSync.syncStatus) : '暂无'}</div>
                <div>失败原因：{feishu?.lastSync?.syncError || '无'}</div>
              </div>
            </section>

            <section className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <h2 className="text-base font-black">安全策略</h2>
              <div className="mt-3 grid gap-2">
                {snapshot.outboundPolicy.map((item) => (
                  <div key={item} className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2 text-xs font-black text-[#475569]">
                    {policyLabel(item)}
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-[8px] border border-[#FECACA] bg-[#FEF2F2] p-3 text-xs font-bold leading-5 text-[#991B1B]">
                真实外发动作必须人工确认；不做无确认的批量私信、批量评论、批量加好友或自动骚扰式群发。
              </div>
            </section>

            <section className="rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <h2 className="text-base font-black">SOP/知识库</h2>
              <div className="mt-3 space-y-2">
                {snapshot.sop.map((item) => (
                  <div key={item.id} className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3">
                    <div className="text-sm font-black">{item.title}</div>
                    <div className="mt-1 text-xs font-semibold leading-5 text-[#647181]">{item.text}</div>
                  </div>
                ))}
              </div>
            </section>

            <section data-followup-log-panel data-acquisition-task-log className="min-h-0 flex-1 rounded-[8px] border border-[#D5DDE5] bg-white p-4">
              <h2 className="text-base font-black">跟进日志</h2>
              <div className="mt-3 max-h-[320px] space-y-2 overflow-auto">
                {snapshot.logs.slice(-12).reverse().map((log) => (
                  <div key={log.logId || `${log.type}-${log.timestamp}`} className="rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-2">
                    <div className="text-[11px] font-black text-[#0F6B7A]">{log.type || 'event'}</div>
                    <div className="mt-1 text-xs font-semibold leading-5 text-[#475569]">{log.message}</div>
                  </div>
                ))}
                {!snapshot.logs.length && <div className="rounded-[8px] border border-dashed border-[#CBD5E1] p-6 text-center text-sm font-bold text-[#647181]">演示流日志会在这里沉淀</div>}
              </div>
            </section>
          </aside>
        </main>
      </div>
    </div>
  );
};

function policyLabel(value: string): string {
  if (value === 'draft_only') return '只生成草稿';
  if (value === 'manual_confirm') return '人工确认';
  if (value === 'whitelist') return '白名单';
  if (value === 'frequency_cap') return '频控';
  if (value === 'audit_log') return '日志留痕';
  return value;
}

function templateUploadLabel(value: string): string {
  if (value === 'uploaded') return '已上传';
  if (value === 'upload_failed') return '上传失败';
  if (value === 'pending_upload') return '待上传';
  return value || '待上传';
}

function LeadColumn({
  title,
  empty,
  rows,
}: {
  title: string;
  empty: string;
  rows: Array<{ id: string; title: string; body: string; meta: string }>;
}) {
  return (
    <div className="min-h-[180px] rounded-[8px] border border-[#E1E7EE] bg-[#F8FAFC] p-3">
      <div className="text-sm font-black">{title}</div>
      <div className="mt-2 space-y-2">
        {rows.map((row) => (
          <div key={row.id} className="rounded-[8px] border border-[#E1E7EE] bg-white p-3">
            <div className="truncate text-sm font-black">{row.title}</div>
            <div className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-[#647181]">{row.body}</div>
            <div className="mt-2 text-[11px] font-black text-[#0F6B7A]">{row.meta}</div>
          </div>
        ))}
        {!rows.length ? <div className="rounded-[8px] border border-dashed border-[#CBD5E1] p-5 text-center text-sm font-bold text-[#647181]">{empty}</div> : null}
      </div>
    </div>
  );
}
