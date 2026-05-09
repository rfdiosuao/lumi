# APKClaw 与 Lumi 桌面端对接交接文档

> 更新时间：2026-05-10
> 目的：给新的开发窗口或 APKClaw 侧开发任务使用，明确 Lumi 桌面端与 APKClaw 手机端的长期接口方向、当前实测结果、兼容策略和下一步改造清单。

## 1. 结论先说

正式方向建议使用新 header：

```text
X-AGENT-PHONE-TOKEN: <token>
```

旧 header：

```text
X-APKCLAW-TOKEN: <token>
```

只保留为过渡兼容。

原因：

- `X-AGENT-PHONE-TOKEN` 更通用，不把协议名字绑死在 APKClaw 上。
- 未来可能不止 APKClaw，也可能有 iOS 端、模拟器端、USB/ADB 代理端、云手机端，用 `AGENT-PHONE` 更像长期协议。
- Lumi 已经可以同时发送新旧 header，因此 APKClaw 可以大胆改，迁移期不会立刻断掉旧版本。
- APKClaw 新版本应优先接受 `X-AGENT-PHONE-TOKEN`，同时临时接受 `X-APKCLAW-TOKEN`，等稳定后再考虑移除旧 header。

## 2. 当前真实设备实测

测试设备：

```text
APKClaw 地址：http://192.168.1.137:9527
Token：已由用户提供，文档不记录明文
```

实测结果：

- `GET /api/agent/status` 可访问。
- 单独发送 `X-AGENT-PHONE-TOKEN` 时当前运行版本返回 401。
- 发送 `X-APKCLAW-TOKEN` 可成功鉴权。
- 同时发送两个 header 可成功鉴权。
- `GET /api/tool/screenshot` 可成功返回 PNG base64。
- 截图尺寸：`1280 x 2772`。
- `GET /api/tool/get_screen_info` 可成功返回无障碍控件树。

当前状态返回内容解析后大致为：

```json
{
  "taskRunning": false,
  "agentInitialized": false,
  "llmConfigured": true,
  "accessibilityRunning": true
}
```

无障碍控件树已经能返回可点击控件的文本和 bounds，例如：

```text
[TextView] text="设置"
[LinearLayout] [clickable] bounds=[51,453][1229,631]
  [TextView] text="LLM 配置"
  [TextView] text="Kimi-K2.6"
[LinearLayout] [clickable] bounds=[51,1853][1229,2034]
  [TextView] text="API Token"
  [TextView] text="已设置"
```

这说明后续可以走“截图视觉 + 无障碍结构树 + 动作执行”的混合控制路线，不必只靠裸截图盲点。

## 3. Lumi 当前行为

Lumi 当前已经新增手机连接服务：

```text
openclaw_new_launcher/src/services/phoneApi.ts
```

当前请求会同时发送：

```text
X-AGENT-PHONE-TOKEN: <token>
X-APKCLAW-TOKEN: <token>
```

这是为了兼容当前 APKClaw 运行版本。

长期目标不是让两个 header 永久存在，而是：

1. APKClaw 新版本正确支持 `X-AGENT-PHONE-TOKEN`。
2. Lumi 保留旧 header 一段时间用于兼容旧手机端。
3. 等 APKClaw 发布稳定后，再决定是否移除 `X-APKCLAW-TOKEN`。

## 4. 标准 API 契约

### 4.1 鉴权

所有 API 都应接受：

```text
X-AGENT-PHONE-TOKEN: <token>
```

迁移期兼容：

```text
X-APKCLAW-TOKEN: <token>
```

优先级建议：

1. 如果存在 `X-AGENT-PHONE-TOKEN`，优先校验它。
2. 如果不存在，再尝试 `X-APKCLAW-TOKEN`。
3. 如果两个都存在但其中一个正确，迁移期建议允许通过；稳定期可以改为新 header 优先且必须正确。

### 4.2 CORS

APKClaw 如果继续让 Lumi 前端直接访问手机 HTTP server，需要 CORS 允许这两个 header。

建议所有响应带：

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-AGENT-PHONE-TOKEN, X-APKCLAW-TOKEN
```

`OPTIONS` 预检也必须返回同样的 `Access-Control-Allow-Headers`。

否则命令行能通，但 Lumi WebView 里会被浏览器 CORS 拦掉。

### 4.3 统一响应格式

建议 APKClaw 所有 API 统一返回：

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "unauthorized",
    "message": "Invalid or missing token"
  }
}
```

