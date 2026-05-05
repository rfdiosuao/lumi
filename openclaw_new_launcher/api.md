# OpenClaw Launcher API 文档

## 架构概述

```
前端 (React)  →  Tauri invoke ('proxy_request')  →  Python Bridge (HTTP)  →  业务逻辑
```

- 前端通过 `invoke('proxy_request', { path, method, body })` 调用 Tauri Rust 命令
- Rust 层转发 HTTP 请求到本地 Python Bridge（端口动态分配，约 `18791`）
- Python Bridge 处理业务逻辑并返回 JSON

---

## Tauri 原生命令 (Rust 层)

| 命令 | 类型 | 说明 |
|------|------|------|
| `get_bridge_port` | 同步 | 返回当前 Bridge 端口号（`u16`） |
| `start_bridge` | 异步 | 启动 Python Bridge 子进程，返回 `"Bridge started on port XXX"` |
| `proxy_request` | 异步 | 代理 HTTP 请求到 Bridge，返回响应体文本 |

---

## Python Bridge 端点

Base URL: `http://127.0.0.1:{port}`（端口由 `get_bridge_port` 获取）

### 1. 进程管理

#### `POST /api/process/start`
启动 OpenClaw 服务进程。

**请求体**: 无
```json
{}
```

**响应** (200):
```json
{
  "status": "started",
  "pid": 12345
}
```

**响应** (已在运行):
```json
{
  "status": "already_running"
}
```

---

#### `POST /api/process/stop`
停止 OpenClaw 服务进程。

**请求体**: 无
```json
{}
```

**响应** (200):
```json
{
  "status": "stopped",
  "message": "..."
}
```

---

#### `GET /api/process/status`
查询服务进程状态。

**请求参数**: 无

**响应** (200):
```json
{
  "running": true,
  "pid": 12345
}
```

---

### 2. 日志

#### `GET /api/log/get`
获取日志缓冲区内容。

**请求参数**: 无

**响应** (200):
```json
{
  "log": "[服务] 启动成功\n[INFO] ..."
}
```

---

#### `POST /api/log/clear`
清空日志缓冲区。

**请求体**: 无
```json
{}
```

**响应** (200):
```json
{
  "status": "cleared"
}
```

---

### 3. 授权

#### `GET /api/license/current`
获取当前本地许可证信息。

**请求参数**: 无

**响应** (200):
```json
{
  "license": {
    "licenseId": "...",
    "licensee": "客户名",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "...",
    "deviceId": "...",
    "activatedAt": "2025-01-01T00:00:00+00:00",
    "signature": "base64-encoded-ed25519-signature"
  }
}
```

无许可证时:
```json
{
  "license": null
}
```

---

#### `POST /api/license/activate`
使用授权码在线激活。

**请求体**:
```json
{
  "code": "OC-PRO-XXXX-XXXX-XXXX-XXXX"
}
```

**响应** (200):
```json
{
  "license": {
    "licenseId": "...",
    "licensee": "客户名",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "...",
    "deviceId": "...",
    "activatedAt": "2025-01-01T00:00:00+00:00",
    "signature": "base64-encoded-ed25519-signature"
  }
}
```

**错误响应**:

| HTTP 状态 | 错误信息 | 含义 |
|-----------|---------|------|
| 400 | `授权码不能为空` | 空授权码 |
| 404 | `授权码不存在` | 数据库中找不到 |
| 403 | `授权码已停用` | 被管理员停用 |
| 403 | `授权码已被其他设备激活` | 超过最大激活次数 |
| 400 | `授权服务器返回的许可证无效` | 签名验证失败（client 端校验） |

---

#### `POST /api/license/authorized`
检查是否已授权（可选指定功能）。

**请求体**:
```json
{
  "feature": "image"
}
```

**响应** (200):
```json
{
  "authorized": true
}
```

---

### 4. AI 生图

#### `POST /api/image/generate`
调用 AI 图像 API 生成图片。

