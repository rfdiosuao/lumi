# OpenClaw Launcher UI 重写规范文档

> **版本**: v2.0 (Tauri + Web UI 重写)
> **日期**: 2026-05-03
> **目标**: 用 Tauri + 现代 Web 前端重写 OpenClaw Launcher 的 UI 层，保留所有后端 Python 逻辑
> **技术栈**: Tauri 2.0 (Rust 外壳) + React/Vue (前端) + Python 侧边车 (后台进程)
> **平台**: 仅 Windows 10/11

---

## 1. 架构总览

### 1.1 新旧架构对比

```
┌────────────────────────────────────────────────────┐
│  旧架构 (现状)                                       │
│                                                    │
│  ┌──────────────────┐                              │
│  │  PyInstaller EXE │                              │
│  │  ┌──────────────┐│                              │
│  │  │ tkinter UI   ││── 直接调用 ──┐              │
│  │  │ 460行 app.py ││              │              │
│  │  └──────────────┘│              ▼              │
│  └──────────────────┘  ┌──────────────────────┐  │
│                          │ Python 模块直接调用   │  │
│                          │ ├── process.py       │  │
│                          │ ├── image_api.py     │  │
│                          │ ├── video_api.py     │  │
│                          │ └── license_manager  │  │
│                          └──────────────────────┘  │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│  新架构 (Tauri + Web UI)                             │
│                                                    │
│  ┌─────────────────────┐                            │
│  │  Tauri 2.0 EXE      │                            │
│  │  ┌───────────────┐  │                            │
│  │  │ Webview (HTML)│  │  ◀── 现代 React/Vue 前端   │
│  │  │  (UI 层)      │  │                            │
│  │  └───────┬───────┘  │                            │
│  │          │ invoke   │                            │
│  │  ┌───────▼───────┐  │                            │
│  │  │ Rust Commands │  │  ◀── Tauri 命令层           │
│  │  │  (IPC 桥接)   │  │                            │
│  │  └───────┬───────┘  │                            │
│  └──────────┼──────────┘                            │
│             │ subprocess                             │
│             ▼                                       │
│  ┌──────────────────────┐                           │
│  │  Python 侧边车        │  ◀── 保留现有后端逻辑      │
│  │  (独立 .py 文件)      │                           │
│  │                      │                           │
│  │  ├── bridge.py       │  ◀── 新增: HTTP API 网关   │
│  │  ├── process.py      │  ◀── 保留: 进程管理        │
│  │  ├── license_mgr.py  │  ◀── 保留: 授权验证        │
│  │  ├── paths.py        │  ◀── 保留: 路径发现        │
│  │  ├── storage.py      │  ◀── 保留: JSON 读写       │
│  │  ├── image_api.py    │  ◀── 保留: 图片生成        │
│  │  ├── video_api.py    │  ◀── 保留: 视频生成        │
│  │  └── updater.py      │  ◀── 保留: 版本更新        │
│  └──────────────────────┘                           │
└────────────────────────────────────────────────────┘
```

### 1.2 通信模型

```
前端 (Web UI)              Tauri (Rust)              Python 侧边车
   │                          │                          │
   │── invoke("start_svc") ──▶│                          │
   │                          │── subprocess.Popen ──────▶│
   │◀─────────────────────────│◀────── JSON 响应 ────────│
   │                          │                          │
   │── invoke("get_log") ────▶│                          │
   │                          │── 读取 pipe ─────────────▶│
   │◀── stream (emit) ───────│◀────── stdout 流 ────────│
   │                          │                          │
   │── invoke("activate") ───▶│                          │
   │                          │── subprocess ────────────▶│
   │◀─────────────────────────│◀────── 授权结果 ─────────│
```

---

## 2. Python 侧边车规范

### 2.1 整体设计

Python 侧边车是一个独立的 HTTP 服务（Flask/FastAPI），监听 `127.0.0.1:随机端口`，通过 stdio 将端口号输出给 Rust，Rust 再转发给前端。

**启动流程**:
1. Tauri 启动时，用 `subprocess` 启动 `python bridge.py`
2. bridge.py 启动 HTTP 服务，将端口号写入 stdout
3. Rust 读取 stdout 获取端口，存储为全局变量
4. 前端通过 Tauri fetch proxy 或直接 HTTP 请求 Python API

### 2.2 bridge.py（新增）

