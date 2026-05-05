# OpenClaw Launcher 二次开发文档

## 项目概述

OpenClaw Launcher 是一个基于 Python + tkinter 的桌面启动器，用于管理 OpenClaw AI 助手的便携版部署。支持服务启停、AI生图、AI视频、API配置、飞书/微信绑定等功能，打包为单文件 exe 运行。

## 目录结构

```
D:\Axiangmu\U盘启动器\
├── launcher.py              # 程序入口（只负责启动 App）
├── openclaw_launcher/       # 重构后的应用源码
│   ├── app.py               # 主窗口、导航、日志、模块协调
│   ├── constants.py         # 颜色、端口、模型、URL 等常量
│   ├── paths.py             # 便携版/打包版路径发现
│   ├── storage.py           # JSON 读写与合并工具
│   ├── ui/                  # 通用 tkinter UI 组件
│   ├── pages/               # 右侧页面（广告视频工作台、AI 生图、AI 视频等）
│   ├── dialogs/             # 配置弹窗
│   └── services/            # 进程、更新、AI API 调用
├── OpenClaw.spec            # PyInstaller 打包配置
├── logo_square.ico          # 应用图标（打包进 exe）
├── logo.ico                 # 备用图标
├── dist/
│   └── OpenClaw.exe         # 打包输出
└── build/                   # PyInstaller 临时目录
```

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| GUI | tkinter + ttk | Windows 原生，无额外依赖 |
| 图片处理 | Pillow (PIL) | 图片缩放、格式转换 |
| HTTP 请求 | urllib (标准库) | 不引入 requests，保持轻量 |
| 打包 | PyInstaller | 单文件 exe，无 console 窗口 |
| 运行环境 | Windows 10/11 | 依赖 Node.js + OpenClaw 后端 |

## 依赖安装

```bash
pip install pillow pyinstaller
```

## 打包命令

```bash
pyinstaller OpenClaw.spec --noconfirm
```

输出: `dist/OpenClaw.exe`

## 架构设计

### 类结构

```
ModernButton(tk.Canvas)     # 自定义按钮组件
  └── 支持 primary / highlight / danger 三种样式
  └── 支持图标 + 标题 + 副标题
  └── 悬停动效、圆角矩形

OpenClawLauncher            # 主应用协调器（openclaw_launcher/app.py）
  ├── 构建主窗口、左侧导航、右侧容器、日志页
  ├── 懒加载 pages.ImagePage / pages.VideoPage
  ├── 打开 dialogs.ApiConfigDialog / dialogs.FeishuConfigDialog
  ├── 调用 services.OpenClawProcessService 管理网关进程
  └── 调用 services.OpenClawUpdater 检查与执行更新

pages/
  ├── StoryboardPage         # 小广告视频工作台：分镜、三视图、首尾帧、九宫格
  ├── ImagePage              # AI 生图页面和图片预览/保存
  └── VideoPage              # AI 视频页面和视频保存/播放

services/
  ├── image_api.py           # 生图接口请求与返回解析
  ├── video_api.py           # DashScope 异步任务提交、轮询、下载
  ├── process.py             # OpenClaw gateway 启停与日志读取
  └── updater.py             # 版本检查和 pnpm 更新

dialogs/
  ├── api_config.py          # API 密钥配置，合并保存 auth-profiles
  └── feishu_config.py       # 飞书插件安装与通道配置
```

### 界面布局

