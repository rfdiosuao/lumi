import React from 'react';
import { FolderOpen, RefreshCcw, Search, Upload, X } from 'lucide-react';
import { Button, Chip, EmptyState, InlineState, Modal, Panel, SectionHeader } from '../components/ui';
import { installSkillZip, loadSkillsSnapshot, readSkillReadme, toggleSkill, uninstallSkill } from '../api/adapters';
import { useAsync } from '../lib/useAsync';
import { usePreviewStore } from '../store/appStore';

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
}

export function SkillsPage() {
  const settings = usePreviewStore((state) => state.settings);
  const pushToast = usePreviewStore((state) => state.pushToast);
  const { data, loading, error, refresh } = useAsync(() => loadSkillsSnapshot(settings), [settings], { cacheKey: "skills" });
  const [query, setQuery] = React.useState('');
  const [readme, setReadme] = React.useState<{ title: string; path: string; content: string } | null>(null);
  const [busyId, setBusyId] = React.useState('');
  const filtered = (data?.skills || []).filter((skill) => {
    const text = `${skill.name} ${skill.description} ${skill.category} ${skill.runtime}`.toLowerCase();
    return text.includes(query.toLowerCase());
  });

  const handleUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip,application/zip,application/x-zip-compressed';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      setBusyId('upload');
      try {
        const dataUrl = await readAsDataUrl(file);
        await installSkillZip(settings, file.name, dataUrl);
        pushToast({ tone: 'ok', title: 'Skill 已安装', detail: file.name });
        refresh();
      } catch (err) {
        pushToast({ tone: 'danger', title: '安装失败', detail: String(err) });
      } finally {
        setBusyId('');
      }
    };
    input.click();
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    setBusyId(id);
    try {
      await toggleSkill(settings, id, enabled);
      pushToast({ tone: 'warn', title: enabled ? 'Skill 已启用' : 'Skill 已停用', detail: id });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '切换失败', detail: String(err) });
    } finally {
      setBusyId('');
    }
  };

  const handleReadme = async (id: string, title: string) => {
    setBusyId(id);
    try {
      const response = await readSkillReadme(settings, id);
      setReadme({ title, path: response.data?.path || '', content: response.data?.content || '' });
    } catch (err) {
      pushToast({ tone: 'danger', title: 'README 读取失败', detail: String(err) });
    } finally {
      setBusyId('');
    }
  };

  const handleRemove = async (id: string) => {
    setBusyId(id);
    try {
      await uninstallSkill(settings, id);
      pushToast({ tone: 'warn', title: 'Skill 已移除', detail: id });
      refresh();
    } catch (err) {
      pushToast({ tone: 'danger', title: '移除失败', detail: String(err) });
    } finally {
      setBusyId('');
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-band">
        <div className="hero-copy">
          <div className="eyebrow">Skills 工作区</div>
          <h1>管理 OpenClaw 可以调用的能力模块。</h1>
          <p>安装、启用、查看说明或移除本地模块；每个操作都靠近对应 Skill。</p>
        </div>
        <div className="hero-actions">
          <Button variant="primary" icon={Upload} onClick={handleUpload} disabled={busyId === 'upload'}>安装 ZIP</Button>
          <Button variant="quiet" icon={RefreshCcw} onClick={refresh}>刷新</Button>
        </div>
      </section>

      <section className="content-grid content-grid-skills">
        <Panel className="surface-panel surface-panel-narrow">
          <SectionHeader eyebrow="筛选" title="查找模块" subtitle="搜索本地 Skills 工作区。" />
          <div className="search-row">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 Skill、运行时或分类" />
          </div>
          <div className="detail-stack">
            <div className="detail-row"><span className="detail-label">状态文件</span><span className="detail-value">{data?.statePath || '暂无'}</span></div>
            <div className="detail-row"><span className="detail-label">目录</span><span className="detail-value">{data?.directories.length || 0}</span></div>
            <div className="detail-row"><span className="detail-label">站点</span><span className="detail-value">{data?.sites.length || 0}</span></div>
          </div>
          <div className="path-list">
            {data?.directories.map((dir) => (
              <div key={dir.key} className="path-card">
                <strong>{dir.label}</strong>
                <span>{dir.path}</span>
                <Chip tone={dir.writable ? 'ok' : 'warn'}>{dir.writable ? '可写' : '只读'}</Chip>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="surface-panel">
          <SectionHeader eyebrow="已安装" title="可用 Skills" subtitle="启用、查看和移除操作直接放在每条记录旁边。" action={<Chip tone={data?.source === 'live' ? 'ok' : 'warn'}>{sourceLabel(data?.source || 'mock')}</Chip>} />
          {loading ? (
            <div className="panel-loading-inline">正在读取 Skills...</div>
          ) : error ? (
            <InlineState tone="danger" title="Skills 读取失败" description={error} />
          ) : filtered.length ? (
            <div className="skill-list">
              {filtered.map((skill) => (
                <div key={skill.id} className="skill-row">
                  <div className="skill-badge">{skill.icon}</div>
                  <div className="skill-copy">
                    <div className="skill-head">
                      <strong>{skill.name}</strong>
                      <Chip tone={skill.enabled ? 'ok' : 'warn'}>{skill.enabled ? '已启用' : '已停用'}</Chip>
                    </div>
                    <div className="skill-meta">{skill.description}</div>
                    <div className="skill-meta">{skill.category} · {skill.runtime} · {skill.version}</div>
                    <div className="skill-meta">{skill.path}</div>
                  </div>
                  <div className="skill-actions">
                    <Button variant={skill.enabled ? 'danger' : 'success'} onClick={() => handleToggle(skill.id, !skill.enabled)} disabled={busyId === skill.id}>
                      {skill.enabled ? '停用' : '启用'}
                    </Button>
                    {skill.hasReadme ? <Button variant="quiet" onClick={() => handleReadme(skill.id, skill.name)} disabled={busyId === skill.id}>说明</Button> : null}
                    {skill.writable ? <Button variant="quiet" onClick={() => handleRemove(skill.id)} disabled={busyId === skill.id}>移除</Button> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="暂无 Skills" description="安装一个 ZIP 后会出现在这里。" />
          )}
        </Panel>
      </section>

      <Panel className="surface-panel">
        <SectionHeader eyebrow="外部地址" title="Skill 站点" subtitle="外部地址直接展示，避免藏在弹窗里。" />
        <div className="site-grid">
          {data?.sites.map((site) => (
            <div key={site.url} className="site-card">
              <strong>{site.name}</strong>
              <span>{site.url}</span>
              <Button variant="quiet" icon={FolderOpen} onClick={() => window.open(site.url, '_blank', 'noopener,noreferrer')}>打开</Button>
            </div>
          ))}
        </div>
      </Panel>

      <Modal open={Boolean(readme)} title={readme?.title || '说明'} subtitle={readme?.path || ''} onClose={() => setReadme(null)} actions={<Button variant="secondary" onClick={() => setReadme(null)} icon={X}>关闭</Button>}>
        {readme ? <pre className="modal-pre">{readme.content}</pre> : null}
      </Modal>
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
