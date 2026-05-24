# OpenClaw / Lumi 交接文档
> 更新时间：2026-05-21
> 作用：给下一位接手者快速定位当前状态、已完成事项、产物路径、已知问题和下一步。

## 1. 当前定位

- 主工作区：`D:\Axiangmu\AUSTART`
- 主启动器：`D:\Axiangmu\AUSTART\openclaw_new_launcher`
- 授权服务：`D:\Axiangmu\AUSTART\license_server`
- 旧的 `openclaw_launcher/` Tkinter 线已废弃，不要再回头做这条线
- 不要把 `D:\Axiangmu\U盘启动器` 当成主工作区，它只是当前会话的外层目录

## 2. 当前已完成

### 启动器侧

- 已继续推进 `OpenClaw / Lumi` 新启动器主线
- 已打通授权页、会员模式、AI 生图、AI 视频、分镜页、手机控制、桌面控制等主流程
- 已把授权成功后的展示补成“授权码后八位”
- 已把生图 / 视频的 `gatewayMode` 兼容成 `member / manual`
- 已加了会员网关默认值读取逻辑，避免空配置时直接卡死

### 授权服务侧

- 已推进 SaaS 风格授权后台
- 已支持月卡套餐、网关配置、操作审计、授权编辑等方向
- 已生成可部署的服务端包

### 打包产物

- 启动器包：`D:\Axiangmu\AUSTART\release\OpenClaw-Portable-v2.0.6-2026.05.21-code8.zip`
- 启动器 SHA256：`D8A125E6B278C83DBD799294D37B169443E33F44927EE7F15B7ECCF1E04820F8`
- 服务端包：`D:\Axiangmu\AUSTART\release\openclaw-license-server-v2026.05.21.zip`
- 服务端 SHA256：`A19711E710595DCF08F2AA24822196BC9D5BD92EBD83A100C1966A6B5C61AA7C`

## 3. 当前主代码入口

### 前端

- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\App.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\features\registry.ts`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\features\pages.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\license\LicensePage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\image\ImagePage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\video\VideoPage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\storyboard\StoryboardPage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\dialogs\ApiConfigDialog.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\services\gatewayConfig.ts`

### Python / Bridge

- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\bridge.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\core\license_manager.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\core\paths.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\services\image_api.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\services\process.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\api\fastapi_routes.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\api\routes_media.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\api\routes_member.py`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\python\api\routes_desktop_agent.py`

### Rust / Tauri

- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src-tauri\src\lib.rs`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src-tauri\src\license.rs`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src-tauri\tauri.conf.json`

### 授权服务

- `D:\Axiangmu\AUSTART\license_server\server.py`
- `D:\Axiangmu\AUSTART\license_server\admin_console.html`
- `D:\Axiangmu\AUSTART\license_server\deploy_member_update.py`
- `D:\Axiangmu\AUSTART\license_server\openclaw-license.service`

## 4. 当前最要紧的问题

### 4.1 网站 / 启动器里出现大量问号

这是当前最明显的高优先级问题，不是浏览器渲染问题，源码里已经有大量 `????` 和编码损坏内容。

已确认的坏点：

- `D:\Axiangmu\AUSTART\license_server\admin_console.html`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\features\registry.ts`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\image\ImagePage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\video\VideoPage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\dashboard\DashboardPage.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\dialogs\ApiConfigDialog.tsx`
- `D:\Axiangmu\AUSTART\openclaw_new_launcher\docs\task.md`

典型现象：

- 按钮文案直接显示 `????`
- 授权后台页面报 `Cannot set properties of null (setting 'innerHTML')`
- 部分页面 DOM id 也有脏字符，导致脚本找不到元素

处理建议：

1. 先统一把相关文件重存为正常 UTF-8
2. 替换所有占位 `????`
3. 校正 admin 页 DOM id 和脚本绑定
4. 再跑一次前端 build 和服务端 smoke

### 4.2 API Key 需要收口到统一设置页

目前生图、视频、分镜页各自都有 API 配置入口，后续应该合并成一个独立设置页：

- 统一管理 `baseUrl / apiKey / model`
- 统一管理 `member / manual` 模式
- 预留“激活会员链接”位置，后面再接真实地址

### 4.3 授权后台需要继续 SaaS 化

当前后台已经有方向，但还不算完整生产级：

- 会员套餐可配置
- 网关配置可配置
- 生图模型可配置
- 视频模型可配置
- 操作审计要更清楚
- 文档入口要更直观

## 5. 当前已知技术债

### P0

- UI 文案和编码损坏导致的问号
- 授权后台页面部分模块渲染失败
- 设置入口分散，API 配置不够集中

### P1

- 授权后台 SaaS 化还没做完
- 会员套餐、网关、审计、文档还要补齐
- 桌面控制 / SightFlow 集成还在演进
- 打包前的自动校验还可以再收紧

### P2

- 文档里还有历史遗留的乱码和旧说明，需要持续清理
- 需要把 release / smoke / 验证流程再固化一层

## 6. 当前建议顺序

1. 先修 `????` 和编码损坏
2. 再把 API Key 和网关配置收口到一个设置页
3. 再补会员激活链接预留位
4. 再继续完善授权后台 SaaS 能力
5. 最后再继续做 GitHub Release 和生产包验证

## 7. 常用命令

### 启动器

```powershell
cd D:\Axiangmu\AUSTART\openclaw_new_launcher
npm run build
```

### Rust 检查

```powershell
cd D:\Axiangmu\AUSTART\openclaw_new_launcher\src-tauri
cargo check
```

### Python 语法检查

```powershell
python -m py_compile D:\Axiangmu\AUSTART\license_server\server.py D:\Axiangmu\AUSTART\openclaw_new_launcher\python\core\license_manager.py
```

### 打包

```powershell
cd D:\Axiangmu\AUSTART
powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1 -PackageName "OpenClaw-Portable-v2.0.6-2026.05.21-code8"
```

### 服务端部署

```powershell
python D:\Axiangmu\AUSTART\license_server\deploy_member_update.py
```

## 8. 交接提醒

- 当前工作区是脏的，里面有很多历史实验文件和临时脚本，别无脑清理、别回滚用户改动
- 不要把 `release/`、`dist/`、`target/`、`license.db`、`private_key.b64` 当成需要提交的内容
- 后续如果继续做后台和设置页，优先以“可维护、可配置、可部署”为目标，不要再把逻辑拆散到多个页面里
