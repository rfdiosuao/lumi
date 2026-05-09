# Phone Connector API Contract

> 更新时间：2026-05-10
> 用途：定义 Lumi 桌面端对接 APKClaw 手机端的最小 API 契约，先支撑“连接手机、显示截图、点击截图”的 MVP。

## 1. 当前 APKClaw 事实

源码位置：

```text
D:\Axiangmu\AUSTART\apkclaw\Hermes-Agent-phone-codex-template-parameter-extraction
```

当前手机端实现：

- HTTP server：NanoHTTPD。
- 默认端口：`9527`。
- Server 文件：`app/src/main/java/com/apk/claw/android/server/ConfigServer.kt`。
- Tool API：`ToolApiController.kt`。
- Agent API：`AgentApiController.kt`。
- Token 校验：`TokenValidator.kt`。

当前已存在的可用接口：

- `GET /api/agent/status`
- `POST /api/agent/execute_task`
- `POST /api/agent/cancel_task`
- `GET /api/tool/screenshot`
- `POST /api/tool/tap`
- `POST /api/tool/swipe`
- `POST /api/tool/long_press`
- `GET /api/tool/get_screen_info`
- `POST /api/tool/input_text`
- `POST /api/tool/system_key`
- `POST /api/tool/open_app`

当前鉴权 Header：

```text
X-AGENT-PHONE-TOKEN: <token>
```

兼容旧 Header：

```text
X-APKCLAW-TOKEN: <token>
```

Lumi 新接入统一使用 `X-AGENT-PHONE-TOKEN`。

## 2. Lumi 端连接配置

Lumi 需要保存一组最小配置：

```json
{
  "name": "My Android Phone",
  "baseUrl": "http://192.168.1.100:9527",
  "token": "your-token"
}
```

规则：

- `baseUrl` 必须包含协议。
- 默认端口是 `9527`。
- 末尾 `/` 在保存时去掉。
- Token 只用于请求 Header，不写入日志明文。
- MVP 先支持单设备，数据结构预留多设备。

## 3. 统一响应模型

APKClaw 当前多数 API 返回：

```json
{
  "success": true,
  "data": "...",
  "error": null
}
```

Lumi `phoneApi` 内部统一转换成：

```ts
interface PhoneApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  raw?: unknown;
}
```

转换规则：

- `success === true` -> `ok: true`
- `success === false` -> `ok: false`
- HTTP `401` -> `ok: false`, `error: "unauthorized"`
- 网络失败 -> `ok: false`, `error: "network_error"`
- JSON 解析失败 -> `ok: false`, `error: "invalid_response"`

## 4. 状态接口

### MVP 使用现有接口

```text
GET /api/agent/status
```

Header：

```text
X-AGENT-PHONE-TOKEN: <token>
```

当前 APKClaw 返回的 `data` 是 JSON 字符串，内容类似：

```json
{
  "taskRunning": false,
  "agentInitialized": true,
  "llmConfigured": true,
  "accessibilityRunning": true
}
```

Lumi 端规范化为：

```ts
interface PhoneStatus {
  online: boolean;
  taskRunning: boolean;
  agentInitialized: boolean;
  llmConfigured: boolean;
  accessibilityRunning: boolean;
  screenshotSupported?: boolean;
  version?: string;
}
```

### 后续建议新增接口

后续 APKClaw 可新增：

```text
GET /api/device/status
```

建议返回：

```json
{
  "success": true,
  "data": {
    "app": "APKClaw",
    "version": "0.1.0",
    "serverPort": 9527,
    "accessibilityRunning": true,
    "screenshotSupported": true,
    "overlayPermission": false,
    "taskRunning": false,
    "screen": {
      "width": 1080,
      "height": 2400,
      "orientation": "portrait"
    }
  }
}
```

MVP 不依赖这个新接口。

## 5. 截图接口

```text
GET /api/tool/screenshot
```

Header：

```text
X-AGENT-PHONE-TOKEN: <token>
```

当前返回：

```json
{
  "success": true,
  "data": "<base64 png>",
  "error": null
}
```

Lumi 端规范化为：

```ts
interface PhoneScreenshot {
  mime: "image/png";
  base64: string;
  dataUrl: string;
  capturedAt: string;
  width?: number;
  height?: number;
}
```

MVP 显示方式：

```text
data:image/png;base64,<base64>
```

后续建议 APKClaw 返回宽高：

```json
{
  "success": true,
  "data": {
    "mime": "image/png",
    "base64": "...",
    "width": 1080,
    "height": 2400,
    "orientation": "portrait"
  }
}
```

MVP 里如果后端没有宽高，Lumi 可从 `<img>` 加载完成后的 `naturalWidth` / `naturalHeight` 读取。

## 6. 点击接口

```text
POST /api/tool/tap
```

Header：

```text
Content-Type: application/json
X-AGENT-PHONE-TOKEN: <token>
```

请求：

```json
{
  "x": 512,
  "y": 1360
}
```

当前返回：

```json
{
  "success": true,
  "data": "...",
  "error": null
}
```

Lumi 端请求模型：

```ts
interface PhoneTapRequest {
  x: number;
  y: number;
  traceId?: string;
  visualize?: boolean;
}
```

MVP 只发送 `x` 和 `y`。`traceId` 和 `visualize` 先保留在 Lumi 内部，等待 APKClaw AI Cursor Overlay 支持。

## 7. 坐标换算

Lumi 截图预览区域坐标转换为手机真实坐标：

```text
phoneX = previewX / renderedImageWidth * naturalImageWidth
phoneY = previewY / renderedImageHeight * naturalImageHeight
```

要求：

- 使用图片真实渲染区域，不使用外层容器尺寸。
- 结果四舍五入为整数。
- 坐标最小值为 `0`。
- 坐标最大值不超过图片宽高。
- 点击后自动刷新截图。

## 8. Agent 自然语言任务

```text
POST /api/agent/execute_task
```

请求：

```json
{
  "prompt": "打开微信",
  "use_template": true,
  "force_agent": false,
  "template_params": {}
}
```

MVP 页面先预留入口，不作为第一步验收必需。

## 9. 安全边界

MVP 必须做到：

- Token 不在 UI 日志中明文输出。
- 连接失败不泄露 Token。
- 默认只连接用户手动输入的局域网地址。
- 不自动扫描局域网。
- 不自动执行敏感动作。

后续必须补：

- 手机端配对确认。
- 敏感操作二次确认。
- 任务暂停和终止。
- 操作 trace。
- 日志脱敏。

## 10. 第一轮验收

第一轮只验收这 5 件事：

- [ ] Lumi 能保存手机地址和 Token。
- [ ] Lumi 点击连接后能调用 `/api/agent/status`。
- [ ] Lumi 能显示在线、无障碍、LLM、任务运行状态。
- [ ] Lumi 能调用 `/api/tool/screenshot` 并显示手机截图。
- [ ] Lumi 点击截图能换算坐标并调用 `/api/tool/tap`。

不在第一轮做：

- WebRTC。
- 多设备并发。
- Workflow template 市场。
- 完整手机 Agent UI。
- USB / ADB 通道。
