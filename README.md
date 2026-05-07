# Lumi / OpenClaw 便携启动器

Lumi 是面向商家交付的 OpenClaw 便携式 AI 服务启动器。项目目标是把 OpenClaw 本体、离线依赖、授权激活、AI 生图、AI 视频、广告视频工作台和机器人绑定能力封装成一个客户可直接运行的桌面工具。

当前主力版本：`v2.0.1`

## 当前状态

- Windows 便携包：已支持根目录仅保留 `OpenClaw.exe` 和 `OpenClawFiles/`。
- 授权码：支持在线激活，核心授权校验已迁移到 Rust 二进制，交付包不内置授权文件。
- 环境诊断：未授权也可进入，可一键修复端口占用、残留进程和基础目录。
- AI 生图 / AI 视频：支持 API 配置后调用。
- 广告视频工作台：支持分镜、素材、九宫格和首尾帧工作流。
- 飞书 / 微信机器人：支持离线插件包检测、安装和扫码/手动配置入口。
- Skills：支持本地 Skill 包管理、启用/停用和 Skill 网站跳转。
- 品牌换壳：支持通过主题文件替换 Logo、名称、窗口标题和主题颜色。
- Mac 迁移：已提供源码包和迁移文档，仍需在真实 Mac 环境完成 `.app/.dmg` 验收。

## 目录结构

```text
.
├─ openclaw_new_launcher/      # 新版 Tauri + React + Python Bridge 启动器
├─ license_server/             # 在线授权码服务器
├─ scripts/                    # 本地检查、打包、发布脚本
├─ docs/                       # 项目级文档
├─ release/                    # 本地构建产物，不提交到仓库
└─ openclaw_launcher/          # 旧版 Python 启动器，仅作历史参考
```

## 快速开始

开发环境建议：

- Windows 10/11
- Node.js 20+
- Rust stable
- Python 3.11+
- npm

安装和构建：

```powershell
cd openclaw_new_launcher
npm ci
npm run build
npm run tauri dev
```

完整检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1
```

轻量检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1 -SkipFrontend -SkipRust
```

## Windows 便携包打包

使用最新可用的便携包作为种子目录：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1 -Version 2.0.1 -PackageName OpenClaw-Portable-v2.0.1-YYYY.MM.DD
```

打包脚本会执行：

- 清理源码缓存
- 检查源码文本
- 构建 Tauri 应用
- 复制 OpenClaw 离线依赖
- 清空授权文件、安装 ID 和 API Key
- 安装/校验飞书与微信插件
- 整理便携包目录为 `OpenClaw.exe + OpenClawFiles/`
- 校验 zip 包和生成 SHA256

交付前必须确认：

- 不存在 `data/license.json`
- 不存在 `data/install_id.txt`
- `imgapi_config.json` 和 `video_config.json` 为空配置
- 根目录只保留 `OpenClaw.exe` 和 `OpenClawFiles/`

## Mac 迁移

Mac 源码迁移文档：

- `openclaw_new_launcher/docs/MAC_BUILD_NOTES.md`
- `openclaw_new_launcher/docs/MAC_MIGRATION_CHECKLIST.md`
- `openclaw_new_launcher/docs/RUNTIME_PATHS.md`

Mac 上建议先跑开发版：

```bash
cd openclaw_new_launcher
npm ci
npm run build
npm run tauri dev
```

开发版跑通后再打包：

```bash
npm run tauri build -- --bundles app,dmg
```

注意：Mac 不能复用 Windows 的 `node_modules`、`src-tauri/target`、Windows Node runtime 或 `.exe` 文件。

## 品牌换壳与二开

如果要更换 Logo、名称、窗口标题、主题颜色并重新打包，请先看：

- `docs/BRANDING_AND_PACKAGING.md`：更换 Logo、名称并重新打包
- `docs/BRAND_THEME.md`：主题文件结构说明

常用品牌文件：

```text
openclaw_new_launcher/data/themes/default/theme.json
openclaw_new_launcher/data/themes/default/logo.png
openclaw_new_launcher/src-tauri/icons/
openclaw_new_launcher/index.html
openclaw_new_launcher/src-tauri/tauri.conf.json
```

注意：只改主题文件不会改变 Windows 文件图标；只改 Tauri 图标也不会改变启动器内部 Logo。

## 重要文档

- `openclaw_new_launcher/docs/DOCS_INDEX.md`：当前文档入口和历史文档状态说明
- `openclaw_new_launcher/docs/BRIDGE_MIGRATION_GUARD.md`：Bridge 冒烟检查与 FastAPI 迁移护栏
- `docs/BRANDING_AND_PACKAGING.md`：更换 Logo、名称并重新打包
- `docs/BRAND_THEME.md`：主题 / 品牌配置说明
- `openclaw_new_launcher/docs/UI_CUSTOMIZATION_DESIGN.md`：UI 自定义与模块化设计方案
- `openclaw_new_launcher/docs/AD_VIDEO_WORKBENCH_GUIDE.md`：AI 广告工作台使用文档
- `openclaw_new_launcher/docs/RUNTIME_PATHS.md`：Windows / Mac 运行时路径规范
- `openclaw_new_launcher/docs/MAC_BUILD_NOTES.md`：Mac 编译注意事项
- `openclaw_new_launcher/docs/MAC_MIGRATION_CHECKLIST.md`：Mac 迁移验收清单
- `openclaw_new_launcher/docs/PRODUCT_ROADMAP.md`：产品路线规划
- `openclaw_new_launcher/docs/MODULE_EXTENSION_GUIDE.md`：模块扩展与二开说明
- `openclaw_new_launcher/docs/GITEE_SETUP.md`：Gitee 配置说明
- `openclaw_new_launcher/docs/GIT_CICD_PLAN.md`：CI/CD 规划

## 安全与交付规则

禁止提交或打入交付包：

- 授权服务器私钥、后台 token、数据库文件
- `data/license.json`
- `data/install_id.txt`
- 客户 API Key
- 客户扫码后的微信 / 飞书账号缓存
- `node_modules/`
- `dist/`
- `src-tauri/target/`
- `release/`

## 当前优先级

1. 保持 Windows 便携包稳定可交付。
2. 完成环境诊断和一键修复闭环。
3. 继续稳定飞书 / 微信绑定流程。
4. 让广告视频工作台按创作者流程继续打磨。
5. 在 Mac 真机跑通 `.app/.dmg` 构建和验收。

## 维护说明

每次准备交付前，至少执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-source-text.ps1 -NoGit
powershell -ExecutionPolicy Bypass -File scripts\smoke-bridge.ps1
cd openclaw_new_launcher
npm run build
```

打包后再执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-release.ps1 -Path release\你的包名.zip
```
