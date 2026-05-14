# 启动器与 APKClaw 技术债总账

> 更新时间：2026-05-11
> 用途：把启动器和 APKClaw 手机端剩余技术债收敛成一份可执行清单。
> 原则：先交付闭环，再产品化；先验收真实环境，再继续叠功能；不把“路线规划”误当成“已完成”。

## 当前基线

### 启动器

- 主线形态：Tauri + React + Python Bridge。
- 当前重点：真实机器验收、真实 U 盘验收、授权全流程、交付包清洁度、客户交付说明。
- 已具备：启动器 UI、Bridge、品牌 profile、环境诊断、授权入口、AI 生图/视频/广告视频入口、Phone Agent 工作台、`phone:image` 生图/传图 CLI、OpenClaw 便携工作区、初始化体检报告、当前屏幕节点统计、vision hint 和视觉兜底提示入口。
- 当前风险：能跑，但还没有完全变成“敢交付给客户”的稳定包。

### APKClaw 手机端

- 当前推荐版：`AgentPhone_v6.26_<build-time>.apk`。
- 当前版本目标：`versionName=6.26` / `versionCode=860`。
- 稳定下载别名：`http://192.168.1.166:8765/AgentPhone_latest.apk`。
- 当前远程验收设备：荣耀，`http://192.168.1.12:9527`，Token `88888888`。
- 已具备：状态接口、截图、结构树、低层动作、Agent 主控、只读/安全/完全访问策略、初始化体检、自动亮屏、商家中性视觉皮肤、悬浮球大小配置、PC 图片导入手机相册、录屏回传、游戏/视觉模式帧、游戏模式闭环 CLI、视觉动作安全黑名单与视觉坐标动作。
- 当前风险：功能迭代很快，最终交付包验收、产品化说明和工作区提交收口还需要完成。
- 当前超短时死点：已解除。6.21 已成功安装到 HONOR 192.168.1.12，9527 HTTP 接口恢复，`verify:phone` 31/31 通过；6.25 补入只读当前屏幕观察工具收窄；6.26 增加游戏/视觉闭环和安全黑名单，待真机安装复测。

## P0：交付前必须收

### 启动器 P0

- [ ] 真实 Windows 机器验收。
  - 验收标准：在另一台机器解压 portable 包，双击 `OpenClaw.exe` 正常打开。
  - 验收标准：Bridge 能启动，OpenClaw 本地页面能打开。
  - 验收标准：记录系统版本、WebView2 状态、杀毒软件拦截情况。

- [ ] 真实 U 盘验收。
  - 验收标准：同一 U 盘拔插后授权仍有效。
  - 验收标准：同一 U 盘换盘符后授权仍有效。
  - 验收标准：复制到另一块 U 盘不能直接继承授权。
  - 验收标准：U 盘不可写或写入失败时，诊断页能给出可理解提示。
  - 2026-05-11 进展：`E:\` OpenClaw exFAT U 盘完成修正版 zip 写入、SHA256 校验、U 盘解压和 `verify-release.ps1`；从 U 盘启动 `OpenClaw.exe` 成功，窗口有响应。
  - 2026-05-11 发现：直接镜像 5 万个小文件到 U 盘时曾导致 Windows I/O 卡死；建议交付流程优先复制单个 zip，再由用户解压，或后续优化为更少文件的便携包。
  - 2026-05-11 待补：授权拔插、换盘符、复制到另一块 U 盘的绑定行为尚未验收。

- [ ] 授权全流程验收。
  - 验收标准：未授权状态进入授权页。
  - 验收标准：正确授权码可激活。
  - 验收标准：错误、过期、服务器不可达都有明确提示。
  - 验收标准：授权成功后重启仍保持授权状态。

- [ ] 交付包清洁度验收。
  - 验收标准：最终 zip 跑 `verify-release.ps1`。
  - 验收标准：包内不包含 `data/license.json`、`data/install_id.txt`。
  - 验收标准：包内不包含 API Key、授权码、服务器密码、私钥、用户机器人缓存。
  - 验收标准：`data/brand_profile.json` 是目标客户 profile。

- [ ] 客户交付说明补齐。
  - 验收标准：写清楚解压、启动、授权、API 配置、启动核心服务、常见问题恢复。
  - 建议输出：一份客户可读的短文档，不使用开发者口吻。

- [ ] 当前工作区改动收口。
  - 验收标准：把本轮启动器改动、APKClaw 集成改动、文档改动拆成可理解的提交或变更说明。

### APKClaw P0

- [x] v6.11 最终真机验收。
  - 验收命令：
    ```powershell
    npm run verify:phone -- -BaseUrl http://192.168.1.12:9527 -Token 88888888
    ```
  - v6.10 验收结果：状态、截图、结构树、画像、wake endpoint、任务模式、安全阻断全部通过，27 项通过、0 项失败。
  - v6.26 验收目标：`GET /api/device/status` 返回 `version=6.26` / `versionCode=860`。
    - v6.21 验收结果：`POST /api/lumi/media/import_image` 成功把测试图片写入手机相册，返回 `success=true`。

- [x] APKClaw 源码版本管理收口。
  - 已建立独立 GitHub 仓库：`https://github.com/rfdiosuao/lumiapkclaw`。
  - 默认分支：`main`，可从提交历史恢复当前 APKClaw 源码。
  - 已补 `.gitignore` 和 `.gitattributes`，排除 `local.properties`、`debug.keystore`、构建目录和 APK/AAB 产物。
  - GitHub Actions `Android CI` 已通过，可构建 debug APK。

