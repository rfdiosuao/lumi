import React, { useState } from 'react';
import { Button, Input, showToast } from '../common';
import { licenseApi } from '../../services/api';
import { useAppStore } from '../../stores/appStore';
import { useLogStore } from '../../stores/logStore';

export const LicensePage: React.FC = () => {
  const [code, setCode] = useState('');
  const [activating, setActivating] = useState(false);
  const [statusText, setStatusText] = useState('');
  const { isAuthorized, licenseInfo, setAuthorized, setLicenseInfo, setCurrentPage } = useAppStore();
  const appendLog = useLogStore((s) => s.append);

  const handleActivate = async () => {
    if (!code.trim()) {
      showToast('请输入授权码', 'error');
      return;
    }
    setActivating(true);
    setStatusText('正在连接授权服务器...');
    try {
      const resp = await licenseApi.activate(code);
      const license = resp.license;
      if (!license || typeof license !== 'object') {
        setStatusText('激活失败：服务器返回无效的许可证');
        showToast('激活失败', 'error');
        return;
      }
      setLicenseInfo(license as any);
      setAuthorized(true);
      if (typeof (window as any).__reloadTheme === 'function') {
        await (window as any).__reloadTheme();
      }
      setStatusText(`激活成功：${(license as any).licensee || '客户'}`);
      appendLog(`[授权] 激活成功：${(license as any).licensee}\n`);
      showToast('激活成功，主题已更新', 'success');
      setTimeout(() => setCurrentPage('terminal'), 1500);
    } catch (e: any) {
      setStatusText(e?.error || '激活失败');
      showToast('激活失败', 'error');
    } finally {
      setActivating(false);
    }
  };

  const handleRefresh = async () => {
    try {
      const resp = await licenseApi.current();
      if (resp.license) {
        setLicenseInfo(resp.license as any);
        setAuthorized(true);
      } else {
        setLicenseInfo(null);
        setAuthorized(false);
      }
    } catch {
      // ignore
    }
  };

  const features = licenseInfo?.features?.join(' / ') || '';

  return (
    <div className="flex flex-col h-full bg-surface overflow-y-auto">
      <div className="flex-shrink-0 px-8 py-6 border-b border-border bg-surface">
        <h1 className="text-xl font-semibold text-text">授权管理</h1>
        <p className="text-sm text-text-muted mt-1">输入授权码后解锁启动服务、AI 生图、AI 视频和广告视频工作台。</p>
      </div>

      <div className="flex-1 px-8 py-6">
        <div className="max-w-xl">
          {/* Status Card */}
          <div className="bg-surface-alt rounded-lg border border-border p-6 mb-6">
            <div className={`text-sm font-medium mb-3 ${isAuthorized ? 'text-status-success' : 'text-status-danger'}`}>
              {isAuthorized ? '已授权' : '未授权'}
            </div>

            {isAuthorized && licenseInfo && (
              <div className="text-sm text-text-muted space-y-1 mb-4">
                <p>客户：{licenseInfo.licensee || '未命名'}</p>
                <p>版本：{licenseInfo.edition || 'pro'}</p>
                <p>到期：{licenseInfo.expires || '永久'}</p>
                <p>功能：{features}</p>
              </div>
            )}

            {/* Code Input */}
            <label className="text-sm text-text-muted mb-2 block">授权码</label>
            <div className={`border-2 rounded-md transition-colors ${statusText === '' ? 'border-accent' : 'border-accent'} focus-within:border-amber-500`}>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="OC-PRO-XXXX-XXXX-XXXX-XXXX"
                className="border-0 bg-transparent focus:ring-0 text-base py-3 px-4 font-mono"
              />
            </div>
            <p className="text-xs text-accent-ink mt-1 mb-4">格式示例：OC-PRO-XXXX-XXXX-XXXX-XXXX</p>

            {/* Actions */}
            <div className="flex items-center gap-3 mb-4">
              <Button
                onClick={handleActivate}
                variant="primary"
                disabled={activating}
              >
                {activating ? '激活中...' : isAuthorized ? '重新激活' : '在线激活'}
              </Button>
              <Button onClick={handleRefresh} variant="quiet">
                刷新状态
              </Button>
              <Button onClick={() => setCurrentPage('diagnostics')} variant="quiet">
                环境诊断
              </Button>
            </div>

            {/* Status Text */}
            {statusText && (
              <p className={`text-sm ${
                statusText.includes('成功') ? 'text-status-success' :
                statusText.includes('连接') ? 'text-accent' :
                'text-status-danger'
              }`}>
                {statusText}
              </p>
            )}
          </div>

          {/* Install ID */}
          <p className="text-xs text-text-muted">安装 ID 将在激活时自动生成</p>
        </div>
      </div>
    </div>
  );
};
