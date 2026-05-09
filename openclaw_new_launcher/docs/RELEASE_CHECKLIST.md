# 交付检查清单

本文档用于每次给客户交付离线包前自检。目标是避免缺运行时、混入本机授权、混入密钥、端口冲突处理回退等问题。

## 一、打包前

- 确认代码已提交到 Gitee，工作区没有未确认改动。
- 清理源码缓存和构建产物：

```powershell
powershell -ExecutionPolicy Bypass -File D:\Axiangmu\AUSTART\scripts\clean-workspace.ps1
```

- 本机执行基础检查：

```powershell
powershell -ExecutionPolicy Bypass -File D:\Axiangmu\AUSTART\scripts\ci-check.ps1
```

- 确认本次目标品牌 profile：
  - `lumi`：Lumi 私人版 / 内部演示版。
  - `customer`：客户交付版，默认使用 `yonghao_tech` 主题。
  - 自定义 profile：必须存在 `openclaw_new_launcher/data/themes/<profile>/theme.json`。

- 生成正式离线包：

```powershell
powershell -ExecutionPolicy Bypass -File D:\Axiangmu\AUSTART\scripts\build-portable.ps1 -BrandProfile customer
```

- 不要把以下文件提交进仓库：
  - `release/`
  - `node_modules/`
  - `dist/`
  - `target/`
  - `license_server/private_key.b64`
  - `license_server/license.db`
  - `license_server/admin_token.txt`
  - `data/license.json`
  - `data/install_id.txt`
  - `*.zip`

## 二、打包后

- 对离线包执行交付校验：

```powershell
$zip = Get-ChildItem D:\Axiangmu\AUSTART\release\OpenClaw-Portable-v*.zip | Sort-Object LastWriteTime -Descending | Select-Object -First 1
powershell -ExecutionPolicy Bypass -File D:\Axiangmu\AUSTART\scripts\verify-release.ps1 -Path $zip.FullName
```

- 生成 SHA256，作为交付记录：

```powershell
$zip = Get-ChildItem D:\Axiangmu\AUSTART\release\OpenClaw-Portable-v*.zip | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-FileHash -Algorithm SHA256 $zip.FullName
```

- 离线包至少应包含：
  - `OpenClaw.exe`
  - `node/node.exe`
  - `node_modules/openclaw/openclaw.mjs`
  - `start.js`
  - `_up_/python-runtime/python.exe`
  - `_up_/python/bridge.py`
  - `data/.openclaw/openclaw.json`
  - `data/brand_profile.json`
  - `data/themes/<brand_profile.themeId>/theme.json`

## 三、手动验收

- 在一个全新目录解压离线包，不依赖源码目录启动。
- 启动后进入授权页，未授权时应阻止启动 OpenClaw 服务。
- 输入有效授权码后，授权状态应保持，重启后仍然有效。
- 点击“启动服务”，日志中应出现 OpenClaw 网关启动信息。
- 打开网页界面，应该能进入 OpenClaw 控制台，不再要求额外 token。
- 配置 API 后重启应用，API 地址和密钥仍应保持。
- AI 生图、AI 视频页面能读取配置并开始任务。
- 核对应用内品牌、窗口标题、Logo 是否符合本次 `BrandProfile`。

## 四、交付记录

每次交付至少记录：

- 交付日期
- 包文件名
- SHA256
- Git commit
- 客户授权码批次
- 已知问题和临时处理方式
