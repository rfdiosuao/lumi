# 新会话对接文档

> 更新时间：2026-05-09
> 目的：给新的 Codex/GPT 会话快速接手当前项目，避免重复踩旧坑。  
> 注意：本文不包含服务器密码、API Key、授权码等敏感信息。

## 1. 当前项目定位

这个仓库是 `Lumi / OpenClaw` 便携式桌面启动器项目。

当前主线不是旧版 Tkinter 启动器，而是：

```text
D:\Axiangmu\AUSTART\openclaw_new_launcher
```

当前仓库根目录是：

```text
D:\Axiangmu\AUSTART
```

不要把 `D:\Axiangmu\U盘启动器` 当成主工作区，除非用户明确说那是某个测试包路径。

核心目标：

- 封装 OpenClaw 本体和离线依赖，做成客户可直接运行的 Windows 便携包。
- 支持授权码激活、U盘绑定、AI 生图、AI 视频、广告视频工作台、飞书/微信机器人绑定、Skills。
- 后续往 Lumi 个人版、多 Agent 工作台、CLI、Skill 平台方向演进。

## 2. 当前仓库结构

```text
D:\Axiangmu\AUSTART
├─ openclaw_new_launcher/      # 当前主力启动器：Tauri + React + Python Bridge
├─ license_server/             # 在线授权服务器
├─ scripts/                    # 检查、打包、发布脚本
├─ docs/                       # 项目级文档
├─ release/                    # 本地构建产物，已被 .gitignore 忽略
└─ README.md
```

旧版 `openclaw_launcher/` 已经删除。不要再恢复它，也不要再围绕旧 Tkinter 架构做分析。

## 3. 最近刚完成的清理

已删除：

- `openclaw_launcher/`
- `launcher.py`
- `OpenClaw.spec`
- `OpenClaw-USB.spec`
- `clean_portable_package.ps1`
- `DEVELOPMENT.md`
- `项目二次开发说明.md`
- `logo_square.ico`
- `openclaw_new_launcher/api.md`
- `openclaw_new_launcher/REWRITE_SPEC.md`
- `openclaw_new_launcher/重构文档.md`
- 旧的 API / 架构 / Agent 任务文档：
  - `openclaw_new_launcher/docs/AGENT_TASKS.md`
  - `openclaw_new_launcher/docs/API_SPEC.md`
  - `openclaw_new_launcher/docs/api-reference.md`
  - `openclaw_new_launcher/docs/ARCHITECTURE.md`
  - `openclaw_new_launcher/docs/ARCHITECTURE_REVIEW_2026-05-05.md`
  - `openclaw_new_launcher/docs/server_patched.py`
  - `openclaw_new_launcher/docs/license-server-merchant-patch.py`

已更新：

- `README.md`
- `README.en.md`
- `openclaw_new_launcher/docs/DOCS_INDEX.md`

已清理构建缓存：

- `openclaw_new_launcher/dist`
- `openclaw_new_launcher/src-tauri/target`
- `openclaw_new_launcher/src-tauri/target2`
- Python `__pycache__`

## 4. 最近重要修复

### U盘授权一致性

用户说国产模型已经修过“U盘拔插后重新授权”的问题。随后检查发现一个现役一致性问题：

- Python 激活端：已经使用 U盘卷序列号生成 `deviceId`。
- Rust 启动前校验端：之前还在使用 `盘符 + 卷序列号`。

已修复：

```text
openclaw_new_launcher/src-tauri/src/license.rs
```

现在 Rust 使用和 Python 一致的 `volume:{serial}|openclaw-launcher` 逻辑，并保留旧格式兼容。

验证过：

```powershell
cargo check
python -m py_compile openclaw_new_launcher\python\core\license_manager.py
powershell -ExecutionPolicy Bypass -File scripts\verify-source-text.ps1
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1 -SkipRust
```

以上都通过。

注意：还没有重新打包，也没有做真实 U盘拔插验收。后续交付前必须测：

