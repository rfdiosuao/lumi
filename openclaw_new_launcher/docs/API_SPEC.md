# OpenClaw U盘便携版桌面管理器 - API 规范文档

> **版本**: v2.0
> **日期**: 2026-05-04
> **状态**: 实施规范
> **适用范围**: 云端授权服务器、客户端 Python Sidecar、Tauri Rust IPC

---

## 目录

- [1. 系统架构概述](#1-系统架构概述)
- [2. 通用约定](#2-通用约定)
  - [2.1 认证方式](#21-认证方式)
  - [2.2 错误响应格式](#22-错误响应格式)
  - [2.3 日期与时间格式](#23-日期与时间格式)
  - [2.4 字符编码](#24-字符编码)
- [3. 数据模型定义](#3-数据模型定义)
  - [3.1 License 许可证](#31-license-许可证)
  - [3.2 Merchant 商家](#32-merchant-商家)
  - [3.3 ThemeConfig 主题配置](#33-themeconfig-主题配置)
  - [3.4 ProcessStatus 进程状态](#34-processstatus-进程状态)
  - [3.5 UpdateInfo 更新信息](#35-updateinfo-更新信息)
  - [3.6 AuthProfiles 认证配置](#36-authprofiles-认证配置)
- [4. Ed25519 签名验证](#4-ed25519-签名验证)
  - [4.1 概述](#41-概述)
  - [4.2 验证流程](#42-验证流程)
  - [4.3 规范化序列化](#43-规范化序列化)
  - [4.4 客户端验证逻辑](#44-客户端验证逻辑)
- [5. 授权码格式说明](#5-授权码格式说明)
- [Part 1: 云端授权服务器 API](#part-1-云端授权服务器-api)
  - [6. 公开端点](#6-公开端点)
  - [7. 授权激活端点](#7-授权激活端点)
  - [8. 管理后台端点](#8-管理后台端点)
  - [9. 商家管理端点（新增）](#9-商家管理端点新增)
- [Part 2: 客户端 Python Sidecar API](#part-2-客户端-python-sidecar-api)
  - [10. 进程管理](#10-进程管理)
  - [11. 日志管理](#11-日志管理)
  - [12. 授权管理](#12-授权管理)
  - [13. AI 图片生成](#13-ai-图片生成)
  - [14. AI 视频生成](#14-ai-视频生成)
  - [15. 版本更新](#15-版本更新)
  - [16. 配置读写](#16-配置读写)
  - [17. 认证配置管理](#17-认证配置管理)
  - [18. 系统信息](#18-系统信息)
  - [19. 主题配置（新增）](#19-主题配置新增)
- [Part 3: Tauri Rust IPC Commands](#part-3-tauri-rust-ipc-commands)
  - [20. 现有命令](#20-现有命令)
  - [21. 计划改造命令](#21-计划改造命令)
- [附录 A: 端口分配](#附录-a-端口分配)
- [附录 B: 受保护端点清单](#附录-b-受保护端点清单)
- [附录 C: 错误码速查表](#附录-c-错误码速查表)

---

## 1. 系统架构概述

OpenClaw 桌面管理器采用三层 API 架构，各层职责明确：

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端 (React/WebView)                       │
│                     src/services/api.ts 统一调用                   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Tauri invoke (IPC)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Tauri Rust 层 (src-tauri/src/lib.rs)            │
│           进程内 IPC 命令 + Python Sidecar 生命周期管理             │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP (127.0.0.1:18791~18800)
                           │ X-Bridge-Token 认证
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│               Python Sidecar (python/bridge.py)                   │
│              本地 HTTP 服务，承载业务逻辑与状态管理                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTPS (license.heang.top)
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              云端授权服务器 (license_server/server.py)              │
│           授权码管理、许可证签发、商家主题管理                       │
└──────────────────────────────────────────────────────────────────┘
```

**通信链路**：

| 链路 | 协议 | 认证方式 | 说明 |
|------|------|----------|------|
| 前端 -> Rust | Tauri IPC | 进程内调用 | 无网络开销 |
| Rust -> Python | HTTP/1.1 | X-Bridge-Token | 本机回环，Token 随机生成 |
| Python -> 云端 | HTTPS | 无（公开端点）/ 请求体参数 | 外网通信，User-Agent 标识 |
| 云端管理后台 | HTTPS | X-Admin-Token | 管理员操作需认证 |

---

## 2. 通用约定

### 2.1 认证方式

#### X-Bridge-Token（Python Sidecar 认证）

Python Sidecar 启动时生成 64 字符的十六进制随机令牌，通过 stdout 输出给 Rust 层：

```
BRIDGE_PORT=18793
BRIDGE_TOKEN=a3f8c1...（64字符hex）
```

此后所有对 Sidecar 的 HTTP 请求必须在 Header 中携带此令牌：

```
X-Bridge-Token: a3f8c1d2e4b56789abcdef0123456789abcdef0123456789abcdef0123456789a
```

- 令牌不匹配时返回 HTTP 401
- Rust 层通过 `BRIDGE_TOKEN` 全局变量存储并在 `proxy_request` 中自动附加
- 令牌仅在本机回环接口上传输，不暴露到外网

#### X-Admin-Token（云端管理后台认证）

管理后台的写操作（`/admin/api/*`）需在 Header 中携带管理员令牌：

```
X-Admin-Token: <admin-secret>
```

具体 Token 值由服务端环境变量配置，本文档不记录。

### 2.2 错误响应格式

所有 API 层统一使用以下 JSON 错误格式：

```json
{
  "error": "错误描述文本"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| error | string | 人类可读的错误描述，中文 |

**Rust 层错误传递**：当 Python Sidecar 返回非 2xx 状态码时，Rust `proxy_request` 将错误包装为：

```
Err("[HTTP状态码] 响应体文本")
```

例如：`Err("[400] {\"error\": \"授权码不能为空\"}")`

前端 `api.ts` 在捕获后自动清理前缀，提取纯错误信息。

### 2.3 日期与时间格式

| 场景 | 格式 | 示例 |
|------|------|------|
| 许可证到期日 | ISO 8601 日期 | `2027-05-01` |
| 激活时间戳 | ISO 8601 日期时间 | `2025-01-01T00:00:00+00:00` |
| 健康检查时间 | ISO 8601 日期时间 | `2026-05-03T12:03:35+00:00` |

### 2.4 字符编码

所有请求和响应均使用 UTF-8 编码。JSON 响应中非 ASCII 字符不转义（`ensure_ascii=False`）。

---

## 3. 数据模型定义

### 3.1 License 许可证

许可证是系统的核心数据结构，由云端签发，客户端验证后本地持久化到 `data/license.json`。

```typescript
interface License {
  /** 许可证唯一标识 */
  licenseId: string;
  /** 被授权人/客户名称 */
  licensee: string;
  /** 授权版本: "pro" | "enterprise" | "starter" */
  edition: string;
  /** 到期日期，null 表示永久有效 */
  expires: string | null;
  /** 授权功能列表 */
  features: string[];
  /** 安装唯一标识（UUID v4），绑定到安装实例 */
  installId: string;
  /** 设备硬件指纹（SHA-256），绑定到物理机器 */
  deviceId?: string;
  /** 激活时间 */
  activatedAt: string;
  /** Ed25519 签名（Base64 编码），签名内容为除 signature 外的所有字段 */
  signature: string;
  /** 商家主题配置（新增字段，由商家管理模块注入） */
  theme?: ThemeConfig;
}
```

**features 功能标识**：

| 值 | 说明 | 受保护端点 |
|----|------|-----------|
| openclaw | OpenClaw 网关服务 | `/api/process/start` |
| image | AI 图片生成 | `/api/image/generate` |
| video | AI 视频生成 | `/api/video/generate` |
| storyboard | 广告视频工作台 | `/api/process/start`（间接） |

**本地存储路径**：`{base_path}/data/license.json`

**验证规则**（客户端执行）：

1. Ed25519 签名验证通过
2. `installId` 匹配当前安装实例
3. 若存在 `deviceId`，必须匹配当前设备硬件指纹
4. 若存在 `expires`，当前日期不得晚于到期日

### 3.2 Merchant 商家

商家数据结构用于主题系统，管理员在云端创建商家并配置其主题样式。

```typescript
interface Merchant {
  /** 商家唯一标识 */
  merchantId: string;
  /** 商家名称 */
  name: string;
  /** 商家副标题/口号 */
  subtitle: string;
  /** 主题配置 JSON（完整 ThemeConfig 结构） */
  themeJson: ThemeConfig;
  /** 商家 Logo URL */
  logoUrl: string;
  /** 创建时间 */
  createdAt: string;
  /** 最后更新时间 */
  updatedAt: string;
}
```

### 3.3 ThemeConfig 主题配置

主题配置定义了界面的视觉风格，支持商家级自定义。

```typescript
interface ThemeConfig {
  /** 主题名称 */
  name: string;
  /** 颜色配置 */
  colors: {
    app_bg: string;           // 应用背景 "#F3F4F5"
    sidebar_bg: string;       // 侧边栏背景 "#F9F9FA"
    surface: string;          // 卡片/面板表面 "#FFFFFF"
    surface_alt: string;      // 备选表面 "#F6F7F8"
    surface_deep: string;     // 深色表面 "#1C202A"
    surface_deeper: string;   // 更深表面 "#14171E"
    hover: string;            // 悬停状态 "#EDEFF1"
    input: string;            // 输入框背景 "#F6F7F8"
    border: string;           // 边框 "#DDDFE3"
    border_strong: string;    // 强调边框 "#C1C4CC"
    text: string;             // 主文本 "#1E2A3A"
    text_muted: string;       // 次要文本 "#64748B"
    text_subtle: string;      // 弱文本 "#94A3B8"
    accent: string;           // 主题色 "#1A56DB"
    accent_hover: string;     // 主题色悬停 "#1444AD"
    accent_soft: string;      // 主题色浅色 "#E4E8F0"
    accent_ink: string;       // 主题色深色 "#0F327F"
    success: string;          // 成功 "#059669"
    warning: string;          // 警告 "#D97706"
    danger: string;           // 危险 "#DC2626"
    danger_hover: string;     // 危险悬停 "#B91C1C"
    terminal_bg: string;      // 终端背景 "#0F172A"
    terminal_header: string;  // 终端标题栏 "#1E293B"
    terminal_text: string;    // 终端文本 "#34D399"
  };
  /** 字体配置 */
  fonts: {
    display: [string, number, string];   // [字体名, 大小, 粗细]
    title: [string, number, string];
    section: [string, number, string];
    body: [string, number, string];
    small: [string, number, string];
    mono: [string, number, string];
  };
  /** 品牌信息 */
  brand: {
    name: string;          // "永浩科技"
    subtitle: string;      // "智能AI服务平台"
    app_user_model_id: string;
    terminal_header: string;
  };
}
```

**默认主题**（永浩科技）对应源码 [constants.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/constants.py) 中的 `COLORS`、`FONTS`、`BRAND` 定义。

### 3.4 ProcessStatus 进程状态

```typescript
interface ProcessStatus {
  /** OpenClaw 网关进程是否正在运行 */
  running: boolean;
  /** 进程 PID，未运行时为 null */
  pid: number | null;
}
```

### 3.5 UpdateInfo 更新信息

```typescript
interface UpdateInfo {
  /** 当前安装版本 */
  current: string;
  /** npm 仓库最新版本 */
  latest: string;
  /** 是否有可用更新 */
  hasUpdate: boolean;
}
```

### 3.6 AuthProfiles 认证配置

```typescript
interface AuthProfiles {
  models: {
    providers: Record<string, {
      id: string;
      name: string;
      baseUrl: string;
      apiKey: string;
      models: string[];
    }>;
    primary: string;
  };
}
```

**本地存储路径**：`{base_path}/data/.openclaw/agents/main/agent/auth-profiles.json`

---

## 4. Ed25519 签名验证

### 4.1 概述

授权系统使用 Ed25519 非对称签名算法保证许可证数据的完整性和不可伪造性。

- **签名方**：云端授权服务器（持有私钥）
- **验证方**：客户端 Python Sidecar / 未来 Rust 层（持有公钥）
- **公钥（Base64）**：`njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4=`

源码位置：[license_manager.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L23)

### 4.2 验证流程

```
云端签发                          客户端验证
┌──────────────┐                ┌──────────────────────────┐
│ 1. 构建许可证  │                │ 1. 读取 license.json      │
│    数据字段    │                │ 2. 提取 signature 字段     │
│ 2. 移除签名    │   ────────▶   │ 3. 移除 signature 字段     │
│ 3. 规范化序列化│   HTTPS 传输    │ 4. 规范化序列化剩余字段    │
│ 4. Ed25519    │                │ 5. Ed25519 验签            │
│    签名        │                │ 6. 校验 installId 绑定     │
│ 5. 附加签名    │                │ 7. 校验 deviceId 绑定      │
│    字段        │                │ 8. 校验到期日期             │
└──────────────┘                └──────────────────────────┘
```

### 4.3 规范化序列化

签名内容使用确定性 JSON 序列化，确保云端和客户端生成相同的字节序列：

```python
def _canonical(self, payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,           # 键名字典序排列
        separators=(",", ":"),    # 紧凑格式，无空格
        ensure_ascii=False        # 保留中文字符
    ).encode("utf-8")
```

源码位置：[license_manager.py:L139-140](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L139-L140)

**示例**：

```json
{"activatedAt":"2025-01-01T00:00:00+00:00","deviceId":"abc123","edition":"pro","expires":"2027-05-01","features":["openclaw","image","video","storyboard"],"installId":"uuid-here","licensee":"客户名","licenseId":"lic-001"}
```

### 4.4 客户端验证逻辑

```python
def verify(self, license_data: dict[str, Any]) -> bool:
    try:
        # 1. 提取签名
        signature = base64.b64decode(license_data["signature"])

        # 2. 构建待验签载荷（移除 signature 字段）
        payload = dict(license_data)
        payload.pop("signature", None)

        # 3. Ed25519 验签
        self.public_key.verify(signature, self._canonical(payload))

        # 4. 安装实例绑定校验
        if payload.get("installId") != self.get_install_id():
            return False

        # 5. 设备硬件绑定校验（防止复制文件夹绕过）
        licensed_device = payload.get("deviceId")
        if licensed_device and licensed_device != self.device_id():
            return False

        # 6. 到期日期校验
        expires = payload.get("expires")
        if expires and date.fromisoformat(expires) < date.today():
            return False

        return True
    except (KeyError, ValueError, InvalidSignature, TypeError):
        return False
```

源码位置：[license_manager.py:L88-105](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L88-L105)

**设备指纹生成**：基于 Windows 卷序列号 + 盘符 + 固定盐值，经 SHA-256 哈希生成。

```python
# 卷序列号获取（Windows API）
root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
volume_serial = ctypes.c_ulong()
ctypes.windll.kernel32.GetVolumeInformationW(
    ctypes.c_wchar_p(root), None, 0,
    ctypes.byref(volume_serial), None, None, None, 0
)
serial = str(volume_serial.value)

# 备选方案：卷序列号获取失败时使用 MAC 地址
if serial is None:
    serial = str(uuid.getnode())

raw = f"{root}|{serial}|openclaw-launcher"
device_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

源码位置：[license_manager.py:L50-72](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L50-L72)

---

## 5. 授权码格式说明

授权码采用分段式格式，由字母和数字组成：

```
OC-{EDITION}-XXXX-XXXX-XXXX-XXXX
```

| 段位 | 含义 | 示例值 | 说明 |
|------|------|--------|------|
| OC | 产品前缀 | 固定 `OC` | OpenClaw 缩写 |
| EDITION | 授权版本 | `PRO` / `ENT` / `STD` | PRO=专业版, ENT=企业版, STD=标准版 |
| XXXX-XXXX-XXXX-XXXX | 随机码 | `A1B2-C3D4-E5F6-7890` | 16 位随机字符，分 4 组 |

**完整示例**：`OC-PRO-A1B2-C3D4-E5F6-7890`

**处理规则**：

- 客户端激活时自动转大写：`code = code.strip().upper()`
- 授权码在云端数据库中存储其 SHA-256 哈希值，原始码不落库
- 管理员可通过 `/admin/api/codes/hash` 端点计算授权码哈希

---

# Part 1: 云端授权服务器 API

**Base URL**：`https://license.heang.top`
**协议**：HTTPS
**字符编码**：UTF-8

---

## 6. 公开端点

### 6.1 健康检查

检查授权服务器是否正常运行。

| 项目 | 值 |
|------|-----|
| **接口名称** | 健康检查 |
| **URL路径** | `/health` |
| **请求方法** | GET |
| **请求头** | 无特殊要求 |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | boolean | 服务是否正常 |
| time | string | 服务器当前时间（ISO 8601） |

**示例请求**：

```bash
curl https://license.heang.top/health
```

**示例响应**（200）：

```json
{
  "ok": true,
  "time": "2026-05-03T12:03:35+00:00"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 500 | - | 服务器内部错误 |

---

### 6.2 获取 Ed25519 公钥

获取用于验证许可证签名的 Ed25519 公钥。

| 项目 | 值 |
|------|-----|
| **接口名称** | 获取公钥 |
| **URL路径** | `/public-key` |
| **请求方法** | GET |
| **请求头** | 无特殊要求 |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| publicKey | string | Ed25519 公钥，Base64 编码 |

**示例请求**：

```bash
curl https://license.heang.top/public-key
```

**示例响应**（200）：

```json
{
  "publicKey": "njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4="
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 500 | - | 服务器内部错误 |

---

## 7. 授权激活端点

### 7.1 授权码激活

客户端使用授权码向云端请求许可证。此端点由 Python Sidecar 的 `LicenseManager.activate()` 内部调用，前端不直接访问。

| 项目 | 值 |
|------|-----|
| **接口名称** | 授权码激活 |
| **URL路径** | `/activate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `User-Agent: OpenClaw-Desktop/2.0` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码，格式 `OC-{EDITION}-XXXX-XXXX-XXXX-XXXX` |
| installId | string | 是 | 安装实例 UUID，绑定到当前安装 |
| deviceId | string | 是 | 设备硬件指纹（SHA-256），绑定到物理机器 |
| appVersion | string | 是 | 客户端版本标识，固定值 `desktop` |

**请求示例**：

```bash
curl -X POST https://license.heang.top/activate \
  -H "Content-Type: application/json" \
  -H "User-Agent: OpenClaw-Desktop/2.0" \
  -d '{
    "code": "OC-PRO-A1B2-C3D4-E5F6-7890",
    "installId": "550e8400-e29b-41d4-a716-446655440000",
    "deviceId": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
    "appVersion": "desktop"
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| license | object | 签发后的许可证对象，包含 signature 字段 |
| license.licenseId | string | 许可证唯一标识 |
| license.licensee | string | 被授权人名称 |
| license.edition | string | 授权版本 |
| license.features | string[] | 授权功能列表 |
| license.expires | string\|null | 到期日期 |
| license.installId | string | 绑定的安装实例 ID |
| license.deviceId | string | 绑定的设备指纹 |
| license.activatedAt | string | 激活时间 |
| license.signature | string | Ed25519 签名（Base64） |
| license.theme | object | （新增）商家主题配置，仅当授权码关联商家时返回 |

**示例响应**（200）：

```json
{
  "license": {
    "licenseId": "lic-20260504-001",
    "licensee": "示例科技",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "550e8400-e29b-41d4-a716-446655440000",
    "deviceId": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
    "activatedAt": "2026-05-04T08:30:00+00:00",
    "signature": "base64-encoded-ed25519-signature-here==",
    "theme": {
      "name": "示例科技主题",
      "colors": { "..." : "..." },
      "fonts": { "..." : "..." },
      "brand": { "name": "示例科技", "subtitle": "智能解决方案" }
    }
  }
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 缺少授权码或安装 ID | 请求体缺少必填字段 |
| 404 | 授权码不存在 | 授权码在数据库中未找到 |
| 403 | 授权码已停用 | 管理员已禁用该授权码 |
| 403 | 授权码已被其他设备激活 | 超过最大激活次数限制 |
| 500 | 服务器内部错误 | 签发过程异常 |

---

## 8. 管理后台端点

### 8.1 管理后台页面

返回管理后台的 HTML 页面，供管理员通过浏览器操作。

| 项目 | 值 |
|------|-----|
| **接口名称** | 管理后台页面 |
| **URL路径** | `/admin` |
| **请求方法** | GET |
| **请求头** | 无特殊要求 |
| **请求参数** | 无 |

**响应格式**：`text/html`

**示例请求**：

```bash
curl https://license.heang.top/admin
```

**示例响应**（200）：HTML 页面内容

---

### 8.2 列出所有授权码

获取系统中所有授权码的列表。

| 项目 | 值 |
|------|-----|
| **接口名称** | 列出授权码 |
| **URL路径** | `/admin/api/codes` |
| **请求方法** | GET |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| codes | array | 授权码列表 |

**示例请求**：

```bash
curl https://license.heang.top/admin/api/codes \
  -H "X-Admin-Token: your-admin-token"
```

**示例响应**（200）：

```json
{
  "codes": [
    {
      "codeHash": "sha256-hash-of-code",
      "licensee": "示例科技",
      "edition": "pro",
      "expires": "2027-05-01",
      "maxActivations": 3,
      "currentActivations": 1,
      "active": true,
      "features": ["openclaw", "image", "video", "storyboard"],
      "createdAt": "2026-01-01T00:00:00+00:00"
    }
  ]
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | - | 管理员令牌缺失或无效 |
| 500 | - | 服务器内部错误 |

---

### 8.3 批量生成授权码

批量生成指定数量的授权码。

| 项目 | 值 |
|------|-----|
| **接口名称** | 批量生成授权码 |
| **URL路径** | `/admin/api/codes` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| licensee | string | 是 | 被授权人/客户名称 |
| edition | string | 是 | 授权版本：`pro` / `enterprise` / `starter` |
| count | number | 是 | 生成数量 |
| expires | string | 否 | 到期日期，null 或不传表示永久有效 |
| maxActivations | number | 是 | 单个授权码最大激活次数 |
| features | string[] | 是 | 授权功能列表 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/codes \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "licensee": "示例科技",
    "edition": "pro",
    "count": 5,
    "expires": "2027-05-01",
    "maxActivations": 3,
    "features": ["openclaw", "image", "video", "storyboard"]
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| codes | string[] | 生成的授权码明文列表（仅此一次返回明文） |

**示例响应**（200）：

```json
{
  "codes": [
    "OC-PRO-A1B2-C3D4-E5F6-7890",
    "OC-PRO-B2C3-D4E5-F6A7-8901",
    "OC-PRO-C3D4-E5F6-A7B8-9012",
    "OC-PRO-D4E5-F6A7-B8C9-0123",
    "OC-PRO-E5F6-A7B8-C9D0-1234"
  ]
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | 缺少必填字段或字段值非法 |
| 401 | - | 管理员令牌缺失或无效 |
| 500 | - | 服务器内部错误 |

---

### 8.4 启用/停用授权码

切换指定授权码的启用状态。

| 项目 | 值 |
|------|-----|
| **接口名称** | 切换授权码状态 |
| **URL路径** | `/admin/api/codes/toggle` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| codeHash | string | 是 | 授权码哈希值 |
| active | boolean | 是 | 目标状态：true 启用，false 停用 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/codes/toggle \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "codeHash": "sha256-hash-of-code",
    "active": false
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |
| active | boolean | 更新后的状态 |

**示例响应**（200）：

```json
{
  "status": "ok",
  "active": false
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | 缺少 codeHash 或 active |
| 401 | - | 管理员令牌缺失或无效 |
| 404 | 授权码不存在 | codeHash 对应的授权码未找到 |
| 500 | - | 服务器内部错误 |

---

### 8.5 清空全部授权码

清空数据库中所有授权码记录。此操作不可逆。

| 项目 | 值 |
|------|-----|
| **接口名称** | 清空授权码 |
| **URL路径** | `/admin/api/codes/clear` |
| **请求方法** | POST |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无请求体 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/codes/clear \
  -H "X-Admin-Token: your-admin-token"
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |
| deleted | number | 被删除的授权码数量 |

**示例响应**（200）：

```json
{
  "status": "ok",
  "deleted": 42
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | - | 管理员令牌缺失或无效 |
| 500 | - | 服务器内部错误 |

---

### 8.6 计算授权码哈希

计算给定授权码的 SHA-256 哈希值，用于比对数据库中的记录。

| 项目 | 值 |
|------|-----|
| **接口名称** | 计算授权码哈希 |
| **URL路径** | `/admin/api/codes/hash` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码明文 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/codes/hash \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "code": "OC-PRO-A1B2-C3D4-E5F6-7890"
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| hash | string | 授权码的 SHA-256 哈希值 |

**示例响应**（200）：

```json
{
  "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | 授权码为空 |
| 401 | - | 管理员令牌缺失或无效 |
| 500 | - | 服务器内部错误 |

---

### 8.7 删除单个授权码

删除指定哈希值对应的授权码。

| 项目 | 值 |
|------|-----|
| **接口名称** | 删除授权码 |
| **URL路径** | `/admin/api/codes/delete` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| codeHash | string | 是 | 要删除的授权码哈希值 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/codes/delete \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "codeHash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |

**示例响应**（200）：

```json
{
  "status": "ok"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | codeHash 为空 |
| 401 | - | 管理员令牌缺失或无效 |
| 404 | 授权码不存在 | codeHash 对应的授权码未找到 |
| 500 | - | 服务器内部错误 |

---

## 9. 商家管理端点（新增）

以下端点为主题系统新增，用于管理商家信息及其主题配置。

### 9.1 列出所有商家

| 项目 | 值 |
|------|-----|
| **接口名称** | 列出商家 |
| **URL路径** | `/admin/api/merchants` |
| **请求方法** | GET |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchants | Merchant[] | 商家列表 |

**示例请求**：

```bash
curl https://license.heang.top/admin/api/merchants \
  -H "X-Admin-Token: your-admin-token"
```

**示例响应**（200）：

```json
{
  "merchants": [
    {
      "merchantId": "yonghao-tech",
      "name": "永浩科技",
      "subtitle": "智能AI服务平台",
      "themeJson": {
        "name": "永浩科技主题",
        "colors": { "app_bg": "#F3F4F5", "..." : "..." },
        "fonts": { "..." : "..." },
        "brand": { "name": "永浩科技", "subtitle": "智能AI服务平台" }
      },
      "logoUrl": "https://cdn.heang.top/logos/yonghao.png",
      "createdAt": "2026-01-01T00:00:00+00:00",
      "updatedAt": "2026-05-01T00:00:00+00:00"
    }
  ]
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | - | 管理员令牌缺失或无效 |
| 500 | - | 服务器内部错误 |

---

### 9.2 创建商家

| 项目 | 值 |
|------|-----|
| **接口名称** | 创建商家 |
| **URL路径** | `/admin/api/merchants` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| merchantId | string | 是 | 商家唯一标识，用于关联授权码 |
| name | string | 是 | 商家名称 |
| subtitle | string | 否 | 商家副标题/口号 |
| themeJson | object | 是 | 完整 ThemeConfig 结构 |
| logoUrl | string | 否 | 商家 Logo URL |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/merchants \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "merchantId": "example-tech",
    "name": "示例科技",
    "subtitle": "智能解决方案提供商",
    "themeJson": {
      "name": "示例科技主题",
      "colors": {
        "app_bg": "#F0F2F5",
        "sidebar_bg": "#F5F6F8",
        "surface": "#FFFFFF",
        "accent": "#2563EB",
        "..." : "..."
      },
      "fonts": { "..." : "..." },
      "brand": { "name": "示例科技", "subtitle": "智能解决方案提供商" }
    },
    "logoUrl": "https://cdn.heang.top/logos/example.png"
  }'
```

**响应格式**（201）：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchant | Merchant | 创建的商家对象 |

**示例响应**（201）：

```json
{
  "merchant": {
    "merchantId": "example-tech",
    "name": "示例科技",
    "subtitle": "智能解决方案提供商",
    "themeJson": { "..." : "..." },
    "logoUrl": "https://cdn.heang.top/logos/example.png",
    "createdAt": "2026-05-04T08:00:00+00:00",
    "updatedAt": "2026-05-04T08:00:00+00:00"
  }
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | merchantId 为空或 themeJson 格式非法 |
| 401 | - | 管理员令牌缺失或无效 |
| 409 | 商家已存在 | merchantId 重复 |
| 500 | - | 服务器内部错误 |

---

### 9.3 更新商家信息

| 项目 | 值 |
|------|-----|
| **接口名称** | 更新商家 |
| **URL路径** | `/admin/api/merchants/{merchantId}` |
| **请求方法** | PUT |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**路径参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| merchantId | string | 是 | 商家唯一标识 |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| name | string | 否 | 商家名称 |
| subtitle | string | 否 | 商家副标题 |
| themeJson | object | 否 | 完整 ThemeConfig 结构 |
| logoUrl | string | 否 | 商家 Logo URL |

**示例请求**：

```bash
curl -X PUT https://license.heang.top/admin/api/merchants/example-tech \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-admin-token" \
  -d '{
    "name": "示例科技（更新）",
    "subtitle": "全新的智能解决方案"
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchant | Merchant | 更新后的商家对象 |

**示例响应**（200）：

```json
{
  "merchant": {
    "merchantId": "example-tech",
    "name": "示例科技（更新）",
    "subtitle": "全新的智能解决方案",
    "themeJson": { "..." : "..." },
    "logoUrl": "https://cdn.heang.top/logos/example.png",
    "createdAt": "2026-05-04T08:00:00+00:00",
    "updatedAt": "2026-05-04T09:00:00+00:00"
  }
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 参数错误 | themeJson 格式非法 |
| 401 | - | 管理员令牌缺失或无效 |
| 404 | 商家不存在 | merchantId 对应的商家未找到 |
| 500 | - | 服务器内部错误 |

---

### 9.4 删除商家

| 项目 | 值 |
|------|-----|
| **接口名称** | 删除商家 |
| **URL路径** | `/admin/api/merchants/{merchantId}` |
| **请求方法** | DELETE |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**路径参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| merchantId | string | 是 | 商家唯一标识 |

**示例请求**：

```bash
curl -X DELETE https://license.heang.top/admin/api/merchants/example-tech \
  -H "X-Admin-Token: your-admin-token"
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |

**示例响应**（200）：

```json
{
  "status": "ok"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | - | 管理员令牌缺失或无效 |
| 404 | 商家不存在 | merchantId 对应的商家未找到 |
| 500 | - | 服务器内部错误 |

---

### 9.5 主题预览

生成商家主题的预览，返回预览 HTML 或预览 Token 供前端渲染。

| 项目 | 值 |
|------|-----|
| **接口名称** | 主题预览 |
| **URL路径** | `/admin/api/merchants/{merchantId}/preview` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**路径参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| merchantId | string | 是 | 商家唯一标识 |

**示例请求**：

```bash
curl -X POST https://license.heang.top/admin/api/merchants/example-tech/preview \
  -H "X-Admin-Token: your-admin-token"
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| previewToken | string | 预览令牌，用于在客户端加载预览 |
| previewUrl | string | 预览页面 URL |

**示例响应**（200）：

```json
{
  "previewToken": "preview-abc123-token",
  "previewUrl": "https://license.heang.top/preview/preview-abc123-token"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | - | 管理员令牌缺失或无效 |
| 404 | 商家不存在 | merchantId 对应的商家未找到 |
| 500 | - | 服务器内部错误 |

---

# Part 2: 客户端 Python Sidecar API

**Base URL**：`http://127.0.0.1:{port}`
**端口范围**：18791 ~ 18800（动态分配，首个可用端口）
**协议**：HTTP/1.1（本机回环）
**字符编码**：UTF-8
**认证**：所有请求必须携带 `X-Bridge-Token` Header
**CORS**：`Access-Control-Allow-Origin: http://tauri.localhost`

源码位置：[bridge.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py)

---

## 10. 进程管理

### 10.1 启动 OpenClaw 进程

启动 OpenClaw 网关服务进程。此端点受许可证保护，需有效授权。

| 项目 | 值 |
|------|-----|
| **接口名称** | 启动服务 |
| **URL路径** | `/api/process/start` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/process/start \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 启动状态：`started` 或 `already_running` |
| pid | number\|null | 进程 PID |

**示例响应**（200） - 进程已启动：

```json
{
  "status": "started",
  "pid": 12345
}
```

**示例响应**（200） - 进程已在运行：

```json
{
  "status": "already_running"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 需要有效的许可证才能使用此功能 | 许可证无效或不存在 |
| 500 | 找不到 Node.js / 找不到启动脚本 | 环境配置异常 |

---

### 10.2 停止 OpenClaw 进程

| 项目 | 值 |
|------|-----|
| **接口名称** | 停止服务 |
| **URL路径** | `/api/process/stop` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/process/stop \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `stopped` |
| message | string | 操作结果描述 |

**示例响应**（200）：

```json
{
  "status": "stopped",
  "message": "服务已停止"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

**message 可能的值**：

| 消息 | 场景 |
|------|------|
| 服务已停止 | 正常停止运行中的进程 |
| 已清理 N 个端口占用进程 | 进程已退出但端口仍被占用 |
| 没有运行中的服务 | 进程已退出且无端口占用 |
| 服务未启动 | 从未启动过服务 |

---

### 10.3 获取进程状态

| 项目 | 值 |
|------|-----|
| **接口名称** | 进程状态 |
| **URL路径** | `/api/process/status` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl http://127.0.0.1:18793/api/process/status \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：参见 [ProcessStatus 数据模型](#34-processstatus-进程状态)

**示例响应**（200） - 运行中：

```json
{
  "running": true,
  "pid": 12345
}
```

**示例响应**（200） - 未运行：

```json
{
  "running": false,
  "pid": null
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

## 11. 日志管理

### 11.1 获取日志

获取日志缓冲区的全部内容。日志缓冲区最多保留最近 500 行。

| 项目 | 值 |
|------|-----|
| **接口名称** | 获取日志 |
| **URL路径** | `/api/log/get` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

> 注意：虽然此端点使用 POST 方法，但不需要请求体。这是因为路由层统一通过 `do_POST` 处理。

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/log/get \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| log | string | 完整日志文本，多行以 `\n` 分隔 |

**示例响应**（200）：

```json
{
  "log": "[OpenClaw] Starting service...\n[OpenClaw] Node: C:\\path\\to\\node.exe\n[OpenClaw] PID: 12345\n"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

### 11.2 清除日志

清空日志缓冲区。

| 项目 | 值 |
|------|-----|
| **接口名称** | 清除日志 |
| **URL路径** | `/api/log/clear` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/log/clear \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `cleared` |

**示例响应**（200）：

```json
{
  "status": "cleared"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

## 12. 授权管理

### 12.1 获取当前许可证

获取本地存储的当前许可证信息。此接口读取 `data/license.json` 并验证签名有效性。

| 项目 | 值 |
|------|-----|
| **接口名称** | 获取当前许可证 |
| **URL路径** | `/api/license/current` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/license/current \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| license | object\|null | 许可证对象，验证失败或不存在时为 null |

**示例响应**（200） - 已授权：

```json
{
  "license": {
    "licenseId": "lic-20260504-001",
    "licensee": "示例科技",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "550e8400-e29b-41d4-a716-446655440000",
    "deviceId": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
    "activatedAt": "2026-05-04T08:30:00+00:00",
    "signature": "base64-encoded-signature=="
  }
}
```

**示例响应**（200） - 未授权：

```json
{
  "license": null
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

### 12.2 激活授权码

使用授权码进行在线激活。此端点内部调用云端 `/activate` API，验证返回的许可证签名，并持久化到本地。

| 项目 | 值 |
|------|-----|
| **接口名称** | 激活授权码 |
| **URL路径** | `/api/license/activate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码，自动转大写 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/license/activate \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{"code": "OC-PRO-A1B2-C3D4-E5F6-7890"}'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| license | object | 激活成功后的许可证对象 |

**示例响应**（200）：

```json
{
  "license": {
    "licenseId": "lic-20260504-001",
    "licensee": "示例科技",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "550e8400-e29b-41d4-a716-446655440000",
    "deviceId": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
    "activatedAt": "2026-05-04T08:30:00+00:00",
    "signature": "base64-encoded-signature=="
  }
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 授权码不能为空 | 请求体中 code 字段为空 |
| 400 | 请输入授权码 | code 为空字符串 |
| 400 | 授权码不存在 | 云端返回 404 |
| 400 | 授权码已停用 | 云端返回 403（停用） |
| 400 | 授权码已被其他设备激活 | 云端返回 403（超限） |
| 400 | 授权服务器返回的许可证无效 | 云端返回的许可证签名验证失败 |
| 400 | 无法连接授权服务器 | 网络错误 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

> 注意：Python Bridge 的 `_license_activate` 方法单独捕获 `LicenseError`，将所有业务错误统一返回 HTTP 400。

---

### 12.3 检查授权状态

检查当前是否持有有效授权，可指定检查特定功能。

| 项目 | 值 |
|------|-----|
| **接口名称** | 检查授权状态 |
| **URL路径** | `/api/license/authorized` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| feature | string | 否 | 功能标识，不传则只检查是否有任何有效许可证 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/license/authorized \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{"feature": "image"}'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| authorized | boolean | 是否已授权指定功能 |

**示例响应**（200） - 已授权图片功能：

```json
{
  "authorized": true
}
```

**示例响应**（200） - 未授权：

```json
{
  "authorized": false
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

## 13. AI 图片生成

### 13.1 图片生成/编辑

调用 OpenAI 兼容的图片生成 API 生成或编辑图片。此端点受许可证保护，需有效授权且包含 `image` 功能。

| 项目 | 值 |
|------|-----|
| **接口名称** | AI 图片生成 |
| **URL路径** | `/api/image/generate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| baseUrl | string | 是 | 图像 API 中转站地址，如 `https://api.heang.top/v1` |
| apiKey | string | 否 | API Key，附加到请求的 Authorization Header |
| prompt | string | 是 | 图片描述提示词 |
| size | string | 否 | 图片尺寸，默认 `1024x1024`，可选值：`1024x1024`、`1024x1536`、`1536x1024`、`512x512` |
| count | number | 否 | 生成数量，默认 `1`，范围 1~9 |
| editImagePath | string | 否 | 编辑参考图，支持本地文件路径或 base64 数据 URL（`data:image/png;base64,...`） |

**示例请求** - 文生图：

```bash
curl -X POST http://127.0.0.1:18793/api/image/generate \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "baseUrl": "https://api.heang.top/v1",
    "apiKey": "sk-xxx",
    "prompt": "一只猫在阳光下睡觉",
    "size": "1024x1024",
    "count": 1
  }'
```

**示例请求** - 图编辑（base64 数据 URL）：

```bash
curl -X POST http://127.0.0.1:18793/api/image/generate \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "baseUrl": "https://api.heang.top/v1",
    "apiKey": "sk-xxx",
    "prompt": "将背景改为白色",
    "size": "1024x1024",
    "editImagePath": "data:image/png;base64,iVBORw0KGgo..."
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| images | string[] | 生成的图片列表，每项为 Base64 编码的图片数据 |
| count | number | 实际生成的图片数量 |

**示例响应**（200）：

```json
{
  "images": ["iVBORw0KGgoAAAANSUhEUgAA..."],
  "count": 1
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 中转站地址不能为空 | baseUrl 为空 |
| 400 | 提示词不能为空 | prompt 为空 |
| 400 | 图片数据解码失败 | editImagePath 的 base64 数据格式错误 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 需要有效的许可证才能使用此功能 | 许可证无效或不含 image 功能 |
| 500 | 图像 API 调用失败 | 上游 API 返回错误 |

**内部实现细节**：

- 使用的模型：`gpt-image-2`（定义在 [constants.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/constants.py#L19)）
- 生成请求：`POST {baseUrl}/v1/images/generations`
- 编辑请求：`POST {baseUrl}/v1/images/edits`（multipart/form-data）
- base64 数据 URL 会被解码保存为临时文件，请求完成后自动删除

---

## 14. AI 视频生成

### 14.1 视频生成

调用阿里云 DashScope 视频 API 生成视频。此端点受许可证保护，需有效授权且包含 `video` 功能。

| 项目 | 值 |
|------|-----|
| **接口名称** | AI 视频生成 |
| **URL路径** | `/api/video/generate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| dashKey | string | 是 | DashScope API Key |
| prompt | string | 是 | 视频描述提示词 |
| mode | string | 否 | 生成模式：`t2v`（文生视频，默认）或 `i2v`（图生视频） |
| resolution | string | 否 | 分辨率，默认 `720P`，可选值：`720P`、`1080P` |
| duration | number | 否 | 视频时长（秒），默认 `5` |
| ratio | string | 否 | 宽高比，默认 `16:9`，可选值：`16:9`、`9:16`、`1:1`、`4:3`、`3:4` |
| imagePath | string | 否 | 参考图片，i2v 模式必填，支持本地文件路径或 base64 数据 URL |

**示例请求** - 文生视频：

```bash
curl -X POST http://127.0.0.1:18793/api/video/generate \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "dashKey": "sk-dashscope-xxx",
    "prompt": "一只猫在草地上奔跑",
    "mode": "t2v",
    "resolution": "720P",
    "duration": 5,
    "ratio": "16:9"
  }'
```

**示例请求** - 图生视频：

```bash
curl -X POST http://127.0.0.1:18793/api/video/generate \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "dashKey": "sk-dashscope-xxx",
    "prompt": "让图片中的场景动起来",
    "mode": "i2v",
    "resolution": "720P",
    "duration": 5,
    "imagePath": "data:image/png;base64,iVBORw0KGgo..."
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| video | string | 生成的视频数据，Base64 编码 |

**示例响应**（200）：

```json
{
  "video": "AAAAIGZ0eXBpc29tAA..."
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | DashScope API Key 不能为空 | dashKey 为空 |
| 400 | 提示词不能为空 | prompt 为空 |
| 400 | 图片数据解码失败 | imagePath 的 base64 数据格式错误 |
| 400 | 图生视频需要上传参考图 | i2v 模式未提供 imagePath |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 需要有效的许可证才能使用此功能 | 许可证无效或不含 video 功能 |
| 500 | DashScope 视频 API 调用失败 | 上游 API 返回错误 |
| 500 | 生成超时，请稍后重试 | 轮询超过 120 次（约 10 分钟） |

**内部实现细节**：

- 文生视频模型：`happyhorse-1.0-t2v`
- 图生视频模型：`happyhorse-1.0-i2v`
- 提交任务 URL：`https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
- 轮询任务 URL：`https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}`
- 异步模式：请求时携带 `X-DashScope-Async: enable` Header
- 轮询间隔：5 秒，最多 120 次
- base64 数据 URL 会被解码保存为临时文件，请求完成后自动删除

---

## 15. 版本更新

### 15.1 检查更新

查询 npm 仓库中 openclaw 包的最新版本，与本地安装版本对比。

| 项目 | 值 |
|------|-----|
| **接口名称** | 检查更新 |
| **URL路径** | `/api/update/check` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/update/check \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| current | string | 当前安装版本 |
| latest | string | npm 仓库最新版本 |
| hasUpdate | boolean | 是否有可用更新 |

**示例响应**（200）：

```json
{
  "current": "2.0.0",
  "latest": "2.1.0",
  "hasUpdate": true
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 500 | 找不到 Node.js / 找不到 pnpm / 网络错误 / 请求超时 | 环境或网络异常 |

---

### 15.2 执行更新

执行 openclaw 包的版本更新，通过 pnpm 安装最新版本。

| 项目 | 值 |
|------|-----|
| **接口名称** | 执行更新 |
| **URL路径** | `/api/update/do` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/update/do \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| success | boolean | 更新是否成功 |
| current_version | string | 更新后的当前版本 |
| log | string[] | 更新过程的日志输出 |

**示例响应**（200）：

```json
{
  "success": true,
  "current_version": "2.1.0",
  "log": ["npm http GET https://registry.npmjs.org/openclaw", "..."]
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 500 | 更新执行失败 | pnpm 命令执行异常 |

---

## 16. 配置读写

### 16.1 读取配置文件

读取指定路径的 JSON 配置文件。路径必须位于允许的目录范围内（base_path 或 data_dir），否则返回 403。

| 项目 | 值 |
|------|-----|
| **接口名称** | 读取配置 |
| **URL路径** | `/api/config/read` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件的绝对路径或相对路径 |
| default | any | 否 | 文件不存在时的默认返回值，默认 `{}` |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/config/read \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "path": "data/.openclaw/openclaw.json",
    "default": { "plugins": {} }
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| data | any | 读取到的 JSON 内容，文件不存在时返回 default |

**示例响应**（200）：

```json
{
  "data": {
    "plugins": {
      "feishu": { "enabled": true }
    }
  }
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 路径不在允许的范围内 | 路径超出 base_path 或 data_dir |

---

### 16.2 写入配置文件

将 JSON 数据写入指定路径的配置文件。路径必须位于允许的目录范围内。

| 项目 | 值 |
|------|-----|
| **接口名称** | 写入配置 |
| **URL路径** | `/api/config/write` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件的绝对路径或相对路径 |
| data | any | 是 | 要写入的 JSON 数据 |

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/config/write \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "path": "data/.openclaw/openclaw.json",
    "data": { "plugins": { "feishu": { "enabled": false } } }
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `ok` |

**示例响应**（200）：

```json
{
  "status": "ok"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 路径不在允许的范围内 | 路径超出 base_path 或 data_dir |

---

## 17. 认证配置管理

### 17.1 获取/保存认证配置

此端点根据 HTTP 方法不同执行不同操作：

- **POST/GET**：读取当前 API 提供商认证配置
- **PUT**：合并更新 API 提供商认证配置

| 项目 | 值 |
|------|-----|
| **接口名称** | 认证配置管理 |
| **URL路径** | `/api/auth/profiles` |
| **请求方法** | POST / PUT |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**读取配置（POST）**：

无请求参数。

**示例请求**：

```bash
curl -X POST http://127.0.0.1:18793/api/auth/profiles \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| profiles | object | 认证配置对象 |

**示例响应**（200）：

```json
{
  "profiles": {
    "models": {
      "providers": {
        "heang_ai": {
          "id": "heang_ai",
          "name": "Heang AI",
          "baseUrl": "https://api.heang.top/v1",
          "apiKey": "sk-xxx",
          "models": ["kimi-k2.5", "gpt-4o"]
        }
      },
      "primary": "heang_ai"
    }
  }
}
```

**保存配置（PUT）**：

请求体为要合并的配置数据，会与现有配置合并（`dict.update`）。

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| models | object | 否 | 模型提供商配置 |
| *(其他字段)* | any | 否 | 会被合并到现有配置中 |

**示例请求**：

```bash
curl -X PUT http://127.0.0.1:18793/api/auth/profiles \
  -H "Content-Type: application/json" \
  -H "X-Bridge-Token: a3f8c1d2..." \
  -d '{
    "models": {
      "providers": {
        "heang_ai": {
          "id": "heang_ai",
          "name": "Heang AI",
          "baseUrl": "https://api.heang.top/v1",
          "apiKey": "sk-new-key",
          "models": ["kimi-k2.5", "gpt-4o"]
        }
      },
      "primary": "heang_ai"
    }
  }'
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `ok` |

**示例响应**（200）：

```json
{
  "status": "ok"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

**本地存储路径**：`{base_path}/data/.openclaw/agents/main/agent/auth-profiles.json`

---

## 18. 系统信息

### 18.1 获取系统环境信息

获取当前运行环境的关键路径和版本信息。

| 项目 | 值 |
|------|-----|
| **接口名称** | 系统信息 |
| **URL路径** | `/api/system/info` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl http://127.0.0.1:18793/api/system/info \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| node_path | string | Node.js 可执行文件路径 |
| base_path | string | 应用根目录路径 |
| openclaw_version | string | 当前安装的 openclaw 版本号 |

**示例响应**（200）：

```json
{
  "node_path": "C:\\OpenClaw\\SystemData\\.core\\node\\node.exe",
  "base_path": "C:\\OpenClaw",
  "openclaw_version": "2.0.0"
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

## 19. 主题配置（新增）

### 19.1 获取当前主题配置

获取当前许可证关联的商家主题配置。若许可证包含 `theme` 字段，则返回该主题；否则返回默认主题（永浩科技）。

| 项目 | 值 |
|------|-----|
| **接口名称** | 获取当前主题 |
| **URL路径** | `/api/theme/current` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**示例请求**：

```bash
curl http://127.0.0.1:18793/api/theme/current \
  -H "X-Bridge-Token: a3f8c1d2..."
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| theme | ThemeConfig | 当前主题配置 |
| isCustom | boolean | 是否为商家自定义主题（非默认） |
| merchantId | string\|null | 关联的商家 ID，默认主题为 null |

**示例响应**（200） - 自定义主题：

```json
{
  "theme": {
    "name": "示例科技主题",
    "colors": {
      "app_bg": "#F0F2F5",
      "sidebar_bg": "#F5F6F8",
      "surface": "#FFFFFF",
      "accent": "#2563EB"
    },
    "fonts": { "..." : "..." },
    "brand": { "name": "示例科技", "subtitle": "智能解决方案" }
  },
  "isCustom": true,
  "merchantId": "example-tech"
}
```

**示例响应**（200） - 默认主题：

```json
{
  "theme": {
    "name": "永浩科技主题",
    "colors": { "app_bg": "#F3F4F5", "..." : "..." },
    "fonts": { "..." : "..." },
    "brand": { "name": "永浩科技", "subtitle": "智能AI服务平台" }
  },
  "isCustom": false,
  "merchantId": null
}
```

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

---

# Part 3: Tauri Rust IPC Commands

**通信方式**：Tauri IPC（进程内调用，无网络开销）
**调用方式**：前端通过 `@tauri-apps/api/core` 的 `invoke()` 函数调用
**线程模型**：同步命令在主线程执行，异步命令在异步运行时执行
**源码位置**：[lib.rs](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src-tauri/src/lib.rs)

---

## 20. 现有命令

### 20.1 get_bridge_port

获取当前 Python Sidecar 的 HTTP 监听端口号。

| 项目 | 值 |
|------|-----|
| **命令名称** | `get_bridge_port` |
| **调用方式** | 同步（`#[tauri::command]`） |
| **参数** | 无 |
| **返回值** | `u16` - 端口号，0 表示 Sidecar 未启动 |

**前端调用示例**：

```typescript
import { invoke } from '@tauri-apps/api/core';
const port = await invoke<number>('get_bridge_port');
// port = 18793 或 0
```

**返回值说明**：

| 值 | 含义 |
|-----|------|
| 18791~18800 | Sidecar 正在监听的端口号 |
| 0 | Sidecar 尚未启动 |

---

### 20.2 start_bridge

启动 Python Sidecar 子进程。应用启动时自动调用。

| 项目 | 值 |
|------|-----|
| **命令名称** | `start_bridge` |
| **调用方式** | 异步（`#[tauri::command] async`） |
| **参数** | 无（`app: AppHandle` 由 Tauri 自动注入） |
| **返回值** | `Result<String, String>` |

**前端调用示例**：

```typescript
const result = await invoke<string>('start_bridge');
// Ok: "Bridge started on port 18793"
// Err: "启动 Python bridge 失败: ..."
```

**成功响应**：

```
"Bridge started on port 18793"
```

**错误响应**：

| 错误信息 | 原因 |
|---------|------|
| `bridge.py 未找到: {path}` | Python 脚本文件不存在 |
| `启动 Python bridge 失败: {io_error}` | 无法创建子进程 |
| `无法获取 bridge 端口` | Sidecar 启动后未输出 BRIDGE_PORT |

**内部流程**：

1. 尝试从 Tauri Resource 目录查找 `python/bridge.py`（生产模式）
2. 回退到项目相对路径 `python/bridge.py`（开发模式）
3. 使用 `Command::new("python")` 启动子进程
4. 从 stdout 逐行读取，解析 `BRIDGE_PORT=xxxx` 和 `BRIDGE_TOKEN=xxx`
5. 将端口号存入全局原子变量 `BRIDGE_PORT`
6. 将 Token 存入全局互斥锁 `BRIDGE_TOKEN`
7. 在后台线程中持续读取 stderr

---

### 20.3 proxy_request

代理 HTTP 请求到 Python Sidecar。此命令是当前前端与 Python 通信的核心桥接。

| 项目 | 值 |
|------|-----|
| **命令名称** | `proxy_request` |
| **调用方式** | 异步（`#[tauri::command] async`） |
| **返回值** | `Result<String, String>` |

**参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | API 路径，如 `/api/process/start` |
| method | string | 是 | HTTP 方法：`GET` / `POST` / `PUT` |
| body | string\|null | 否 | JSON 请求体字符串 |

**前端调用示例**：

```typescript
const responseText = await invoke<string>('proxy_request', {
  path: '/api/license/current',
  method: 'POST',
  body: null,
});
const data = JSON.parse(responseText);
```

**成功响应**：Python Sidecar 返回的响应体文本（JSON 字符串）

**错误响应**：

| 错误格式 | 原因 |
|---------|------|
| `Bridge 未启动` | `BRIDGE_PORT` 为 0 |
| `不支持的方法: {method}` | method 不是 GET/POST/PUT |
| `请求失败: {reqwest_error}` | HTTP 请求发送失败 |
| `读取响应失败: {reqwest_error}` | 响应体读取失败 |
| `[400] {"error":"授权码不能为空"}` | Sidecar 返回非 2xx 状态码 |

**内部流程**：

1. 从全局变量读取 `BRIDGE_PORT`，为 0 时返回错误
2. 构造 URL：`http://127.0.0.1:{port}/{path}`
3. 根据 method 创建 reqwest 请求
4. 若有 body，附加 JSON Content-Type
5. 从全局互斥锁读取 `BRIDGE_TOKEN`，附加 `X-Bridge-Token` Header
6. 发送请求，检查响应状态码
7. 非 2xx 状态码返回 `Err("[{status}] {body}")`
8. 2xx 状态码返回 `Ok(body)`

---

## 21. 计划改造命令

以下为计划中的改造方案，目标是将安全敏感逻辑从 Python 迁移到 Rust，提升安全性和性能。

### 21.1 get_bridge_token（新增）

获取当前 Python Sidecar 的认证令牌。

| 项目 | 值 |
|------|-----|
| **命令名称** | `get_bridge_token` |
| **调用方式** | 同步 |
| **参数** | 无 |
| **返回值** | `String` - 64 字符十六进制令牌，空字符串表示未初始化 |

**前端调用示例**：

```typescript
const token = await invoke<string>('get_bridge_token');
```

---

### 21.2 verify_license（新增，Ed25519 验签迁移到 Rust）

在 Rust 层直接验证本地许可证的 Ed25519 签名，无需经过 Python Sidecar。验签逻辑从 Python `license_manager.py` 迁移。

| 项目 | 值 |
|------|-----|
| **命令名称** | `verify_license` |
| **调用方式** | 异步 |
| **参数** | 无 |
| **返回值** | `Result<LicenseInfo, String>` |

**返回的 LicenseInfo 结构**：

| 字段 | 类型 | 说明 |
|------|------|------|
| licensee | string | 被授权人名称 |
| edition | string | 授权版本 |
| expires | string\|null | 到期日期 |
| features | string[] | 功能列表 |
| installId | string | 安装实例 ID |
| deviceId | string | 设备指纹 |
| valid | boolean | 许可证是否有效 |

**前端调用示例**：

```typescript
const licenseInfo = await invoke<LicenseInfo>('verify_license');
```

**错误响应**：

| 错误信息 | 原因 |
|---------|------|
| `许可证文件不存在` | data/license.json 未找到 |
| `许可证签名无效` | Ed25519 验签失败 |
| `许可证已过期` | 当前日期超过 expires |
| `安装 ID 不匹配` | installId 与当前安装不一致 |
| `设备指纹不匹配` | deviceId 与当前设备不一致 |

**迁移要点**：

- Rust 侧需实现 `install_id.txt` 的读取和生成（对应 Python `get_install_id()`）
- Rust 侧需实现 Windows 卷序列号获取（对应 Python `device_id()` 中的 `GetVolumeInformationW`）
- Rust 侧需实现规范化 JSON 序列化（`sort_keys`, `separators=(",",":")`）
- 使用 `ed25519-dalek` crate 进行签名验证

---

### 21.3 activate_license（新增）

在 Rust 层直接向云端授权服务器发起激活请求，接收并验证许可证。

| 项目 | 值 |
|------|-----|
| **命令名称** | `activate_license` |
| **调用方式** | 异步 |
| **参数** | `code: String` |
| **返回值** | `Result<LicenseInfo, String>` |

**参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码 |

**前端调用示例**：

```typescript
const licenseInfo = await invoke<LicenseInfo>('activate_license', {
  code: 'OC-PRO-A1B2-C3D4-E5F6-7890'
});
```

**内部流程**：

1. 获取 `installId` 和 `deviceId`
2. 构造请求体：`{ code, installId, deviceId, appVersion: "desktop" }`
3. POST 到 `https://license.heang.top/activate`
4. 解析响应中的 `license` 对象
5. 在 Rust 侧执行 Ed25519 验签
6. 验证通过后写入 `data/license.json`
7. 返回 `LicenseInfo`

---

### 21.4 config_read（新增）

在 Rust 层直接读取 JSON 配置文件，无需经过 Python Sidecar。

| 项目 | 值 |
|------|-----|
| **命令名称** | `config_read` |
| **调用方式** | 异步 |
| **返回值** | `Result<Value, String>` |

**参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件路径 |
| default | Value | 是 | 文件不存在时的默认值 |

**前端调用示例**：

```typescript
const data = await invoke('config_read', {
  path: 'data/.openclaw/openclaw.json',
  default: { plugins: {} }
});
```

**安全限制**：同 Python Sidecar 的路径验证，必须在 base_path 或 data_dir 下。

---

### 21.5 config_write（新增）

在 Rust 层直接写入 JSON 配置文件。

| 项目 | 值 |
|------|-----|
| **命令名称** | `config_write` |
| **调用方式** | 异步 |
| **返回值** | `Result<(), String>` |

**参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件路径 |
| data | Value | 是 | 要写入的 JSON 数据 |

**前端调用示例**：

```typescript
await invoke('config_write', {
  path: 'data/.openclaw/openclaw.json',
  data: { plugins: { feishu: { enabled: true } } }
});
```

---

### 21.6 proxy_request（计划删除）

`proxy_request` 命令将在 Rust 层功能完善后逐步淘汰。迁移路径：

| 当前通过 proxy_request 调用的端点 | 迁移目标 |
|--------------------------------|---------|
| `/api/license/current` | `verify_license` IPC 命令 |
| `/api/license/activate` | `activate_license` IPC 命令 |
| `/api/license/authorized` | `verify_license` IPC 命令（本地判断） |
| `/api/config/read` | `config_read` IPC 命令 |
| `/api/config/write` | `config_write` IPC 命令 |
| `/api/process/*` | 暂保留 proxy_request |
| `/api/image/*` | 暂保留 proxy_request |
| `/api/video/*` | 暂保留 proxy_request |
| `/api/log/*` | 暂保留 proxy_request |
| `/api/update/*` | 暂保留 proxy_request |
| `/api/auth/profiles` | 暂保留 proxy_request |
| `/api/system/info` | 暂保留 proxy_request |
| `/api/theme/current` | 暂保留 proxy_request |

---

# 附录

---

## 附录 A: 端口分配

| 端口 | 用途 | 协议 | 说明 |
|------|------|------|------|
| 18790 | OpenClaw 网关 | HTTP | 固定端口，由 OpenClaw npm 包监听 |
| 18791~18800 | Python Sidecar | HTTP | 动态分配，首个可用端口 |
| 5173 | Vite Dev Server | HTTP | 仅开发模式 |

---

## 附录 B: 受保护端点清单

以下端点需要有效的许可证才能访问：

| 端点路径 | 需要的功能 | 说明 |
|---------|-----------|------|
| `/api/process/start` | openclaw | 启动网关服务 |
| `/api/image/generate` | image | AI 图片生成 |
| `/api/video/generate` | video | AI 视频生成 |

源码位置：[bridge.py:L89](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L89)

```python
PROTECTED_PATHS = {"/api/process/start", "/api/image/generate", "/api/video/generate"}
```

---

## 附录 C: 错误码速查表

### 云端授权服务器

| HTTP 状态码 | 场景 |
|-------------|------|
| 200 | 成功 |
| 400 | 请求参数错误、授权码无效/为空/已停用 |
| 403 | 授权码已被其他设备激活 |
| 404 | 授权码/商家不存在 |
| 409 | 商家 ID 重复 |
| 500 | 服务器内部错误 |

### Python Sidecar

| HTTP 状态码 | 场景 |
|-------------|------|
| 200 | 成功 |
| 400 | 请求参数错误（授权码为空、API Key 为空等） |
| 401 | X-Bridge-Token 缺失或不匹配 |
| 403 | 许可证无效或路径不在允许范围 |
| 404 | 未知端点路径 |
| 500 | 内部错误（API 调用失败、子进程异常等） |

### Tauri IPC Commands

| 错误类型 | 场景 |
|---------|------|
| `Err("Bridge 未启动")` | Sidecar 尚未启动 |
| `Err("[400] ...")` | Sidecar 返回 400 |
| `Err("[403] ...")` | Sidecar 返回 403（许可证无效） |
| `Err("[500] ...")` | Sidecar 返回 500 |
| `Err("bridge.py 未找到")` | Python 脚本不存在 |
| `Err("启动 Python bridge 失败")` | 子进程创建失败 |