# 打包发布与 CI/CD

当前仓库有本地打包脚本和 GitHub Actions。文档先讲清“本地完整包”和“云端 release 资产”的差异，避免以为每个 CI 产物都是客户可直接使用的完整包。

## 当前版本口径

| 项 | 当前值 |
| --- | --- |
| 启动器包 | `openclaw_ui_integration` |
| package 版本 | `2.1.8` |
| Tauri 版本 | `2.11.0` |
| Rust edition | `2021` |
| Node 版本 | CI 使用 `22` |
| Python 版本 | CI 使用 `3.11` |
| OpenClaw runtime | 当前交付包使用 `2026.6.5` |
| Runtime layers Release | [rfdiosuao/openclaw-runtime-layers v2.1.8](https://github.com/rfdiosuao/openclaw-runtime-layers/releases/tag/v2.1.8) |

## v2.1.8 资产清单

| 资产 | 用途 | SHA256 |
| --- | --- | --- |
| `LumiClaw-Online-v2.1.8.zip` | 小于 100MB 的在线便携包 | `9AF277666BE0C30BB1DFF6BEBDA121224928D6706675C07B58F567A3C15F90DA` |
| `OpenClaw-Portable-v2.1.8-2026.06.14-full-offline.zip` | 完整离线包 | `2D26B96314BDB455D6FEF3D4761E18BEF9E19649A06F099EB5BCBC63F819DFEA` |
| `LumiClaw-Setup-v2.1.8.exe` | 启动器自更新安装器 | `6B6DF7A7B77147A2F9692E01457233C86B2F99661AA4E1E3EB35B58B75540F95` |

运行时分层资产：

| 层 | 用途 |
| --- | --- |
| `node.tar.gz` | Node 运行时 |
| `python-runtime.tar.gz` | Python 运行时 |
| `openclaw-deps.tar.gz` | OpenClaw npm 运行时和依赖 |
| `luminode-desktop.tar.gz` | 桌面 RPA 组件 |

## 本地构建

```powershell
cd D:\Axiangmu\AUSTART\openclaw_ui_integration
npm install
npm run build
npm run tauri build
```

便携包构建脚本在 `openclaw_ui_integration/scripts/` 下。完整包应包含运行时层，并在打包阶段清理授权、安装 ID、密钥和缓存。

## GitHub Actions

仓库当前有两个关键 workflow：

| Workflow | 作用 |
| --- | --- |
| `.github/workflows/ci.yml` | Windows checks，安装 Node/Python/Rust，执行 `scripts\ci-check.ps1` |
| `.github/workflows/openclaw-ui-integration-release.yml` | 手动触发，构建 source package 和 Windows portable package，并发布 Release |

Release workflow 的输入：

| 输入 | 说明 |
| --- | --- |
| `release_tag` | GitHub Release tag |
| `openclaw_version` | OpenClaw npm runtime 版本；当前交付口径是 `2026.6.5` |
| `package_kind` | `all`、`source`、`windows-portable` |
| `include_phone_agent_apk` | 是否附带手机 APK |

## 源码包给 Mac 端怎么用

源码包应该包含：

1. `openclaw_ui_integration` 源码。
2. `scripts` 和 `.github/workflows`。
3. `docs` 和本 VitePress 文档站。
4. 必要的配置模板。

源码包不应该包含：

1. Windows 便携包产物。
2. 本地 `node_modules`。
3. `src-tauri/target`。
4. 授权数据库、密钥、用户缓存。
5. APK 或桌面组件，除非 release 明确声明。

## 发布前检查

```powershell
git status --short
powershell -ExecutionPolicy Bypass -File scripts\ci-check.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-source-text.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-version-consistency.ps1
```

还要人工确认：

- `OpenClawFiles/node_modules/openclaw/src/agents/templates` 模板完整。
- 桌面 RPA 组件来自正确的 `sightflow-desktop-agent-main`。
- 手机 APK 是否应该内置。
- 更新 manifest 源和 hash 是否同步。
- README 和 release note 里的版本号没有过期。

## GitHub 发行策略

推荐 release 资产：

| 资产 | 用途 |
| --- | --- |
| `OpenClaw-Launcher-Source-*.zip` | Mac/Linux 适配和源码审查 |
| `OpenClaw-Portable-*.zip` | Windows 客户便携包 |
| `LumiClaw-Online-*.zip` | Windows 在线瘦包 |
| `manifest.json` | 运行时层下载清单 |
| `launcher.json` | 启动器自更新清单 |
| `*.sha256.txt` | 校验下载完整性 |
| Release notes | 说明版本、runtime、已知问题和升级建议 |

只有在 Mac 构建、签名、公证和依赖层全部验证通过后，文档才应写入“自动发行各平台完整包”之类的公开承诺。
