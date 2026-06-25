# 更新日志

本页记录启动器、运行时、在线包和完整离线包的交付口径。发布前以本页、GitHub Release 资产和本地 `release/` 目录三处互相校验。
## v2.1.18 - 2026-06-26

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.18` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.18](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.18) |
| 在线便携包 | `LumiClaw-Online-v2.1.18.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.18-2026.06.26-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.18.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.18.zip` | `19,436,519 bytes` | `D9C8DE983CA3EBE36F3D87E06C43753A111EE7D28A70A629D54A040EDBF64C64` |
| `OpenClaw-Portable-v2.1.18-2026.06.26-full-offline.zip` | `359,184,919 bytes` | `E1C402EC1F3FB5652F8540F2144DBBF7AB92A4B3208DF393E648002A0A727A1D` |
| `LumiClaw-Setup-v2.1.18.exe` | `13,092,406 bytes` | `698F867859B00FCCA744D2B4BE3DF68313ACF7DD010859BAFC51277775E6EED1` |

### 本次更新

1. 修复中转站登录点击无响应：正式包补齐账号路由与 NewAPI manager，前端不再吞掉桥接 `{ error }` 响应。
2. 授权码模式继续保留，与账号登录双入口并行，作为 NewAPI 异常时的回滚路径。
3. 在线包内置多源运行时 manifest：自有镜像、GitHub、ghproxy 依次兜底。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| `python -m py_compile` | 已通过 |
| `npm run build` | 已通过 |
| 账号路由 smoke | 已通过：`current/login/sync/logout` 已注册 |
| 完整离线包验包和 runtime smoke | 已通过 |
| 在线便携包重层剥离 | 已通过，包体 18.5MB |
| 自更新通道 notes 为字符串 | 已通过 |

## v2.1.14 - 2026-06-19

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.14` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.14](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.14) |
| 在线便携包 | `LumiClaw-Online-v2.1.14.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.14-2026.06.19-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.14.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.14.zip` | `24,023,599 bytes` | `129E0FA4E1DC65590823E09F0BB21AAB89526C3850325713D64E30E857CA29F5` |
| `OpenClaw-Portable-v2.1.14-2026.06.19-full-offline.zip` | `360,030,162 bytes` | `81D1429467620B89B8420E108452343C23F77DCFFDE9A288B39B08DE34A8D566` |
| `LumiClaw-Setup-v2.1.14.exe` | `16,905,982 bytes` | `6BF1303E92356F065DCDC41A01CD990EC3B86DF4A193CD86DB5BCC34566DAD2C` |

### 本次更新

1. **图像与视频可以同时生成**：此前用单一「忙」状态把两个生成按钮绑死（一个在跑另一个就被禁用），现拆成独立的图像/视频忙状态，互不阻塞；顶栏角标可同时显示「图像/视频生成中」。
2. 延续 2.1.13：修复启动器窗口「localhost 拒绝连接 / 装好打不开」、正确构建（tauri build）。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 构建产物不连开发端口 :1420 | 已通过 |
| 安装器线上 sha256 | 已通过（== `launcher.json`） |
| 自更新通道 | v2.1.8–v2.1.14 均指向 2.1.14 |
| 官网下载（ghfast 加速） | 已更新到 2.1.14 |