如果暂时不想改太多，`error` 也可以先继续用字符串，但长期建议改成对象，方便 Lumi 展示可读错误。

## 5. MVP 必须稳定的接口

### 5.1 状态

```text
GET /api/agent/status
```

当前可用，但 `data` 是 JSON 字符串。长期建议直接返回对象。

建议目标返回：

```json
{
  "success": true,
  "data": {
    "taskRunning": false,
    "agentInitialized": true,
    "llmConfigured": true,
    "accessibilityRunning": true,
    "screenshotSupported": true,
    "screenInfoSupported": true,
    "overlayPermission": false,
    "version": "0.1.0"
  },
  "error": null
}
```

### 5.2 截图

```text
GET /api/tool/screenshot
```

当前可用，返回 PNG base64 字符串。

建议目标返回：

```json
{
  "success": true,
  "data": {
    "mime": "image/png",
    "base64": "...",
    "width": 1280,
    "height": 2772,
    "orientation": "portrait",
    "capturedAt": "2026-05-10T01:50:00+08:00"
  },
  "error": null
}
```

### 5.3 屏幕结构树

```text
GET /api/tool/get_screen_info
```

当前可用，返回文本化无障碍树。

MVP 可以继续返回文本，但长期建议增加结构化 JSON 接口：

```text
GET /api/tool/screen_tree
```

建议返回：

```json
{
  "success": true,
  "data": {
    "screen": {
      "width": 1280,
      "height": 2772,
      "orientation": "portrait"
    },
    "nodes": [
      {
        "id": "node-1",
        "className": "TextView",
        "text": "LLM 配置",
        "description": null,
        "clickable": false,
        "bounds": {
          "left": 228,
          "top": 512,
          "right": 957,
          "bottom": 572
        }
      }
    ]
  },
  "error": null
}
```

这个接口是后续“AI 精准控制手机”的关键，比只看截图更稳。

### 5.4 点击

```text
POST /api/tool/tap
```

请求：

```json
{
  "x": 512,
  "y": 1360
}
```

长期建议扩展为：

```json
{
  "x": 512,
  "y": 1360,
  "traceId": "lumi-20260510-0001",
  "visualize": true,
  "durationMs": 120
}
```

返回：

```json
{
  "success": true,
  "data": {
    "x": 512,
    "y": 1360,
    "traceId": "lumi-20260510-0001",
    "executedAt": "2026-05-10T01:50:00+08:00"
  },
  "error": null
}
```

### 5.5 滑动

```text
POST /api/tool/swipe
```

建议请求：

```json
{
  "startX": 640,
  "startY": 2200,
  "endX": 640,
  "endY": 800,
  "durationMs": 450,
  "traceId": "lumi-20260510-0002",
  "visualize": true
}
```

### 5.6 输入文本

```text
POST /api/tool/input_text
```

建议请求：

```json
{
  "text": "hello",
  "traceId": "lumi-20260510-0003"
}
```

### 5.7 系统按键

```text
POST /api/tool/system_key
```

建议请求：

```json
{
  "key": "BACK",
  "traceId": "lumi-20260510-0004"
}
```

建议支持 key：

```text
BACK
HOME
RECENTS
ENTER
POWER
VOLUME_UP
VOLUME_DOWN
```

## 6. AI Cursor Overlay 协议

用户希望手机端有一个“AI 鼠标/指针”，让 OpenClaw 截屏时能看到 AI 的运动轨迹。

这个方向建议做，而且非常适合 APKClaw。

### 6.1 权限

APKClaw 需要悬浮窗权限：

```text
SYSTEM_ALERT_WINDOW
```

状态接口需要返回：

```json
{
  "overlayPermission": true,
  "cursorOverlayEnabled": true
}
```

### 6.2 开关接口

```text
POST /api/overlay/cursor
```

请求：

```json
{
  "enabled": true,
  "style": "lumi",
  "showTrail": true,
  "showTapRipple": true
}
```

### 6.3 移动指针

```text
POST /api/overlay/cursor/move
```

请求：

```json
{
  "x": 512,
  "y": 1360,
  "durationMs": 300,
  "traceId": "lumi-20260510-0005"
}
```

### 6.4 点击可视化

`tap` 请求里的 `visualize: true` 可以触发：

