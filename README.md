# Lumi / OpenClaw U盘启动器

这是一个面向商家交付的 OpenClaw 便携式 AI 服务启动器项目。

当前仓库采用 monorepo 管理:

- `openclaw_new_launcher/`: 新版 Tauri + React + Python Bridge 启动器。
- `license_server/`: 在线授权码服务器。
- `scripts/`: 本地检查、后续打包和发布脚本。
- `openclaw_launcher/`: 旧版 Python 启动器与历史重构资料。

## 当前目标

- 提供可离线运行的 OpenClaw 启动器。
- 支持授权码激活。
- 支持商户主题和白标 UI。
- 支持 AI 生图、AI 视频、广告视频分镜工作台。
- 后续接入 Gitee 版本管理和 CI/CD。

## 本地检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ci-check.ps1
```

轻量检查:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ci-check.ps1 -SkipFrontend -SkipRust
```

## 文档入口

- `openclaw_new_launcher/docs/PRODUCT_ROADMAP.md`
- `openclaw_new_launcher/docs/ARCHITECTURE_REVIEW_2026-05-05.md`
- `openclaw_new_launcher/docs/GITEE_SETUP.md`
- `openclaw_new_launcher/docs/GIT_CICD_PLAN.md`

## 注意

不要提交以下内容:

- `release/`
- `node_modules/`
- `dist/`
- `src-tauri/target/`
- 授权服务器私钥、数据库、后台 token。
- 客户授权文件、安装 ID、API Key。