## v2.1.13 - 2026-06-19

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.13` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.13](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.13) |
| 在线便携包 | `LumiClaw-Online-v2.1.13.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.13-2026.06.19-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.13.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.13.zip` | `24,023,660 bytes` | `CF114388E750C8C1BC9CD2EB9C8553BFB02CBC695B995DC2F864F85346CFBE32` |
| `OpenClaw-Portable-v2.1.13-2026.06.19-full-offline.zip` | `360,030,223 bytes` | `5FAF8C767F2865D4D4DBDE595F37B2697ABC2B7F07EDAE47B77DE973680C7F1B` |
| `LumiClaw-Setup-v2.1.13.exe` | `16,909,921 bytes` | `3B6F3A5F8EB9847DF38281D19A60CF53A43C5AE53A6D84C4C32CCC032FEAFC9A` |

### 本次更新

1. **重大修复：启动器窗口「localhost 拒绝连接 / 无法访问」打不开。** 2.1.9–2.1.12 因构建方式问题（误用 `cargo build` 而非 `tauri build`），生产包的窗口去加载开发地址 `localhost:1420`，导致装好后窗口无法加载。2.1.13 用 `tauri build` 正确构建并校验，窗口正常加载内嵌界面。**强烈建议所有用户更新。**
2. 运行时下载源 GitHub 优先、自有镜像 / Gitee 兜底；manifest 多源容错。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 构建产物不再连开发端口 :1420 | 已通过（netstat 无 SYN_SENT） |
| 安装器线上 sha256 | 已通过（== `launcher.json`） |
| 自更新通道 | v2.1.8–v2.1.13 均指向 2.1.13 |
| 官网下载链接 | 已更新到 2.1.13（在线包 + 离线包） |

## v2.1.12 - 2026-06-18

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.12` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.12](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.12) |
| 在线便携包 | `LumiClaw-Online-v2.1.12.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.12-2026.06.18-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.12.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.12.zip` | `21,256,120 bytes` | `D8C84E854D16DDC93567C1FC2FBBD55668561FD8806833031A4C8170FFE18F4F` |
| `OpenClaw-Portable-v2.1.12-2026.06.18-full-offline.zip` | `357,262,683 bytes` | `01244F6EFF50D24389FD6788E95D6BBEE35C1B184F24F1183912398035C487FE` |
| `LumiClaw-Setup-v2.1.12.exe` | `14,118,988 bytes` | `83E6F9D6B5443D25D70F7579F6A8CD9A665960D1C6CEAACCA8E095EEB0659C36` |

### 本次更新

1. 修复在线包「装好打不开 / 访问不了」：运行时组件原先只从 GitHub 下载、国内拉不到；现在改为 **Gitee 国内镜像优先**，GitHub 兜底。
2. manifest 与运行时层三重源，按顺序自动切换：
   - 主源：`https://gitee.com/rfdiosuao/lumi-claw/releases/download/dist-v2.1.8/`
   - 自有镜像：`https://lumiu.heang.top/dist/`
   - 兜底：ghproxy / `github.com/rfdiosuao/openclaw-runtime-layers`
3. 延续 2.1.11：安装静默无黑窗、安装器单实例、不内置 APKClaw。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| Gitee 镜像层 URL | 已通过（node/openclaw-deps/python-runtime/manifest 均 200） |
| 自有镜像 lumiu.heang.top/dist | 已通过（4 层 + manifest 均 200） |
| 安装器线上 sha256 | 已通过（== `launcher.json`） |
| 自更新通道 | v2.1.8–v2.1.12 均指向 2.1.12 |
| 官网下载链接 | 已更新到 2.1.12（自托管） |

