# OpenClaw U盘便携版桌面管理器 — API 完整参考文档

> **文档状态：历史参考。**
> 当前 Bridge 迁移和只读接口冒烟检查以 `BRIDGE_MIGRATION_GUARD.md`
> 和 `scripts/smoke-bridge.ps1` 为准。本文来自早期代码快照，若与当前代码冲突，以代码和冒烟脚本为准。

> **版本**: 2.1
> **日期**: 2026-05-05
> **状态**: 实施规范 (基于实际代码核实)
> **适用范围**: 云端授权服务器、客户端 Python Sidecar、Tauri Rust IPC

---

## 目录

- [1. 文档说明](#1-文档说明)
- [2. 通用约定](#2-通用约定)
  - [2.1 认证方式](#21-认证方式)
  - [2.2 错误响应格式](#22-错误响应格式)
  - [2.3 日期与时间格式](#23-日期与时间格式)
  - [2.4 字符编码](#24-字符编码)
  - [2.5 HTTP 方法与路由](#25-http-方法与路由)
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
  - [9. 商家管理端点](#9-商家管理端点)
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
  - [19. 主题配置 (新增)](#19-主题配置-新增)
- [Part 3: Tauri Rust IPC Commands](#part-3-tauri-rust-ipc-commands)
  - [20. 现有命令](#20-现有命令)
  - [21. 计划改造命令](#21-计划改造命令)
- [附录 A: 端口分配](#附录-a-端口分配)
- [附录 B: 受保护端点清单](#附录-b-受保护端点清单)
- [附录 C: 错误码速查表](#附录-c-错误码速查表)
- [附录 D: API_SPEC.md 与实际代码差异记录](#附录-d-api_specmd-与实际代码差异记录)

---

## 1. 文档说明

本文档是 OpenClaw 桌面管理器的完整 API 参考手册，覆盖三层 API 架构的所有端点。

**与 API_SPEC.md 的关系**：本文档是 `API_SPEC.md` 的精炼替代品，修正了原规范中与实际代码不一致的部分（详见附录 D），并新增了主题系统 API 设计。

**数据来源**：
- Part 1 (云端 API) — 基于 `API_SPEC.md` 和 `ARCHITECTURE.md` 的设计规范
- Part 2 (Python Sidecar) — 基于 [bridge.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py) 实际源码核实
- Part 3 (Tauri IPC) — 基于 [lib.rs](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src-tauri/src/lib.rs) 实际源码核实
- 前端调用方式 — 基于 [api.ts](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/services/api.ts) 实际源码核实

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
- 源码位置：[bridge.py:L498-503](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L498-L503)

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

前端 [api.ts](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/services/api.ts#L27) 在捕获后自动清理前缀，提取纯错误信息：

```typescript
const cleanMsg = msg.replace(/^\[\d+\]\s*/, '');
```

### 2.3 日期与时间格式

| 场景 | 格式 | 示例 |
|------|------|------|
| 许可证到期日 | ISO 8601 日期 | `2027-05-01` |
| 激活时间戳 | ISO 8601 日期时间 | `2025-01-01T00:00:00+00:00` |
| 健康检查时间 | ISO 8601 日期时间 | `2026-05-03T12:03:35+00:00` |

### 2.4 字符编码

所有请求和响应均使用 UTF-8 编码。JSON 响应中非 ASCII 字符不转义（`ensure_ascii=False`）。

源码位置：[bridge.py:L479](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L479)

### 2.5 HTTP 方法与路由

**Python Sidecar 路由机制**：[bridge.py](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py) 的 `_route()` 方法统一处理 GET/POST/PUT 请求，路由判断基于路径而非方法。但部分端点对方法有语义要求（如 PUT 用于认证配置更新）。

**前端调用约定**：[api.ts](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/src/services/api.ts) 中默认使用 GET 方法，仅需要传参的端点使用 POST/PUT。

| 前端 api.ts 默认方法 | 使用场景 |
|---|---|
| GET（默认） | 查询类端点：status、current、info、get、check、list |
| POST | 操作类端点：start、stop、clear、activate、generate、do、read、write |
| PUT | 更新类端点：auth/profiles 的保存操作 |

---

## 3. 数据模型定义

### 3.1 License 许可证

许可证是系统的核心数据结构，由云端签发，客户端验证后本地持久化到 `data/license.json`。

```typescript
interface License {
  licenseId: string;
  licensee: string;
  edition: string;           // "pro" | "enterprise" | "starter"
  expires: string | null;    // ISO 8601 日期，null 表示永久有效
  features: string[];
  installId: string;         // UUID v4，绑定到安装实例
  deviceId?: string;         // SHA-256，绑定到物理机器
  activatedAt: string;       // ISO 8601 日期时间
  signature: string;         // Ed25519 签名 (Base64)
  theme?: ThemeConfig;       // 商家主题配置（新增，由商家管理模块注入）
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

**验证规则**（客户端执行，源码 [license_manager.py:L88-105](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L88-L105)）：

1. Ed25519 签名验证通过
2. `installId` 匹配当前安装实例
3. 若存在 `deviceId`，必须匹配当前设备硬件指纹
4. 若存在 `expires`，当前日期不得晚于到期日

### 3.2 Merchant 商家

商家数据结构用于主题系统，管理员在云端创建商家并配置其主题样式。

```typescript
interface Merchant {
  merchantId: string;
  name: string;
  subtitle: string;
  themeJson: ThemeConfig;
  logoUrl: string;
  createdAt: string;
  updatedAt: string;
}
```

### 3.3 ThemeConfig 主题配置

主题配置定义了界面的视觉风格，支持商家级自定义。

```typescript
interface ThemeConfig {
  name: string;
  colors: {
    app_bg: string;           // "#F3F4F5"
    sidebar_bg: string;       // "#F9F9FA"
    surface: string;          // "#FFFFFF"
    surface_alt: string;      // "#F6F7F8"
    surface_deep: string;     // "#1C202A"
    surface_deeper: string;   // "#14171E"
    hover: string;            // "#EDEFF1"
    input: string;            // "#F6F7F8"
    border: string;           // "#DDDFE3"
    border_strong: string;    // "#C1C4CC"
    text: string;             // "#1E2A3A"
    text_muted: string;       // "#64748B"
    text_subtle: string;      // "#94A3B8"
    accent: string;           // "#1A56DB"
    accent_hover: string;     // "#1444AD"
    accent_soft: string;      // "#E4E8F0"
    accent_ink: string;       // "#0F327F"
    success: string;          // "#059669"
    warning: string;          // "#D97706"
    danger: string;           // "#DC2626"
    danger_hover: string;     // "#B91C1C"
    terminal_bg: string;      // "#0F172A"
    terminal_header: string;  // "#1E293B"
    terminal_text: string;    // "#34D399"
  };
  fonts: {
    display: [string, number, string];   // [字体名, 大小, 粗细]
    title: [string, number, string];
    section: [string, number, string];
    body: [string, number, string];
    small: [string, number, string];
    mono: [string, number, string];
  };
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
  running: boolean;
  pid: number | null;
}
```

### 3.5 UpdateInfo 更新信息

```typescript
interface UpdateInfo {
  current: string;
  latest: string;
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

源码位置：[license_manager.py:L23](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L23)

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

源码位置：[license_manager.py:L88-105](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L88-L105)

```python
def verify(self, license_data: dict[str, Any]) -> bool:
    try:
        signature = base64.b64decode(license_data["signature"])
        payload = dict(license_data)
        payload.pop("signature", None)
        self.public_key.verify(signature, self._canonical(payload))
        if payload.get("installId") != self.get_install_id():
            return False
        licensed_device = payload.get("deviceId")
        if licensed_device and licensed_device != self.device_id():
            return False
        expires = payload.get("expires")
        if expires and date.fromisoformat(expires) < date.today():
            return False
        return True
    except (KeyError, ValueError, InvalidSignature, TypeError):
        return False
```

**设备指纹生成**：基于 Windows 卷序列号 + 盘符 + 固定盐值，经 SHA-256 哈希生成。

源码位置：[license_manager.py:L50-72](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/license_manager.py#L50-L72)

```python
root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
volume_serial = ctypes.c_ulong()
ctypes.windll.kernel32.GetVolumeInformationW(
    ctypes.c_wchar_p(root), None, 0,
    ctypes.byref(volume_serial), None, None, None, 0
)
serial = str(volume_serial.value)
if serial is None:
    serial = str(uuid.getnode())
raw = f"{root}|{serial}|openclaw-launcher"
device_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

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

**字符集**：`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`（去除 I/O/0/1 避免混淆）

**处理规则**：

- 客户端激活时自动转大写：`code = code.strip().upper()`
- 授权码在云端数据库中存储其 SHA-256 哈希值，原始码不落库
- 哈希算法：`SHA256("openclaw-license-v1:" + code.upper())`
- 管理员可通过 `/admin/api/codes/hash` 端点计算授权码哈希

---

# Part 1: 云端授权服务器 API

**Base URL**：`https://license.heang.top`
**协议**：HTTPS
**字符编码**：UTF-8

---

## 6. 公开端点

### 6.1 健康检查

| 项目 | 值 |
|------|-----|
| **URL路径** | `/health` |
| **请求方法** | GET |
| **认证** | 无 |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | boolean | 服务是否正常 |
| time | string | 服务器当前时间（ISO 8601） |

**示例响应**（200）：

```json
{
  "ok": true,
  "time": "2026-05-03T12:03:35+00:00"
}
```

**错误码**：500 — 服务器内部错误

---

### 6.2 获取 Ed25519 公钥

| 项目 | 值 |
|------|-----|
| **URL路径** | `/public-key` |
| **请求方法** | GET |
| **认证** | 无 |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| publicKey | string | Ed25519 公钥，Base64 编码 |

**示例响应**（200）：

```json
{
  "publicKey": "njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4="
}
```

**错误码**：500 — 服务器内部错误

---

## 7. 授权激活端点

### 7.1 授权码激活

客户端使用授权码向云端请求许可证。此端点由 Python Sidecar 的 `LicenseManager.activate()` 内部调用，前端不直接访问。

| 项目 | 值 |
|------|-----|
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

```json
{
  "code": "OC-PRO-A1B2-C3D4-E5F6-7890",
  "installId": "550e8400-e29b-41d4-a716-446655440000",
  "deviceId": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
  "appVersion": "desktop"
}
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
| license.theme | object | 商家主题配置（新增，仅当授权码关联商家时返回） |

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
      "colors": { "app_bg": "#F0F2F5" },
      "fonts": { "display": ["Microsoft YaHei UI", 21, "bold"] },
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

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin` |
| **请求方法** | GET |
| **认证** | 无 |
| **响应格式** | `text/html` |

---

### 8.2 列出所有授权码

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/codes` |
| **请求方法** | GET |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| codes | array | 授权码列表 |

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

**错误码**：401 — 管理员令牌缺失或无效 | 500 — 服务器内部错误

---

### 8.3 批量生成授权码

| 项目 | 值 |
|------|-----|
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
| merchantId | string | 否 | 关联商家 ID（新增，用于主题下发） |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| codes | string[] | 生成的授权码明文列表（仅此一次返回明文） |

**示例响应**（200）：

```json
{
  "codes": [
    "OC-PRO-A1B2-C3D4-E5F6-7890",
    "OC-PRO-B2C3-D4E5-F6A7-8901"
  ]
}
```

**错误码**：400 — 参数错误 | 401 — 管理员令牌无效 | 500 — 服务器内部错误

---

### 8.4 启用/停用授权码

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/codes/toggle` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| codeHash | string | 是 | 授权码哈希值 |
| active | boolean | 是 | 目标状态：true 启用，false 停用 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |
| active | boolean | 更新后的状态 |

**错误码**：400 — 参数错误 | 401 — 令牌无效 | 404 — 授权码不存在 | 500 — 服务器内部错误

---

### 8.5 清空全部授权码

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/codes/clear` |
| **请求方法** | POST |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |
| deleted | number | 被删除的授权码数量 |

**错误码**：401 — 令牌无效 | 500 — 服务器内部错误

---

### 8.6 计算授权码哈希

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/codes/hash` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码明文 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| hash | string | 授权码的 SHA-256 哈希值 |

**错误码**：400 — 授权码为空 | 401 — 令牌无效 | 500 — 服务器内部错误

---

### 8.7 删除单个授权码

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/codes/delete` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| codeHash | string | 是 | 要删除的授权码哈希值 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |

**错误码**：400 — codeHash 为空 | 401 — 令牌无效 | 404 — 授权码不存在 | 500 — 服务器内部错误

---

## 9. 商家管理端点

以下端点为主题系统新增，用于管理商家信息及其主题配置。

### 9.1 列出所有商家

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/merchants` |
| **请求方法** | GET |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchants | Merchant[] | 商家列表 |

**示例响应**（200）：

```json
{
  "merchants": [
    {
      "merchantId": "yonghao-tech",
      "name": "永浩科技",
      "subtitle": "智能AI服务平台",
      "themeJson": { "name": "永浩科技主题", "colors": { "app_bg": "#F3F4F5" } },
      "logoUrl": "https://cdn.heang.top/logos/yonghao.png",
      "createdAt": "2026-01-01T00:00:00+00:00",
      "updatedAt": "2026-05-01T00:00:00+00:00"
    }
  ]
}
```

**错误码**：401 — 令牌无效 | 500 — 服务器内部错误

---

### 9.2 创建商家

| 项目 | 值 |
|------|-----|
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

**响应格式**（201）：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchant | Merchant | 创建的商家对象 |

**错误码**：400 — 参数错误 | 401 — 令牌无效 | 409 — 商家已存在 | 500 — 服务器内部错误

---

### 9.3 更新商家信息

| 项目 | 值 |
|------|-----|
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

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| merchant | Merchant | 更新后的商家对象 |

**错误码**：400 — 参数错误 | 401 — 令牌无效 | 404 — 商家不存在 | 500 — 服务器内部错误

---

### 9.4 删除商家

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/merchants/{merchantId}` |
| **请求方法** | DELETE |
| **请求头** | `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 操作结果 |

**错误码**：401 — 令牌无效 | 404 — 商家不存在 | 500 — 服务器内部错误

---

### 9.5 主题预览

| 项目 | 值 |
|------|-----|
| **URL路径** | `/admin/api/merchants/{merchantId}/preview` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Admin-Token: <admin-secret>` |
| **请求参数** | 无 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| previewToken | string | 预览令牌 |
| previewUrl | string | 预览页面 URL |

**错误码**：401 — 令牌无效 | 404 — 商家不存在 | 500 — 服务器内部错误

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
| **URL路径** | `/api/process/start` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `processApi.start()` → `api('/api/process/start', 'POST')` |

> 源码位置：[bridge.py:L208-218](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L208-L218)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 启动状态：`started` 或 `already_running` |
| pid | number\|null | 进程 PID（仅 status=started 时返回） |

**示例响应** — 进程已启动：

```json
{
  "status": "started",
  "pid": 12345
}
```

**示例响应** — 进程已在运行：

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
| 500 | (异常信息) | 环境配置异常 |

---

### 10.2 停止 OpenClaw 进程

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/process/stop` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `processApi.stop()` → `api('/api/process/stop', 'POST')` |

> 源码位置：[bridge.py:L220-223](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L220-L223)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `stopped` |
| message | string | 操作结果描述 |

**message 可能的值**：

| 消息 | 场景 |
|------|------|
| 服务已停止 | 正常停止运行中的进程 |
| 已清理 N 个端口占用进程 | 进程已退出但端口仍被占用 |
| 没有运行中的服务 | 进程已退出且无端口占用 |
| 服务未启动 | 从未启动过服务 |

**错误码**：401 — 未授权的请求

---

### 10.3 获取进程状态

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/process/status` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `processApi.status()` → `api('/api/process/status')` |

> 源码位置：[bridge.py:L225-230](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L225-L230)

**响应格式**（200）：参见 [ProcessStatus 数据模型](#34-processstatus-进程状态)

**示例响应** — 运行中：

```json
{
  "running": true,
  "pid": 12345
}
```

**示例响应** — 未运行：

```json
{
  "running": false,
  "pid": null
}
```

**错误码**：401 — 未授权的请求

---

## 11. 日志管理

### 11.1 获取日志

获取日志缓冲区的全部内容。日志缓冲区最多保留最近 500 行。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/log/get` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `logApi.get()` → `api('/api/log/get')` |

> ⚠️ **与 API_SPEC.md 的差异**：API_SPEC.md 标注此端点使用 POST 方法，但前端实际使用 GET 调用（`logApi.get()` 默认方法为 GET）。Python Bridge 路由不区分方法，因此两种方法均可工作，但推荐使用 GET 以符合语义。

> 源码位置：[bridge.py:L234-237](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L234-L237)

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

**错误码**：401 — 未授权的请求

---

### 11.2 清除日志

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/log/clear` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `logApi.clear()` → `api('/api/log/clear', 'POST')` |

> 源码位置：[bridge.py:L239-242](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L239-L242)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `cleared` |

**错误码**：401 — 未授权的请求

---

## 12. 授权管理

### 12.1 获取当前许可证

获取本地存储的当前许可证信息。此接口读取 `data/license.json` 并验证签名有效性。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/license/current` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `licenseApi.current()` → `api('/api/license/current')` |

> ⚠️ **与 API_SPEC.md 的差异**：API_SPEC.md 标注此端点使用 POST 方法，但前端实际使用 GET 调用。Python Bridge 路由不区分方法，因此两种方法均可工作，但推荐使用 GET。

> 源码位置：[bridge.py:L246-249](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L246-L249)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| license | object\|null | 许可证对象，验证失败或不存在时为 null |

**示例响应** — 已授权：

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

**示例响应** — 未授权：

```json
{
  "license": null
}
```

**错误码**：401 — 未授权的请求

---

### 12.2 激活授权码

使用授权码进行在线激活。此端点内部调用云端 `/activate` API，验证返回的许可证签名，并持久化到本地。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/license/activate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `licenseApi.activate(code)` → `api('/api/license/activate', 'POST', { code })` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| code | string | 是 | 授权码，自动转大写 |

> 源码位置：[bridge.py:L251-262](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L251-L262)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| license | object | 激活成功后的许可证对象 |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 授权码不能为空 | code 字段为空 |
| 400 | 请输入授权码 | code 为空字符串 |
| 400 | 授权码不存在 | 云端返回 404 |
| 400 | 授权码已停用 | 云端返回 403（停用） |
| 400 | 授权码已被其他设备激活 | 云端返回 403（超限） |
| 400 | 授权服务器返回的许可证无效 | 云端返回的许可证签名验证失败 |
| 400 | 无法连接授权服务器：... | 网络错误 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |

> 注意：Python Bridge 的 `_license_activate` 方法单独捕获 `LicenseError`，将所有业务错误统一返回 HTTP 400。源码 [bridge.py:L251-262](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L251-L262)

---

### 12.3 检查授权状态

检查当前是否持有有效授权，可指定检查特定功能。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/license/authorized` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `licenseApi.authorized(feature?)` → `api('/api/license/authorized', 'POST', { feature })` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| feature | string | 否 | 功能标识，不传则只检查是否有任何有效许可证 |

> 源码位置：[bridge.py:L264-267](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L264-L267)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| authorized | boolean | 是否已授权指定功能 |

**示例响应** — 已授权图片功能：

```json
{
  "authorized": true
}
```

**错误码**：401 — 未授权的请求

---

## 13. AI 图片生成

### 13.1 图片生成/编辑

调用 OpenAI 兼容的图片生成 API 生成或编辑图片。此端点受许可证保护，需有效授权且包含 `image` 功能。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/image/generate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `imageApi.generate(params)` → `api('/api/image/generate', 'POST', params)` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| baseUrl | string | 是 | 图像 API 中转站地址，如 `https://api.heang.top/v1` |
| apiKey | string | 否 | API Key，附加到请求的 Authorization Header |
| prompt | string | 是 | 图片描述提示词 |
| size | string | 否 | 图片尺寸，默认 `1024x1024`，可选值：`1024x1024`、`1024x1536`、`1536x1024`、`512x512` |
| count | number | 否 | 生成数量，默认 `1`，范围 1~9 |
| editImagePath | string | 否 | 编辑参考图，支持本地文件路径或 base64 数据 URL（`data:image/png;base64,...`） |

> 源码位置：[bridge.py:L271-316](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L271-L316)

**示例请求** — 文生图：

```json
{
  "baseUrl": "https://api.heang.top/v1",
  "apiKey": "sk-xxx",
  "prompt": "一只猫在阳光下睡觉",
  "size": "1024x1024",
  "count": 1
}
```

**示例请求** — 图编辑（base64 数据 URL）：

```json
{
  "baseUrl": "https://api.heang.top/v1",
  "apiKey": "sk-xxx",
  "prompt": "将背景改为白色",
  "size": "1024x1024",
  "editImagePath": "data:image/png;base64,iVBORw0KGgo..."
}
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| images | string[] | 生成的图片列表，每项为 Base64 编码的图片数据 |
| count | number | 实际生成的图片数量 |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | 中转站地址不能为空 | baseUrl 为空 |
| 400 | 提示词不能为空 | prompt 为空 |
| 400 | 图片数据解码失败: ... | editImagePath 的 base64 数据格式错误 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 需要有效的许可证才能使用此功能 | 许可证无效或不含 image 功能 |
| 500 | (ImageApiError) | 上游 API 返回错误 |

**内部实现细节**：

- 使用的模型：`gpt-image-2`（定义在 [constants.py:L19](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/constants.py#L19)）
- 生成请求：`POST {baseUrl}/v1/images/generations`
- 编辑请求：`POST {baseUrl}/v1/images/edits`（multipart/form-data）
- base64 数据 URL 会被解码保存为临时文件，请求完成后自动删除

---

## 14. AI 视频生成

### 14.1 视频生成

调用阿里云 DashScope 视频 API 生成视频。此端点受许可证保护，需有效授权且包含 `video` 功能。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/video/generate` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `videoApi.generate(params)` → `api('/api/video/generate', 'POST', params)` |

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

> 源码位置：[bridge.py:L320-367](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L320-L367)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| video | string | 生成的视频数据，Base64 编码 |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | DashScope API Key 不能为空 | dashKey 为空 |
| 400 | 提示词不能为空 | prompt 为空 |
| 400 | 图片数据解码失败: ... | imagePath 的 base64 数据格式错误 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 需要有效的许可证才能使用此功能 | 许可证无效或不含 video 功能 |
| 500 | (VideoApiError) | DashScope 视频 API 调用失败或生成超时 |

**内部实现细节**：

- 文生视频模型：`happyhorse-1.0-t2v`（定义在 [constants.py:L25](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/constants.py#L25)）
- 图生视频模型：`happyhorse-1.0-i2v`（定义在 [constants.py:L26](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/core/constants.py#L26)）
- 提交任务 URL：`https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis`
- 轮询任务 URL：`https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}`
- 异步模式：请求时携带 `X-DashScope-Async: enable` Header
- base64 数据 URL 会被解码保存为临时文件，请求完成后自动删除

---

## 15. 版本更新

### 15.1 检查更新

查询 npm 仓库中 openclaw 包的最新版本，与本地安装版本对比。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/update/check` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `updateApi.check()` → `api('/api/update/check')` |

> 源码位置：[bridge.py:L371-378](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L371-L378)

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
| 500 | (updater 错误信息) | 找不到 Node.js / 找不到 pnpm / 网络错误 |

---

### 15.2 执行更新

执行 openclaw 包的版本更新，通过 pnpm 安装最新版本。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/update/do` |
| **请求方法** | POST |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `updateApi.do()` → `api('/api/update/do', 'POST')` |

> 源码位置：[bridge.py:L380-409](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L380-L409)

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
| 500 | (异常信息) | pnpm 命令执行异常 |

---

## 16. 配置读写

### 16.1 读取配置文件

读取指定路径的 JSON 配置文件。路径必须位于允许的目录范围内（base_path 或 data_dir），否则返回 403。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/config/read` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `configApi.read(path, defaultValue)` → `api('/api/config/read', 'POST', { path, default: defaultValue })` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件的绝对路径或相对路径 |
| default | any | 否 | 文件不存在时的默认返回值，默认 `{}` |

> 源码位置：[bridge.py:L425-432](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L425-L432)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| data | any | 读取到的 JSON 内容，文件不存在时返回 default |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 路径不在允许的范围内 | 路径超出 base_path 或 data_dir |

**路径安全校验**（源码 [bridge.py:L413-423](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L413-L423)）：

```python
def _safe_path(self, file_path: str) -> str | None:
    if not file_path:
        return None
    real_path = os.path.realpath(file_path)
    allowed_prefixes = (os.path.realpath(paths.base_path), os.path.realpath(paths.data_dir))
    if real_path.startswith(allowed_prefixes):
        return real_path
    return None
```

---

### 16.2 写入配置文件

将 JSON 数据写入指定路径的配置文件。路径必须位于允许的目录范围内。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/config/write` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |
| **前端调用** | `configApi.write(path, data)` → `api('/api/config/write', 'POST', { path, data })` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| path | string | 是 | 配置文件的绝对路径或相对路径 |
| data | any | 是 | 要写入的 JSON 数据 |

> 源码位置：[bridge.py:L434-441](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L434-L441)

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `ok` |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 403 | 路径不在允许的范围内 | 路径超出 base_path 或 data_dir |

---

## 17. 认证配置管理

### 17.1 获取/保存认证配置

此端点根据 HTTP 方法不同执行不同操作：

- **GET/POST**：读取当前 API 提供商认证配置
- **PUT**：合并更新 API 提供商认证配置

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/auth/profiles` |
| **请求方法** | GET / POST / PUT |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

> 源码位置：[bridge.py:L445-454](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L445-L454)

**读取配置（GET/POST）**：无请求参数。

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

**保存配置（PUT）**：请求体为要合并的配置数据，会与现有配置合并（`dict.update`）。

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| models | object | 否 | 模型提供商配置 |
| *(其他字段)* | any | 否 | 会被合并到现有配置中 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定值 `ok` |

**错误码**：401 — 未授权的请求

**本地存储路径**：`{base_path}/data/.openclaw/agents/main/agent/auth-profiles.json`

---

## 18. 系统信息

### 18.1 获取系统环境信息

获取当前运行环境的关键路径和版本信息。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/system/info` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |
| **前端调用** | `systemApi.info()` → `api('/api/system/info')` |

> 源码位置：[bridge.py:L458-464](file:///d:/Axiangmu/AUSTART/openclaw_new_launcher/python/bridge.py#L458-L464)

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

**错误码**：401 — 未授权的请求

---

## 19. 主题配置 (新增)

以下 3 个端点为主题系统新增设计，基于 ARCHITECTURE.md 中的主题系统架构和 AGENT_TASKS.md 中的接口契约。

### 19.1 获取当前主题配置

获取当前许可证关联的商家主题配置。若许可证包含 `theme` 字段，则返回该主题；否则返回默认主题（永浩科技）。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/theme/current` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**设计说明**：此端点不需要许可证鉴权，未激活用户也需要看到默认主题。

**三级回退策略**：

```
1. license_data["theme"]    — 激活时服务器下发 (最优先)
2. data/themes/{merchantId}/theme.json — 本地主题包 (离线回退)
3. DEFAULT_THEME            — 内置默认主题 (兜底)
```

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| theme | ThemeConfig | 当前主题配置 |
| isCustom | boolean | 是否为商家自定义主题（非默认） |
| merchantId | string\|null | 关联的商家 ID，默认主题为 null |

**示例响应** — 自定义主题：

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
    "fonts": {
      "display": ["Microsoft YaHei UI", 21, "bold"],
      "body": ["Microsoft YaHei UI", 10],
      "mono": ["Consolas", 10]
    },
    "brand": {
      "name": "示例科技",
      "subtitle": "智能解决方案"
    }
  },
  "isCustom": true,
  "merchantId": "example-tech"
}
```

**示例响应** — 默认主题：

```json
{
  "theme": {
    "name": "永浩科技主题",
    "colors": { "app_bg": "#F3F4F5" },
    "fonts": { "display": ["Microsoft YaHei UI", 21, "bold"] },
    "brand": { "name": "永浩科技", "subtitle": "智能AI服务平台" }
  },
  "isCustom": false,
  "merchantId": null
}
```

**错误码**：401 — 未授权的请求

---

### 19.2 根据 merchantId 获取主题配置

根据商家标识查找本地主题包，用于离线场景或主题预览。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/theme/merchant` |
| **请求方法** | POST |
| **请求头** | `Content-Type: application/json`, `X-Bridge-Token: <token>` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| merchantId | string | 是 | 商家唯一标识 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| theme | ThemeConfig | 商家主题配置 |

**错误码**：

| HTTP 状态码 | 错误信息 | 说明 |
|-------------|---------|------|
| 400 | merchantId 不能为空 | merchantId 为空 |
| 401 | 未授权的请求 | X-Bridge-Token 缺失或不匹配 |
| 404 | 主题包不存在 | 对应 merchantId 的本地主题包未找到 |

---

### 19.3 列出所有可用主题

列出所有本地可用的主题包。

| 项目 | 值 |
|------|-----|
| **URL路径** | `/api/theme/list` |
| **请求方法** | GET |
| **请求头** | `X-Bridge-Token: <token>` |
| **请求参数** | 无 |

**响应格式**（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| themes | object[] | 可用主题列表 |
| themes[].merchantId | string | 商家 ID |
| themes[].name | string | 主题名称 |
| themes[].isCustom | boolean | 是否为自定义主题 |

**示例响应**（200）：

```json
{
  "themes": [
    { "merchantId": null, "name": "永浩科技主题", "isCustom": false },
    { "merchantId": "example-tech", "name": "示例科技主题", "isCustom": true }
  ]
}
```

**错误码**：401 — 未授权的请求