```python
"""HTTP API bridge - bridges Tauri frontend to Python backend modules."""

import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 导入现有模块
from paths import AppPaths
from services.process import OpenClawProcessService
from services.image_api import ImageApiClient, ImageApiError
from services.video_api import DashScopeVideoClient
from services.updater import OpenClawUpdater
from license_manager import LicenseManager

paths = AppPaths.discover()
process_svc = OpenClawProcessService(paths, lambda x: print(x, flush=True), lambda f, *a: f(*a))
license_mgr = LicenseManager(paths)
updater = OpenClawUpdater(paths)

log_buffer: list[str] = []
log_lock = threading.Lock()

def append_log(text: str):
    with log_lock:
        log_buffer.append(text)
        # Keep last 500 lines
        if len(log_buffer) > 500:
            log_buffer[:] = log_buffer[-500:]

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}
        path = self.path

        # === Process Management ===
        if path == "/api/process/start":
            try:
                process_svc.start(on_exit=lambda code: append_log(f"\n[OpenClaw] Process ended (exit: {code})\n"))
                self._ok({"status": "started", "pid": process_svc.process.pid if process_svc.process else None})
            except Exception as e:
                self._error(500, str(e))

        elif path == "/api/process/stop":
            try:
                msg = process_svc.stop()
                self._ok({"status": "stopped", "message": msg})
            except Exception as e:
                self._error(500, str(e))

        elif path == "/api/process/status":
            self._ok({"running": process_svc.running, "pid": process_svc.process.pid if process_svc.process else None})

        # === Log ===
        elif path == "/api/log/get":
            with log_lock:
                lines = list(log_buffer)
            self._ok({"log": "".join(lines)})

        elif path == "/api/log/clear":
            with log_lock:
                log_buffer.clear()
            self._ok({"status": "cleared"})

        # === License ===
        elif path == "/api/license/current":
            lic = license_mgr.current_license()
            self._ok({"license": lic})

        elif path == "/api/license/activate":
            try:
                result = license_mgr.activate(body.get("code", ""))
                self._ok({"license": result})
            except Exception as e:
                self._error(400, str(e))

        elif path == "/api/license/authorized":
            feature = body.get("feature")
            self._ok({"authorized": license_mgr.is_authorized(feature)})

        # === Image API ===
        elif path == "/api/image/generate":
            try:
                client = ImageApiClient()
                result = client.generate(
                    body["baseUrl"], body["apiKey"], body["prompt"],
                    body.get("size", "1024x1024"),
                    edit_image_path=body.get("editImagePath"),
                )
                import base64
                self._ok({"image": base64.b64encode(result).decode()})
            except ImageApiError as e:
                self._error(500, str(e))

        # === Video API ===
        elif path == "/api/video/generate":
            try:
                client = DashScopeVideoClient()
                result = client.generate(
                    body["apiKey"], body["prompt"],
                    model=body.get("model"),
                    resolution=body.get("resolution", "720P"),
                    duration=body.get("duration", 5),
                    aspect_ratio=body.get("aspectRatio", "16:9"),
                    first_frame_b64=body.get("firstFrameB64"),
                )
                self._ok(result)
            except Exception as e:
                self._error(500, str(e))

        # === Updater ===
        elif path == "/api/update/check":
            current = updater.current_version()
            latest, error = updater.latest_version()
            if error:
                self._error(500, error)
            else:
                self._ok({"current": current, "latest": latest})

        elif path == "/api/update/do":
            # Streaming update (SSE or polling)
            import subprocess
            node_exe = paths.node_exe
            pnpm_cli = paths.pnpm_cli
            proc = subprocess.Popen(
                [node_exe, pnpm_cli, "add", "openclaw@latest"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace",
                cwd=paths.base_path,
            )
            output = []
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        output.append(line)
                        append_log(line)
            exit_code = proc.wait()
            self._ok({"success": exit_code == 0, "current_version": updater.current_version()})

        # === Config ===
        elif path == "/api/config/read":
            from storage import read_json
            file_path = body.get("path", "")
            default = body.get("default", None)
            self._ok({"data": read_json(file_path, default)})

        elif path == "/api/config/write":
            from storage import write_json
            write_json(body["path"], body["data"])
            self._ok({"status": "ok"})

        # === Auth Profiles ===
        elif path == "/api/auth/profiles":
            from storage import read_json, update_json
            if self.headers.get("X-Method") == "PUT":
                update_json(paths.auth_profiles, body)
                self._ok({"status": "ok"})
            else:
                self._ok({"profiles": read_json(paths.auth_profiles, [])})

        # === System ===
        elif path == "/api/system/info":
            self._ok({
                "node_path": paths.node_exe,
                "base_path": paths.base_path,
                "openclaw_version": updater.current_version(),
            })

        else:
            self._error(404, "Not found")

    def _ok(self, data):
        self._send_json(200, data)

    def _error(self, code, message):
        self._send_json(code, {"error": message})

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress default logging

# Find available port
def find_port(start=18791, end=18800):
    import socket
    for port in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            pass
    return 0

if __name__ == "__main__":
    port = find_port()
    print(f"BRIDGE_PORT={port}", flush=True)
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
```