- 同一 U盘激活后拔插，授权仍有效。
- 同一 U盘换盘符，授权仍有效。
- 复制到另一块 U盘，不能直接继承授权。
- 交付包内不包含 `data/license.json` 和 `data/install_id.txt`。

## 5. 2026-05-09 已同步状态

当前主线已收束并推送到 GitHub `master`。本地继续开发前仍要先看 `git status --short`，但上一轮混在一起的 P1 改动已经拆分提交。

最新 GitHub Release:

```text
https://github.com/rfdiosuao/lumi/releases/tag/v2.0.2-github-2026.05.09
```

最近关键提交：

1. `238345e chore: sync vite optional runtime deps`
2. `9f25376 chore: upgrade frontend build dependencies`
3. `de5f3c9 refactor: retire legacy bridge routing`
4. `2d9def0 chore: add brand profile release checks`
5. `17d4149 feat: add launcher storage diagnostics`

已验证：

- 本地完整 `scripts\ci-check.ps1` 通过。
- 本地 `scripts\smoke-bridge.ps1` 和 `scripts\smoke-bridge.ps1 -RequireFastApi` 通过。
- GitHub CI run `25601441504` 通过。
- GitHub Release run `25601531758` 通过，并生成 exe/msi 安装产物。

## 6. 当前有效文档入口

优先看：

```text
openclaw_new_launcher/docs/DOCS_INDEX.md
openclaw_new_launcher/docs/BRIDGE_MIGRATION_GUARD.md
openclaw_new_launcher/docs/RUNTIME_PATHS.md
openclaw_new_launcher/docs/RELEASE_CHECKLIST.md
openclaw_new_launcher/docs/UI_CUSTOMIZATION_DESIGN.md
openclaw_new_launcher/docs/MODULE_EXTENSION_GUIDE.md
openclaw_new_launcher/docs/MODULE_BOUNDARIES.md
openclaw_new_launcher/docs/PRODUCT_ROADMAP.md
openclaw_new_launcher/docs/LUMI_AGENT_PLATFORM_ROADMAP.md
openclaw_new_launcher/docs/LUMI_PERSONAL_UI_DESIGN.md
openclaw_new_launcher/docs/广告视频使用文档.md
```

旧 `API_SPEC.md`、旧 `api-reference.md`、旧 `ARCHITECTURE.md` 已删除，不要再依赖。

## 7. 当前代码主线

### 前端

```text
openclaw_new_launcher/src/App.tsx
openclaw_new_launcher/src/features/registry.ts
openclaw_new_launcher/src/features/pages.tsx
openclaw_new_launcher/src/components/common/index.tsx
openclaw_new_launcher/src/components/sidebar/Sidebar.tsx
openclaw_new_launcher/src/components/terminal/TerminalPage.tsx
openclaw_new_launcher/src/components/window/WindowTitlebar.tsx
openclaw_new_launcher/src/components/license/LicensePage.tsx
openclaw_new_launcher/src/components/image/ImagePage.tsx
openclaw_new_launcher/src/components/video/VideoPage.tsx
openclaw_new_launcher/src/components/storyboard/StoryboardPage.tsx
openclaw_new_launcher/src/components/skills/SkillsPage.tsx
```

### API 调用

```text
openclaw_new_launcher/src/services/api.ts
openclaw_new_launcher/src/stores/appStore.ts
openclaw_new_launcher/src/stores/logStore.ts
```

### Python Bridge

```text
openclaw_new_launcher/python/bridge.py
openclaw_new_launcher/python/api/*.py
openclaw_new_launcher/python/core/*.py
openclaw_new_launcher/python/services/*.py
```

FastAPI 已成为主实现，旧 Handler 的完整 API 路由实现已移除。`bridge.py` 现在只保留启动入口、共享上下文和 FastAPI 缺依赖时的 dependency-error 503 服务。

### Rust / Tauri

```text
openclaw_new_launcher/src-tauri/src/lib.rs
openclaw_new_launcher/src-tauri/src/license.rs
openclaw_new_launcher/src-tauri/tauri.conf.json
```

Rust 负责：

- 启动 Python Bridge。
- 转发请求。
- 启动前授权校验。
- 保护关键接口：启动 OpenClaw、AI 生图、AI 视频。