- [ ] APK 产物入口稳定化。
  - 已完成部分：旧 APK 已归档，根目录只保留当前推荐包和 `AgentPhone_latest.apk`。
  - 待确认：每次重新构建后，`AgentPhone_latest.apk` 同步到启动器根目录和当前 `8765` 文件服务目录。
  - 验收标准：`http://192.168.1.166:8765/AgentPhone_latest.apk` 返回 `200 OK`。

- [ ] 手机端操作说明补齐。
  - 验收标准：写清楚安装 APK、开启无障碍、开启悬浮窗、配置 Token、连接启动器、初始化体检、常见恢复方式。

- [x] 图片导入验收脚本补齐。
  - 当前状态：手工真机验证已通过，CLI 上传已通过。
  - 已完成：`scripts/verify-phone-agent.ps1` 已增加 `POST /api/lumi/media/import_image` 自动验收项，并走安全通道。
  - 验收标准：上传测试 PNG 后返回 `success=true`，`relativePath` 指向配置相册，且错误 Token 返回 `401`。

## P1：产品化技术债

### 启动器 P1

- [ ] 授权后台正式版。
  - 内容：商户管理、授权码生成、有效期、设备绑定/解绑、售后重置、操作日志、管理员权限。
  - 风险：没有后台时，销售和售后都依赖手工处理。

- [ ] 授权核心安全边界统一。
  - 内容：明确 Python 与 Rust 各自负责的授权逻辑。
  - 内容：统一授权文件读写入口。
  - 内容：补充授权失败可诊断错误码。
  - 风险：授权绕过和售后排查成本高。

- [ ] Feishu / WeChat 插件状态机。
  - 内容：未安装、未绑定、扫码中、已绑定、绑定失效、重新绑定、错误恢复。
  - 风险：当前脚本驱动较多，客户遇到异常后不知道下一步。

- [ ] Skills 系统规范。
  - 内容：manifest、版本兼容、签名校验、安装/卸载、权限边界、崩溃隔离。
  - 风险：后续扩展能力变多后，缺少统一约束。

- [ ] 统一发布流程。
  - 内容：portable zip 纳入 CI。
  - 内容：Release 同时上传 installer、msi、portable zip、sha256。
  - 内容：Release notes 必须使用中文，自动带版本、提交、校验哈希和面向用户的更新摘要。
  - 2026-05-11 发现：`v2.0.4` 原始 zip 缺少 `scripts/openclaw-phone-vision.mjs`，展开目录补齐后 `verify-release.ps1` 通过；发布自动化必须先跑校验再上传附件。
  - 2026-05-11 发现：`runtime-context.json` 中 `phoneAgent.verifiedVersion` 仍为旧值，发布脚本应从当前 APK 版本或参数统一写入。
  - 2026-05-11 进展：`publish-gitee-release.ps1` 默认发布说明改为中文模板；`verify-release.ps1` 已检查手机端 CLI 套件、便携工作区、runtime context 和 APK 附件。
  - 2026-05-11 进展：`build-portable.ps1` 支持 `PhoneAgentVerifiedVersion` / `PhoneAgentVerifiedVersionCode` 参数，并用 fresh nozip 包验证 `6.23/830` 写入和发布校验通过。
  - 2026-05-11 进展：`.github/workflows/release.yml` 已纳入 portable zip 构建、SHA256 生成、中文 Release notes 和 GitHub Release 附件上传；workflow 可从上一版 Release 下载 portable seed。
  - 2026-05-11 剩余：`AgentPhone_latest.apk` 需要和版本化 APK 文件名/哈希保持一致，减少手工传参；GitHub Actions 需要跑一次真实 tag release 验证。
  - 风险：手工打包容易漏文件、带隐私配置、版本混乱。

### APKClaw P1

- [ ] APK 自更新后复活机制。
  - 当前状态：暂缓。
  - 内容：安装后自动恢复前台服务和 `9527` server。
  - 内容：若无法恢复，启动器给出“需要手动打开 Agent Phone 一次”的明确提示。
  - 风险：安装升级后服务中断，用户以为系统坏了。

- [ ] 多设备管理。
  - 内容：启动器保存多个手机设备。
  - 内容：按设备隔离 baseUrl、Token、画像、体检报告和任务历史。
  - 风险：远程 HONOR 和 USB 荣耀容易混淆。