### 2.3 保留的 Python 模块（无需改动）

| 文件 | 改动 | 说明 |
|---|---|---|
| `paths.py` | **无需改动** | 路径发现逻辑完全复用 |
| `storage.py` | **无需改动** | JSON 读写工具完全复用 |
| `services/process.py` | **无需改动** | 进程管理，被 bridge.py 调用 |
| `services/image_api.py` | **无需改动** | 图片 API 客户端，被 bridge.py 调用 |
| `services/video_api.py` | **无需改动** | 视频 API 客户端，被 bridge.py 调用 |
| `services/updater.py` | **无需改动** | 版本更新，被 bridge.py 调用 |
| `license_manager.py` | **无需改动** | 授权验证，被 bridge.py 调用 |
| `constants.py` | **导出 JSON** | 主题色板需导出为 JSON/CSS |
| `ui/` 目录 | **废弃** | tkinter 组件不再需要 |
| `pages/` 目录 | **废弃** | 页面逻辑转为前端 |
| `dialogs/` 目录 | **废弃** | 弹窗转为前端模态 |
| `app.py` | **废弃** | 主窗口转为 Tauri |

---

## 3. Tauri 层规范

### 3.1 tauri.conf.json

```json
{
  "productName": "YonghaoTech Launcher",
  "version": "2.0.0",
  "identifier": "com.yonghaotech.launcher",
  "build": {
    "beforeDevCommand": "npm run dev",
    "devUrl": "http://localhost:5173",
    "frontendDist": "../dist"
  },
  "app": {
    "windows": [{
      "title": "永浩科技 - 智能AI服务平台",
      "width": 1200,
      "height": 800,
      "minWidth": 960,
      "minHeight": 640,
      "resizable": true,
      "center": true
    }],
    "security": {
      "csp": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: http: https:; connect-src 'self' http://127.0.0.1:*"
    }
  },
  "bundle": {
    "active": true,
    "icon": ["icons/icon.ico"],
    "windows": {
      "webviewInstallMode": {
        "type": "embedBootstrapper"
      }
    }
  }
}
```

### 3.2 Rust Commands (src-tauri/src/lib.rs)

```rust
use tauri::Manager;
use std::process::Command;
use std::sync::atomic::{AtomicU16, Ordering};

static BRIDGE_PORT: AtomicU16 = AtomicU16::new(0);

#[tauri::command]
fn get_bridge_port() -> u16 {
    BRIDGE_PORT.load(Ordering::Relaxed)
}

#[tauri::command]
async fn start_bridge(app: tauri::AppHandle) -> Result<String, String> {
    // 启动 Python bridge
    let mut child = Command::new("python")
        .arg("bridge.py")
        .current_dir(app.path().app_data_dir().unwrap())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动 Python 失败: {}", e))?;

    // 读取端口号 (BRIDGE_PORT=xxxx)
    let mut reader = std::io::BufReader::new(child.stdout.take().unwrap());
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|e| e.to_string())?;

    let port: u16 = line
        .trim()
        .strip_prefix("BRIDGE_PORT=")
        .and_then(|s| s.parse().ok())
        .ok_or("无法获取 bridge 端口")?;

    BRIDGE_PORT.store(port, Ordering::Relaxed);

    // 在后台等待进程退出
    std::thread::spawn(move || {
        let _ = child.wait();
    });

    Ok(format!("Bridge started on port {}", port))
}

#[tauri::command]
async fn proxy_request(
    path: String,
    method: String,
    body: Option<String>,
) -> Result<String, String> {
    let port = BRIDGE_PORT.load(Ordering::Relaxed);
    if port == 0 {
        return Err("Bridge not started".into());
    }

    let url = format!("http://127.0.0.1:{}/{}", port, path.trim_start_matches('/'));
    let client = reqwest::Client::new();

    let mut req = client.request(
        match method.as_str() {
            "GET" => reqwest::Method::GET,
            "POST" => reqwest::Method::POST,
            _ => return Err("Unsupported method".into()),
        },
        &url,
    );

    if let Some(b) = body {
        req = req.body(b).header("Content-Type", "application/json");
    }

    let resp = req.send().await.map_err(|e| e.to_string())?;
    let text = resp.text().await.map_err(|e| e.to_string())?;
    Ok(text)
}

#[cfg_attr(mobile, tauri::mobile_init)]
pub fn init() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_bridge_port,
            start_bridge,
            proxy_request,
        ])
        .setup(|app| {
            // 启动 bridge
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let _ = start_bridge(app_handle).await;
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri");
}
```