- 指针移动到目标位置。
- 点击前停顿 100-200ms。
- 目标点显示 ripple。
- 点击后保留短暂轨迹。

这样 OpenClaw 后续再次截图时，能看见“AI 刚刚点了哪里”，有助于多模态自校正。

## 7. Lumi 侧下一步

Lumi 已经做完：

- 手机控制入口。
- 地址和 token 保存。
- 状态测试。
- 截图显示。
- 点击截图坐标换算到手机真实坐标。
- tap 调用。
- 新旧 token header 兼容。

Lumi 下一步建议：

1. 在手机控制页显示 `get_screen_info` 的关键节点摘要。
2. 给截图叠加可点击节点 bounds，可开关显示。
3. 增加“刷新截图 + 刷新结构树”的组合请求。
4. 增加 `BACK`、`HOME`、`RECENTS` 三个基础系统键按钮。
5. 增加 AI Cursor Overlay 开关，但先只做 UI 和接口调用，不强依赖。
6. 后续再做自然语言任务入口 `execute_task`。

## 8. APKClaw 侧下一步

建议按这个顺序改：

1. 修 `TokenValidator`，正式支持 `X-AGENT-PHONE-TOKEN`。
2. 保留 `X-APKCLAW-TOKEN` 兼容旧调用。
3. 修 CORS `OPTIONS`，允许两个 token header。
4. 给 `/api/agent/status` 增加 `version`、`screenshotSupported`、`screenInfoSupported`、`overlayPermission`。
5. 让 `/api/tool/screenshot` 返回对象，带 `width`、`height`、`mime`。
6. 新增结构化 `/api/tool/screen_tree`，不要只返回文本树。
7. 扩展 `tap/swipe/input_text/system_key`，支持 `traceId` 和 `visualize`。
8. 做 AI Cursor Overlay 的最小版本：显示圆点、移动、点击 ripple。

## 9. 当前代码位置提示

APKClaw 本地源码位置：

```text
D:\Axiangmu\AUSTART\apkclaw\Hermes-Agent-phone-codex-template-parameter-extraction
```

已知关键文件：

```text
app/src/main/java/com/apk/claw/android/server/ConfigServer.kt
app/src/main/java/com/apk/claw/android/server/TokenValidator.kt
app/src/main/java/com/apk/claw/android/server/ToolApiController.kt
app/src/main/java/com/apk/claw/android/server/AgentApiController.kt
app/src/main/java/com/apk/claw/android/server/ConfigServerManager.kt
```

Lumi 关键文件：

```text
D:\Axiangmu\AUSTART\openclaw_new_launcher\src\services\phoneApi.ts
D:\Axiangmu\AUSTART\openclaw_new_launcher\src\components\phone\PhoneControlPage.tsx
D:\Axiangmu\AUSTART\openclaw_new_launcher\src\features\registry.ts
D:\Axiangmu\AUSTART\openclaw_new_launcher\src\features\pages.tsx
```

## 10. 验收标准

第一轮验收：

- Lumi 输入 `http://手机IP:9527` 和 token 后，可以连接成功。
- Lumi 能显示手机状态。
- Lumi 能显示实时截图。
- Lumi 点击截图后，手机能收到 tap。
- APKClaw 日志不泄露 token 明文。
- WebView 中没有 CORS 报错。

第二轮验收：

- Lumi 能拿到结构化 screen tree。
- Lumi 能在截图上叠加可点击区域。
- Lumi 能调用 BACK/HOME/RECENTS。
- APKClaw 能显示 AI Cursor Overlay。
- 点击/滑动动作能显示轨迹和 ripple。

第三轮验收：

- OpenClaw 可以根据截图和 screen tree 生成动作计划。
- APKClaw 执行动作后返回 traceId。
- Lumi 能把 before/after screenshot、动作坐标、结构树摘要串成一次可追踪操作。

## 11. 给新窗口的开工提示

可以直接从这句话开始：

```text
请按 D:\Axiangmu\AUSTART\openclaw_new_launcher\docs\APKCLAW_LUMI_INTEGRATION_HANDOFF.md 的契约改 APKClaw。优先修 TokenValidator 和 CORS，让 X-AGENT-PHONE-TOKEN 成为正式 header，保留 X-APKCLAW-TOKEN 兼容；然后把 screenshot/status/screen_tree 按文档补齐。
```