```
┌──────────────────────────────────────────────┐
│  1080 x 720  窗口                             │
├──────────┬───────────────────────────────────┤
│ 左面板    │  右面板（可切换）                    │
│ 300px    │  填充剩余空间                        │
│          │                                     │
│ [Logo]   │  ┌─ terminal ──────────────────┐   │
│ OpenClaw │  │ Service Log                 │   │
│ 个人AI助手│  │ [日志输出区域]                │   │
│ ──────── │  │                              │   │
│ ▶启动服务 │  └──────────────────────────────┘   │
│ 🎨AI生图  │                                     │
│ 🎬AI视频  │  ┌─ image ────────────────────┐   │
│ 🔑API配置 │  │ 🎨 AI 生图                  │   │
│ 🤖飞书机器人│  │ [中转站] [Key]              │   │
│ 💬微信绑定 │  │ [尺寸] [上传原图]            │   │
│ 🌐网页界面 │  │ [提示词]                    │   │
│ ⬆检查更新 │  │ [生成] [图片展示区]          │   │
│ 📖帮助    │  └──────────────────────────────┘   │
│          │                                     │
│ ⏹退出    │  ┌─ video ────────────────────┐   │
│ ● 已配置  │  │ 🎬 AI 视频                  │   │
│          │  │ [DashScope Key]             │   │
│          │  │ [文生视频|图生视频]           │   │
│          │  │ [分辨率][时长][比例]          │   │
│          │  │ [提示词]                    │   │
│          │  │ [生成] [视频展示区]          │   │
│          │  └──────────────────────────────┘   │
└──────────┴───────────────────────────────────┘
```

### 右面板页面切换机制

```python
self._current_right = "terminal"  # 当前页面
self.img_page = None              # 懒加载：首次点击才创建
self.video_page = None

def _switch_right(self, target):
    # 再次点击同一页面 → 切回 terminal
    if self._current_right == target:
        target = "terminal"
    # pack_forget 所有页面，再 pack 目标页面
    ...
```

**新增页面步骤：**
1. `setup_ui()` 中初始化 `self.xxx_page = None`
2. `_switch_right()` 中添加 `pack_forget` 和 `pack` 分支
3. 创建 `show_xxx()` 方法，首次调用时构建页面
4. 左面板添加按钮调用 `self.show_xxx()`

## 主题配色

所有颜色定义在 `COLORS` 字典中，修改一处即可全局生效：

```python
COLORS = {
    "bg": "#F5F5F7",           # 主背景
    "bg_card": "#FFFFFF",      # 卡片背景
    "bg_hover": "#EDEDF0",     # 悬停背景
    "bg_input": "#F0F0F3",     # 输入框背景
    "bg_terminal": "#1E1E2E",  # 终端背景
    "accent": "#7C3AED",       # 主强调色（紫色）
    "accent_hover": "#6D28D9", # 强调色悬停
    "accent_light": "#EDE9FE", # 强调色浅色
    "accent_gen": "#8B5CF6",   # AI生图/视频按钮色
    "accent_gen_hover": "#7C3AED",
    "success": "#10B981",      # 成功状态
    "warning": "#F59E0B",      # 警告状态
    "danger": "#EF4444",       # 危险/退出
    "text": "#1F2937",         # 主文字
    "text_muted": "#6B7280",   # 次要文字
    "border": "#E5E7EB",       # 边框
}
```

## 配置文件

启动器读写以下配置文件（均在 `base_path` 下）：

| 文件 | 用途 | 格式 |
|------|------|------|
| `data/.openclaw/openclaw.json` | OpenClaw 主配置 | JSON |
| `data/.openclaw/agents/main/agent/auth-profiles.json` | API 认证信息 | JSON |
| `imgapi_config.json` | AI生图中转站配置 | JSON |
| `video_config.json` | AI视频 DashScope 配置 | JSON |
| `data/storyboards/ad_video_project.json` | 小广告视频工作台项目 | JSON |
| `data/storyboards/assets/` | 三视图、首尾帧、候选图、镜头视频素材 | 文件目录 |
| `data/license.json` | 在线激活后保存的本地授权文件 | JSON |
| `data/install_id.txt` | 本机/本 U 盘安装 ID | 文本 |

## 授权机制

启动器内置在线授权门禁。未授权时只能打开授权页、配置页和帮助文档；启动服务、网页界面、AI 生图、AI 视频、广告视频工作台都会被锁定。

授权流程：