---

## 4. 前端规范

### 4.1 技术选型

| 选择 | 推荐 | 说明 |
|---|---|---|
| 框架 | React 18 + Vite | 生态成熟，组件库丰富 |
| 语言 | TypeScript | 类型安全 |
| 样式 | Tailwind CSS | 原子化 CSS，方便主题定制 |
| 组件库 | shadcn/ui 或 Ant Design | 企业级组件 |
| 状态 | Zustand | 轻量级状态管理 |
| 路由 | 不需要（单页应用，侧边栏切换） |

### 4.2 目录结构

```
src/
├── main.tsx                    ← 入口
├── App.tsx                     ← 主应用壳（侧边栏 + 内容区）
├── components/
│   ├── sidebar/
│   │   ├── Sidebar.tsx         ← 侧边栏布局
│   │   ├── BrandHeader.tsx     ← 品牌 Logo + 名称
│   │   ├── NavButton.tsx       ← 导航按钮
│   │   └── StatusIndicator.tsx ← 状态指示器
│   ├── terminal/
│   │   ├── Terminal.tsx        ← 终端日志查看器
│   │   └── TerminalHeader.tsx  ← 终端头部（红黄绿点）
│   ├── image/
│   │   ├── ImagePage.tsx       ← 图片生成页
│   │   ├── ImagePreview.tsx    ← 图片预览
│   │   └── TripleCards.tsx     ← 一键三图卡片
│   ├── video/
│   │   ├── VideoPage.tsx       ← 视频生成页
│   │   └── VideoPreview.tsx    ← 视频预览
│   ├── storyboard/
│   │   ├── StoryboardPage.tsx  ← 故事板页
│   │   ├── SceneList.tsx       ← 场景列表
│   │   ├── FrameAssign.tsx     ← 首末帧分配
│   │   └── GridCandidates.tsx  ← 9 宫格候选
│   ├── license/
│   │   └── LicensePage.tsx     ← 授权激活页
│   ├── common/
│   │   ├── FormField.tsx       ← 表单字段
│   │   ├── Button.tsx          ← 按钮（4 变体）
│   │   ├── Input.tsx           ← 输入框
│   │   ├── TextArea.tsx        ← 文本域
│   │   ├── Select.tsx          ← 下拉选择
│   │   ├── Modal.tsx           ← 模态弹窗
│   │   ├── Toast.tsx           ← 通知提示
│   │   └── Loading.tsx         ← 加载指示器
│   └── dialogs/
│       ├── ApiConfigDialog.tsx ← API 配置弹窗
│       └── FeishuConfigDialog.tsx ← 飞书配置弹窗
├── stores/
│   ├── appStore.ts             ← 应用状态（页面切换、服务状态）
│   ├── logStore.ts             ← 日志流状态
│   ├── licenseStore.ts         ← 授权状态
│   └── themeStore.ts           ← 主题色板
├── services/
│   ├── api.ts                  ← HTTP 客户端（fetch bridge API）
│   ├── process.ts              ← 进程管理 API 调用
│   ├── image.ts                ← 图片生成 API 调用
│   ├── video.ts                ← 视频生成 API 调用
│   └── license.ts              ← 授权 API 调用
├── theme/
│   ├── colors.json             ← 从 constants.py 导出的色板
│   └── tailwind.config.ts      ← Tailwind 主题配置
└── types/
    └── index.ts                ← TypeScript 类型定义
```

### 4.3 主题色板映射（从 constants.py 导出）

```json
{
  "yonghao_tech": {
    "app_bg": "#F3F4F5",
    "sidebar_bg": "#F9F9FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F6F7F8",
    "accent": "#1A56DB",
    "accent_hover": "#1444AD",
    "accent_soft": "#E4E8F0",
    "accent_ink": "#0F327F",
    "text": "#1E2A3A",
    "text_muted": "#64748B",
    "text_subtle": "#94A3B8",
    "success": "#059669",
    "warning": "#D97706",
    "danger": "#DC2626",
    "terminal_bg": "#0F172A",
    "terminal_header": "#1E293B",
    "terminal_text": "#34D399"
  }
}
```

