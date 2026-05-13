# OpenClaw Launcher 当前任务清单

> 更新日期：2026-05-13  
> 当前分支重点：手机端硬约束、离线包发包稳定性、文档收口。  
> 桌面客服 / SightFlow 相关工作本地保留，暂不纳入当前 GitHub 推送批次。

## 当前状态

- 启动器版本基线：`2.0.6`
- APKClaw 验收基线：`6.26 / versionCode 860`
- 手机 Agent 协作方式：OpenClaw 只能通过 launcher CLI wrapper 指挥 APKClaw，默认命令是 `npm run phone:agent`
- 手机端 runtime context：不暴露手机 IP、端口、token 和底层 `/api/lumi/*` 任务端点
- 发包校验：`verify-release.ps1` 已强制检查 phone wrapper、workspace、runtime context、APK 附件和敏感配置
- 新增离线包 smoke：`scripts/verify-portable-smoke.ps1`

## P0 交付稳定性

### 1. 离线包完整性验收

- [x] `verify-release.ps1` 检查 `openclaw-phone-agent.mjs`
- [x] `verify-release.ps1` 检查 OpenClaw workspace 四件套
- [x] `verify-release.ps1` 检查 runtime context 不预置手机连接
- [x] `verify-release.ps1` 禁止 runtime context 暴露底层手机端点
- [x] `verify-portable-smoke.ps1` 检查 Python 依赖 `fastapi/uvicorn`
- [x] `verify-portable-smoke.ps1` 检查 Node CLI 脚本语法
- [x] `build-portable.ps1` 接入 smoke 验收
- [ ] 下一次正式 zip 打包后跑完整目录 + zip 双验收

### 2. 低配一体机启动稳定性

- [x] 启动超时放宽，低配机器启动慢时保留进程继续等待
- [x] 启动失败快照写入 `data/logs/openclaw-startup-snapshot.json`
- [x] Bridge 服务日志落盘到 `data/logs/bridge-service.log`
- [ ] 继续减少启动首屏阻塞检查
- [ ] 将非关键检查懒加载到环境诊断页
- [ ] 在 500 元级一体机上做真实冷启动计时

### 3. 环境诊断闭环

- [x] 诊断导出包含日志、配置、启动快照
- [x] 诊断可识别 Python/Node/WebView2 缺失
- [x] 诊断可识别端口占用和残留进程
- [x] 诊断可识别 runtime-context 和便携包关键文件缺失
- [ ] 增加杀毒软件拦截提示
- [ ] 增加“全绿但启动失败”的专项摘要规则

## P1 手机 Agent / APKClaw

### 4. OpenClaw 指挥 APKClaw 硬约束

- [x] 新增 `npm run phone:agent`
- [x] `openclaw-phone-agent` skill 写入硬规则：不得直连 APKClaw 任务端点
- [x] `AGENTS.md` 写入硬规则：不得硬编码、推断、打印、请求手机 IP/端口/token
- [x] `runtime-context.json` 改为 `endpoint: launcher-cli-wrapper`
- [x] 打包脚本写入 wrapper-only runtime context
- [ ] 给 `phone:agent` 增加任务历史落盘
- [ ] 给 `phone:agent` 增加失败分类：离线、未授权、无障碍关闭、任务超时、APKClaw 崩溃

### 5. APKClaw 稳定性

- [ ] APKClaw 端增加崩溃日志导出
- [ ] APKClaw 端 Agent worker 异常兜底，避免 HTTP 服务一起挂掉
- [ ] 任务超过 60 轮时返回部分结果和 follow-up 建议
- [ ] 针对购物/搜索类任务固化 `collect_list_items target=product`

### 6. 手机演示场景

- [ ] 固化一个可重复 demo：搜索商品、收集 10 个候选、返回性价比摘要
- [ ] 固化一个只读 demo：读取当前屏幕并返回可见入口
- [ ] 固化一个视觉 fallback demo：低节点/游戏画面时走 `phone:game`

## P1 发布与 CI/CD

### 7. GitHub Release 自动化

- [x] GitHub 分支 `codex/phone-agent-hardguard` 已推送
- [x] 提交 `1b2553f Add phone agent launcher wrappers`
- [x] 提交 `26f52ab Add portable package smoke verification`
- [x] Release notes 默认中文
- [ ] 正式 tag release 跑一次完整 GitHub Actions
- [ ] Release 附件确认包含 portable zip、sha256、安装器
- [ ] Release 页面展示中文更新摘要和校验值

### 8. 版本号一致性

- [x] 启动器基线统一到 `2.0.6`
- [x] `package.json` / `package-lock.json` 已同步
- [ ] 每次发包前自动检查 Tauri 版本、package 版本、包名版本一致
- [ ] APKClaw latest 与版本化 APK 文件 hash 一致性自动检查

## P1 文档债

### 9. 文档入口收口

- [x] 重写 `DOCS_INDEX.md` 为当前文档入口
- [x] 重写 `task.md` 为当前可执行任务清单
- [ ] 清理或标记乱码历史文档
- [ ] 把 `TECH_DEBT_LAUNCHER_AND_APKCLAW.md` 改成精简债务台账
- [ ] 更新 `RELEASE_CHECKLIST.md`，加入 `verify-portable-smoke.ps1`
- [ ] 更新 `CUSTOMER_GUIDE.md`，加入 WebView2 和环境诊断说明

### 10. 文档规则

- [x] `DOCS_INDEX.md` 明确事实源优先级
- [ ] 新增“每次改接口必须同步契约 + 验收脚本”的检查项
- [ ] 新增“每次改发包流程必须同步 release checklist”的检查项

## P2 桌面 Agent / SightFlow

> 暂缓推送。当前本地已有实验实现，但不进入本批 GitHub 变更。

- [ ] 电脑端 Bridge-only 硬约束正式拆分成单独 PR
- [ ] SightFlow 配置策略产品化：截图、点击、输入、微信发送开关
- [ ] 微信发送默认草稿模式，用户确认后再发送
- [ ] 桌面 Agent 环境诊断：exe 缺失、端口占用、token 不匹配、微信窗口不可见
- [ ] 打包时是否附带 SightFlow sidecar 需单独评审

## 推荐下一步

1. 把本次文档债提交到 GitHub，不包含桌面客服实现。
2. 更新 `RELEASE_CHECKLIST.md`，把 smoke 验收加入正式发包流程。
3. 跑一次正式 zip 打包，确认目录和 zip 都通过 `verify-release.ps1` 与 `verify-portable-smoke.ps1`。
4. 再处理低配一体机启动性能：减少首屏阻塞、延长可视化进度、懒加载非关键诊断。