1. 用户输入授权码
2. 启动器请求 `http://118.145.98.220/openclaw-license/activate`
3. 授权服务器校验授权码是否存在、是否已被其他安装使用
4. 校验通过后返回 Ed25519 签名的 license
5. 启动器用内置公钥验签，并保存到 `data/license.json`
6. 后续启动优先本地验签，可离线运行

授权服务部署目录：

```
/opt/openclaw-license/
├── server.py
├── license.db
├── private_key.b64
└── venv/
```

systemd 服务名：`openclaw-license.service`

常用管理命令：

```bash
systemctl status openclaw-license.service
/opt/openclaw-license/venv/bin/python /opt/openclaw-license/server.py create-code --licensee "客户名称" --edition pro --expires 2027-05-01 --count 1
/opt/openclaw-license/venv/bin/python /opt/openclaw-license/server.py list-codes
```

## 离线便携包

当前已生成：

```
release/OpenClaw-Portable/
release/OpenClaw-Portable-2026.4.29-node24.15.0.zip
```

便携包内置：

- `OpenClaw.exe` 启动器
- Node.js `v24.15.0`
- OpenClaw `2026.4.29`
- pnpm `10.33.2`
- `start.js` 本地 gateway 启动脚本
- 空 `data/` 用户数据目录

### openclaw.json 关键结构

```json
{
  "models": {
    "providers": {
      "deepseek": {
        "baseUrl": "https://api.deepseek.com/v1",
        "api": "openai-completions",
        "models": [{"id": "deepseek-chat", "name": "deepseek-chat", "contextWindow": 128000, "maxTokens": 4096}]
      }
    }
  },
  "agents": {
    "defaults": {"model": {"primary": "deepseek/deepseek-chat"}}
  },
  "channels": {
    "feishu": {"enabled": true, "appId": "...", "appSecret": "...", "domain": "feishu", "connectionMode": "websocket"}
  },
  "plugins": {
    "allow": ["openclaw-lark"],
    "entries": {"openclaw-lark": {"enabled": true}}
  },
  "gateway": {"port": 18790, "mode": "local", "bind": "loopback", "auth": {"mode": "none"}}
}
```

## AI 生图功能详解

### API 调用流程

```
用户输入提示词 → 构建请求 → 调用中转站 /v1/images/generations → 解析返回 → 显示图片
                         ↓ (编辑模式)
                         调用 /v1/images/edits (multipart/form-data 上传原图)
```

### 支持的返回格式
- `b64_json`：Base64 编码的图片数据
- `url`：图片下载链接

### 关键实现
- **编辑模式**：手动构建 `multipart/form-data` 请求体，图片转 PNG 格式上传
- **全屏查看**：`_show_fullscreen_image()` 创建 Toplevel 窗口，图片缩放至屏幕大小
- **保存**：`filedialog.asksaveasfilename` 选择路径后写入文件

## AI 视频功能详解

### API 调用流程（DashScope 异步）

```
用户输入 → POST 提交任务（X-DashScope-Async: enable）
         → 获取 task_id
         → 每5秒轮询 GET /api/v1/tasks/{task_id}
         → SUCCEEDED → 下载视频 → 显示结果
         → FAILED → 显示错误
         → 超时(10分钟) → 提示重试
```

### 文生视频 (t2v) vs 图生视频 (i2v)

| 参数 | 文生视频 | 图生视频 |
|------|---------|---------|
| 模型 | happyhorse-1.0-t2v | happyhorse-1.0-i2v |
| input | prompt | prompt + media[first_frame] |
| ratio | 支持 | 不支持 |
| 图片 | 不需要 | 上传参考图 (base64 data URL) |

### 关键实现
- **图生视频图片上传**：读取本地图片 → base64 编码 → `data:{mime};base64,{data}` 格式
- **轮询**：后台线程 `time.sleep(5)` + `urllib.request`，通过 `root.after()` 更新 UI
- **播放**：写入临时 MP4 文件 → `os.startfile()` 系统默认播放器打开

## 飞书插件安装