- [ ] 手机 Agent 安全策略产品化。
  - 内容：敏感操作二次确认。
  - 内容：危险 App 黑名单。
  - 内容：任务暂停、人工接管、最大步骤数、最大执行时间。
  - 风险：真实客户环境里安全边界不够清晰。

- [ ] 固定 demo 场景。
  - 建议场景：打开 Via，进入京东，搜索 500 元左右移动硬盘，读取页面结果并返回摘要。
  - 验收标准：能重复演示，不依赖临场 prompt 运气。

- [ ] APKClaw UI 文案与视觉继续收口。
  - 内容：权限页、设置页、通知、悬浮球、内置 Web 配置页统一为商家中性语气和视觉。
  - 风险：目前主视觉已切换，但仍可能有旧 Agent Phone 或旧通道文案残留。

## P2：体验增强债

### 启动器 P2

- [ ] 首次启动引导。
  - 路径：授权 -> API 配置 -> 启动核心服务 -> 打开工作台。
  - 要求：已完成步骤可视化，跳过步骤有明确后果提示。

- [ ] 诊断页增强。
  - 内容：一键复制诊断报告、导出日志包、检查端口、WebView2、Python、Node、U 盘读写、OpenClaw 配置文件。

- [ ] 全页面 UI 统一。
  - 范围：授权页、API 配置页、日志页、Skills 页、诊断页、弹窗、按钮、输入框、提示条。
  - 风险：目前主控制台风格已升级，但局部页面仍有历史样式。

- [ ] 自动化测试补齐。
  - 范围：打包清洁度、授权、机器人绑定、广告视频工作流、Phone Agent 工作台、图片导入手机相册。

### APKClaw P2

- [x] API 契约文档阶段同步。
  - 已完成：把 `/api/device/status`、`/api/device/wake`、`/api/lumi/agent/execute_task`、tool policy、drag、`/api/lumi/media/import_image`、Device Profile vision hints、游戏/视觉模式和图片导入 JSON `dataUrl` 契约更新回 contract。
  - 后续规则：每次 APKClaw 新增 `/api/lumi/*` 或改变请求体时，必须同轮更新 `PHONE_CONNECTOR_API_CONTRACT.md` 和验收脚本。

- [ ] 工作流模板市场暂缓。
  - 暂不做原因：当前先稳定手机 Agent 主控和安全边界。

- [ ] 多 Agent 编排暂缓。
  - 暂不做原因：单手机、单 Agent 闭环还需要交付验收。

- [ ] WebRTC 真投屏暂缓。
  - 暂不做原因：截图 + 结构树 + Agent 主控已经够当前演示，真投屏会显著增加复杂度。

## 共同债务

- [x] 文档源头阶段收敛。
  - 当前问题：`task.md`、roadmap、handoff、contract 中有重复清单。
  - 2026-05-11 已处理：`DOCS_INDEX.md` 指向真实文件名，`PHONE_CONNECTOR_API_CONTRACT.md` 作为当前接口契约，`APKCLAW_LUMI_INTEGRATION_HANDOFF.md` 标注历史版本属性，`task.md` 保持执行清单。
  - 后续规则：本文件作为技术债入口，`task.md` 保持执行清单，handoff 保持历史变更记录。

- [ ] 版本命名统一。
  - 启动器：portable zip、Tauri 版本、Release tag 需要统一。
  - APKClaw：`versionName`、`versionCode`、APK 文件名、验收脚本默认版本需要同步；当前源码已到 `6.26/860`，验收脚本已纳入图片导入、安全通道和游戏/视觉模式验收项。

- [ ] 变更记录与构建产物绑定。
  - 要求：每次出包都记录包名、版本、构建时间、验收命令、验收结果。

- [ ] 隐私与安全边界显式化。
  - 启动器：交付包不带用户隐私。
  - APKClaw：初始化体检只读取设备画像和 UI 摘要，不扫私人文件内容。

## 建议下一步顺序

1. 把图片导入加入 `scripts/verify-phone-agent.ps1` 自动验收。
2. 做启动器真实 U 盘和另一台 Windows 机器验收。
3. 跑启动器交付包清洁度检查。
4. 补客户交付说明和 APKClaw 安装说明。
5. 固化 OpenClaw 便携工作区与 `SOUL.md` / Skill 注入验收。
6. 固化一个手机 Agent demo 场景。
7. 再推进授权后台、插件状态机、Skills 产品化。

## 当前不建议做

- 不建议马上大规模重构 Bridge。
- 不建议马上做完整主题市场。
- 不建议同时推进多手机、多 Agent、WebRTC 真投屏。
- 不建议在真实 U 盘和授权验收前继续增加授权复杂度。
- 不建议继续堆 APKClaw 功能而不把新增接口纳入自动验收。