对应的 Tailwind 配置：

```ts
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: {
        accent: { DEFAULT: "#1A56DB", hover: "#1444AD", soft: "#E4E8F0", ink: "#0F327F" },
        surface: { DEFAULT: "#FFFFFF", alt: "#F6F7F8", deep: "#1C202A", deeper: "#14171E" },
        text: { DEFAULT: "#1E2A3A", muted: "#64748B", subtle: "#94A3B8" },
        status: { success: "#059669", warning: "#D97706", danger: "#DC2626" },
        terminal: { bg: "#0F172A", header: "#1E293B", text: "#34D399" },
      },
      fontFamily: {
        sans: ["Microsoft YaHei UI", "system-ui", "sans-serif"],
        mono: ["Consolas", "monospace"],
      },
    },
  },
};
```

---

## 5. 页面详细规范

### 5.1 主应用壳 (App.tsx)

**对应旧文件**: `app.py` (OpenClawLauncher 类)

**布局**:
- 左侧栏: 固定宽度 280px，可滚动
- 右侧内容区: 弹性填充
- 外层容器: 全屏，圆角，带边框

**状态管理**:
```ts
interface AppState {
  currentPage: string;       // 当前页面 ID
  serviceRunning: boolean;   // 服务是否运行
  serviceStatus: "idle" | "starting" | "running" | "stopping" | "stopped";
  isAuthorized: boolean;     // 是否已授权
  licenseInfo: License | null;
  logLines: string[];        // 日志行
}
```

**受保护页面**:
- `storyboard`, `image`, `video` 需要 `isAuthorized === true`
- 未授权时自动跳转到 `license` 页

### 5.2 侧边栏 (Sidebar.tsx)

**对应旧文件**: `app.py` (_build_sidebar 方法)

**结构**:
```
┌──────────────────────────────┐
│  [YH] 永浩科技               │  ← BrandHeader
│       智能AI服务平台          │
├──────────────────────────────┤
│  ▶ 启动服务                  │  ← NavButton (primary)
│     本地网关 18790            │
├──────────────────────────────┤
│  工作台                       │  ← SectionLabel
│  LOG  服务日志               │  ← NavButton (active)
│  AD   广告视频               │
│  IMG  AI 生图                │
│  VID  AI 视频                │
│                              │
│  配置                         │
│  LIC  授权码                 │
│  KEY  API 配置               │
│  BOT  飞书机器人              │
│  WX   微信绑定               │
│                              │
│  维护                         │
│  WEB  网页界面               │
│  UP   检查更新               │
│  DOC  帮助文档               │
├──────────────────────────────┤
│  ■ 停止服务                  │  ← NavButton (danger)
│     结束当前网关进程          │
├──────────────────────────────┤
│  ● 服务运行中                 │  ← StatusIndicator
└──────────────────────────────┘
```

**交互**:
- 点击 NavButton 切换页面
- 启动服务: 调用 `/api/process/start`
- 停止服务: 调用 `/api/process/stop`
- 受保护页面: 检查授权，未授权跳转授权页

### 5.3 终端页 (Terminal.tsx)

**对应旧文件**: `app.py` (_build_terminal_page 方法)

**结构**:
```
┌────────────────────────────────────────────┐
│ ● ● ● Service Console    127.0.0.1:18790   │
│                                            │
│ $ openclaw gateway start                   │
│ [INFO] Node.js v24.15.0 detected           │
│ [INFO] Starting OpenClaw gateway...         │
│ [INFO] Gateway listening on :18790          │
│                                            │
│                                            │
│                                            │
└────────────────────────────────────────────┘
```

**实现**:
- 使用 `<pre>` 或自定义日志组件
- 定时轮询 `/api/log/get` 获取新日志
- 支持 Ctrl+C / Ctrl+A 复制
- 日志自动滚动到底部
- 日志语法高亮: `[INFO]` 绿色, `[WARN]` 黄色, `[Error]` 红色

### 5.4 图片页 (ImagePage.tsx)

**对应旧文件**: `pages/image_page.py`

**表单字段**:
- 中转站地址 (Input)
- API Key (Input, password 类型，带显示/隐藏切换)
- 尺寸 (Select: 1024x1024, 1024x1536, 1536x1024, 512x512)
- 上传原图 (File Picker, 编辑模式)
- 提示词 (TextArea, 3 行)

**操作按钮**:
- 生成图片 (Primary Button)
- 一键三图 (Success Button)