### 安装流程

1. 检测 `data/.openclaw/extensions/openclaw-lark` 是否存在
2. 清理旧配置残留（openclaw.json 中的 plugins 条目）
3. 设置 exFAT 兼容环境变量（`NPM_CONFIG_NODE_LINKER=hoisted`）
4. 写入临时 `_install_lark.bat` 避免路径转义问题
5. `cmd /k` 执行 bat，先更新 OpenClaw 再安装插件
6. 安装后 xcopy openclaw 到插件 node_modules（解决 exFAT 不支持 symlink）

### exFAT 兼容性

exFAT 文件系统不支持符号链接（symlink），这会导致：
- pnpm install 失败（`EISDIR: symlink`）
- npm 部分操作异常

解决方案：
- 环境变量 `NPM_CONFIG_NODE_LINKER=hoisted`
- `.npmrc` 添加 `node-linker=hoisted`
- 插件 peerDependency 用 xcopy 替代 symlink

## 路径查找机制

启动器需要兼容不同的目录结构（便携版、安装版等）：

```python
def _find_node(self):
    # 按优先级查找 Node.js
    candidates = [
        os.path.join(base_path, "SystemData", ".core", "node"),  # 某些安装版
        os.path.join(base_path, "node"),                          # 标准便携版
    ]
    # 返回第一个存在的，或最后一个作为默认值

def _find_file(self, filename, search_dirs=["", "back", "backup", "SystemData"]):
    # 在多个子目录中查找文件（如 start.js）
```

### base_path 检测

```python
# PyInstaller 打包后：exe 所在目录
# 开发模式：launcher.py 所在目录
self.base_path = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

# 特殊处理：如果上一级是 "OpenClaw启动"，则再上一级
if os.path.basename(self.base_path) == "OpenClaw启动":
    self.base_path = os.path.dirname(self.base_path)
```

## 线程模型

```
主线程 (tkinter mainloop)
  ├── UI 事件处理
  ├── root.after() 调度的 UI 更新
  │
  ├── [守护线程] _read_output()
  │     └── 循环读取子进程 stdout → root.after(0, append_log)
  │
  ├── [守护线程] gen_thread() (AI生图)
  │     └── urllib 请求 → root.after(0, show_result)
  │
  ├── [守护线程] gen_thread() (AI视频)
  │     └── 提交任务 + 轮询 → root.after(0, 更新状态)
  │
  └── [守护线程] update_thread() (检查更新)
        └── pnpm view → root.after(0, 显示结果)
```

**重要**：tkinter 不是线程安全的，所有 UI 操作必须通过 `root.after()` 调度到主线程执行。

## PyInstaller 打包配置

```python
# OpenClaw.spec
a = Analysis(
    ['launcher.py'],
    datas=[('logo_square.ico', '.')],  # 图标打包进 exe
    hiddenimports=['PIL._tkinter_finder'],  # Pillow tkinter 支持
)
exe = EXE(
    ...
    name='OpenClaw',
    console=False,    # 不显示终端窗口
    icon='logo_square.ico',
    upx=True,         # UPX 压缩
)
```

## 二次开发指南

### 添加新的左侧按钮

在 `setup_ui()` 的 `btn_frame` 中添加：

```python
ModernButton(btn_frame, "功能名称", "描述文字", "🎯", self.show_xxx, highlight=True).pack(fill="x", pady=3)
```

参数说明：
- `primary=True`：紫色填充，播放图标
- `highlight=True`：浅紫色填充，适合 AI 功能
- `danger=True`：红色填充，用于退出
- 默认：白色背景，紫色边框

### 添加新的右面板页面

1. `setup_ui()` 末尾添加 `self.xxx_page = None`
2. `_switch_right()` 中添加 pack_forget 和 pack 分支
3. 创建方法：

