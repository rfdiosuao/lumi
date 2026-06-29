import React from 'react';
import { Button, Select, showToast } from '../common';
import { LumingWordmarkImage } from '../brand/LoomBrand';
import { useTheme } from '../../hooks/useTheme';
import { useAppStore } from '../../stores/appStore';

type SettingsTab = 'appearance' | 'data' | 'about';

const tabs: Array<{ key: SettingsTab; label: string }> = [
  { key: 'appearance', label: '外观' },
  { key: 'data', label: '数据' },
  { key: 'about', label: '关于' },
];

const SettingRow: React.FC<{
  title: string;
  desc: string;
  children: React.ReactNode;
}> = ({ title, desc, children }) => (
  <div className="grid gap-4 border-t border-border/75 py-5 md:grid-cols-[220px_minmax(0,1fr)]">
    <div>
      <div className="text-sm font-black text-text">{title}</div>
      <div className="mt-1 text-xs leading-5 text-text-muted">{desc}</div>
    </div>
    <div className="min-w-0">{children}</div>
  </div>
);

export const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = React.useState<SettingsTab>('appearance');
  const { themeMode, switchThemeMode } = useTheme();
  const setCurrentPage = useAppStore((state) => state.setCurrentPage);

  return (
    <div className="h-full overflow-y-auto bg-app-bg">
      <div className="mx-auto flex w-full max-w-[1080px] flex-col gap-6 px-8 py-7">
        <header className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <div className="text-[11px] font-bold tracking-[0.42em] text-accent">系统</div>
            <h1 className="mt-2 text-[36px] font-black leading-tight text-text">系统设置</h1>
          </div>
          <LumingWordmarkImage className="h-[46px] w-[128px]" />
        </header>

        <div className="flex border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`border-b-2 px-4 py-3 text-sm font-black transition ${
                activeTab === tab.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <section className="border-y border-border bg-surface/58 px-6">
          {activeTab === 'appearance' ? (
            <>
              <SettingRow title="语言" desc="演示版先锁定中文，减少现场语言切换带来的变量。">
                <Select value="zh-CN" disabled className="w-full max-w-[360px]">
                  <option value="zh-CN">中文</option>
                </Select>
              </SettingRow>
              <SettingRow title="主题" desc="当前版本以米白高级感为默认视觉，深色主题后续再独立打磨。">
                <div className="flex flex-wrap gap-3">
                  <Button variant={themeMode === 'light' ? 'primary' : 'quiet'} onClick={() => switchThemeMode('light')}>
                    米白
                  </Button>
                  <Button
                    variant="quiet"
                    disabled
                    onClick={() => showToast('深色主题暂未开放', 'info')}
                  >
                    深色
                  </Button>
                  <Button
                    variant="quiet"
                    disabled
                    onClick={() => showToast('跟随系统暂未开放', 'info')}
                  >
                    跟随系统
                  </Button>
                </div>
              </SettingRow>
              <SettingRow title="窗口按钮" desc="窗口控制使用系统级最小化、最大化和关闭按钮。">
                <div className="text-sm font-bold text-status-success">已启用标准窗口控制</div>
              </SettingRow>
            </>
          ) : null}

          {activeTab === 'data' ? (
            <>
              <SettingRow title="诊断与日志" desc="日志、诊断包和环境修复集中到高级诊断页，避免主流程信息过载。">
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" onClick={() => setCurrentPage('diagnostics')}>打开诊断</Button>
                  <Button variant="quiet" onClick={() => setCurrentPage('terminal')}>查看日志</Button>
                </div>
              </SettingRow>
              <SettingRow title="账号与模型" desc="中转站登录、模型同步和运行配置都集中在模型账号页。">
                <Button variant="primary" onClick={() => setCurrentPage('license')}>打开模型账号</Button>
              </SettingRow>
              <SettingRow title="组件数据" desc="Agent 组件由安装页统一检测、安装、启动、升级、卸载和回滚。">
                <Button variant="primary" onClick={() => setCurrentPage('agents')}>打开安装器</Button>
              </SettingRow>
            </>
          ) : null}

          {activeTab === 'about' ? (
            <>
              <SettingRow title="应用" desc="LOOM / 麓鸣演示稳定版。">
                <div className="space-y-2 text-sm text-text-muted">
                  <div><span className="font-black text-text">名称：</span>LOOM / 麓鸣</div>
                  <div><span className="font-black text-text">版本：</span>2.1.21</div>
                  <div><span className="font-black text-text">定位：</span>多智能体安装器与手机控制启动器</div>
                </div>
              </SettingRow>
              <SettingRow title="开放能力" desc="第一版演示只保留安装器、手机控制、模型账号和诊断。">
                <div className="flex flex-wrap gap-2 text-xs font-bold">
                  {['安装器', '手机控制', '模型账号', '诊断'].map((item) => (
                    <span key={item} className="rounded-full border border-[#0B4A3E]/20 bg-[#0B4A3E]/10 px-3 py-1.5 text-[#0B4A3E]">{item}</span>
                  ))}
                </div>
              </SettingRow>
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
};