**预览区**:
- 默认显示占位文字
- 生成中显示 Loading
- 生成成功显示图片 + 保存按钮
- 点击放大查看 (Modal)

**一键三图模式**:
- 横向 3 列卡片: 主图 / 白底图 / 详情图
- 每卡片: 标题 + 图片容器 + 状态 + 保存按钮
- 生成进度: "生成中: 1/3"
- 可单独保存每张

### 5.5 视频页 (VideoPage.tsx)

**对应旧文件**: `pages/video_page.py`

**表单字段**:
- DashScope API Key (Input)
- 模式切换 (Toggle: 文生视频 / 图生视频)
- 提示词 (TextArea)
- 首帧图片 (File Picker, 图生视频模式)
- 分辨率 (Select: 720P, 1080P)
- 时长 (Select: 5s, 10s)
- 比例 (Select: 16:9, 9:16, 1:1, 4:3, 3:4)

**操作**:
- 异步任务提交 + 轮询状态
- 生成中显示进度条
- 完成后显示视频 + 播放/保存按钮

### 5.6 故事板页 (StoryboardPage.tsx)

**对应旧文件**: `pages/storyboard_page.py`

**三栏布局**:
- 左栏: 场景列表（可增删改、拖拽排序）
- 中栏: 可视化工作区（产品三视图上传、首末帧、9 宫格候选）
- 右栏: 场景参数（提示词、运镜方式、卖点描述）

**功能**:
- 产品三视图: 上传正面/侧面/背面参考图
- 首末帧: 为每个场景分配首帧和末帧图片
- 9 宫格候选: 生成 9 张图片候选，选一张作为首/末帧
- 场景管理: 添加/复制/删除场景
- 项目保存/加载: 持久化到 JSON
- 质量检查清单: 每个场景 5 项检查（产品稳定性、Logo 清晰度、卖点清晰度、画面连贯性、裁剪准备度）
- 视频生成: 基于首帧 + 提示词调用 i2v 生成视频

### 5.7 授权页 (LicensePage.tsx)

**对应旧文件**: `pages/license_page.py`

**表单**:
- 授权码输入 (Input, 格式提示: OC-PRO-XXXX-XXXX-XXXX-XXXX)
- 激活按钮 (Primary Button)

**授权状态显示**:
- 授权状态: 已授权 / 未授权
- 授权人名称
- 授权版本
- 到期日期
- 可用功能列表
- 安装 ID 显示

### 5.8 配置弹窗

**ApiConfigDialog.tsx** - 对应 `dialogs/api_config.py`:
- 提供商选择 (Select: Heang AI, OpenAI, Claude, DeepSeek, 智谱AI, Moonshot, 自定义)
- 自动填充 URL 和默认模型
- API Key 输入
- 保存到 auth-profiles.json + openclaw.json

**FeishuConfigDialog.tsx** - 对应 `dialogs/feishu_config.py`:
- 插件安装检测
- appId / appSecret 输入
- WebSocket 模式选择
- 保存到 openclaw.json

---

## 6. API 接口完整清单

所有接口通过 Python bridge 的 HTTP API 暴露：

### 进程管理

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| POST | `/api/process/start` | `{}` | `{"status":"started","pid":1234}` | 启动网关 |
| POST | `/api/process/stop` | `{}` | `{"status":"stopped","message":"..."}` | 停止网关 |
| GET | `/api/process/status` | - | `{"running":true,"pid":1234}` | 查询状态 |

### 日志

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| GET | `/api/log/get` | - | `{"log":"完整日志文本"}` | 获取日志 |
| POST | `/api/log/clear` | `{}` | `{"status":"cleared"}` | 清空日志 |

### 授权

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| GET | `/api/license/current` | - | `{"license":{...}}` | 获取当前授权 |
| POST | `/api/license/activate` | `{"code":"OC-PRO-..."}` | `{"license":{...}}` | 激活授权 |
| POST | `/api/license/authorized` | `{"feature":"image"}` | `{"authorized":true}` | 检查功能权限 |

### 图片生成

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| POST | `/api/image/generate` | `{"baseUrl","apiKey","prompt","size","editImagePath?"}` | `{"image":"base64..."}` | 生成/编辑图片 |

### 视频生成

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| POST | `/api/video/generate` | `{"apiKey","prompt","model?","resolution?","duration?","aspectRatio?","firstFrameB64?"}` | `{...}` | 文生/图生视频 |