## v2.1.11 - 2026-06-18

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.11` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.11](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.11) |
| 在线便携包 | `LumiClaw-Online-v2.1.11.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.11-2026.06.18-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.11.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.11.zip` | `19,405,508 bytes` | `1ACCE34A33ADBD4060C2142DE707115AFD48837044F370E9F4D1E33161FE7359` |
| `OpenClaw-Portable-v2.1.11-2026.06.18-full-offline.zip` | `353,497,759 bytes` | `9E07F45FC3A802B6102ABE02DDBA0A527022B6B73A0BEDBAE853F659D60B9FEE` |
| `LumiClaw-Setup-v2.1.11.exe` | `13,068,718 bytes` | `EF9D2C3A02007C5007C2E99ABC13ADD8A7A8D2F1674897C0C0565B645FEBA5E0` |

### 本次更新

1. 安装过程不再弹出黑色终端窗口；定时任务运行时也全程后台静默（taskkill/PowerShell/node/tasklist 均隐藏窗口）。
2. 安装器加单实例锁（`CreateMutexW`），双击不再打开两个安装窗口。
3. 在线 / 离线包不再内置 APKClaw 安装包（手机端改用二维码扫码下载），包体更小。
4. 官网下载按钮修复「一次点击下载两次」。
5. 运行时层复用 v2.1.8（未变更）。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 安装器线上回读 sha256 | 已通过（== `launcher.json`） |
| `launcher.json` 回读 | 已通过（v2.1.8 / v2.1.9 / v2.1.10 / v2.1.11 通道均指向 2.1.11） |
| 在线包不含 APK | 已通过（0 个 `.apk` 条目） |
| 官网下载链接 | 已更新到 2.1.11（自托管） |

## v2.1.10 - 2026-06-18

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.10` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.10](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.10) |
| 在线便携包 | `LumiClaw-Online-v2.1.10.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.10-2026.06.18-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.10.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.10.zip` | `60,858,439 bytes` | `63129A38CFA5ED4C2850CFFA26E31CE30059F386B4D93113F3C4DFA00E3B0358` |
| `OpenClaw-Portable-v2.1.10-2026.06.18-full-offline.zip` | `394,950,114 bytes` | `61750A41CA757ECE8719539794787ECA26FD34B207B087AEA1CD4FF8F0290E48` |
| `LumiClaw-Setup-v2.1.10.exe` | `28,452,751 bytes` | `8BEF1D0C187E094F62E9AEB9670DD543CC6CA953D62A879A3A4A63512E706BF8` |

### 本次更新

1. 修复窗口「最小化 / 最大化 / 关闭」按钮：顶栏改为固定吸顶，页面下滑后这三个按钮依然在原位、可点击。
2. 其余延续 v2.1.9 的小白化改版；运行时层复用 v2.1.8（未变更）。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 安装器线上回读 sha256 | 已通过（== `launcher.json`） |
| `launcher.json` 回读 | 已通过（v2.1.8 / v2.1.9 / v2.1.10 通道均指向 2.1.10） |
| 官网下载链接 | 已更新到 2.1.10（自托管） |

