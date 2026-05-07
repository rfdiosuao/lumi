import React from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-shell';
import { Button, Loading, showToast } from '../common';
import { skillsApi, type SkillDirectory, type SkillItem, type SkillSite } from '../../services/api';
import { useLogStore } from '../../stores/logStore';

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'enabled', label: '已启用' },
  { key: 'disabled', label: '已关闭' },
  { key: 'uploaded', label: '上传安装' },
  { key: 'external', label: 'OpenClaw 扫描' },
];

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => resolve(String(event.target?.result || ''));
    reader.onerror = () => reject(reader.error || new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
}

function sourceFilter(skill: SkillItem, filter: string): boolean {
  if (filter === 'all') return true;
  if (filter === 'enabled') return skill.enabled;
  if (filter === 'disabled') return !skill.enabled;
  if (filter === 'uploaded') return skill.source === 'uploaded';
  if (filter === 'external') return skill.source !== 'uploaded';
  return true;
}

const SkillCard: React.FC<{
  skill: SkillItem;
  onToggle: (skill: SkillItem) => void;
  onOpenDir: (path: string) => void;
}> = ({ skill, onToggle, onOpenDir }) => (
  <div className="rounded-2xl border border-border bg-surface-alt/80 p-4 shadow-[0_18px_44px_rgba(0,0,0,0.08)]">
    <div className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-surface text-xs font-bold text-accent">
          {skill.icon || 'SK'}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-bold text-text">{skill.name}</h3>
            <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${
              skill.enabled
                ? 'border-status-success/30 bg-status-success/10 text-status-success'
                : 'border-border bg-surface text-text-muted'
            }`}>
              {skill.enabled ? '已启用' : '已关闭'}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-text-muted">
            {skill.description || '这个 Skill 没有提供描述。'}
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-text-subtle">
            <span>{skill.sourceLabel}</span>
            <span>v{skill.version}</span>
            <span>{skill.runtime}</span>
            <span>{skill.category}</span>
          </div>
        </div>
      </div>
      <Button onClick={() => onToggle(skill)} variant={skill.enabled ? 'danger' : 'success'} className="shrink-0">
        {skill.enabled ? '关闭' : '启用'}
      </Button>
    </div>
    <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-border bg-surface/65 px-3 py-2">
      <div className="min-w-0 truncate font-mono text-xs text-text-subtle">{skill.path}</div>
      <button onClick={() => onOpenDir(skill.path)} className="shrink-0 text-xs font-bold text-accent hover:underline">
        打开目录
      </button>
    </div>
  </div>
);

export const SkillsPage: React.FC = () => {
  const [skills, setSkills] = React.useState<SkillItem[]>([]);
  const [directories, setDirectories] = React.useState<SkillDirectory[]>([]);
  const [sites, setSites] = React.useState<SkillSite[]>([]);
  const [filter, setFilter] = React.useState('all');
  const [loading, setLoading] = React.useState(true);
  const [installing, setInstalling] = React.useState(false);
  const appendLog = useLogStore((state) => state.append);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const resp = await skillsApi.list();
      setSkills(resp.skills || []);
      setDirectories(resp.directories || []);
      setSites(resp.sites || []);
    } catch (error: any) {
      showToast(`扫描 Skills 失败：${error?.error || error}`, 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const handleUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip,application/zip,application/x-zip-compressed';
    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setInstalling(true);
      try {
        const data = await readFileAsDataUrl(file);
        const resp = await skillsApi.installZip(file.name, data);
        showToast(`Skill 已安装并启用：${resp.skill.name}`, 'success');
        appendLog(`[Skills] 已安装 ${resp.skill.name} (${resp.skill.id})\n`);
        await refresh();
      } catch (error: any) {
        showToast(`安装失败：${error?.error || error}`, 'error');
        appendLog(`[Skills] 安装失败: ${error?.error || error}\n`);
      } finally {
        setInstalling(false);
      }
    };
    input.click();
  };

  const handleToggle = async (skill: SkillItem) => {
    try {
      const nextEnabled = !skill.enabled;
      await skillsApi.setEnabled(skill.id, nextEnabled);
      setSkills((items) => items.map((item) => item.id === skill.id ? { ...item, enabled: nextEnabled } : item));
      showToast(`${skill.name} 已${nextEnabled ? '启用' : '关闭'}`, nextEnabled ? 'success' : 'info');
      appendLog(`[Skills] ${skill.name} ${nextEnabled ? 'enabled' : 'disabled'}\n`);
    } catch (error: any) {
      showToast(`操作失败：${error?.error || error}`, 'error');
    }
  };

  const handleOpenDir = async (path: string) => {
    try {
      await invoke('open_path', { path });
    } catch (error: any) {
      showToast(`打开目录失败：${error?.error || error}`, 'error');
    }
  };

  const handleOpenSkillsDir = () => {
    const writable = directories.find((item) => item.writable) || directories[0];
    if (writable?.path) {
      handleOpenDir(writable.path);
    }
  };

  const handleOpenSite = () => {
    const site = sites[0];
    if (!site?.url) {
      showToast('暂未配置 Skill 网站', 'info');
      return;
    }
    open(site.url);
  };

  const filteredSkills = skills.filter((skill) => sourceFilter(skill, filter));

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <div className="shrink-0 border-b border-border bg-surface px-8 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-text">Skills</h1>
            <p className="mt-1 text-sm text-text-muted">上传、扫描、启用和关闭 OpenClaw 能力模块</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleUpload} variant="primary" disabled={installing}>
              {installing ? '安装中...' : '上传 Skill 包'}
            </Button>
            <Button onClick={refresh} variant="default" disabled={loading}>扫描本地</Button>
            <Button onClick={handleOpenSkillsDir} variant="quiet">打开目录</Button>
            <Button onClick={handleOpenSite} variant="quiet">Skill 网站</Button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <div className="mb-5 flex flex-wrap gap-2">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              onClick={() => setFilter(item.key)}
              className={`rounded-full border px-3 py-1.5 text-xs font-bold transition-all ${
                filter === item.key
                  ? 'border-border-strong bg-accent text-white'
                  : 'border-border bg-surface-alt text-text-muted hover:bg-hover hover:text-text'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {loading ? (
          <Loading text="正在扫描 Skills..." />
        ) : filteredSkills.length > 0 ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {filteredSkills.map((skill) => (
              <SkillCard key={`${skill.source}-${skill.id}`} skill={skill} onToggle={handleToggle} onOpenDir={handleOpenDir} />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-border bg-surface-alt/80 px-6 py-16 text-center">
            <div className="text-base font-bold text-text">还没有识别到 Skill</div>
            <p className="mt-2 text-sm text-text-muted">上传 zip 包，或把 Skill 文件夹放进本地 Skills 目录后重新扫描。</p>
            <div className="mt-5 flex justify-center gap-3">
              <Button onClick={handleUpload} variant="primary">上传 Skill 包</Button>
              <Button onClick={handleOpenSite} variant="quiet">打开 Skill 网站</Button>
            </div>
          </div>
        )}

        <div className="mt-6 rounded-2xl border border-border bg-surface-alt/65 p-4">
          <div className="mb-3 text-sm font-bold text-text">扫描目录</div>
          <div className="space-y-2">
            {directories.map((directory) => (
              <div key={directory.key} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface/60 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-text">{directory.label}</div>
                  <div className="truncate font-mono text-xs text-text-subtle">{directory.path}</div>
                </div>
                <button onClick={() => handleOpenDir(directory.path)} className="shrink-0 text-xs font-bold text-accent hover:underline">
                  打开
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