**请求体**:
```json
{
  "baseUrl": "https://api.heang.top/v1",
  "apiKey": "sk-xxx",
  "prompt": "一只猫",
  "size": "1024x1024",
  "count": 1,
  "editImagePath": null
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `baseUrl` | string | 是 | 图像 API 中转站地址 |
| `apiKey` | string | 是 | API Key |
| `prompt` | string | 是 | 提示词 |
| `size` | string | 是 | 图片尺寸，默认 `"1024x1024"` |
| `count` | number | 否 | 生成数量，默认 `1` |
| `editImagePath` | string | 否 | 编辑参考图的 base64 数据 URL（`data:image/png;base64,...`） |

**响应** (200):
```json
{
  "images": ["base64-encoded-image-data..."],
  "count": 1
}
```

**错误响应**:
| HTTP 状态 | 说明 |
|-----------|------|
| 400 | 中转站地址/提示词为空 |
| 400 | 图片数据解码失败 |
| 500 | 图像 API 调用失败 |

---

### 5. AI 视频

#### `POST /api/video/generate`
调用 DashScope 视频 API 生成视频。

**请求体**:
```json
{
  "dashKey": "sk-dashscope-xxx",
  "prompt": "一只猫在跑",
  "mode": "t2v",
  "resolution": "720P",
  "duration": 5,
  "ratio": "16:9",
  "imagePath": null
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `dashKey` | string | 是 | DashScope API Key |
| `prompt` | string | 是 | 提示词 |
| `mode` | string | 是 | 模式: `"t2v"` (文生视频) 或 `"i2v"` (图生视频) |
| `resolution` | string | 是 | 分辨率，默认 `"720P"` |
| `duration` | number | 是 | 视频时长（秒），默认 `5` |
| `ratio` | string | 是 | 宽高比，默认 `"16:9"` |
| `imagePath` | string | 否 | 参考图片 base64 数据 URL（i2v 模式必填） |

**响应** (200):
```json
{
  "video": "base64-encoded-video-data..."
}
```

**错误响应**:
| HTTP 状态 | 说明 |
|-----------|------|
| 400 | DashScope Key / 提示词为空 |
| 400 | 图片数据解码失败 |
| 500 | DashScope 视频 API 调用失败 |

---

### 6. 更新

#### `GET /api/update/check`
检查是否有新版本。

**请求参数**: 无

**响应** (200):
```json
{
  "current": "2.0.0",
  "latest": "2.1.0",
  "hasUpdate": true
}
```

---

#### `POST /api/update/do`
执行版本更新。

**请求体**: 无
```json
{}
```

**响应** (200):
```json
{
  "success": true,
  "current_version": "2.1.0",
  "log": ["package.json updated", "..."]
}
```

---

### 7. 配置

#### `POST /api/config/read`
读取配置文件。

**请求体**:
```json
{
  "path": "data/.openclaw/openclaw.json",
  "default": { "plugins": {} }
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 配置文件路径（相对于项目根目录） |
| `default` | any | 否 | 文件不存在时的默认值，默认 `{}` |

**响应** (200):
```json
{
  "data": { ...读取的JSON内容... }
}
```

---

#### `POST /api/config/write`
写入配置文件。

**请求体**:
```json
{
  "path": "data/.openclaw/openclaw.json",
  "data": { "plugins": { ... } }
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | string | 是 | 配置文件路径 |
| `data` | any | 是 | 要写入的 JSON 数据 |

**响应** (200):
```json
{
  "status": "ok"
}
```

---

### 8. 授权配置

#### `GET /api/auth/profiles`
获取已保存的 API 提供商配置。

**请求参数**: 无

**响应** (200):
```json
{
  "profiles": {
    "models": {
      "providers": {
        "heang_ai": {
          "id": "heang_ai",
          "name": "Heang AI",
          "baseUrl": "https://api.heang.top/v1",
          "apiKey": "...",
          "models": ["kimi-k2.5", "gpt-4o"]
        }
      },
      "primary": "heang_ai"
    }
  }
}
```

---

#### `PUT /api/auth/profiles`
保存 API 提供商配置。

**请求体**: 完整配置 JSON（会合并到现有文件）

```json
{
  "models": {
    "providers": {
      "heang_ai": { ... }
    },
    "primary": "heang_ai"
  }
}
```

**响应** (200):
```json
{
  "status": "ok"
}
```

---

### 9. 系统信息

#### `GET /api/system/info`
获取系统环境信息。

**请求参数**: 无

**响应** (200):
```json
{
  "node_path": "C:\\path\\to\\node.exe",
  "base_path": "C:\\path\\to\\openclaw",
  "openclaw_version": "2.0.0"
}
```

---

## 云端授权服务器 API

Base URL: `https://license.heang.top`

### `GET /health`
健康检查。

**响应** (200):
```json
{
  "ok": true,
  "time": "2026-05-03T12:03:35+00:00"
}
```

---

### `GET /public-key`
获取 Ed25519 公钥（Base64 编码）。

**响应** (200):
```json
{
  "publicKey": "njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4="
}
```

---

### `POST /activate`
授权码激活端点（客户端调用，非直接访问）。

**请求体**:
```json
{
  "code": "OC-PRO-XXXX-XXXX-XXXX-XXXX",
  "installId": "uuid-here",
  "deviceId": "sha256-here",
  "appVersion": "desktop"
}
```

**响应** (200):
```json
{
  "license": {
    "licenseId": "...",
    "licensee": "...",
    "edition": "pro",
    "features": ["openclaw", "image", "video", "storyboard"],
    "expires": "2027-05-01",
    "installId": "...",
    "deviceId": "...",
    "activatedAt": "...",
    "signature": "..."
  }
}
```

**错误响应**:

| HTTP 状态 | 说明 |
|-----------|------|
| 400 | 缺少授权码或安装 ID |
| 404 | 授权码不存在 |
| 403 | 授权码已停用 |
| 403 | 已被其他设备激活（超过激活次数） |
| 500 | 服务器内部错误 |

---

## 前端 API 封装 (api.ts)

所有前端调用均通过 `invoke('proxy_request')` 转发到 Python Bridge。封装路径：

```
src/services/api.ts
  └→ api(path, method, body)  // 统一入口
       └→ proxyRequest(path, method, body)  // 底层 invoke
            └→ tauri invoke('proxy_request')
                 └→ reqwest → Python Bridge HTTP
```

错误统一格式: `{ error: "错误信息" }`