## v2.1.9 - 2026-06-16

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.9` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.9](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.9) |
| 在线便携包 | `LumiClaw-Online-v2.1.9.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.9-2026.06.16-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.9.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.9.zip` | `60,854,292 bytes` | `EFE57B482445059160D8C52959F775ABF445DC3F1A7986A55170AA9F1199DD0E` |
| `OpenClaw-Portable-v2.1.9-2026.06.16-full-offline.zip` | `394,946,421 bytes` | `29D018E7FC0E2B2E2DD6D34849D6B89E336EC6060A6BB33598BA86540EDC175D` |
| `LumiClaw-Setup-v2.1.9.exe` | `28,457,261 bytes` | `D4A74911AC0C5527E3DDE2EB2419A77104678A3F2A345334F425BCEE119F4B83` |

### 本次更新

全面小白化改版，按《启动器小白视角体感审查》逐条落地，降低新手上手门槛并保留全部高级能力：

1. 首页给出状态驱动的「推荐下一步」与三步引导（启动核心 / 配置模型 / 连接手机）。
2. 服务启动/停止显示实时进度、阶段、已耗时与最近日志，失败给出下一步；按钮防连点。
3. 报错统一翻译成人话，可一键展开详情、复制诊断、打开日志，错误提示不再一闪而过。
4. 统一设置新增普通/高级模式；新增 OpenAI 代理检测；onboard 改为「打开配置向导」。
5. 图像/视频失败分类卡片 + 复制诊断；缺配置直达设置；顶栏常驻生成任务角标。
6. 手机控制台拆分连接/执行/定时三区，新增一键修复连接、错误翻译、常用自动化快捷卡、任务模式中文三档。
7. 桌面微信自动回复默认只写草稿，开启开关后才真正发送，更安全。
8. 首装下载显示总大小、速度与下载源，自动切换备用源。

> 运行时层（`node` / `python-runtime` / `openclaw-deps` / `luminode-desktop`）与 v2.1.8 一致，未重新构建；在线包 manifest 仍复用 v2.1.8 源。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 在线包体积小于 100MB | 已通过（约 58MB） |
| 安装器线上回读 sha256 | 已通过（== `launcher.json`） |
| `launcher.json` 回读 | 已通过（v2.1.8 与 v2.1.9 通道均指向 2.1.9） |
| 官网下载链接 | 已更新到 2.1.9（自托管） |

## v2.1.8 - 2026-06-14

| 项 | 值 |
| --- | --- |
| 启动器版本 | `2.1.8` |
| OpenClaw runtime | `2026.6.5` |
| GitHub Release | [openclaw-runtime-layers v2.1.8](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.8) |
| 在线便携包 | `LumiClaw-Online-v2.1.8.zip` |
| 完整离线包 | `OpenClaw-Portable-v2.1.8-2026.06.14-full-offline.zip` |
| 安装器更新包 | `LumiClaw-Setup-v2.1.8.exe` |

### 交付资产

| 资产 | 体积 | SHA256 |
| --- | ---: | --- |
| `LumiClaw-Online-v2.1.8.zip` | `63,613,140 bytes` | `9AF277666BE0C30BB1DFF6BEBDA121224928D6706675C07B58F567A3C15F90DA` |
| `OpenClaw-Portable-v2.1.8-2026.06.14-full-offline.zip` | `402,106,333 bytes` | `2D26B96314BDB455D6FEF3D4761E18BEF9E19649A06F099EB5BCBC63F819DFEA` |
| `LumiClaw-Setup-v2.1.8.exe` | `7,048,168 bytes` | `6B6DF7A7B77147A2F9692E01457233C86B2F99661AA4E1E3EB35B58B75540F95` |

### 本次更新

1. 手机 Agent 增加广告等待模板，支持 30 秒观看、奖励领取、链式广告拒绝和未知弹窗停止。
2. 定时任务启动时同步内置模板到调度器，避免新增模板只出现在 UI、不进入后台执行链路。
3. 广告等待类任务按 `maxWatchSeconds` 推导执行窗口，默认保留 135 秒上限，减少短任务误超时。
4. 视频生成流程优化等待体感：任务进行中切换模块后，回到页面仍应恢复生成状态和动效。
5. 在线包 manifest 使用 GitHub Release 主源与 ghproxy 备用源；运行时层包含 `node`、`python-runtime`、`openclaw-deps` 和 `luminode-desktop`。
6. 完整离线包内置 `AgentPhone_latest.apk` 和 Luminode/SightFlow 桌面组件，适合无稳定网络的客户机验收。

### 发布验证

| 检查 | 状态 |
| --- | --- |
| 完整包 `verify-release` | 已通过 |
| 便携包 smoke test | 已通过 |
| 在线包体积小于 100MB | 已通过 |
| Release 资产回读 | 已通过，线上共 12 个资产 |
| `launcher.json` 回读 | 已通过 |
| `manifest.json` 回读 | 已通过 |

### 已知注意

`npm audit` 仍提示依赖中存在 3 个安全告警。本次发布只处理交付包和运行时资产，没有调整依赖锁；依赖治理应单独建任务处理。

## 发布资产位置

当前在线更新资产托管在：

```text
https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.8
```

在线包启动后会读取：

```text
https://github.com/rfdiosuao/openclaw-runtime-layers/releases/download/v2.1.8/manifest.json
https://github.com/rfdiosuao/openclaw-runtime-layers/releases/download/v2.1.8/launcher.json
```

生产环境建议后续增加自有 OSS/CDN 主源。公共代理只适合作为兜底，不应成为唯一下载链路。
