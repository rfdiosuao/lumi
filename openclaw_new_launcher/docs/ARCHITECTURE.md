# OpenClaw U盘便携版桌面管理器 -- 系统架构文档

> **文档状态：历史参考。**
> 当前稳定化、模块扩展、UI 自定义和 Bridge 迁移分别以
> `PRODUCT_ROADMAP.md`、`MODULE_EXTENSION_GUIDE.md`、`UI_CUSTOMIZATION_DESIGN.md`
> 和 `BRIDGE_MIGRATION_GUARD.md` 为准。本文保留用于理解早期整体架构。

> **版本**: 2.0  
> **日期**: 2026-05-05  
> **状态**: 主题系统已实现（客户端），授权服务器扩展进行中  
> **适用范围**: OpenClaw U盘便携版桌面启动器完整系统

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统总体架构](#2-系统总体架构)
3. [技术栈选型及理由](#3-技术栈选型及理由)
4. [核心模块功能描述](#4-核心模块功能描述)
5. [数据流转流程](#5-数据流转流程)
6. [数据库模型设计](#6-数据库模型设计)
7. [主题系统架构](#7-主题系统架构)
8. [安全架构](#8-安全架构)
9. [非功能性需求](#9-非功能性需求)
10. [部署架构](#10-部署架构)
11. [附录](#附录)

---

## 1. 系统概述

### 1.1 项目定位

OpenClaw U盘便携版桌面管理器是一款面向 B 端商家的白色标签桌面启动器。它将 OpenClaw（基于 Node.js 的 AI 网关服务）封装为 U 盘即插即用的便携应用，同时通过授权码机制实现"同一个 exe，不同品牌 UI"的核心商业模式。

### 1.2 核心价值

| 价值维度 | 描述 |
|---|---|
| **便携即用** | 整套运行时（Python、Node.js、OpenClaw）内嵌于 U 盘，插入即可运行，无需安装 |
| **品牌定制** | 不同授权码激活出不同商家品牌的 UI（颜色、名称、Logo、导航项），零代码改动 |
| **授权保护** | Ed25519 签名链 + 硬件绑定，确保功能权限不被绕过 |
| **统一分发** | 同一个 exe 分发给所有商家，通过授权码区分品牌，极大降低维护成本 |

### 1.3 目标用户

| 用户角色 | 使用场景 |
|---|---|
| **商家管理员** | 在云端管理后台创建商家、配置主题、生成授权码 |
| **终端用户** | 在 U 盘上运行启动器，输入授权码激活，使用 AI 生图/生视频/广告分镜等功能 |
| **运维人员** | 部署云端授权服务器，管理授权码生命周期 |

---

## 2. 系统总体架构

### 2.1 四层架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        云端授权服务器                                 │
│              license_server/server.py (Python)                      │
│           SQLite + Ed25519 + 管理后台 HTML                           │
│           0.0.0.0:18791 / https://license.heang.top                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTPS (/activate, /public-key)
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     客户端 Tauri 桌面应用                            │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ 第三层: React UI 层                                           │  │
│  │  React 18 + TypeScript + Tailwind CSS + Zustand              │  │
│  │  ├── ThemeProvider (动态主题注入 CSS 变量)                     │  │
│  │  ├── 5 个业务页面 (Terminal/License/Image/Video/Storyboard)   │  │
│  │  ├── 通用组件库 (Button/Input/Modal/Toast/Loading)            │  │
│  │  └── api.ts → invoke('proxy_request') → Rust → Python        │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │ Tauri IPC (invoke)                   │
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ 第一层: Rust 核心层                                           │  │
│  │  Tauri 2.0 (Rust)                                           │  │
│  │  ├── 进程管理: 启动 Python Sidecar (subprocess)               │  │
│  │  ├── 代理转发: proxy_request (reqwest → Python API)           │  │
│  │  ├── 端口/Token 管理: AtomicU16 + Mutex<Option<String>>       │  │
│  │  └── 应用生命周期: setup() 中自动启动 bridge                   │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │ subprocess + stdout (BRIDGE_PORT/TOKEN)
│  ┌───────────────────────────▼───────────────────────────────────┐  │
│  │ 第二层: Python Sidecar 业务层                                  │  │
│  │  Python 3.x (bridge.py + core/ + services/)                  │  │
│  │  ├── bridge.py: HTTP API 网关 (15 个端点)                     │  │
│  │  ├── core/license_manager.py: Ed25519 验签 + 在线激活          │  │
│  │  ├── core/paths.py: 路径发现 (U盘/开发/打包三种模式)           │  │
│  │  ├── core/storage.py: JSON 读写工具                           │  │
│  │  ├── core/constants.py: 品牌/颜色/模型常量                     │  │
│  │  ├── services/process.py: OpenClaw 进程管理                    │  │
│  │  ├── services/image_api.py: AI 图片生成 (OpenAI 协议)          │  │
│  │  ├── services/video_api.py: AI 视频生成 (DashScope)           │  │
│  │  └── services/updater.py: 版本更新 (pnpm)                     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 层间通信模型

```
React UI                    Rust 核心                   Python Sidecar             云端服务器
   │                           │                            │                         │
   │ invoke('proxy_request',   │                            │                         │
   │   {path, method, body})   │                            │                         │
   │──────────────────────────>│                            │                         │
   │                           │  HTTP + X-Bridge-Token     │                         │
   │                           │  GET/POST http://127.0.0.1 │                         │
   │                           │───────────────────────────>│                         │
   │                           │                            │  HTTPS POST /activate   │
   │                           │                            │────────────────────────>│
   │                           │                            │<────────────────────────│
   │                           │<───────────────────────────│                         │
   │<──────────────────────────│                            │                         │
   │  JSON string              │                            │                         │
```

**关键设计决策**：前端不直接 `fetch` Python API，而是通过 Tauri `invoke('proxy_request')` 间接调用。这样做的原因：

1. CSP 策略限制前端只能连接 `http://127.0.0.1:*`，通过 Rust 代理可统一管控
2. Rust 层自动注入 `X-Bridge-Token`，前端无需感知认证细节
3. Rust 层可在代理层增加缓存、限流、日志等横切关注点

---

## 3. 技术栈选型及理由

### 3.1 桌面框架: Tauri 2.0 (Rust)

| 选型因素 | Tauri 的优势 |
|---|---|
| 体积 | 打包后 EXE < 10MB，对比 Electron 80MB+ |
| 内存 | Rust 原生进程 + 系统 WebView，内存占用 50-100MB |
| 安全 | Rust 内存安全 + CSP 策略 + 细粒度权限控制 |
| 启动速度 | 冷启动 < 1s (不含 Python Sidecar) |
| 跨平台 | 本项目仅 Windows，但 Tauri 天然支持 macOS/Linux |

### 3.2 前端: React 18 + TypeScript + Tailwind CSS + Zustand

| 技术 | 选型理由 |
|---|---|
| React 18 | 生态成熟，函数组件 + Hooks 适合中小型桌面应用 |
| TypeScript | 类型安全，API 契约清晰，减少运行时错误 |
| Tailwind CSS | 原子化 CSS 天然适配主题变量系统（`bg-accent` → CSS 变量 → 运行时替换） |
| Zustand | 轻量级状态管理（< 1KB），无 boilerplate，适合本项目状态简单（5 个 state）的场景 |

### 3.3 后端 Sidecar: Python (http.server)

| 选型因素 | 说明 |
|---|---|
| 复用已有逻辑 | 旧版 tkinter 启动器的全部业务逻辑用 Python 编写，原样迁移 |
| AI 生态 | Pillow (图片处理)、cryptography (Ed25519)、DashScope SDK 均为 Python 生态 |
| 进程管理 | `subprocess.Popen` + `taskkill` 的 Windows 进程管理逻辑成熟 |
| 便携性 | Python 可嵌入 U 盘（embedded distribution），无需系统安装 |
| 迁移计划 | 当前使用 `http.server`，计划迁移到 FastAPI 以获得自动文档和异步支持 |

### 3.4 授权服务端: Python http.server + SQLite + Ed25519

| 选型因素 | 说明 |
|---|---|
| SQLite | 零运维嵌入式数据库，单文件，适合授权码量级（千级以下） |
| Ed25519 | 现代数字签名算法，签名紧凑（64 bytes），验签快速，安全性极高 |
| http.server | 标准库零依赖，适合轻量级 API 服务 |
| 内嵌管理后台 | 单文件 HTML 内嵌于 Python 代码，部署极简（一个文件 = 全部服务） |

---

## 4. 核心模块功能描述

### 4.1 Rust 核心层

**文件**: [lib.rs](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src-tauri/src/lib.rs)

Rust 层是 Tauri 应用的骨架，职责精简而关键：管理 Python Sidecar 的生命周期，充当前端与 Python 之间的安全代理。

#### 4.1.1 进程管理

```rust
// 启动 Python bridge 子进程，通过 stdout 读取端口号和令牌
fn spawn_bridge(py_path: &std::path::Path) -> Result<String, String>
```

- 通过 `Command::new("python")` 启动 `bridge.py`
- Windows 下使用 `CREATE_NO_WINDOW` 标志隐藏控制台窗口
- 从子进程 stdout 逐行读取 `BRIDGE_PORT=18791` 和 `BRIDGE_TOKEN=xxx`
- 在后台线程中持续读取 stderr 并输出到 Rust 日志
- 应用启动时在 `setup()` 中自动异步调用 `start_bridge()`

#### 4.1.2 代理转发

```rust
#[tauri::command]
async fn proxy_request(path: String, method: String, body: Option<String>) -> Result<String, String>
```

- 将前端的 API 请求转发到 Python Sidecar 的 `http://127.0.0.1:{port}/{path}`
- 使用 `reqwest` 客户端发送 GET/POST/PUT 请求
- 自动注入 `X-Bridge-Token` 头进行认证
- HTTP 非 2xx 响应返回 `Err("[{status}] {body}")`，前端可据此区分成功与失败

#### 4.1.3 全局状态

```rust
static BRIDGE_PORT: AtomicU16 = AtomicU16::new(0);
static BRIDGE_TOKEN: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);
```

- `BRIDGE_PORT`: Python Sidecar 监听端口，原子变量，线程安全读取
- `BRIDGE_TOKEN`: 认证令牌，Mutex 保护，代理请求时自动注入

#### 4.1.4 计划中: 授权验证迁移到 Rust

当前 Ed25519 验签在 Python 层执行。计划迁移到 Rust 层的原因：

1. Rust 的 `ed25519-dalek` crate 性能更高，验签延迟 < 0.1ms
2. Rust 编译为原生代码，公钥硬编码在二进制中，比 Python 字节码更难篡改
3. 前端每次启动时可通过 `invoke('verify_license')` 直接在 Rust 层完成验签，无需经过 Python

### 4.2 Python Sidecar 业务层

#### 4.2.1 bridge.py -- HTTP API 网关

**文件**: [bridge.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py)

bridge.py 是整个 Python 业务的统一入口，基于 `http.server.ThreadingHTTPServer` 实现 15 个 API 端点。

**启动流程**:

```
1. 动态端口探测 (18791-18800)
2. 生成随机认证令牌 (secrets.token_hex(32))
3. 输出 BRIDGE_PORT={port} 和 BRIDGE_TOKEN={token} 到 stdout
4. 启动 ThreadingHTTPServer 监听 127.0.0.1:{port}
```

**路由表** (完整 API 清单):

| 端点 | 方法 | 受保护 | 说明 |
|---|---|---|---|
| `/api/process/start` | POST | 是 | 启动 OpenClaw 网关进程 |
| `/api/process/stop` | POST | 否 | 停止网关进程 |
| `/api/process/status` | GET | 否 | 查询进程状态 |
| `/api/log/get` | GET | 否 | 获取日志缓冲区 |
| `/api/log/clear` | POST | 否 | 清空日志缓冲区 |
| `/api/license/current` | GET | 否 | 获取当前许可证 |
| `/api/license/activate` | POST | 否 | 在线激活授权码 |
| `/api/license/authorized` | POST | 否 | 检查功能权限 |
| `/api/image/generate` | POST | 是 | AI 图片生成 |
| `/api/video/generate` | POST | 是 | AI 视频生成 |
| `/api/update/check` | GET | 否 | 检查版本更新 |
| `/api/update/do` | POST | 否 | 执行版本更新 |
| `/api/config/read` | POST | 否 | 读取 JSON 配置文件 |
| `/api/config/write` | POST | 否 | 写入 JSON 配置文件 |
| `/api/auth/profiles` | GET/PUT | 否 | 读写认证配置 |
| `/api/system/info` | GET | 否 | 获取系统信息 |

**安全中间件**:

```python
PROTECTED_PATHS = {"/api/process/start", "/api/image/generate", "/api/video/generate"}

def _route(self, method, body):
    # 1. Token 认证: 检查 X-Bridge-Token 头
    if Handler.bridge_token:
        req_token = self.headers.get("X-Bridge-Token")
        if req_token != Handler.bridge_token:
            self._error(401, "未授权的请求")
            return
    # 2. 授权校验: 受保护端点需验证有效许可证
    if path in PROTECTED_PATHS:
        if not _get_license_mgr().is_authorized():
            self._error(403, "需要有效的许可证才能使用此功能")
            return
```

**路径安全校验** (config 读写):

```python
def _safe_path(self, file_path):
    real_path = os.path.realpath(file_path)
    allowed_prefixes = (os.path.realpath(paths.base_path), os.path.realpath(paths.data_dir))
    if real_path.startswith(allowed_prefixes):
        return real_path
    return None  # 拒绝路径遍历攻击
```

#### 4.2.2 core/license_manager.py -- 授权管理

**文件**: [license_manager.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py)

核心职责：本地许可证验证 + 在线激活。

**Ed25519 验签链**:

```
服务器私钥签名 → license.json (含 signature 字段)
         ↓
客户端公钥验签 → 验证 payload 完整性
         ↓
installId 校验 → 防止许可证文件复制
         ↓
deviceId 校验 → 防止 U 盘文件夹复制 (卷序列号 + SHA256)
         ↓
expires 校验 → 检查到期时间
```

**设备绑定机制**:

```python
def device_id(self) -> str:
    # 获取 U 盘/硬盘卷序列号 (Windows API)
    root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
    ctypes.windll.kernel32.GetVolumeInformationW(root, ..., volume_serial, ...)
    # 卷序列号 + 根路径 + salt → SHA256
    raw = f"{root}|{serial}|openclaw-launcher"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

**激活流程**:

```python
def activate(self, code: str) -> dict:
    # 1. 向服务器发送: 授权码 + installId + deviceId
    # 2. 服务器验证后返回签名的 license 数据
    # 3. 客户端验签 + 校验 installId/deviceId
    # 4. 验证通过 → 保存到 license.json
    license_data = data.get("license")
    if not self.verify(license_data):
        raise LicenseError("授权服务器返回的许可证无效")
    write_json(self.paths.license_file, license_data)
```

#### 4.2.3 core/paths.py -- 路径发现

**文件**: [paths.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/paths.py)

`AppPaths` 数据类自动适配三种运行环境：

| 环境 | base_path 计算逻辑 |
|---|---|
| 开发模式 | `paths.py` → `core/` → `python/` → 项目根目录 |
| Tauri 打包 | `paths.py` → `core/` → `python/` → `resources/` → 安装根目录 |
| U盘便携 | `paths.py` → `core/` → `python/` → `OpenClaw启动/` → U盘根目录 |

关键路径属性：

| 属性 | 路径 | 用途 |
|---|---|---|
| `node_dir` | `{base}/SystemData/.core/node/` 或 `{base}/node/` | Node.js 运行时 |
| `data_dir` | `{base}/data/` | 运行时数据 |
| `state_dir` | `{base}/data/.openclaw/` | OpenClaw 状态目录 |
| `license_file` | `{base}/data/license.json` | 许可证文件 |
| `install_id_file` | `{base}/data/install_id.txt` | 安装 ID |
| `auth_profiles` | `{base}/data/.openclaw/agents/main/agent/auth-profiles.json` | API 认证配置 |

#### 4.2.4 services/process.py -- OpenClaw 进程管理

**文件**: [process.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/services/process.py)

- 启动: `node.exe start.js`，设置 `OPENCLAW_HOME`/`OPENCLAW_STATE_DIR` 环境变量
- 停止: `taskkill /F /T /PID` 强制终止进程树
- 端口清理: `netstat -aon` 查找 18790 端口占用进程并终止
- 日志流: 后台线程读取 stdout，通过回调推送至日志缓冲区

#### 4.2.5 services/image_api.py -- AI 图片生成

**文件**: [image_api.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/services/image_api.py)

- 协议: OpenAI Images API (`/v1/images/generations`, `/v1/images/edits`)
- 模型: `gpt-image-2` (通过 `constants.IMAGE_MODEL` 配置)
- 生成模式: 单图生成 / 多图批量 / 编辑模式 (multipart/form-data 上传)
- 图片提取: 支持 `b64_json` 和 `url` 两种响应格式
- 自动重试: 批量生成时单张失败自动重试

#### 4.2.6 services/video_api.py -- AI 视频生成

**文件**: [video_api.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/services/video_api.py)

- 协议: 阿里云 DashScope 异步视频生成 API
- 模型: `happyhorse-1.0-t2v` (文生视频), `happyhorse-1.0-i2v` (图生视频)
- 流程: 提交任务 → 获取 task_id → 轮询状态 (5s 间隔, 最长 600s) → 下载视频
- 图生视频: 参考图编码为 `data:image/...;base64,...` 格式内嵌请求

#### 4.2.7 services/updater.py -- 版本更新

**文件**: [updater.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/services/updater.py)

- 当前版本: 读取 `node_modules/openclaw/package.json` 的 `version` 字段
- 最新版本: 通过 `node pnpm.cjs view openclaw version` 查询 npm registry
- 执行更新: `node pnpm.cjs add openclaw@latest`，同步等待完成

### 4.3 React UI 层

#### 4.3.1 服务层: api.ts

**文件**: [api.ts](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/services/api.ts)

所有前端 API 调用统一经过 `api()` 函数：

```typescript
async function proxyRequest(path, method, body?) {
  const { invoke } = await import('@tauri-apps/api/core');
  return await invoke<string>('proxy_request', { path, method, body: body ? JSON.stringify(body) : null });
}

export async function api<T>(path, method, body?): Promise<T> {
  const result = await proxyRequest(path, method, body);
  // 错误检测: 如果响应包含 error 字段，抛出错误对象
  if (result && typeof result === 'object' && 'error' in result) {
    throw { error: result.error };
  }
  return result as T;
}
```

导出的 API 命名空间：

| 命名空间 | 方法 |
|---|---|
| `processApi` | `start()`, `stop()`, `status()` |
| `logApi` | `get()`, `clear()` |
| `licenseApi` | `current()`, `activate(code)`, `authorized(feature?)` |
| `imageApi` | `generate(params)` |
| `videoApi` | `generate(params)` |
| `updateApi` | `check()`, `do()` |
| `configApi` | `read(path, default?)`, `write(path, data)` |
| `systemApi` | `info()` |

#### 4.3.2 状态管理: appStore.ts

**文件**: [appStore.ts](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/stores/appStore.ts)

```typescript
interface AppState {
  currentPage: string;                // 当前页面 key
  serviceRunning: boolean;            // 网关是否运行
  serviceStatus: 'idle' | 'starting' | 'running' | 'stopping' | 'stopped';
  isAuthorized: boolean;              // 是否已授权 (权威来源: Python Bridge)
  isLicenseChecking: boolean;         // 启动时正在检查授权
  licenseInfo: License | null;        // 许可证详情
  apiConfigured: boolean;             // API 是否已配置
}
```

关键设计：

- `localStorage` 仅作 UI 缓存，应用启动时必须调用 `licenseApi.current()` 获取权威状态
- `checkLicense()` 在 App.tsx 的 `useEffect` 中自动执行，覆盖 localStorage 中的值

#### 4.3.3 业务页面

| 页面 | 组件 | 功能 |
|---|---|---|
| 服务日志 | TerminalPage | 终端风格日志查看器，语法高亮，自动滚动，支持 Ctrl+C/A |
| 授权码 | LicensePage | 输入 OC-PRO-XXXX 格式授权码，在线激活，显示授权状态 |
| AI 生图 | ImagePage | 单图生成 + 一键三图（主图/白底/详情），图片编辑 |
| AI 视频 | VideoPage | 文生视频 + 图生视频，DashScope 异步任务轮询 |
| 广告视频 | StoryboardPage | 三栏布局：场景列表 / 工作区（三视图+首尾帧+九宫格）/ 参数面板 |

#### 4.3.4 通用组件库

**文件**: [common/index.tsx](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/components/common/index.tsx)

| 组件 | 变体 | 说明 |
|---|---|---|
| Button | primary / danger / success / quiet / default | 统一按钮样式 |
| Input | - | 带 focus:ring-accent 的输入框 |
| TextArea | - | 可调大小文本域 |
| Select | - | 下拉选择器 |
| Modal | - | 模态弹窗 (点击背景关闭) |
| Toast | success / error / info | 全局通知 (Zustand store 驱动) |
| Loading | - | 旋转加载指示器 |
| FieldLabel | required 标记 | 表单字段标签 |

#### 4.3.5 导航与布局

**文件**: [Sidebar.tsx](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/components/sidebar/Sidebar.tsx)

```
┌──────────────────────────────┐
│  [Logo] 永浩科技              │  ← 品牌 Header (由主题控制)
│         智能AI服务平台         │
├──────────────────────────────┤
│  ▶ 启动服务                   │  ← 主操作按钮
├──────────────────────────────┤
│  工作台                       │
│  LOG  服务日志                │
│  AD   广告视频  [受保护]      │
│  IMG  AI 生图   [受保护]      │
│  VID  AI 视频   [受保护]      │
│                               │
│  配置                         │
│  LIC  授权码                  │
│  KEY  API 配置                │
│  BOT  飞书机器人              │
│                               │
│  维护                         │
│  WEB  网页界面                │
│  UP   检查更新                │
│  DOC  帮助文档                │
├──────────────────────────────┤
│  ■ 停止服务                   │
│  ● 服务运行中                 │
└──────────────────────────────┘
```

受保护页面（广告视频/AI生图/AI视频）在未授权时点击会弹出提示并跳转授权页。

### 4.4 云端授权服务器

**文件**: [server.py](file:///d:/Axiangmu/AUSTART/license_server/server.py)

#### 4.4.1 端点清单

| 端点 | 方法 | 认证 | 说明 |
|---|---|---|---|
| `/health` | GET | 无 | 健康检查 |
| `/public-key` | GET | 无 | 获取 Ed25519 公钥 (Base64) |
| `/activate` | POST | 无 | 激活授权码，返回签名的 license |
| `/admin` | GET | 无 | 管理后台 HTML 页面 |
| `/admin/api/codes` | GET | Admin Token | 获取所有授权码列表 |
| `/admin/api/codes` | POST | Admin Token | 批量生成授权码 |
| `/admin/api/codes/toggle` | POST | Admin Token | 启用/停用授权码 |
| `/admin/api/codes/clear` | POST | Admin Token | 清空所有授权码 |
| `/admin/api/codes/hash` | POST | Admin Token | 计算授权码哈希 |
| `/admin/api/codes/delete` | POST | Admin Token | 删除授权码 |

#### 4.4.2 授权码生成

```python
def make_code(edition: str = "PRO") -> str:
    # 格式: OC-{EDITION}-XXXX-XXXX-XXXX-XXXX
    # 字母表: ABCDEFGHJKLMNPQRSTUVWXYZ23456789 (去除 I/O/0/1 避免混淆)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chunks = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return f"OC-{edition.upper()}-" + "-".join(chunks)
```

#### 4.4.3 激活流程

```python
def activate_code(body):
    # 1. 哈希授权码: SHA256("openclaw-license-v1:" + code.upper())
    # 2. 查找 codes 表, 检查 disabled/activations
    # 3. 构建 license payload (licenseId/licensee/edition/features/expires/installId/deviceId)
    # 4. Ed25519 私钥签名 payload 的 canonical JSON
    # 5. 插入 activations 表
    # 6. 返回带签名的 license 数据
```

#### 4.4.4 管理后台

内嵌单文件 HTML 应用，功能包括：

- 生成授权码（指定客户名/版本/数量/到期日/激活次数/功能列表）
- 查看授权码列表（尾号/客户/版本/状态/激活数）
- 启用/停用/删除授权码
- 导出授权码为 TXT 文件
- 统计面板（总数/已激活/可用/停用）

---

## 5. 数据流转流程

### 5.1 启动流程

```
用户双击 OpenClaw.exe
       │
       ▼
Tauri::setup()
       │
       ├── 初始化 tauri-plugin-shell
       ├── 初始化 tauri-plugin-log (debug 模式)
       │
       ▼
tauri::async_runtime::spawn → start_bridge()
       │
       ├── 解析 bridge.py 路径 (Resource 目录 / 项目相对路径)
       │
       ▼
Command::new("python").arg(bridge.py)
       │
       │  ← stdout: BRIDGE_PORT=18791
       │  ← stdout: BRIDGE_TOKEN=a3f8b2c1...
       │
       ├── BRIDGE_PORT.store(18791)
       ├── BRIDGE_TOKEN = Some("a3f8b2c1...")
       │
       ▼
WebView 加载前端 (index.html)
       │
       ├── App.tsx mount
       │     │
       │     ▼
       │   checkLicense()
       │     │
       │     ▼ invoke('proxy_request', {path:'/api/license/current', method:'GET'})
       │     │
       │     │  Rust → GET http://127.0.0.1:18791/api/license/current
       │     │         Header: X-Bridge-Token: a3f8b2c1...
       │     │
       │     │  ← Python: {"license": {...}} 或 {"license": null}
       │     │
       │     ▼ 设置 isAuthorized / licenseInfo
       │
       ▼
渲染 UI (根据 isAuthorized 显示不同状态)
```

### 5.2 授权激活流程

```
用户在 LicensePage 输入授权码: OC-PRO-XXXX-XXXX-XXXX-XXXX
       │
       ▼
licenseApi.activate(code)
       │
       ▼ invoke('proxy_request', {path:'/api/license/activate', method:'POST', body:{code}})
       │
       │  Rust → POST http://127.0.0.1:18791/api/license/activate
       │         Header: X-Bridge-Token: xxx
       │         Body: {"code":"OC-PRO-XXXX-XXXX-XXXX-XXXX"}
       │
       ▼ Python bridge.py: _license_activate(body)
       │
       ▼ LicenseManager.activate(code)
       │
       ├── 读取 install_id (首次则生成 UUID)
       ├── 计算 device_id (卷序列号 SHA256)
       │
       ▼ HTTPS POST https://license.heang.top/activate
       │         Body: {"code":"OC-PRO-...", "installId":"...", "deviceId":"...", "appVersion":"desktop"}
       │
       ▼ 云端服务器: activate_code()
       │
       ├── code_hash = SHA256("openclaw-license-v1:" + code)
       ├── 查询 codes 表, 校验 disabled / max_activations
       ├── 构建 payload: {licenseId, licensee, edition, features, expires, installId, deviceId, activatedAt}
       ├── Ed25519 私钥签名 payload → signature
       ├── 插入 activations 表
       │
       ▼ 返回 {"license": {payload + signature}}
       │
       ▼ Python: LicenseManager.verify(license_data)
       │
       ├── Ed25519 公钥验签
       ├── installId 匹配校验
       ├── deviceId 匹配校验 (如果有)
       ├── expires 过期校验
       │
       ├── 验证通过 → write_json(license.json, license_data)
       │
       ▼ 返回 {"license": license_data}
       │
       ▼ 前端: setLicenseInfo(license) → setAuthorized(true) → localStorage 缓存
       │
       ▼ 1.5s 后自动跳转到 TerminalPage
```

### 5.3 功能调用流程 (以 AI 生图为例)

```
用户在 ImagePage 填写表单, 点击"生成图片"
       │
       ▼ imageApi.generate({baseUrl, apiKey, prompt, size, count})
       │
       ▼ invoke('proxy_request', {path:'/api/image/generate', method:'POST', body:{...}})
       │
       │  Rust → POST http://127.0.0.1:18791/api/image/generate
       │         Header: X-Bridge-Token: xxx
       │
       ▼ Python bridge.py: _route("POST", body)
       │
       ├── [中间件1] Token 认证: X-Bridge-Token 匹配
       ├── [中间件2] 授权校验: license_manager.is_authorized() → True
       │
       ▼ _image_generate(body)
       │
       ├── 参数校验: baseUrl / prompt 不能为空
       ├── base64 data URL → 临时文件 (编辑模式)
       │
       ▼ ImageApiClient.generate_many()
       │
       ├── 构建 OpenAI Images API 请求
       ├── 发送到中转站 (baseUrl/v1/images/generations)
       ├── 提取 base64 图片数据
       │
       ▼ 返回 {"images": ["base64..."], "count": 1}
       │
       ▼ 前端: setResultImage("data:image/png;base64,...")
       │
       ▼ 渲染 <img> 显示生成结果
```

### 5.4 主题切换流程 (新架构)

```
用户输入新授权码 (属于不同商家)
       │
       ▼ licenseApi.activate(code)
       │
       ▼ Python → HTTPS → 云端 /activate
       │
       ▼ 云端: 查询 codes → 获取 merchant_id → 查询 merchants 表 → 获取 theme_json
       │
       ▼ 返回 {"license": {...}, "theme": {brand, colors, navItems, fonts, ...}}
       │                                              ↑
       │                              新增: 激活响应附带 theme 字段
       ▼ Python: 保存 theme.json → {data_dir}/theme.json
       │
       ▼ 新增 API: GET /api/theme/current → 返回 theme.json 内容
       │
       ▼ 前端: ThemeProvider 加载 theme
       │
       ├── 读取 theme.json (或 /api/theme/current)
       ├── 将 colors 映射为 CSS 变量
       ├── document.documentElement.style.setProperty('--color-accent', theme.colors.accent)
       ├── Tailwind 通过 CSS 变量引用: bg-[var(--color-accent)]
       │
       ▼ UI 立即刷新为新商家品牌
```

---

## 6. 数据库模型设计

### 6.1 云端 SQLite

#### 6.1.1 现有表结构

**codes 表** (授权码):

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `code_hash` | TEXT | PRIMARY KEY | SHA256("openclaw-license-v1:" + code) |
| `code_label` | TEXT | NOT NULL | 授权码尾号 (最后 9 字符) |
| `full_code` | TEXT | NOT NULL DEFAULT '' | 完整授权码 (仅生成时存储) |
| `licensee` | TEXT | NOT NULL | 客户名称 |
| `edition` | TEXT | NOT NULL | 版本 (pro/basic/enterprise) |
| `features_json` | TEXT | NOT NULL | 功能列表 JSON |
| `expires` | TEXT | NOT NULL | 到期日期 |
| `max_activations` | INTEGER | NOT NULL DEFAULT 1 | 最大激活次数 |
| `disabled` | INTEGER | NOT NULL DEFAULT 0 | 是否停用 |
| `created_at` | TEXT | NOT NULL | 创建时间 (UTC ISO) |

**activations 表** (激活记录):

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增 ID |
| `code_hash` | TEXT | NOT NULL | 关联授权码 |
| `install_id` | TEXT | NOT NULL | 安装 ID |
| `device_id` | TEXT | NOT NULL | 设备 ID |
| `license_json` | TEXT | NOT NULL | 签名后的许可证 JSON |
| `activated_at` | TEXT | NOT NULL | 激活时间 (UTC ISO) |
| - | UNIQUE(code_hash, install_id) | | 同一授权码+安装ID唯一 |

#### 6.1.2 新增表结构 (主题系统)

**merchants 表** (商家):

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `merchant_id` | TEXT | PRIMARY KEY | 商家唯一标识 (如 `yonghao_tech`) |
| `name` | TEXT | NOT NULL | 商家显示名称 (如 "永浩科技") |
| `subtitle` | TEXT | NOT NULL DEFAULT '' | 副标题 (如 "智能AI服务平台") |
| `theme_json` | TEXT | NOT NULL DEFAULT '{}' | 主题配置 JSON (完整 theme 结构) |
| `logo_url` | TEXT | NOT NULL DEFAULT '' | Logo 图片 URL 或 base64 |
| `created_at` | TEXT | NOT NULL | 创建时间 |

**codes 表变更** (新增字段):

| 新增字段 | 类型 | 说明 |
|---|---|---|
| `merchant_id` | TEXT | 关联商家 (NULL 表示使用默认主题) |

**关联关系**:

```
merchants (1) ──→ (N) codes (1) ──→ (N) activations
 merchant_id         code_hash         code_hash
```

### 6.2 本地文件

#### 6.2.1 license.json -- 签名许可证

```json
{
  "licenseId": "a3f8b2c1d4e5...",
  "licensee": "永浩科技",
  "edition": "pro",
  "features": ["openclaw", "image", "video", "storyboard"],
  "expires": "2027-05-01",
  "installId": "550e8400-e29b-41d4-a716-446655440000",
  "deviceId": "abc123def456...",
  "activatedAt": "2026-05-04T12:00:00+00:00",
  "signature": "BASE64_ED25519_SIGNATURE"
}
```

**安全属性**:

- `signature` 由服务器 Ed25519 私钥对 payload 的 canonical JSON 签名
- payload = 除 `signature` 外的所有字段，按 key 排序、紧凑 JSON
- 客户端验证时移除 `signature` 后重新构建 canonical JSON 进行验签

#### 6.2.2 theme.json -- 主题配置 (新增)

```json
{
  "merchantId": "yonghao_tech",
  "brand": {
    "name": "永浩科技",
    "subtitle": "智能AI服务平台",
    "logoBase64": "data:image/png;base64,..."
  },
  "colors": {
    "appBg": "#F3F4F5",
    "sidebarBg": "#F9F9FA",
    "surface": "#FFFFFF",
    "surfaceAlt": "#F6F7F8",
    "accent": "#1A56DB",
    "accentHover": "#1444AD",
    "accentSoft": "#E4E8F0",
    "accentInk": "#0F327F",
    "text": "#1E2A3A",
    "textMuted": "#64748B",
    "textSubtle": "#94A3B8",
    "success": "#059669",
    "warning": "#D97706",
    "danger": "#DC2626",
    "terminalBg": "#0F172A",
    "terminalHeader": "#1E293B",
    "terminalText": "#34D399"
  },
  "fonts": {
    "display": "Microsoft YaHei UI",
    "mono": "Consolas"
  },
  "navItems": [
    { "key": "terminal", "label": "服务日志", "group": "工作台" },
    { "key": "storyboard", "label": "广告视频", "group": "工作台", "accent": true },
    { "key": "image", "label": "AI 生图", "group": "工作台", "accent": true },
    { "key": "video", "label": "AI 视频", "group": "工作台", "accent": true },
    { "key": "license", "label": "授权码", "group": "配置" },
    { "key": "api", "label": "API 配置", "group": "配置" },
    { "key": "web", "label": "网页界面", "group": "维护" },
    { "key": "update", "label": "检查更新", "group": "维护" },
    { "key": "help", "label": "帮助文档", "group": "维护" }
  ],
  "window": {
    "title": "永浩科技 - 智能AI服务平台",
    "width": 1200,
    "height": 800
  }
}
```

#### 6.2.3 install_id.txt -- 安装标识

- 内容: UUID v4 字符串 (如 `550e8400-e29b-41d4-a716-446655440000`)
- 首次运行时自动生成
- 用于绑定许可证到特定安装实例

---

## 7. 主题系统架构

### 7.1 设计目标

| 目标 | 说明 |
|---|---|
| 运行时切换 | 授权码激活时自动应用新主题，无需重启应用 |
| 零代码新增商家 | 管理后台配置商家主题 → 生成授权码 → 客户激活即生效，无需改动客户端代码 |
| 安全分离 | UI 主题可被用户修改但不影响功能权限，功能由 Ed25519 签名的 license 保护 |
| 渐进式降级 | theme.json 缺失或损坏时回退到默认永浩科技主题 |

### 7.2 服务端: 商家与主题管理

```
管理后台操作流程:

1. 创建商家
   ├── 填写: merchant_id, name, subtitle
   ├── 上传 Logo (存储为 base64 或 URL)
   ├── 配置主题: 颜色 / 字体 / 导航项 / 窗口标题
   └── 保存到 merchants 表 (theme_json 字段)

2. 生成授权码
   ├── 选择: 商家 (merchant_id)
   ├── 填写: 客户名 / 版本 / 到期日 / 功能
   └── codes 表记录 merchant_id 关联

3. 激活响应增强
   ├── 原响应: {"license": {...}}
   └── 新响应: {"license": {...}, "theme": {brand, colors, navItems, ...}}
       └── theme 来自 codes.merchant_id → merchants.theme_json
```

**新增管理后台 API**:

| 端点 | 方法 | 说明 |
|---|---|---|
| `/admin/api/merchants` | GET | 获取所有商家列表 |
| `/admin/api/merchants` | POST | 创建商家 |
| `/admin/api/merchants/{id}` | PUT | 更新商家主题配置 |
| `/admin/api/merchants/{id}` | DELETE | 删除商家 |

### 7.3 传输: 激活响应附带主题

当前 `/activate` 响应:

```json
{
  "license": { "licenseId": "...", "licensee": "...", "signature": "..." }
}
```

新增后 `/activate` 响应:

```json
{
  "license": { "licenseId": "...", "licensee": "...", "signature": "..." },
  "theme": {
    "merchantId": "yonghao_tech",
    "brand": { "name": "...", "subtitle": "...", "logoBase64": "..." },
    "colors": { "accent": "#1A56DB", ... },
    "navItems": [ ... ],
    "window": { "title": "..." }
  }
}
```

**设计考量**: theme 不参与 Ed25519 签名。原因：

1. theme 数据量大，签名后 license.json 会膨胀
2. theme 是 UI 展示数据，篡改不影响功能安全
3. 功能权限由 `license.features` 签名保护，theme 只影响外观

### 7.4 客户端: 主题持久化与注入

```
激活成功
   │
   ▼ Python: 收到 {license, theme}
   │
   ├── 保存 license → data/license.json (现有逻辑)
   ├── 保存 theme  → data/theme.json (新增)
   │
   ▼ 新增 API 端点: GET /api/theme/current
   │
   ▼ 前端: ThemeProvider 组件
   │
   ├── useEffect: 调用 /api/theme/current 获取主题数据
   │
   ├── CSS 变量注入:
   │   document.documentElement.style.setProperty('--color-accent', theme.colors.accent)
   │   document.documentElement.style.setProperty('--color-surface', theme.colors.surface)
   │   ... (所有 colors 字段)
   │
   ├── Tailwind 适配:
   │   方案 A: tailwind.config 引用 CSS 变量
   │     colors: { accent: 'var(--color-accent)' }
   │   方案 B: 使用 Tailwind 任意值
   │     className="bg-[var(--color-accent)]"
   │
   ├── 导航项注入:
   │   Sidebar 组件从 theme.navItems 渲染导航，而非硬编码
   │
   ├── 品牌信息注入:
   │   Sidebar BrandHeader 显示 theme.brand.name / subtitle / logo
   │   Tauri 窗口标题 → theme.window.title
   │
   └── 默认主题:
       theme.json 不存在时使用内置默认值 (永浩科技主题)
```

### 7.5 theme_json 完整数据结构定义

```typescript
interface ThemeConfig {
  /** 商家唯一标识 */
  merchantId: string;

  /** 品牌信息 */
  brand: {
    /** 显示名称 (侧边栏标题、窗口标题) */
    name: string;
    /** 副标题 (侧边栏描述) */
    subtitle: string;
    /** Logo 图片 (data:image/png;base64,... 或 URL) */
    logoBase64?: string;
  };

  /** 颜色配置 (所有值均为 HEX 格式) */
  colors: {
    appBg: string;          // 应用背景色
    sidebarBg: string;      // 侧边栏背景色
    surface: string;        // 卡片/面板背景色
    surfaceAlt: string;     // 次级面板背景色
    accent: string;         // 主强调色 (按钮、选中态)
    accentHover: string;    // 强调色悬停态
    accentSoft: string;     // 强调色柔和态 (浅底色)
    accentInk: string;      // 强调色深色 (选中文字)
    text: string;           // 主文字色
    textMuted: string;      // 次要文字色
    textSubtle: string;     // 提示文字色
    success: string;        // 成功状态色
    warning: string;        // 警告状态色
    danger: string;         // 危险状态色
    terminalBg: string;     // 终端背景色
    terminalHeader: string; // 终端头部色
    terminalText: string;   // 终端文字色
  };

  /** 字体配置 */
  fonts: {
    display: string;  // 标题字体
    mono: string;     // 等宽字体
  };

  /** 导航项配置 (可定制显示哪些页面、标签名、分组) */
  navItems: Array<{
    key: string;       // 页面标识
    label: string;     // 显示名称
    desc?: string;     // 描述文字
    icon?: string;     // 图标标识
    group: string;     // 分组名
    accent?: boolean;  // 是否为强调项 (加粗)
  }>;

  /** 窗口配置 */
  window: {
    title: string;     // 窗口标题
    width?: number;    // 默认宽度
    height?: number;   // 默认高度
  };
}
```

### 7.6 旧版主题系统与新版对比

| 维度 | 旧版 (tkinter) | 新版 (React + Tauri) |
|---|---|---|
| 主题存储 | `themes/merchants/{id}/theme.json` | 云端 `merchants.theme_json` + 本地 `data/theme.json` |
| 切换方式 | 编译时 (替换 constants.py 再打包) | 运行时 (激活即生效，ThemeProvider 动态注入) |
| 主题注册 | `themes/registry.json` | 云端 `merchants` 表 |
| 颜色映射 | Python dict → tkinter configure | JSON → CSS 变量 → Tailwind class |
| 导航定制 | 硬编码 | `navItems` 数组驱动渲染 |

---

## 8. 安全架构

### 8.1 Ed25519 签名链

```
┌──────────────────────────────────────────────────────────┐
│                    签名链完整流程                           │
│                                                          │
│  服务器端                                                 │
│  ┌─────────────┐     ┌──────────────┐                   │
│  │ private_key  │────▶│ sign(payload) │──▶ signature     │
│  │ (b64 文件)   │     └──────────────┘                   │
│  └─────────────┘                                         │
│         │                                                │
│         ▼ 派生                                           │
│  ┌─────────────┐                                        │
│  │ public_key   │──── 分发给客户端 (硬编码)               │
│  │ (b64)        │                                        │
│  └─────────────┘                                         │
│                                                          │
│  客户端                                                   │
│  ┌─────────────┐     ┌──────────────┐                   │
│  │ public_key   │────▶│ verify(payload, │──▶ True/False  │
│  │ (硬编码常量) │     │   signature)   │                  │
│  └─────────────┘     └──────────────┘                   │
│                                                          │
│  payload = canonical(除signature外的所有字段)              │
│  canonical = JSON(sort_keys, compact, ensure_ascii=False) │
└──────────────────────────────────────────────────────────┘
```

**公钥**: `njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4=` (Base64)  
**签名算法**: Ed25519 (RFC 8032)  
**签名长度**: 64 bytes  
**编码**: Base64

### 8.2 Bridge Token 认证

```
Bridge 启动:
  token = secrets.token_hex(32)  # 64 字符随机 hex
  stdout: BRIDGE_TOKEN={token}

Rust 读取:
  BRIDGE_TOKEN = Some(token)

每次代理请求:
  req.header("X-Bridge-Token", token)

Bridge 验证:
  if request.X-Bridge-Token != Handler.bridge_token:
      → 401 Unauthorized
```

**目的**: 防止本机其他程序直接调用 Python API 绕过 Tauri 层。Token 每次启动随机生成，仅 Rust 层和 Python 层知晓。

### 8.3 路径安全校验

```python
def _safe_path(self, file_path: str) -> str | None:
    # 1. 解析真实路径 (处理符号链接和相对路径)
    real_path = os.path.realpath(file_path)
    # 2. 仅允许 base_path 和 data_dir 内的路径
    allowed_prefixes = (
        os.path.realpath(paths.base_path),
        os.path.realpath(paths.data_dir)
    )
    # 3. 路径遍历攻击防护: ../../etc/passwd → 拒绝
    if real_path.startswith(allowed_prefixes):
        return real_path
    return None
```

### 8.4 CSP 策略

当前 Tauri CSP 配置:

```
default-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob: http: https:;
connect-src 'self' http://127.0.0.1:* http://localhost:*
```

| 指令 | 值 | 理由 |
|---|---|---|
| `default-src` | `'self'` | 默认仅允许同源 |
| `style-src` | `'unsafe-inline'` | Tailwind CSS 需要内联样式 |
| `img-src` | `data: blob: http: https:` | base64 图片 + 外部 Logo URL |
| `connect-src` | `http://127.0.0.1:*` | 连接 Python Sidecar |

### 8.5 硬件绑定

| 绑定维度 | 实现 | 防护场景 |
|---|---|---|
| installId | UUID v4，存储在 `data/install_id.txt` | 防止许可证文件复制到另一台电脑 |
| deviceId | Windows 卷序列号 SHA256 | 防止 U 盘整盘复制（不同盘卷序列号不同） |
| 二次验证 | `license.deviceId` 存在时必须匹配 | 服务器可选择是否启用硬件绑定 |

**局限性**: 卷序列号在磁盘格式化后会变化。此时需重新激活。

### 8.6 安全边界总结

| 攻击面 | 防护措施 | 残余风险 |
|---|---|---|
| 修改 license.json | Ed25519 签名校验 | 无 (除非泄露私钥) |
| 复制 license.json 到其他 U 盘 | installId + deviceId 校验 | 低 (需同时复制 install_id.txt 且卷序列号相同) |
| 直接调用 Python API 绕过 UI | X-Bridge-Token 认证 | 低 (Token 随机且每次启动不同) |
| 修改 theme.json 篡改品牌 | 主题数据不参与签名 | 可接受 (仅外观，不影响功能) |
| 路径遍历攻击 | `_safe_path()` 校验 | 无 |
| 内存修改 (Cheat Engine) | Rust 原生代码 + Python 运行时 | 低 (需要专业技能) |

---

## 9. 非功能性需求

### 9.1 性能

| 指标 | 目标值 | 测量方式 |
|---|---|---|
| 应用冷启动 (Tauri → WebView 就绪) | < 1.5s | 进程启动到 WebView `DOMContentLoaded` |
| Python Sidecar 启动 | < 1.5s | bridge.py 启动到输出 BRIDGE_PORT |
| 端到端启动 (双击图标到 UI 可交互) | < 3s | 端到端计时 |
| API 调用延迟 (前端 → Python → 前端) | < 50ms | 本地回环 |
| Ed25519 验签 | < 1ms | Python cryptography 库 |
| 内存占用 (空闲) | < 150MB | 任务管理器 |
| 日志缓冲区 | 最大 500 行 | `log_buffer` 自动截断 |

### 9.2 可扩展性

| 扩展场景 | 实现方式 | 代码改动量 |
|---|---|---|
| 新增商家品牌 | 管理后台创建商家 + 配置主题 + 生成授权码 | 零代码改动 |
| 新增功能模块 | Python 新增 service + bridge.py 注册端点 + 前端新增页面 | 3 处改动 |
| 新增 AI 模型 | 修改 `constants.py` 中的模型常量 | 1 处改动 |
| 新增导航项 | theme.navItems 中添加条目 | 配置改动 |
| 迁移 FastAPI | 替换 bridge.py 的 HTTP 框架，保持端点不变 | 1 处改动 |

### 9.3 可维护性

| 维度 | 当前实现 | 改进方向 |
|---|---|---|
| Python 路由 | 手写 `if/elif` 路由 | 迁移 FastAPI 装饰器路由 |
| 前端 API 封装 | 单文件 `api.ts` | 可按领域拆分 |
| 错误处理 | Rust 层区分 HTTP 状态码 + 前端检测 error 字段 | 统一错误码体系 |
| 日志 | Python 内存缓冲区 + 前端轮询 | 可改为 SSE/WebSocket 推送 |
| 类型安全 | TypeScript 类型定义 + Python type hints | 可考虑 gRPC/Protobuf 契约 |

### 9.4 U盘便携性

| 需求 | 实现 |
|---|---|
| 无需安装 | 所有运行时内嵌 U 盘，包括 Python embedded + Node.js |
| 路径自适应 | `AppPaths.discover()` 自动探测 U 盘根目录 |
| 数据与程序分离 | `data/` 目录存放用户数据，`SystemData/` 存放运行时 |
| 长路径兼容 | 自动去除 Windows `\\?\` 前缀，避免 Node.js 路径解析失败 |
| 中文路径兼容 | 全链路 UTF-8，`ensure_ascii=False` |
| 进程残留清理 | `stop()` 方法清理端口占用，避免拔出 U 盘后残留进程 |

---

## 10. 部署架构

### 10.1 U盘目录结构

```
{U盘根目录}/
├── OpenClaw.exe                    ← Tauri 打包的 EXE (含 Rust + WebView 壳)
├── _internal/                      ← Tauri 运行时 (WebView2 等)
│   └── ...
├── resources/                      ← Tauri 资源目录
│   └── python/                     ← Python Sidecar (整体打包)
│       ├── bridge.py               ← HTTP API 网关
│       ├── core/
│       │   ├── __init__.py
│       │   ├── constants.py        ← 品牌/颜色/模型常量
│       │   ├── paths.py            ← 路径发现
│       │   ├── license_manager.py  ← Ed25519 验签 + 在线激活
│       │   └── storage.py          ← JSON 读写
│       ├── services/
│       │   ├── __init__.py
│       │   ├── process.py          ← OpenClaw 进程管理
│       │   ├── image_api.py        ← AI 图片生成
│       │   ├── video_api.py        ← AI 视频生成
│       │   └── updater.py          ← 版本更新
│       └── data/
│           └── install_id.txt      ← 安装 ID (首次运行生成)
├── node/                           ← 内嵌 Node.js v24.15.0
│   ├── node.exe
│   └── node_modules/
│       └── pnpm/
├── node_modules/
│   └── openclaw/                   ← OpenClaw npm 包
│       ├── openclaw.mjs
│       ├── start.js
│       └── package.json
├── SystemData/
│   └── .core/
│       └── node/                   ← 备选 Node.js 路径
│           └── node.exe
├── data/                           ← 运行时数据目录
│   ├── .openclaw/                  ← OpenClaw 状态
│   │   ├── openclaw.json
│   │   └── agents/
│   │       └── main/agent/
│   │           └── auth-profiles.json
│   ├── license.json                ← 签名许可证
│   ├── theme.json                  ← 主题配置 (新增)
│   └── install_id.txt              ← 安装 ID
├── logo.ico                        ← 应用图标
├── start.js                        ← OpenClaw 启动脚本
├── imgapi_config.json              ← 图片 API 配置
├── video_config.json               ← 视频 API 配置
└── storyboards/                    ← 故事板数据
    ├── ad_video_project.json
    └── assets/
```

### 10.2 内嵌运行时

| 运行时 | 版本 | 路径 | 说明 |
|---|---|---|---|
| Python | 3.10+ | 系统 PATH 或内嵌 | bridge.py 执行环境 |
| Node.js | v24.15.0 | `{base}/node/` 或 `{base}/SystemData/.core/node/` | OpenClaw 网关运行时 |
| WebView2 | 系统自带 | Windows 10/11 内置 | Tauri 前端渲染引擎 |

**Python 内嵌方案** (计划中):

```
{U盘}/python-runtime/
├── python.exe              ← Windows embeddable package
├── python310.dll
├── Lib/site-packages/      ← 预装依赖
│   ├── cryptography/       ← Ed25519
│   ├── PIL/                ← Pillow
│   └── ...
└── ...
```

Tauri 配置中 `Command::new("python")` 将改为指向 `{base}/python-runtime/python.exe`，实现完全离线运行。

### 10.3 云端部署

```bash
# 部署目录
/opt/openclaw-license/
├── server.py              ← 授权服务器
├── license.db             ← SQLite 数据库
├── private_key.b64        ← Ed25519 私钥 (权限 600)
├── admin_token.txt        ← 管理员 Token (权限 600)
└── logo.ico               ← 管理后台 Logo

# systemd 服务
[Unit]
Description=OpenClaw License Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/openclaw-license/server.py serve
WorkingDirectory=/opt/openclaw-license
Environment=LICENSE_HOST=0.0.0.0
Environment=LICENSE_PORT=18791
Restart=always
User=openclaw

[Install]
WantedBy=multi-user.target
```

---

## 附录

### A. 现有代码文件清单

| 文件路径 | 行数 | 核心职责 |
|---|---|---|
| `src-tauri/src/lib.rs` | 169 | Rust 主进程: 启动 bridge + 代理转发 |
| `src-tauri/Cargo.toml` | 27 | Rust 依赖: tauri 2.11, reqwest 0.12 |
| `src-tauri/tauri.conf.json` | 46 | Tauri 配置: CSP, 打包, 窗口 |
| `python/bridge.py` | 506 | Python HTTP 网关: 15 个 API 端点 |
| `python/core/constants.py` | 95 | 品牌常量: 颜色/字体/模型/Provider |
| `python/core/paths.py` | 127 | 路径发现: U盘/开发/打包三种模式 |
| `python/core/license_manager.py` | 143 | 授权: Ed25519 验签 + 在线激活 + 硬件绑定 |
| `python/core/storage.py` | 40 | JSON 读写: read_json / write_json / update_json |
| `python/services/process.py` | 108 | OpenClaw 进程管理: 启动/停止/端口清理 |
| `python/services/image_api.py` | 100 | AI 图片: OpenAI Images API 客户端 |
| `python/services/video_api.py` | 128 | AI 视频: DashScope 异步视频生成 |
| `python/services/updater.py` | 86 | 版本更新: pnpm 查询 + 安装 |
| `src/App.tsx` | 417 | 主应用壳: 侧边栏 + 页面切换 + 弹窗 |
| `src/services/api.ts` | 96 | 前端 API 封装: proxy_request → api() |
| `src/stores/appStore.ts` | 73 | 应用状态: Zustand store |
| `src/stores/logStore.ts` | - | 日志状态: Zustand store |
| `src/types/index.ts` | 101 | TypeScript 类型定义 |
| `src/components/sidebar/Sidebar.tsx` | 125 | 侧边栏: 导航 + 状态指示 |
| `src/components/terminal/TerminalPage.tsx` | 65 | 终端日志: 语法高亮 + 自动滚动 |
| `src/components/license/LicensePage.tsx` | 128 | 授权页: 激活 + 状态显示 |
| `src/components/image/ImagePage.tsx` | 202 | 生图页: 单图/三图/编辑 |
| `src/components/video/VideoPage.tsx` | 191 | 视频页: 文生/图生视频 |
| `src/components/storyboard/StoryboardPage.tsx` | 520 | 分镜页: 三栏布局 + 九宫格 |
| `src/components/common/index.tsx` | 153 | 通用组件库 |
| `src/styles/index.css` | 30 | 全局样式 + 滚动条 |
| `tailwind.config.js` | 22 | Tailwind 主题配置 |
| `package.json` | 28 | 前端依赖 |
| `license_server/server.py` | 853 | 授权服务端 + 管理后台 |

### B. 关键端口

| 端口 | 协议 | 用途 |
|---|---|---|
| 18790 | HTTP | OpenClaw 网关 (Node.js start.js) |
| 18791-18800 | HTTP | Python Bridge (动态分配) |
| 18791 | HTTPS | 云端授权服务器 (生产环境) |
| 1420 | HTTP | Vite 开发服务器 (仅开发模式) |

### C. 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LICENSE_SERVER_URL` | `https://license.heang.top` | 授权服务器地址 |
| `LICENSE_DB` | `/opt/openclaw-license/license.db` | 云端数据库路径 |
| `LICENSE_PRIVATE_KEY_FILE` | `/opt/openclaw-license/private_key.b64` | 私钥文件路径 |
| `LICENSE_ADMIN_TOKEN_FILE` | `/opt/openclaw-license/admin_token.txt` | 管理员 Token 文件 |
| `LICENSE_HOST` | `0.0.0.0` | 授权服务器监听地址 |
| `LICENSE_PORT` | `18791` | 授权服务器监听端口 |
| `OPENCLAW_HOME` | `{base}/data/` | OpenClaw 数据目录 |
| `OPENCLAW_STATE_DIR` | `{base}/data/.openclaw/` | OpenClaw 状态目录 |

### D. 已知限制与演进方向

| 限制 | 当前状态 | 演进方向 |
|---|---|---|
| Python 路由 | 手写 if/elif | 迁移 FastAPI |
| Python 运行时 | 依赖系统 Python | 内嵌 Python embeddable |
| 日志传输 | 前端 1s 轮询 | SSE/WebSocket 推送 |
| Ed25519 验签 | Python 层 | 迁移 Rust (ed25519-dalek) |
| 主题切换 | ~~硬编码永浩科技~~ ThemeProvider + CSS 变量 | ✅ 已实现 |
| 授权码关联商家 | codes 表无 merchant_id | 新增 merchants 表 + 关联 |
| 激活响应 | ~~仅返回 license~~ 附带 theme 字段 | ✅ 客户端已处理 |
| 前端直接 fetch | 经 Rust proxy | 可直接 fetch (需放宽 CSP) |