## 8. 当前真实技术债

按优先级排序：

### P0：交付前必须处理或确认

1. `v2.0.2-github-2026.05.09` 的 exe/msi 需要在真实机器上安装、启动、卸载验收。
2. U盘授权修复仍需要真实拔插测试。
3. 客户交付前必须确认不带授权文件、安装 ID、API Key、用户机器人缓存。
4. 客户版 portable zip 仍需按目标 `BrandProfile` 跑 `verify-release.ps1`。

### P1：当前架构债

已完成：

1. Bridge `_meta` 返回契约已落地。
2. `bridge.py` 旧 Handler API 路由已退场，主路由走 FastAPI native routes。
3. 品牌 profile 已接入打包脚本和 release 校验。
4. Vite / npm audit / GitHub Node 22 CI 已收束。
5. 存储诊断已覆盖运行磁盘/U盘读写和 `openclaw.json` 基础修复。

仍待处理：

1. 授权激活仍在 Python，Rust 只负责启动前校验。以后可以把激活也搬到 Rust，或至少统一安全边界。
2. Feishu / WeChat 插件绑定逻辑偏脚本驱动，需要状态机化。
3. Skills 有基础功能，但 manifest、版本兼容、签名校验还没产品化。
4. GitHub Release 已能出 Tauri installer/msi；本地 portable zip 仍需针对客户 profile 做交付验收。

### P2：增强债

1. 广告视频工作台可以继续 Agent 化，做步骤可观察、结果可复盘。
2. CLI 还没做，未来可以让电脑上的 Agent 调用启动器能力。
3. 多 Agent 协作目前是路线规划，还没落地执行框架。
4. 自动化测试仍偏少，尤其是打包清洁度、授权、机器人绑定、广告视频工作流。

## 9. 常用命令

从仓库根目录运行：

```powershell
cd D:\Axiangmu\AUSTART
```

轻量 CI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1 -SkipRust
```

完整 CI：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1
```

只检查源码文本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-source-text.ps1
```

清理缓存：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean-workspace.ps1
```

清理 Rust 构建缓存：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean-workspace.ps1 -RemoveBuildOutputs
```

前端构建：

```powershell
cd D:\Axiangmu\AUSTART\openclaw_new_launcher
npm run build
```

Rust 检查：

```powershell
cd D:\Axiangmu\AUSTART\openclaw_new_launcher\src-tauri
cargo check
```

打包：

```powershell
cd D:\Axiangmu\AUSTART
powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1 -Version 2.0.2 -PackageName OpenClaw-Portable-v2.0.2-YYYY.MM.DD -BrandProfile customer
```

## 10. Git 注意事项

仓库根目录是：

```text
D:\Axiangmu\AUSTART
```

远端情况之前比较复杂：

- Gitee 是用户主要想用的国内仓库。
- GitHub 也可能要上传，CI/CD 可以走 GitHub Actions。
- 本地分支和 Gitee 可能存在历史分叉，不要盲目 rebase/merge。

提交前建议先：

```powershell
git status --short
git diff --stat
```

不要提交：

- `release/`
- `node_modules/`
- `openclaw_new_launcher/dist/`
- `openclaw_new_launcher/src-tauri/target/`
- `data/license.json`
- `data/install_id.txt`
- API Key、授权码、服务器密码、私钥、数据库。

## 11. 新会话建议第一步

新会话接手后，建议先做这三件事：

1. 读取本文。
2. 运行：

   ```powershell
   cd D:\Axiangmu\AUSTART
   git status --short
   ```

3. 如果用户要继续开发，先问清楚当前目标是：

   - 打包交付版；
   - 完成 Lumi 个人 UI 版；
   - 继续还技术债；
   - 推送 Gitee/GitHub；
   - 继续做 Agent / Skills / CLI。

不要一上来就重构授权或主题系统。当前项目已经能跑，Bridge 和品牌 profile 的 P1 已基本收束，下一步优先做 Release 产物验收、真实 U盘测试或剩余 P1 小步推进。