### 更新

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| GET | `/api/update/check` | - | `{"current":"1.0","latest":"1.1"}` | 检查更新 |
| POST | `/api/update/do` | `{}` | `{"success":true,"current_version":"1.1"}` | 执行更新 |

### 配置

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| POST | `/api/config/read` | `{"path","default"}` | `{"data":{...}}` | 读取配置 |
| POST | `/api/config/write` | `{"path","data"}` | `{"status":"ok"}` | 写入配置 |
| GET | `/api/auth/profiles` | - | `{"profiles":[...]}` | 获取授权配置 |
| PUT | `/api/auth/profiles` | `{...}` | `{"status":"ok"}` | 更新授权配置 |

### 系统

| 方法 | 路径 | 请求体 | 响应体 | 说明 |
|---|---|---|---|---|
| GET | `/api/system/info` | - | `{"node_path","base_path","openclaw_version"}` | 系统信息 |

---

## 7. TypeScript 类型定义

```ts
// types/index.ts

// === Process ===
interface ProcessStatus {
  running: boolean;
  pid: number | null;
}

// === License ===
interface License {
  licensee: string;
  edition: string;
  expires: string | null;
  features: string[];
  installId: string;
  deviceId?: string;
  signature: string;
}

interface LicenseState {
  license: License | null;
  authorized: boolean;
}

// === Image ===
interface ImageConfig {
  baseUrl: string;
  apiKey: string;
}

interface ImageGenerationResult {
  image: string; // base64
}

interface TripleResult {
  main: string | null;
  whiteBg: string | null;
  detail: string | null;
}

// === Video ===
interface VideoConfig {
  apiKey: string;
}

interface VideoGenerationParams {
  prompt: string;
  model?: string;
  resolution?: "720P" | "1080P";
  duration?: 5 | 10;
  aspectRatio?: "16:9" | "9:16" | "1:1" | "4:3" | "3:4";
  firstFrameB64?: string;
}

// === Storyboard ===
interface Scene {
  id: string;
  name: string;
  prompt: string;
  negativePrompt: string;
  sellingPoint: string;
  cameraMovement: string;
  productViews: { front: string | null; side: string | null; back: string | null };
  firstFrame: string | null;
  lastFrame: string | null;
  candidates: string[];
  selectedCandidate: number | null;
  qualityCheck: {
    productStable: boolean;
    logoClear: boolean;
    sellingPointClear: boolean;
    frameFlowGood: boolean;
    cropReady: boolean;
  };
  videoUrl: string | null;
}

interface StoryboardProject {
  scenes: Scene[];
  productName: string;
  productDescription: string;
}

// === Provider ===
interface Provider {
  name: string;
  url: string;
  models: string[];
}

// === Update ===
interface UpdateInfo {
  current: string;
  latest: string;
  hasUpdate: boolean;
}

// === Theme ===
interface ThemeColors {
  app_bg: string;
  sidebar_bg: string;
  surface: string;
  surface_alt: string;
  accent: string;
  accent_hover: string;
  accent_soft: string;
  accent_ink: string;
  text: string;
  text_muted: string;
  text_subtle: string;
  success: string;
  warning: string;
  danger: string;
  terminal_bg: string;
  terminal_header: string;
  terminal_text: string;
}
```

---

## 8. 构建和打包规范

### 8.1 开发命令

```bash
# 安装依赖
npm install

# 开发模式 (热重载)
npm run tauri dev

# 构建生产版
npm run tauri build
```

### 8.2 PyInstaller → Tauri 打包对比

| 旧方式 | 新方式 |
|---|---|
| PyInstaller 打包 Python | Tauri 打包 Rust + Webview |
| Python 内嵌 tkinter | Webview 内嵌浏览器引擎 |
| 输出: dist/OpenClaw.exe | 输出: src-tauri/target/release/bundle |
| 需要内嵌 Node.js | 仍需要内嵌 Node.js (OpenClaw 依赖) |

### 8.3 便携包结构

```
OpenClaw-Portable/
├── OpenClaw.exe              ← Tauri 打包的 EXE
├── bridge.py                 ← Python 侧边车（打包或独立）
├── node/                     ← Node.js v24.15.0
│   └── node.exe
├── node_modules/
│   └── openclaw/             ← OpenClaw npm 包
├── SystemData/
│   └── .core/
│       └── node/             ← 或在这里
├── data/                     ← 运行时数据
│   └── .openclaw/
│       ├── openclaw.json
│       └── agents/
├── logo.ico
└── start.js                  ← OpenClaw 启动脚本
```

---

## 9. 验收标准

### 9.1 功能等价（所有现有功能必须保留）

