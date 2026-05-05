# OpenClaw Launcher UI 架构文档

> **项目**: OpenClaw Launcher（永浩科技品牌版）
> **类型**: Windows 桌面 GUI 应用（Python + tkinter）
> **运行方式**: U 盘便携包，双击启动
> **当前主题**: 永浩科技 v1（科技蓝 #1A56DB）
> **更新日期**: 2026-05-03

---

## 1. 整体架构

```
launcher.py                          ← 入口文件（7 行，仅导入并运行）
│
└── openclaw_launcher/
    ├── app.py                       ← 主应用壳（460 行，OpenClawLauncher 类）
    │   ├── _build_ui()              ← 构建主窗口：左侧栏 + 右侧面板
    │   ├── _build_sidebar()         ← 侧边栏布局（品牌区/导航/状态）
    │   ├── _build_terminal_page()   ← 默认终端页
    │   ├── switch_page()            ← 页面切换逻辑
    │   ├── _create_lazy_page()      ← 延迟加载功能页
    │   └── process_service          ← 进程管理（启动/停止 Node.js 网关）
    │
    ├── constants.py                 ← 视觉常量集中管理
    │   ├── COLORS = {39 个颜色变量}
    │   ├── FONTS  = {8 个字体变量}
    │   └── BRAND  = {品牌名/副标题/终端标题}
    │
    ├── ui/
    │   ├── components.py            ← 基础组件工厂函数
    │   │   ├── configure_ttk_style()   ttk "clam" 主题初始化
    │   │   ├── label()                ← tk.Label 快捷创建
    │   │   ├── field_label()          ← 小标题 Label
    │   │   ├── entry()                ← tk.Entry 快捷创建
    │   │   ├── text_area()            ← tk.Text 快捷创建
    │   │   └── button()               ← tk.Button（4 种变体）
    │   │
    │   └── nav_button.py            ← 侧边栏导航按钮（Canvas 手绘）
    │       └── class NavButton(Canvas)
    │           ├── 圆角矩形背景（_round_rect 多边形）
    │           ├── 左侧激活标记条
    │           ├── 图标/标题/描述文字
    │           └── 4 种视觉状态: primary / danger / active / default
    │
    ├── pages/                       ← 功能页面（按需懒加载）
    │   ├── license_page.py          ← 授权激活页
    │   ├── image_page.py            ← AI 图片生成/编辑页（410 行）
    │   ├── video_page.py            ← AI 视频生成页
    │   └── storyboard_page.py       ← 广告视频故事板页（最大，535 行）
    │
    └── dialogs/
        ├── api_config.py            ← API 提供商配置弹窗
        └── feishu_config.py         ← 飞书机器人配置弹窗
```

---

## 2. 布局系统

### 2.1 主窗口结构

