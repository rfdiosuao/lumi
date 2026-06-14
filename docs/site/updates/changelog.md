# 更新日志

本页记录启动器、运行时、在线包和完整离线包的交付口径。发布前以本页、GitHub Release 资产和本地 `release/` 目录三处互相校验。

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