```python
def show_xxx(self):
    if self.xxx_page:
        self._switch_right("xxx")
        return

    self.xxx_page = tk.Frame(self.right_frame, bg=COLORS["bg_card"])

    # Header（参考 show_image_gen 的 header 写法）
    header = tk.Frame(self.xxx_page, bg=COLORS["accent_light"], height=42)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text=" 🎯 功能名称", ...).pack(side="left", padx=14)
    tk.Button(header, text="← 日志", ..., command=lambda: self._switch_right("terminal")).pack(side="right", padx=14)

    # Content
    content = tk.Frame(self.xxx_page, bg=COLORS["bg_card"])
    content.pack(fill="both", expand=True, padx=18, pady=14)

    # ... 构建内容 ...

    self._switch_right("xxx")
```

### 添加新的弹窗配置

参考 `show_api_config()` 或 `show_feishu_config()`：

```python
def show_xxx_config(self):
    w = tk.Toplevel(self.root)
    w.title("配置标题")
    w.geometry("320x350")
    w.configure(bg=COLORS["bg_card"])
    w.transient(self.root)  # 置于主窗口上方
    w.grab_set()            # 模态窗口

    # 居中显示
    w.update_idletasks()
    w.geometry(f"+{self.root.winfo_x()+(self.root.winfo_width()-320)//2}+{self.root.winfo_y()+(self.root.winfo_height()-350)//2}")

    content = tk.Frame(w, bg=COLORS["bg_card"])
    content.pack(fill="both", expand=True, padx=15, pady=15)

    # ... 构建表单 ...

    # 保存/取消按钮
    tk.Button(content, text="✓ 保存", command=save_func, bg=COLORS["accent"], fg="white", ...).pack(side="left")
    tk.Button(content, text="取消", command=w.destroy, ...).pack(side="left")
```

### 添加新的 AI 功能

参考 `show_video_gen()` 的模式：

1. **配置持久化**：独立 JSON 文件保存 API Key 等配置
2. **后台线程**：耗时操作放 `threading.Thread(daemon=True)` 中
3. **UI 更新**：通过 `self.root.after(0, callback)` 调度到主线程
4. **状态反馈**：`status_label` 显示进度，`gen_btn` 禁用防止重复提交
5. **错误处理**：HTTPError 解析错误体，通用 Exception 记录日志

### 修改主题颜色

编辑 `COLORS` 字典即可。所有 UI 组件都引用这个字典。注意：
- 按钮悬停颜色在 `ModernButton._draw()` 中硬编码了少数值（如 `#DC2626`）
- 终端 header 颜色 `#2D2D3F` 硬编码在 `setup_ui()` 中
- 全屏查看器背景 `#000000` / `#1A1A1A` 硬编码在 `_show_fullscreen_image()` 中

### 修改图标

1. 替换 `logo_square.ico`（建议 256x256 或更大）
2. 更新 `LOGO_BASE64` 常量（作为图标文件不存在时的 fallback）：
   ```python
   # 生成新的 base64
   import base64
   with open("logo_square.ico", "rb") as f:
       print(base64.b64encode(f.read()).decode())
   ```

## 常见问题

### Q: 打包后 exe 运行报错找不到模块？
A: 在 `OpenClaw.spec` 的 `hiddenimports` 中添加缺失的模块。

### Q: exe 被占用无法重新打包？
A: 先关闭正在运行的 OpenClaw.exe，或执行 `taskkill /F /IM OpenClaw.exe`。

### Q: 如何调试？
A: 临时将 `OpenClaw.spec` 中 `console=False` 改为 `console=True`，打包后可看到终端输出和错误信息。

### Q: exFAT U盘上插件安装失败？
A: 确保设置了 `NPM_CONFIG_NODE_LINKER=hoisted` 和 `.npmrc` 中的 `node-linker=hoisted`。参考飞书安装流程中的处理。

### Q: 如何添加新的 AI 服务商？
A: 在 `PROVIDERS` 字典中添加条目：
```python
PROVIDERS = {
    "新服务商": {"url": "https://api.xxx.com/v1", "models": ["model-name"]},
}
```
