import React from 'react';
import { Button, showToast } from '../common';

interface ChecklistItem {
  id: string;
  title: string;
  desc: string;
}

interface ChecklistGroup {
  title: string;
  desc: string;
  items: ChecklistItem[];
}

const STORAGE_KEY = 'openclaw_delivery_checklist_v1';

const CHECKLIST: ChecklistGroup[] = [
  {
    title: '基础交付',
    desc: '客户首次打开时必须稳定通过',
    items: [
      { id: 'license_activate', title: '授权码激活', desc: '输入授权码后显示已授权，重启启动器后授权状态仍保留。' },
      { id: 'api_save', title: 'API 配置保存', desc: '保存 Base URL、API Key 和模型后，重启仍显示 API 已配置。' },
      { id: 'service_start', title: '启动核心服务', desc: '点击启动后 18790 端口可访问，网页界面不白屏、不再要求网关令牌。' },
      { id: 'service_stop', title: '停止服务', desc: '点击停止后服务状态回到空闲，残留进程和端口不会影响下次启动。' },
    ],
  },
  {
    title: 'AI 能力',
    desc: '广告生产链路的核心功能',
    items: [
      { id: 'image_generate', title: 'AI 生图', desc: '至少完成一次图片生成，结果可预览、可保存、不会空结果。' },
      { id: 'video_generate', title: 'AI 视频', desc: '至少完成一次视频生成，播放器能加载结果，失败时提示可读。' },
      { id: 'storyboard_flow', title: '广告工作台', desc: '三视图、分镜、首帧/尾帧、九宫格和候选图流程能完整走通。' },
      { id: 'model_custom', title: '自定义模型', desc: '自定义供应商可手动填写模型，保存后 OpenClaw 可读取模型配置。' },
    ],
  },
  {
    title: '外部集成',
    desc: '安装包对外能力和可维护性',
    items: [
      { id: 'lark_plugin', title: '飞书插件', desc: '能检测是否安装，未安装时可执行 npx 安装命令，配置保存后不丢。' },
      { id: 'diagnostics', title: '环境诊断', desc: '环境诊断能显示检查项，一键修复能清理端口/残留进程。' },
      { id: 'diagnostics_export', title: '导出诊断包', desc: '能生成 zip 诊断包，包内不包含 API Key、授权签名等敏感明文。' },
      { id: 'help_docs', title: '帮助入口', desc: '帮助文档和网页界面入口可打开，不影响主流程。' },
    ],
  },
  {
    title: '离线包',
    desc: '最终发给客户前的包装检查',
    items: [
      { id: 'portable_runtime', title: '运行时完整', desc: '压缩包内包含 OpenClaw.exe、node.exe、python.exe、start.js 和 OpenClaw 本体。' },
      { id: 'portable_clean', title: '无敏感文件', desc: '压缩包内不包含 license.db、private_key、admin_token、客户 API Key 或旧 license.json。' },
      { id: 'portable_new_dir', title: '新目录冷启动', desc: '把包解压到全新目录后启动，不依赖你电脑上的旧安装环境。' },
      { id: 'release_hash', title: '校验信息', desc: '记录 zip 文件名、版本号和 SHA256，方便售后确认客户拿到的是同一包。' },
    ],
  },
];

function flattenItems(): ChecklistItem[] {
  return CHECKLIST.flatMap((group) => group.items);
}