- [ ] 启动/停止 OpenClaw 网关 + 日志流
- [ ] 端口占用清理
- [ ] AI 图片生成（单图 + 一键三图）
- [ ] AI 图片编辑（上传原图）
- [ ] AI 视频生成（文生视频 + 图生视频）
- [ ] 故事板：场景管理、三视图、首末帧、9 宫格、质量检查
- [ ] 授权激活（Ed25519 验证）
- [ ] API 配置（多提供商）
- [ ] 飞书机器人配置
- [ ] 微信绑定流程
- [ ] 版本检查与更新
- [ ] 网页界面跳转
- [ ] 帮助文档跳转
- [ ] 窗口居中启动 + 最小尺寸限制

### 9.2 UI 质量

- [ ] 所有颜色使用主题色板变量，无硬编码颜色
- [ ] 响应式布局（窗口缩放无溢出）
- [ ] 加载/生成中状态有 Loading 指示器
- [ ] 错误使用 Toast 通知而非 alert
- [ ] 页面切换流畅
- [ ] 侧边栏支持鼠标滚轮滚动
- [ ] 终端日志支持 Ctrl+C/A 复制
- [ ] 图片支持点击放大预览
- [ ] 视频支持播放

### 9.3 打包

- [ ] 可独立运行（不依赖系统 Python/Node，除非 OpenClaw 需要）
- [ ] 输出体积合理（Tauri EXE < 10MB）
- [ ] 启动速度 < 3 秒

---

## 10. 实施步骤

1. **Step 1**: 创建 Tauri 2.0 项目 + React + TypeScript + Tailwind
2. **Step 2**: 实现 bridge.py（Python HTTP API 网关）
3. **Step 3**: 实现 Rust 层（启动 bridge + proxy 转发）
4. **Step 4**: 搭建主应用壳（侧边栏 + 内容区）
5. **Step 5**: 实现终端页 + 进程管理
6. **Step 6**: 实现授权页 + 授权验证
7. **Step 7**: 实现图片页（生成/编辑/三图）
8. **Step 8**: 实现视频页
9. **Step 9**: 实现故事板页
10. **Step 10**: 实现配置弹窗
11. **Step 11**: 实现更新功能
12. **Step 12**: 测试 + 打包 + 验收

---

## 附录 A: 当前文件引用关系图

```
launcher.py
    └── openclaw_launcher/app.py
            ├── constants.py          (COLORS, FONTS, BRAND, APP_NAME, APP_PORT, HELP_URL, LICENSE_SERVER_URL, PROVIDERS)
            ├── paths.py              (AppPaths.discover)
            ├── license_manager.py    (LicenseManager)
            ├── storage.py            (read_json, write_json)
            ├── ui/components.py      (button, label, entry, text_area, configure_ttk_style)
            ├── ui/nav_button.py      (NavButton)
            ├── pages/license_page.py (LicensePage)
            ├── pages/image_page.py   (ImagePage)
            ├── pages/video_page.py   (VideoPage)
            ├── pages/storyboard_page.py (StoryboardPage)
            ├── dialogs/api_config.py (ApiConfigDialog)
            ├── dialogs/feishu_config.py (FeishuConfigDialog)
            └── services/
                ├── process.py        (OpenClawProcessService)
                ├── updater.py        (OpenClawUpdater)
                ├── image_api.py      (ImageApiClient)
                └── video_api.py      (DashScopeVideoClient)
```

## 附录 B: 关键安全常量

```python
# license_manager.py 中的 Ed25519 公钥 - 不可修改
LICENSE_PUBLIC_KEY_B64 = "njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4="

# 授权服务器地址 - 不可修改
LICENSE_SERVER_URL = "https://license.heang.top"
```

## 附录 C: 已知边界条件

1. **打包模式**: PyInstaller 的 `sys._MEIPASS` 在 Tauri 中不再适用，资源路径需改为相对于 EXE 或 data 目录
2. **编码**: 所有中文文本使用 UTF-8
3. **端口**: OpenClaw 网关固定端口 18790，Bridge 端口 18791-18800 动态分配
4. **Node.js**: 内嵌 v24.15.0，路径为 `SystemData/.core/node/node.exe` 或 `node/node.exe`
5. **Windows 专属**: 使用 `ctypes.windll`、`taskkill`、`netstat`、`CREATE_NO_WINDOW`
6. **授权文件**: `data/license.json` 和 `data/install_id.txt`
7. **项目配置文件**: `data/.openclaw/openclaw.json`、`auth-profiles.json`