```
┌─────────────────────────────────────────────────────┐
│  OpenClaw 1120×740（最小 940×620）                    │
│                                                     │
│  ┌─────────────────┬───────────────────────────────┐│
│  │  Sidebar 300px  │  Right Panel (flex)           ││
│  │                 │                               ││
│  │  ┌──────────┐   │  ┌─────────────────────────┐ ││
│  │  │ LOGO +   │   │  │  Header (per page)       │ ││
│  │  │ Brand    │   │  ├─────────────────────────┤ ││
│  │  ├──────────┤   │  │                         │ ││
│  │  │ ▶ 启动   │   │  │  Page Content           │ ││
│  │  ├──────────┤   │  │  (dynamic, lazy loaded)  │ ││
│  │  │ 工作台   │   │  │                         │ ││
│  │  │  • 服务日志│  │  │                         │ ││
│  │  │  • 广告视频│  │  └─────────────────────────┘ ││
│  │  │  • AI 生图 │  │                               ││
│  │  │  • AI 视频 │  │                               ││
│  │  ├──────────┤   │                               ││
│  │  │ 配置     │   │                               ││
│  │  │  • 授权码 │  │                               ││
│  │  │  • API   │  │                               ││
│  │  │  • 飞书   │  │                               ││
│  │  ├──────────┤   │                               ││
│  │  │ 维护     │   │                               ││
│  │  │  • 网页   │  │                               ││
│  │  │  • 更新   │  │                               ││
│  │  ├──────────┤   │                               ││
│  │  │ ■ 停止   │   │                               ││
│  │  │ ● 状态   │   │                               ││
│  │  └──────────┘   │                               ││
│  └─────────────────┴───────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### 2.2 布局技术

- **全部使用 `pack()` 布局**，没有 `grid()` 或 `place()`
- 间距靠硬编码 `padx` / `pady`
- 侧边栏滚动：Canvas + Scrollbar + ▲▼ 按钮（非标准滚轮滚动）
- 页面切换：`pack_forget()` + `pack()` 切换显示

---

## 3. 组件清单

### 3.1 基础组件（components.py）

| 组件 | 底层 | 变体 | 样式来源 |
|---|---|---|---|
| `label()` | `tk.Label` | body/title/section/muted | COLORS + FONTS |
| `entry()` | `tk.Entry` | 明文/密码 | flat relief, COLORS["input"] |
| `text_area()` | `tk.Text` | 自动高度 | flat relief |
| `button()` | `tk.Button` | primary/danger/success/quiet | COLORS 映射 |

### 3.2 自定义组件（nav_button.py）

| 组件 | 实现方式 | 状态 |
|---|---|---|
| `NavButton` | Canvas 手绘圆角矩形 | primary / danger / active / default + hover |

### 3.3 系统组件（各页面内直接使用）

- `ttk.Combobox`（带自定义 "Launcher.TCombobox" 样式）
- `tk.Canvas`（状态点、Logo）
- `tk.Toplevel`（图片全屏查看器）
- `tk.Scrollbar`

---

## 4. 页面结构

### 4.1 终端页（默认，内嵌在主窗口）

```
┌─────────────────────────────────────────┐
│ ● ● ● Service Console    127.0.0.1:18790│  ← macOS 风格窗口点
│                                         │  ← 深色终端区域
│ $ openclaw gateway start                │  ← 等宽字体 Consolas
│ [INFO] Node.js v24.15.0 detected        │
│ [INFO] Starting OpenClaw gateway...      │
│ [INFO] Gateway listening on :18790       │
│ $ _                                     │
└─────────────────────────────────────────┘
```

### 4.2 图片页（image_page.py）

```
┌─────────────────────────────────────────┐
│ AI 生图  生成或编辑图片                   │
├─────────────────────────────────────────┤
│ ┌─ 表单区（浅灰背景卡片）──────────────┐ │
│ │ 中转站地址: [                    ]   │ │
│ │ API Key:    [                    ]   │ │
│ │ 尺寸: [1024x1024▼] [上传原图] 清除   │ │
│ │ 提示词:                              │ │
│ │ ┌────────────────────────────────┐  │ │
│ │ │                                │  │ │
│ │ └────────────────────────────────┘  │ │
│ └─────────────────────────────────────┘ │
│ [生成图片] [一键三图]                   │
├─────────────────────────────────────────┤
│                                         │
│  生成结果会显示在这里                    │
│  点击图片可放大查看                       │
│                                         │
└─────────────────────────────────────────┘
```

### 4.3 视频页 / 故事板页

类似结构，更多表单控件 + 图片上传区域 + 预览区

---

## 5. 当前色板与主题系统

### 5.1 永浩科技 v1 色板（39 色）

| 分类 | 变量 | 色值 | 用途 |
|---|---|---|---|
| **主色** | accent | `#1A56DB` | 按钮/高亮/激活态 |
| | accent_hover | `#1444AD` | 悬停加深 |
| | accent_soft | `#E4E8F0` | 激活态背景 |
| | accent_ink | `#0F327F` | 激活态文字 |
| **背景** | app_bg | `#F3F4F5` | 应用底色 |
| | sidebar_bg | `#F9F9FA` | 侧边栏底色 |
| | surface | `#FFFFFF` | 卡片面 |
| | surface_alt | `#F6F7F8` | 表单区底色 |
| **文字** | text | `#1E2A3A` | 正文 |
| | text_muted | `#64748B` | 次要文字 |
| | text_subtle | `#94A3B8` | 分组标题 |
| **状态** | success | `#059669` | 成功绿 |
| | warning | `#D97706` | 警告黄 |
| | danger | `#DC2626` | 错误红 |
| **终端** | terminal_bg | `#0F172A` | 终端背景 |
| | terminal_text | `#34D399` | 终端文字 |

### 5.2 主题切换机制

```
themes/
├── _base/backup/           ← 原始基准备份
├── merchants/
│   └── yonghao_tech/       ← 永浩科技主题
│       ├── constants.py    ← 该主题完整色板/品牌
│       ├── theme.json      ← 元数据（品牌名/主色/风格/版本）
│       ├── preview.html    ← HTML 预览
│       └── versions/v1/    ← 版本存档
├── registry.json           ← 总注册表
└── theme_switch.py         ← 切换工具
```

切换方式：`python theme_switch.py <商家ID>` 或 `--restore`

---