function loadState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveState(state: Record<string, boolean>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export const DeliveryChecklistPage: React.FC = () => {
  const [checked, setChecked] = React.useState<Record<string, boolean>>(() => loadState());
  const allItems = React.useMemo(() => flattenItems(), []);
  const done = allItems.filter((item) => checked[item.id]).length;
  const total = allItems.length;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;
  const ready = done === total;

  React.useEffect(() => {
    saveState(checked);
  }, [checked]);

  const toggle = (id: string) => {
    setChecked((state) => ({ ...state, [id]: !state[id] }));
  };

  const reset = () => {
    if (!confirm('确认重置所有验收项？')) return;
    setChecked({});
    showToast('验收清单已重置', 'info');
  };

  const markAll = () => {
    const next: Record<string, boolean> = {};
    for (const item of allItems) {
      next[item.id] = true;
    }
    setChecked(next);
    showToast('已全部标记为通过', 'success');
  };

  const copyReport = async () => {
    const lines = [
      `OpenClaw 交付验收：${done}/${total} (${progress}%)`,
      `交付判定：${ready ? '可以交付' : '仍需检查'}`,
      '',
      ...CHECKLIST.flatMap((group) => [
        `[${group.title}]`,
        ...group.items.map((item) => `${checked[item.id] ? '[x]' : '[ ]'} ${item.title} - ${item.desc}`),
        '',
      ]),
    ];
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      showToast('验收结果已复制', 'success');
    } catch {
      showToast('复制失败，请手动截图或选择文本', 'error');
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-transparent">
      <div className="flex h-[72px] shrink-0 items-center justify-between border-b border-white/10 bg-surface/70 px-8 backdrop-blur-xl">
        <div>
          <h1 className="text-xl font-bold text-text">交付验收清单</h1>
          <p className="mt-1 text-sm text-text-muted">出包前逐项确认，避免客户现场翻车</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="quiet" onClick={copyReport}>复制结果</Button>
          <Button variant="quiet" onClick={reset}>重置</Button>
          <Button variant="primary" onClick={markAll}>全部通过</Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-8">
        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-4">
            <section className={`rounded-2xl border p-5 ${ready ? 'border-status-success/30 bg-status-success/10' : 'border-status-warning/30 bg-status-warning/10'}`}>
              <div className="text-sm font-bold text-text">验收进度</div>
              <div className="mt-2 text-4xl font-black text-text">{progress}%</div>
              <div className="mt-2 text-sm text-text-muted">{done}/{total} 项已确认</div>
              <div className="mt-5 h-3 overflow-hidden rounded-full border border-white/10 bg-black/25">
                <div
                  className={`h-full rounded-full transition-all ${ready ? 'bg-status-success' : 'bg-status-warning'}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="mt-5 rounded-xl border border-white/10 bg-black/15 p-4">
                <div className="text-xs font-bold uppercase tracking-[0.18em] text-text-subtle">交付判定</div>
                <div className={`mt-2 text-lg font-black ${ready ? 'text-status-success' : 'text-status-warning'}`}>
                  {ready ? '可以交付' : '仍需检查'}
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
              <h2 className="text-sm font-bold text-text">使用建议</h2>
              <p className="mt-3 text-sm leading-relaxed text-text-muted">
                每次打包后在全新目录跑一遍。客户遇到问题时，优先让客户导出诊断包，再对照这张清单定位是哪一环没过。
              </p>
            </section>
          </aside>

          <section className="min-w-0 space-y-4">
            {CHECKLIST.map((group) => {
              const groupDone = group.items.filter((item) => checked[item.id]).length;
              return (
                <div key={group.title} className="rounded-2xl border border-white/10 bg-white/[0.035] p-5">
                  <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                      <h2 className="text-base font-bold text-text">{group.title}</h2>
                      <p className="mt-1 text-sm text-text-muted">{group.desc}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs font-bold text-text-muted">
                      {groupDone}/{group.items.length}
                    </span>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {group.items.map((item) => {
                      const active = !!checked[item.id];
                      return (
                        <button
                          key={item.id}
                          onClick={() => toggle(item.id)}
                          className={`min-h-[116px] rounded-xl border p-4 text-left transition-all ${
                            active
                              ? 'border-status-success/35 bg-status-success/10 shadow-[0_0_24px_rgba(22,199,132,0.12)]'
                              : 'border-white/10 bg-black/15 hover:border-border-strong hover:bg-white/[0.055]'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-xs font-black ${
                              active
                                ? 'border-status-success bg-status-success text-white'
                                : 'border-white/15 bg-white/[0.035] text-text-subtle'
                            }`}>
                              {active ? '✓' : ''}
                            </span>
                            <div className="min-w-0">
                              <div className="text-sm font-bold text-text">{item.title}</div>
                              <p className="mt-2 text-sm leading-relaxed text-text-muted">{item.desc}</p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        </div>
      </div>
    </div>
  );
};