## 6. 已知设计痛点

### 6.1 布局问题
- [ ] 纯 `pack()` 堆叠，无网格系统，复杂表单排版困难
- [ ] 间距全部硬编码（`padx=24`, `pady=(0, 22)` 等），难以统一调整
- [ ] 侧边栏滚动用 ▲▼ 按钮代替滚轮，体验差
- [ ] 无响应式布局，窗口缩放后部分区域溢出或空白

### 6.2 组件问题
- [ ] 按钮/输入框为系统原生控件，仅能改颜色，无法定制圆角/阴影
- [ ] NavButton 用 Canvas 手动绘制圆角多边形，性能低且不可复用
- [ ] 无 Toast/通知/骨架屏/Loading 状态等现代交互组件
- [ ] 弹窗（Toplevel）样式简陋，无遮罩层

### 6.3 视觉问题
- [ ] 无阴影、无渐变、无圆角（除 NavButton）、无分割线设计
- [ ] 所有页面自行绘制，缺乏统一组件库
- [ ] 无统一的 spacing system（4px/8px 基准网格）
- [ ] 字体只有 Microsoft YaHei UI 和 Consolas，层级不够丰富

### 6.4 交互问题
- [ ] 无页面切换动画
- [ ] 无 hover 反馈动画（仅颜色瞬时切换）
- [ ] 生成/加载中无进度指示（仅文字提示）
- [ ] 错误处理全靠 `messagebox.showerror` 系统弹窗

---

## 7. 技术栈详情

| 层级 | 技术 | 说明 |
|---|---|---|
| GUI 框架 | tkinter + ttk | Python 标准库，Windows 原生渲染 |
| 图像 | Pillow (PIL) | 图片缩放、缩略图、PhotoImage 转换 |
| HTTP | urllib | 标准库，无 requests 依赖 |
| 加密 | cryptography | Ed25519 签名验证 |
| 打包 | PyInstaller | 单文件 .exe，console=False |
| 后端 | Node.js v24.15.0 | 内嵌 Node，运行 openclaw npm 包 |
| 平台 | Windows 10/11 | 使用 ctypes.windll、taskkill、os.startfile |

---

## 8. 可选改进方向

### 方案 A：CustomTkinter（推荐快速改进）
- **优点**：基于 tkinter，API 兼容，零迁移成本，原生圆角/现代组件
- **缺点**：仍受 tkinter 底层限制，动画/阴影支持有限
- **工作量**：1-2 天，替换组件调用即可

### 方案 B：PyQt6 / PySide6
- **优点**：企业级，QSS 类 CSS，完善组件库，信号槽机制
- **缺点**：依赖大（~200MB），学习曲线，需重写全部 UI
- **工作量**：1-2 周

### 方案 C：Flet（Flutter Python）
- **优点**：Material Design 现代 UI，跨平台，声明式
- **缺点**：较新生态，性能一般，需重写全部 UI
- **工作量**：1-2 周

### 方案 D：Web 前端（Tauri / Electron）
- **优点**：完整 Web 生态（React/Vue/Tailwind），最佳视觉表现
- **缺点**：架构大改，Python 后端需转为 API，开发量大
- **工作量**：3-4 周

---

## 9. 主题化流程

为商家出 UI 的标准流程：

```
1. 收集品牌参数（名称/副标题/主色/风格/Logo）
2. 生成 38 色色板（HSL 衍生算法）
3. 更新 constants.py + BRAND dict
4. 如需替换 Logo：提供新 .ico 文件
5. 生成 HTML 预览页
6. 归档到 themes/merchants/<商家ID>/
7. 版本管理：存入 versions/vN/
8. 注册到 registry.json
```

---

## 10. 代码文件索引

| 文件 | 行数 | 核心职责 |
|---|---|---|
| `app.py` | 460 | 主窗口、侧边栏、终端页、页面切换、进程管理 |
| `constants.py` | 96 | 颜色/字体/品牌/提供商/功能常量 |
| `ui/components.py` | 105 | Label/Entry/Button/TextArea 工厂函数 |
| `ui/nav_button.py` | 128 | Canvas 侧边栏导航按钮 |
| `pages/image_page.py` | 410 | AI 图片生成/编辑（含一键三图） |
| `pages/video_page.py` | ~300 | AI 视频生成 |
| `pages/storyboard_page.py` | ~535 | 广告视频故事板 |
| `pages/license_page.py` | ~150 | 授权激活 |
| `dialogs/api_config.py` | ~120 | API 配置弹窗 |
| `dialogs/feishu_config.py` | ~200 | 飞书配置弹窗 |
