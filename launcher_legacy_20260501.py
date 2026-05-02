# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess, os, webbrowser, sys, json, threading, time
from PIL import Image, ImageTk
import io
import base64
import ctypes

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenClaw.Launcher")
except Exception:
    pass

LOGO_BASE64 = """
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="""

PROVIDERS = {
    "Heang AI": {"url": "https://api.heang.top/v1", "models": ["kimi-k2.5", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "OpenAI": {"url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "Claude": {"url": "https://api.anthropic.com/v1", "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]},
    "DeepSeek": {"url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-coder"]},
    "智谱AI": {"url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4", "glm-4-flash"]},
    "Moonshot": {"url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k"]},
    "自定义": {"url": "", "models": []},
}

# Light theme
COLORS = {
    "bg": "#F5F5F7",
    "bg_card": "#FFFFFF",
    "bg_hover": "#EDEDF0",
    "bg_input": "#F0F0F3",
    "bg_terminal": "#1E1E2E",
    "accent": "#7C3AED",
    "accent_hover": "#6D28D9",
    "accent_light": "#EDE9FE",
    "accent_gen": "#8B5CF6",
    "accent_gen_hover": "#7C3AED",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text": "#1F2937",
    "text_muted": "#6B7280",
    "border": "#E5E7EB",
    "border_focus": "#7C3AED",
    "gradient_start": "#7C3AED",
    "gradient_end": "#EC4899",
}


class ModernButton(tk.Canvas):
    def __init__(self, parent, text, desc="", icon="", command=None, primary=False, danger=False, highlight=False, **kwargs):
        bg = COLORS["bg"]
        super().__init__(parent, height=56, bg=bg, highlightthickness=0, **kwargs)
        self.text = text
        self.desc = desc
        self.icon = icon
        self.command = command
        self.primary = primary
        self.danger = danger
        self.highlight = highlight
        self.hovered = False
        self._bg = bg
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._draw)
        self.configure(cursor="hand2")

    def _on_enter(self, e):
        self.hovered = True
        self._draw()

    def _on_leave(self, e):
        self.hovered = False
        self._draw()

    def _on_click(self, e):
        if self.command:
            self.command()

    def _draw(self, e=None):
        self.delete("all")
        w = self.winfo_width()
        h = 56
        if self.primary:
            bg = COLORS["accent_hover"] if self.hovered else COLORS["accent"]
            text_color = "white"
        elif self.highlight:
            bg = COLORS["accent_gen_hover"] if self.hovered else COLORS["accent_gen"]
            text_color = "white"
        elif self.danger:
            bg = "#DC2626" if self.hovered else COLORS["danger"]
            text_color = "white"
        else:
            bg = COLORS["bg_hover"] if self.hovered else COLORS["bg_card"]
            text_color = COLORS["text"]

        radius = 10
        outline = COLORS["border"] if not self.primary and not self.danger and not self.highlight else ""
        self._round_rect(0, 0, w, h, radius, fill=bg, outline=outline)

        x_offset = 20
        if self.primary:
            self.create_polygon(20, 19, 20, 37, 34, 28, fill="white", outline="")
            x_offset = 46
        elif self.icon:
            self.create_text(24, 28, text=self.icon, font=("Segoe UI Emoji", 15), fill=COLORS["accent"] if not self.highlight else "white")
            x_offset = 48

        y_text = 20 if self.desc else 28
        self.create_text(x_offset, y_text, text=self.text, anchor="w", font=("Microsoft YaHei UI", 11, "bold"), fill=text_color)
        if self.desc:
            desc_color = "#DBEAFE" if self.primary else ("#F3E8FF" if self.highlight else COLORS["text_muted"])
            self.create_text(x_offset, 38, text=self.desc, anchor="w", font=("Microsoft YaHei UI", 9), fill=desc_color)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)


class OpenClawLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpenClaw")
        self.root.geometry("1080x720")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        self.root.configure(bg=COLORS["bg"])
        self.base_path = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(self.base_path) == "OpenClaw启动":
            self.base_path = os.path.dirname(self.base_path)
        self.node_path = self._find_node()
        self.process = None
        self.running = False
        self.setup_ui()
        self.center_window()
        self.check_config()

    def _find_node(self):
        candidates = [
            os.path.join(self.base_path, "SystemData", ".core", "node"),
            os.path.join(self.base_path, "node"),
        ]
        for p in candidates:
            if os.path.exists(os.path.join(p, "node.exe")):
                return p
        return candidates[-1]

    def _find_file(self, filename, search_dirs=["", "back", "backup", "SystemData"]):
        for d in search_dirs:
            path = os.path.join(self.base_path, d, filename) if d else os.path.join(self.base_path, filename)
            if os.path.exists(path):
                return path
        return os.path.join(self.base_path, filename)

    def center_window(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self.root.geometry(f"{w}x{h}+{(self.root.winfo_screenwidth()-w)//2}+{(self.root.winfo_screenheight()-h)//2}")

    def _get_resource_path(self, filename):
        if getattr(sys, 'frozen', False):
            return os.path.join(sys._MEIPASS, filename)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

    def setup_ui(self):
        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill="both", expand=True)

        # Left panel
        left_frame = tk.Frame(main, bg=COLORS["bg_card"], width=300)
        left_frame.pack(side="left", fill="y", padx=(20, 0), pady=20)
        left_frame.pack_propagate(False)
        left_inner = tk.Frame(left_frame, bg=COLORS["bg_card"])
        left_inner.pack(fill="both", expand=True, padx=20, pady=20)

        # Logo
        try:
            ico_path = self._get_resource_path("logo_square.ico")
            if os.path.exists(ico_path):
                self.root.iconbitmap(default=ico_path)
                logo_image = Image.open(ico_path)
                logo_image.thumbnail((56, 56), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
            else:
                logo_data = base64.b64decode(LOGO_BASE64)
                logo_image = Image.open(io.BytesIO(logo_data))
                logo_image.thumbnail((56, 56), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                self.root.iconphoto(True, self.logo_photo)
            tk.Label(left_inner, image=self.logo_photo, bg=COLORS["bg_card"]).pack(pady=(0, 8))
        except:
            pass

        tk.Label(left_inner, text="OpenClaw", font=("Microsoft YaHei UI", 20, "bold"), bg=COLORS["bg_card"], fg=COLORS["text"]).pack()
        tk.Label(left_inner, text="个人 AI 助手", font=("Microsoft YaHei UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(pady=(2, 20))

        # Divider
        tk.Frame(left_inner, height=1, bg=COLORS["border"]).pack(fill="x", pady=(0, 16))

        btn_frame = tk.Frame(left_inner, bg=COLORS["bg_card"])
        btn_frame.pack(fill="x")

        self.start_btn = ModernButton(btn_frame, "启动服务", command=self.start_openclaw, primary=True)
        self.start_btn.pack(fill="x", pady=3)
        ModernButton(btn_frame, "AI 生图", "输入提示词生成/编辑图片", "🎨", self.show_image_gen, highlight=True).pack(fill="x", pady=3)
        ModernButton(btn_frame, "AI 视频", "文生视频 & 图生视频", "🎬", self.show_video_gen, highlight=True).pack(fill="x", pady=3)
        ModernButton(btn_frame, "API 配置", "设置 API 密钥", "🔑", self.show_api_config).pack(fill="x", pady=3)
        ModernButton(btn_frame, "飞书机器人", "绑定消息通道", "🤖", self.show_feishu_config).pack(fill="x", pady=3)
        ModernButton(btn_frame, "微信绑定", "扫码登录微信", "💬", self.bind_weixin).pack(fill="x", pady=3)
        ModernButton(btn_frame, "网页界面", "127.0.0.1:18790", "🌐", self.open_web).pack(fill="x", pady=3)
        ModernButton(btn_frame, "检查更新", "更新版本", "⬆", self.check_update).pack(fill="x", pady=3)
        ModernButton(btn_frame, "帮助", "使用说明", "📖", self.open_readme).pack(fill="x", pady=3)

        tk.Frame(btn_frame, bg=COLORS["bg_card"], height=8).pack(fill="x")
        self.stop_btn = ModernButton(btn_frame, "退出", "停止服务并退出", "⏹", self.stop_openclaw, danger=True)
        self.stop_btn.pack(fill="x", pady=3)

        # Status
        status_frame = tk.Frame(left_inner, bg=COLORS["bg_card"])
        status_frame.pack(side="bottom", fill="x", pady=(12, 0))
        self.status_canvas = tk.Canvas(status_frame, width=10, height=10, bg=COLORS["bg_card"], highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(0, 6))
        self.status_dot = self.status_canvas.create_oval(1, 1, 9, 9, fill=COLORS["warning"], outline="")
        self.status_label = tk.Label(status_frame, text="未配置", font=("Microsoft YaHei UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"])
        self.status_label.pack(side="left")

        # Right panel
        self.right_frame = tk.Frame(main, bg=COLORS["bg_terminal"], width=680)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        self.right_frame.pack_propagate(False)
        self._current_right = "terminal"

        # Terminal page
        self.terminal_page = tk.Frame(self.right_frame, bg=COLORS["bg_terminal"])
        term_header = tk.Frame(self.terminal_page, bg="#2D2D3F", height=36)
        term_header.pack(fill="x")
        term_header.pack_propagate(False)

        mac_btns = tk.Frame(term_header, bg="#2D2D3F")
        mac_btns.pack(side="left", padx=12, pady=12)
        for color in ["#FF5F56", "#FFBD2E", "#27C93F"]:
            c = tk.Canvas(mac_btns, width=12, height=12, bg="#2D2D3F", highlightthickness=0)
            c.create_oval(0, 0, 12, 12, fill=color, outline="")
            c.pack(side="left", padx=3)
        tk.Label(term_header, text=" Service Log", font=("Consolas", 10), bg="#2D2D3F", fg="#8888AA").pack(side="left", padx=10)

        self.log_text = tk.Text(self.terminal_page, bg=COLORS["bg_terminal"], fg="#00FF41",
                                font=("Consolas", 11), wrap="none", relief="flat", padx=16, pady=16,
                                insertbackground="#00FF41", selectbackground="#1A4A28")
        self.log_text.pack(fill="both", expand=True)

        def _log_key_filter(event):
            if event.state & 0x4 and event.keysym in ('c', 'a', 'C', 'A'):
                return None
            return "break"
        self.log_text.bind("<Key>", _log_key_filter)

        scrollbar = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        self.terminal_page.pack(fill="both", expand=True)
        self.img_page = None
        self.video_page = None

    def _switch_right(self, target):
        if self._current_right == target:
            target = "terminal"
        if self.terminal_page:
            self.terminal_page.pack_forget()
        if self.img_page:
            self.img_page.pack_forget()
        if self.video_page:
            self.video_page.pack_forget()
        if target == "terminal":
            self.terminal_page.pack(fill="both", expand=True)
        elif target == "image":
            self.img_page.pack(fill="both", expand=True)
        elif target == "video":
            self.video_page.pack(fill="both", expand=True)
        self._current_right = target

    def _interpolate_color(self, c1, c2, t):
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

    def check_config(self):
        auth_file = os.path.join(self.base_path, "data", ".openclaw", "agents", "main", "agent", "auth-profiles.json")
        if os.path.exists(auth_file):
            self.status_canvas.itemconfig(self.status_dot, fill=COLORS["success"])
            self.status_label.config(text="已配置")
        else:
            self.status_label.config(text="未配置")

    def append_log(self, text):
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def start_openclaw(self):
        if self.running:
            messagebox.showinfo("提示", "服务已在运行中")
            return
        try:
            node_exe = os.path.join(self.node_path, "node.exe")
            if not os.path.exists(node_exe):
                return messagebox.showerror("错误", f"找不到 Node.js：\n{node_exe}")
            start_js = self._find_file("start.js", ["back", "backup", ""])
            if not os.path.exists(start_js):
                return messagebox.showerror("错误", f"找不到启动脚本：\n{start_js}")
            env = os.environ.copy()
            env["OPENCLAW_HOME"] = os.path.join(self.base_path, "data")
            env["OPENCLAW_STATE_DIR"] = os.path.join(self.base_path, "data", ".openclaw")
            env["OPENCLAW_CONFIG_PATH"] = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
            self.append_log(f"[OpenClaw] Starting service...\n")
            self.append_log(f"[OpenClaw] Node: {node_exe}\n")
            self.append_log(f"[OpenClaw] Script: {start_js}\n\n")
            self.process = subprocess.Popen(
                [node_exe, start_js], cwd=self.base_path, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            self.append_log(f"[OpenClaw] PID: {self.process.pid}\n")
            self.running = True
            self.start_btn._draw()
            threading.Thread(target=self._read_output, daemon=True).start()
            self.root.after(3000, self.open_web)
        except Exception as e:
            import traceback
            self.append_log(f"[Error] {traceback.format_exc()}\n")
            messagebox.showerror("启动失败", str(e))

    def _read_output(self):
        try:
            while True:
                line = self.process.stdout.readline()
                if not line: break
                self.root.after(0, self.append_log, line)
        except Exception as e:
            self.root.after(0, self.append_log, f"[Error: {e}]\n")
        exit_code = self.process.poll()
        self.root.after(0, self._on_process_ended, exit_code)

    def _on_process_ended(self, exit_code=None):
        self.running = False
        if exit_code is None and self.process:
            exit_code = self.process.poll()
        self.append_log(f"\n[OpenClaw] Process ended (exit: {exit_code})\n")

    def stop_openclaw(self):
        if self.process and self.process.poll() is None:
            try:
                self.append_log("\n[OpenClaw] Stopping...\n")
                subprocess.run(f'taskkill /F /T /PID {self.process.pid}', shell=True, capture_output=True)
                self.process.wait(timeout=5)
                self.running = False
                self.append_log("[OpenClaw] Stopped.\n")
            except Exception as e:
                self.append_log(f"[Error: {e}]\n")
        elif self.process:
            self.append_log("\n[OpenClaw] Cleaning up...\n")
            try:
                subprocess.run('for /f "tokens=5" %a in (\'netstat -aon ^| findstr :18790\') do taskkill /F /PID %a', shell=True, capture_output=True)
            except: pass
            self.running = False
            self.process = None
        else:
            messagebox.showinfo("提示", "服务未启动")

    def show_api_config(self):
        w = tk.Toplevel(self.root)
        w.title("API 密钥配置")
        w.geometry("340x470")
        w.configure(bg=COLORS["bg_card"])
        w.transient(self.root)
        w.grab_set()
        w.update_idletasks()
        w.geometry(f"+{self.root.winfo_x()+(self.root.winfo_width()-340)//2}+{self.root.winfo_y()+(self.root.winfo_height()-470)//2}")

        content = tk.Frame(w, bg=COLORS["bg_card"])
        content.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(content, text="API 密钥配置", font=("Segoe UI", 14, "bold"), bg=COLORS["bg_card"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 12))

        tk.Label(content, text="AI 服务商", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        provider_var = tk.StringVar(value="Heang AI")
        ttk.Combobox(content, textvariable=provider_var, values=list(PROVIDERS.keys()), state="readonly", font=("Segoe UI", 9)).pack(fill="x", pady=(3, 8), ipady=4)

        tk.Label(content, text="API URL", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        url_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
        url_entry.pack(fill="x", pady=(3, 8), ipady=5)

        tk.Label(content, text="API 密钥", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        key_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
        key_entry.pack(fill="x", pady=(3, 8), ipady=5)

        show_var = tk.BooleanVar(value=False)
        def toggle_key(): key_entry.config(show="" if show_var.get() else "●")
        tk.Checkbutton(content, text="显示密钥", variable=show_var, command=toggle_key, bg=COLORS["bg_card"], fg=COLORS["text_muted"], selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        tk.Label(content, text="模型名称（可选）", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        model_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
        model_entry.pack(fill="x", pady=(3, 10), ipady=5)

        def on_provider_change(e=None):
            provider = provider_var.get()
            url_entry.delete(0, tk.END); url_entry.insert(0, PROVIDERS.get(provider, {}).get("url", ""))
            models = PROVIDERS.get(provider, {}).get("models", [])
            model_entry.delete(0, tk.END)
            if models: model_entry.insert(0, models[0])
        provider_var.trace_add("write", lambda *a: on_provider_change())
        # need to get the combobox for binding
        for child in content.winfo_children():
            if isinstance(child, ttk.Combobox):
                child.bind("<<ComboboxSelected>>", on_provider_change)
        on_provider_change()

        def save_config():
            provider = provider_var.get()
            api_key = key_entry.get().strip()
            api_url = url_entry.get().strip()
            model = model_entry.get().strip()
            if not api_key: return messagebox.showerror("错误", "请输入 API 密钥", parent=w)
            profile_key = provider.lower().replace(" ", "_")
            if provider == "自定义": profile_key = "custom"
            auth_config = {"version": 1, "profiles": {profile_key: {"type": "token", "provider": profile_key, "token": api_key}}}
            auth_file = os.path.join(self.base_path, "data", ".openclaw", "agents", "main", "agent", "auth-profiles.json")
            os.makedirs(os.path.dirname(auth_file), exist_ok=True)
            with open(auth_file, "w", encoding="utf-8") as f: json.dump(auth_config, f, indent=2)
            config_file = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
            existing = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f: existing = json.load(f)
                except: pass
            model_id = model or "default"
            model_name = model or provider
            p_cfg = {"api": "openai-completions", "models": [{"id": model_id, "name": model_name, "contextWindow": 128000, "maxTokens": 4096}]}
            if api_url: p_cfg["baseUrl"] = api_url
            existing.setdefault("models", {}).setdefault("providers", {})[profile_key] = p_cfg
            existing.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = f"{profile_key}/{model_id}"
            with open(config_file, "w", encoding="utf-8") as f: json.dump(existing, f, indent=2, ensure_ascii=False)
            self.check_config(); w.destroy()
            messagebox.showinfo("成功", f"API 密钥已保存！\n服务商：{provider}\n模型：{model_name}")

        btn_f = tk.Frame(content, bg=COLORS["bg_card"])
        btn_f.pack(fill="x", pady=(10, 0))
        tk.Button(btn_f, text="✓ 保存", font=("Segoe UI", 10, "bold"), command=save_config, bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", width=10, activebackground=COLORS["accent_hover"]).pack(side="left", padx=(0, 8))
        tk.Button(btn_f, text="取消", font=("Segoe UI", 10), command=w.destroy, bg=COLORS["bg_input"], fg=COLORS["text"], relief="flat", cursor="hand2", width=10).pack(side="left")

    def show_feishu_config(self):
        w = tk.Toplevel(self.root)
        w.title("飞书机器人配置")
        w.geometry("320x350")
        w.configure(bg=COLORS["bg_card"])
        w.transient(self.root); w.grab_set()
        w.update_idletasks()
        w.geometry(f"+{self.root.winfo_x()+(self.root.winfo_width()-320)//2}+{self.root.winfo_y()+(self.root.winfo_height()-350)//2}")

        content = tk.Frame(w, bg=COLORS["bg_card"])
        content.pack(fill="both", expand=True, padx=15, pady=15)
        tk.Label(content, text="飞书机器人配置", font=("Segoe UI", 14, "bold"), bg=COLORS["bg_card"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 10))

        plugin_path = os.path.join(self.base_path, "data", ".openclaw", "extensions", "openclaw-lark")
        plugin_installed = os.path.exists(plugin_path)

        current_appid = None
        config_path = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f: config = json.load(f)
                current_appid = config.get("channels", {}).get("feishu", {}).get("appId")
            except: pass

        if not plugin_installed:
            tk.Label(content, text="⚠️ 飞书插件未安装", font=("Segoe UI", 10), bg=COLORS["bg_card"], fg=COLORS["warning"], justify="left").pack(anchor="w", pady=(0, 6))
            install_frame = tk.Frame(content, bg=COLORS["bg_card"])
            install_frame.pack(anchor="w", pady=(0, 10))
            def install_lark():
                self.append_log("[飞书] 正在安装飞书插件...\n")
                try:
                    # 清理旧配置残留
                    config_path = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
                    if os.path.exists(config_path):
                        try:
                            with open(config_path, "r", encoding="utf-8") as f: cfg = json.load(f)
                            changed = False
                            if "plugins" in cfg:
                                if "entries" in cfg["plugins"] and "openclaw-lark" in cfg["plugins"]["entries"]:
                                    del cfg["plugins"]["entries"]["openclaw-lark"]; changed = True
                                if "allow" in cfg["plugins"] and "openclaw-lark" in cfg["plugins"]["allow"]:
                                    cfg["plugins"]["allow"].remove("openclaw-lark"); changed = True
                            if changed:
                                with open(config_path, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2, ensure_ascii=False)
                                self.append_log("[飞书] 已清理旧配置残留\n")
                        except: pass

                    npx_exe = os.path.join(self.node_path, "npx.cmd") if os.path.exists(os.path.join(self.node_path, "npx.cmd")) else "npx"
                    env = os.environ.copy()
                    env["OPENCLAW_HOME"] = os.path.join(self.base_path, "data")
                    env["OPENCLAW_STATE_DIR"] = os.path.join(self.base_path, "data", ".openclaw")
                    env["OPENCLAW_CONFIG_PATH"] = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
                    # exFAT不支持symlink，pnpm必须用hoisted模式；npm会报warning但不影响功能
                    env["NPM_CONFIG_NODE_LINKER"] = "hoisted"
                    # 确保 .npmrc 也有 node-linker=hoisted（pnpm优先读.npmrc）
                    npmrc_path = os.path.join(self.base_path, ".npmrc")
                    need_hoisted = True
                    if os.path.exists(npmrc_path):
                        try:
                            with open(npmrc_path, "r", encoding="utf-8") as f: content = f.read()
                            if "node-linker" in content: need_hoisted = False
                        except: pass
                    if need_hoisted:
                        with open(npmrc_path, "a", encoding="utf-8") as f: f.write("\nnode-linker=hoisted\n")
                    # 写临时 bat 文件避免路径转义问题
                    node_exe = os.path.join(self.node_path, "node.exe")
                    pnpm_cli = self._find_pnpm_cli()
                    openclaw_mjs = os.path.join(self.base_path, "node_modules", "openclaw", "openclaw.mjs")
                    bat_path = os.path.join(self.base_path, "_install_lark.bat")
                    if os.path.exists(node_exe) and os.path.exists(pnpm_cli):
                        bat_content = f'@echo off\nchcp 65001 >nul\necho [1/2] Updating OpenClaw...\n"{node_exe}" "{pnpm_cli}" add openclaw@latest\necho.\necho [2/2] Installing Lark Plugin...\n"{npx_exe}" -y @larksuite/openclaw-lark install\necho.\necho Fixing symlink issue for exFAT...\nif exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark" (\n  if not exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" (\n    mkdir "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" 2>nul\n    xcopy "%~dp0node_modules\\openclaw" "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" /E /Y /Q >nul\n    echo   Copied openclaw peerDependency.\n  ) else (\n    echo   Already exists, skipping.\n  )\n)\necho.\necho Done!\npause\n'
                    else:
                        bat_content = f'@echo off\nchcp 65001 >nul\necho Installing Lark Plugin...\n"{npx_exe}" -y @larksuite/openclaw-lark install\necho.\necho Fixing symlink issue for exFAT...\nif exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark" (\n  if not exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" (\n    mkdir "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" 2>nul\n    xcopy "%~dp0node_modules\\openclaw" "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" /E /Y /Q >nul\n    echo   Copied openclaw peerDependency.\n  ) else (\n    echo   Already exists, skipping.\n  )\n)\necho.\necho Done!\npause\n'
                    with open(bat_path, "w", encoding="utf-8") as f: f.write(bat_content)
                    subprocess.Popen(["cmd", "/k", bat_path], env=env, cwd=self.base_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
                    messagebox.showinfo("飞书插件安装", "安装命令已执行，请在弹出的终端窗口中查看进度。\n将先更新 OpenClaw 再安装飞书插件。\n安装完成后请重新打开此窗口。", parent=w)
                except Exception as e:
                    self.append_log(f"[飞书] 安装失败: {str(e)}\n")
                    messagebox.showerror("安装失败", str(e), parent=w)
            tk.Button(install_frame, text="📦 安装飞书插件", font=("Segoe UI", 10, "bold"), command=install_lark, bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", padx=16, pady=4, activebackground=COLORS["accent_hover"]).pack(side="left")
        else:
            if current_appid:
                tk.Label(content, text=f"✅ 飞书已配置\nApp ID: {current_appid}", font=("Segoe UI", 10), bg=COLORS["bg_card"], fg=COLORS["success"], justify="left").pack(anchor="w", pady=(0, 10))
            else:
                tk.Label(content, text="❌ 飞书应用未配置", font=("Segoe UI", 10), bg=COLORS["bg_card"], fg=COLORS["danger"], justify="left").pack(anchor="w", pady=(0, 10))

        if plugin_installed:
            tk.Frame(content, height=1, bg=COLORS["border"]).pack(fill="x", pady=(10, 10))
            tk.Label(content, text="配置飞书应用（需要 App ID 和 Secret）", font=("Segoe UI", 10, "bold"), bg=COLORS["bg_card"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 3))
            tk.Label(content, text="1. 打开 open.feishu.cn/app\n2. 创建或选择应用\n3. 复制 App ID 和 Secret", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"], justify="left").pack(anchor="w", pady=(0, 8))
            tk.Button(content, text="🔗 打开飞书开放平台", font=("Segoe UI", 9), command=lambda: webbrowser.open("https://open.feishu.cn/app"), bg=COLORS["bg_input"], fg=COLORS["accent"], relief="flat", cursor="hand2").pack(anchor="w", pady=(0, 10))

            tk.Label(content, text="App ID", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
            appid_entry = tk.Entry(content, font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
            appid_entry.pack(fill="x", pady=(3, 8), ipady=4)
            if current_appid: appid_entry.insert(0, current_appid)

            tk.Label(content, text="App Secret", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
            secret_entry = tk.Entry(content, font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
            secret_entry.pack(fill="x", pady=(3, 10), ipady=4)

            def save_feishu_config():
                aid, sec = appid_entry.get().strip(), secret_entry.get().strip()
                if not aid or not sec: return messagebox.showerror("错误", "请输入 App ID 和 App Secret", parent=w)
                try:
                    config = {}
                    if os.path.exists(config_path):
                        with open(config_path, "r", encoding="utf-8") as f: config = json.load(f)
                    config.setdefault("channels", {})["feishu"] = {"enabled": True, "appId": aid, "appSecret": sec, "domain": "feishu", "connectionMode": "websocket", "requireMention": True, "dmPolicy": "open", "groupPolicy": "open", "streaming": True}
                    config.setdefault("plugins", {})["allow"] = ["openclaw-lark"]
                    config["plugins"].setdefault("entries", {})["openclaw-lark"] = {"enabled": True}
                    with open(config_path, "w", encoding="utf-8") as f: json.dump(config, f, indent=2, ensure_ascii=False)
                    messagebox.showinfo("成功", f"飞书配置已保存！\n\nApp ID: {aid}", parent=w); w.destroy()
                except Exception as e: messagebox.showerror("错误", f"保存失败：\n{e}", parent=w)

            tk.Button(content, text="✓ 保存", font=("Segoe UI", 10, "bold"), command=save_feishu_config, bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", width=10).pack(side="left")
            tk.Button(content, text="取消", font=("Segoe UI", 10), command=w.destroy, bg=COLORS["bg_input"], fg=COLORS["text"], relief="flat", cursor="hand2", width=10).pack(side="left", padx=(8, 0))

    def bind_weixin(self):
        try:
            plugin_path = os.path.join(self.base_path, "data", ".openclaw", "extensions", "openclaw-weixin")
            plugin_installed = os.path.exists(plugin_path) and os.path.exists(os.path.join(plugin_path, "package.json"))
            node_exe = os.path.join(self.node_path, "node.exe")
            if not os.path.exists(node_exe): return messagebox.showerror("错误", f"找不到 Node.js：\n{node_exe}")
            openclaw_mjs = os.path.join(self.base_path, "node_modules", "openclaw", "openclaw.mjs")
            if not os.path.exists(openclaw_mjs): return messagebox.showerror("错误", f"找不到 OpenClaw：\n{openclaw_mjs}")
            env = os.environ.copy()
            env["OPENCLAW_STATE_DIR"] = os.path.join(self.base_path, "data", ".openclaw")
            env["OPENCLAW_CONFIG_PATH"] = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
            if plugin_installed:
                self.append_log("[微信] 启动登录流程...\n")
                subprocess.Popen(["cmd", "/k", node_exe, openclaw_mjs, "channels", "login", "--channel", "openclaw-weixin"], env=env, cwd=self.base_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                result = messagebox.askyesno("微信绑定", "微信插件未安装，是否现在安装？")
                if result:
                    self.append_log("[微信] 正在安装插件...\n")
                    subprocess.Popen(["cmd", "/k", node_exe, openclaw_mjs, "plugins", "install", "@tencent-weixin/openclaw-weixin", "&", node_exe, openclaw_mjs, "config", "set", "plugins.entries.openclaw-weixin.enabled", "true", "&", node_exe, openclaw_mjs, "channels", "login", "--channel", "openclaw-weixin"], env=env, cwd=self.base_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            self.append_log(f"[微信错误] {str(e)}\n")
            messagebox.showerror("微信绑定失败", str(e))

    def _find_pnpm_cli(self):
        p = os.path.join(self.node_path, "node_modules", "pnpm", "bin", "pnpm.cjs")
        return p if os.path.exists(p) else p

    def _get_current_version(self):
        pj = os.path.join(self.base_path, "node_modules", "openclaw", "package.json")
        if os.path.exists(pj):
            try:
                with open(pj, "r", encoding="utf-8") as f: return json.load(f).get("version", "未知")
            except: pass
        return "未知"

    def _get_latest_version(self):
        try:
            node_exe = os.path.join(self.node_path, "node.exe")
            pnpm_cli = self._find_pnpm_cli()
            if not os.path.exists(node_exe): return None, "找不到 Node.js"
            if not os.path.exists(pnpm_cli): return None, "找不到 pnpm"
            result = subprocess.run([node_exe, pnpm_cli, "view", "openclaw", "version"], capture_output=True, text=True, cwd=self.base_path, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            return (result.stdout.strip(), None) if result.returncode == 0 else (None, result.stderr.strip() or "网络错误")
        except subprocess.TimeoutExpired: return None, "请求超时"
        except Exception as e: return None, str(e)

    def check_update(self):
        self.append_log("\n[更新] 正在检查更新...\n")
        current = self._get_current_version()
        latest, error = self._get_latest_version()
        if error:
            self.append_log(f"[更新] 失败: {error}\n")
            messagebox.showerror("检查更新", f"失败：\n{error}"); return
        if current == latest:
            self.append_log("[更新] 已是最新版本\n")
            messagebox.showinfo("检查更新", f"已是最新版本！\n\n当前: {current}"); return
        if messagebox.askyesno("发现新版本", f"当前: {current}\n最新: {latest}\n\n是否更新？"):
            self._do_update(latest)

    def _do_update(self, target):
        self.append_log(f"\n[更新] 更新到 {target}...\n")
        def update_thread():
            try:
                node_exe = os.path.join(self.node_path, "node.exe")
                pnpm_cli = self._find_pnpm_cli()
                if not os.path.exists(node_exe) or not os.path.exists(pnpm_cli):
                    self.root.after(0, messagebox.showerror, "更新失败", "找不到 Node.js 或 pnpm"); return
                process = subprocess.Popen([node_exe, pnpm_cli, "add", "openclaw@latest"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', cwd=self.base_path, creationflags=subprocess.CREATE_NO_WINDOW)
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None: break
                    if line: self.root.after(0, self.append_log, f"  {line}")
                exit_code = process.wait()
                if exit_code == 0:
                    self.root.after(0, self.append_log, f"\n[更新] 完成: {self._get_current_version()}\n")
                    self.root.after(0, messagebox.showinfo, "更新成功", f"新版本: {self._get_current_version()}")
                else:
                    self.root.after(0, messagebox.showwarning, "更新失败", "请检查网络连接后重试。")
            except Exception as e:
                self.root.after(0, messagebox.showerror, "更新失败", str(e))
        threading.Thread(target=update_thread, daemon=True).start()

    def _show_fullscreen_image(self, img_bytes):
        """Show image in fullscreen lightbox"""
        viewer = tk.Toplevel(self.root)
        viewer.title("图片预览")
        viewer.configure(bg="#000000")
        viewer.attributes('-topmost', True)
        # Maximize
        viewer.state('zoomed')

        pil_img = Image.open(io.BytesIO(img_bytes))
        # Fit to screen
        screen_w = viewer.winfo_screenwidth()
        screen_h = viewer.winfo_screenheight()
        pil_img.thumbnail((screen_w - 40, screen_h - 80), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(pil_img)

        # Top bar
        top_bar = tk.Frame(viewer, bg="#1A1A1A", height=40)
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        tk.Label(top_bar, text="图片预览", font=("Segoe UI", 11, "bold"), bg="#1A1A1A", fg="white").pack(side="left", padx=16)

        def save_img():
            from tkinter import filedialog
            filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")], initialfile=f"image-{int(time.time())}.png", parent=viewer)
            if filepath:
                with open(filepath, "wb") as f: f.write(img_bytes)

        tk.Button(top_bar, text="💾 保存", font=("Segoe UI", 9, "bold"), bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", command=save_img).pack(side="right", padx=12, pady=6)
        tk.Button(top_bar, text="✕ 关闭", font=("Segoe UI", 9), bg="#333333", fg="white", relief="flat", cursor="hand2", command=viewer.destroy).pack(side="right", padx=4, pady=6)

        # Image
        img_label = tk.Label(viewer, image=photo, bg="#000000")
        img_label.image = photo
        img_label.pack(expand=True)

        viewer.bind("<Escape>", lambda e: viewer.destroy())
        viewer.bind("<Button-1>", lambda e: viewer.destroy())

    def show_image_gen(self):
        import urllib.request, urllib.error

        if self.img_page:
            self._switch_right("image")
            return

        self.img_page = tk.Frame(self.right_frame, bg=COLORS["bg_card"])

        # Header
        header = tk.Frame(self.img_page, bg=COLORS["accent_light"], height=42)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text=" 🎨 AI 生图", font=("Microsoft YaHei UI", 12, "bold"), bg=COLORS["accent_light"], fg=COLORS["accent"]).pack(side="left", padx=14)
        tk.Button(header, text="← 日志", font=("Segoe UI", 9), bg=COLORS["accent_light"], fg=COLORS["accent"], relief="flat", cursor="hand2", command=lambda: self._switch_right("terminal")).pack(side="right", padx=14)

        # Content
        content = tk.Frame(self.img_page, bg=COLORS["bg_card"])
        content.pack(fill="both", expand=True, padx=18, pady=14)

        # Load config
        img_config_path = os.path.join(self.base_path, "imgapi_config.json")
        saved = {}
        if os.path.exists(img_config_path):
            try:
                with open(img_config_path, "r", encoding="utf-8") as f: saved = json.load(f)
            except: pass

        # URL + Key row
        top_row = tk.Frame(content, bg=COLORS["bg_card"])
        top_row.pack(fill="x", pady=(0, 8))

        url_frame = tk.Frame(top_row, bg=COLORS["bg_card"])
        url_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(url_frame, text="中转站地址", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        url_entry = tk.Entry(url_frame, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
        url_entry.pack(fill="x", pady=(3, 0), ipady=4)
        if saved.get("baseUrl"): url_entry.insert(0, saved["baseUrl"])

        key_frame = tk.Frame(top_row, bg=COLORS["bg_card"])
        key_frame.pack(side="left", fill="x", expand=True)
        tk.Label(key_frame, text="API Key", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        key_entry = tk.Entry(key_frame, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
        key_entry.pack(fill="x", pady=(3, 0), ipady=4)
        if saved.get("apiKey"): key_entry.insert(0, saved["apiKey"])

        # Options row
        opt_row = tk.Frame(content, bg=COLORS["bg_card"])
        opt_row.pack(fill="x", pady=(0, 8))

        tk.Label(opt_row, text="尺寸", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=(0, 4))
        size_var = tk.StringVar(value="1024x1024")
        ttk.Combobox(opt_row, textvariable=size_var, values=["1024x1024", "1024x1536", "1536x1024", "512x512"], state="readonly", font=("Segoe UI", 9), width=12).pack(side="left", padx=(0, 16))

        upload_btn = tk.Button(opt_row, text="📷 上传原图（编辑模式）", font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text_muted"], relief="flat", cursor="hand2", activebackground=COLORS["bg_hover"])
        upload_btn.pack(side="left", padx=(0, 4))
        upload_info = tk.Label(opt_row, text="", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["success"])
        upload_info.pack(side="left", padx=(0, 4))
        upload_clear = tk.Button(opt_row, text="✕", font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["danger"], relief="flat", cursor="hand2", width=3)

        # Prompt
        tk.Label(content, text="提示词", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        prompt_text = tk.Text(content, font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", height=3, wrap="word")
        prompt_text.pack(fill="x", pady=(3, 10), ipady=3)

        # Button row
        btn_row = tk.Frame(content, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", pady=(0, 10))
        gen_btn = tk.Button(btn_row, text="🎨 生成图片", font=("Microsoft YaHei UI", 11, "bold"), bg=COLORS["accent_gen"], fg="white", relief="flat", cursor="hand2", padx=24, pady=6, activebackground=COLORS["accent_gen_hover"], activeforeground="white")
        gen_btn.pack(side="left", padx=(0, 12))
        status_label = tk.Label(btn_row, text="", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["accent"])
        status_label.pack(side="left")

        # Image display area
        img_frame = tk.Frame(content, bg=COLORS["bg_input"], height=10, bd=1, relief="solid")
        img_frame.pack(fill="both", expand=True)
        img_frame.pack_propagate(False)

        img_placeholder = tk.Label(img_frame, text="点击「生成图片」开始\n生成的图片可点击放大查看", font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text_muted"])
        img_placeholder.pack(expand=True)

        # State
        self._img_photo = None
        self._img_data = None
        edit_image_path = [None]

        def pick_image():
            from tkinter import filedialog
            fpath = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择原图")
            if fpath:
                edit_image_path[0] = fpath
                upload_info.config(text=f"✓ {os.path.basename(fpath)}")
                upload_clear.pack(side="left", padx=(0, 4))
                gen_btn.config(text="🎨 编辑图片")

        def clear_image():
            edit_image_path[0] = None
            upload_info.config(text="")
            upload_clear.pack_forget()
            gen_btn.config(text="🎨 生成图片")

        upload_btn.config(command=pick_image)
        upload_clear.config(command=clear_image)

        def save_image_config():
            cfg = {"baseUrl": url_entry.get().strip().rstrip("/"), "apiKey": key_entry.get().strip()}
            with open(img_config_path, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)
            status_label.config(text="✓ 配置已保存", fg=COLORS["success"])
            self.root.after(2000, lambda: status_label.config(text=""))

        def do_generate():
            base_url = url_entry.get().strip().rstrip("/")
            api_key = key_entry.get().strip()
            prompt = prompt_text.get("1.0", "end-1c").strip()
            size = size_var.get()

            if not base_url: messagebox.showerror("错误", "请输入中转站地址"); return
            if not prompt: messagebox.showerror("错误", "请输入提示词"); return

            save_image_config()
            is_edit = edit_image_path[0] is not None
            gen_btn.config(state="disabled", text="⏳ 处理中...")
            status_label.config(text="正在编辑..." if is_edit else "正在生成，请稍候...", fg=COLORS["accent"])

            def gen_thread():
                try:
                    if is_edit:
                        boundary = "----PythonFormBoundary" + hex(int(time.time() * 1000))
                        parts = []
                        for field, val in [("model", "gpt-image-2"), ("prompt", prompt), ("n", "1"), ("size", size)]:
                            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"\r\n\r\n{val}\r\n".encode("utf-8"))
                        with open(edit_image_path[0], "rb") as f: file_data = f.read()
                        try:
                            pil_src = Image.open(io.BytesIO(file_data))
                            buf = io.BytesIO(); pil_src.save(buf, format="PNG"); file_data = buf.getvalue()
                        except: pass
                        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"image.png\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"))
                        parts.append(file_data)
                        parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
                        body = b"".join(parts)
                        url = f"{base_url}/v1/images/edits"
                        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                    else:
                        url = f"{base_url}/v1/images/generations"
                        body = json.dumps({"model": "gpt-image-2", "prompt": prompt, "n": 1, "size": size}).encode("utf-8")
                        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

                    if api_key: req.add_header("Authorization", f"Bearer {api_key}")

                    resp = urllib.request.urlopen(req, timeout=120)
                    data = json.loads(resp.read().decode("utf-8"))

                    if not data.get("data") or len(data["data"]) == 0:
                        self.root.after(0, lambda: status_label.config(text="✗ 未返回图片数据", fg=COLORS["danger"])); return

                    item = data["data"][0]
                    img_bytes = None
                    if item.get("b64_json"): img_bytes = base64.b64decode(item["b64_json"])
                    elif item.get("url"): img_bytes = urllib.request.urlopen(item["url"], timeout=60).read()

                    if not img_bytes:
                        self.root.after(0, lambda: status_label.config(text="✗ 图片数据为空", fg=COLORS["danger"])); return

                    self._img_data = img_bytes

                    def show_result():
                        pil_img = Image.open(io.BytesIO(img_bytes))
                        max_w = img_frame.winfo_width() - 20
                        max_h = img_frame.winfo_height() - 50
                        if max_w < 100: max_w = 400
                        if max_h < 100: max_h = 200
                        pil_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                        self._img_photo = ImageTk.PhotoImage(pil_img)
                        for widget in img_frame.winfo_children(): widget.destroy()

                        img_label = tk.Label(img_frame, image=self._img_photo, bg=COLORS["bg_input"], cursor="hand2")
                        img_label.pack(expand=True, pady=(4, 0))
                        # Click to view fullscreen
                        img_label.bind("<Button-1>", lambda e: self._show_fullscreen_image(img_bytes))

                        bottom_bar = tk.Frame(img_frame, bg=COLORS["bg_card"], height=36)
                        bottom_bar.pack(fill="x", side="bottom", pady=(4, 0))

                        def save_to_file():
                            from tkinter import filedialog
                            filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")], initialfile=f"image-{int(time.time())}.png", parent=self.root)
                            if filepath:
                                with open(filepath, "wb") as f: f.write(self._img_data)
                                status_label.config(text=f"✓ 已保存: {os.path.basename(filepath)}", fg=COLORS["success"])

                        tk.Button(bottom_bar, text="💾 保存图片", font=("Segoe UI", 9, "bold"), bg=COLORS["accent_gen"], fg="white", relief="flat", cursor="hand2", command=save_to_file).pack(side="left", padx=8, pady=4)
                        tk.Label(bottom_bar, text="🔍 点击图片放大查看", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=8)
                        status_label.config(text="✓ 生成成功", fg=COLORS["success"])

                    self.root.after(0, show_result)

                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read().decode("utf-8")
                        self.append_log(f"[AI生图] HTTP {e.code}: {err_body}\n")
                        err_msg = json.loads(err_body).get("error", {}).get("message", str(e))
                    except: err_msg = f"HTTP {e.code}"
                    self.root.after(0, lambda: status_label.config(text=f"✗ {err_msg}", fg=COLORS["danger"]))
                except Exception as e:
                    self.append_log(f"[AI生图] 错误: {str(e)}\n")
                    self.root.after(0, lambda: status_label.config(text=f"✗ {str(e)}", fg=COLORS["danger"]))
                finally:
                    self.root.after(0, lambda: gen_btn.config(state="normal", text="🎨 编辑图片" if is_edit else "🎨 生成图片"))

            threading.Thread(target=gen_thread, daemon=True).start()

        gen_btn.config(command=do_generate)
        self._switch_right("image")

    def show_video_gen(self):
        import urllib.request, urllib.error

        if self.video_page:
            self._switch_right("video")
            return

        self.video_page = tk.Frame(self.right_frame, bg=COLORS["bg_card"])

        # Header
        header = tk.Frame(self.video_page, bg="#EDE9FE", height=42)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=" 🎬 AI 视频", font=("Microsoft YaHei UI", 12, "bold"), bg="#EDE9FE", fg=COLORS["accent"]).pack(side="left", padx=14)
        tk.Button(header, text="← 日志", font=("Segoe UI", 9), bg="#EDE9FE", fg=COLORS["accent"], relief="flat", cursor="hand2", command=lambda: self._switch_right("terminal")).pack(side="right", padx=14)

        # Content
        content = tk.Frame(self.video_page, bg=COLORS["bg_card"])
        content.pack(fill="both", expand=True, padx=18, pady=14)

        # Load config
        vid_config_path = os.path.join(self.base_path, "video_config.json")
        saved = {}
        if os.path.exists(vid_config_path):
            try:
                with open(vid_config_path, "r", encoding="utf-8") as f: saved = json.load(f)
            except: pass

        # DashScope API Key row
        key_frame = tk.Frame(content, bg=COLORS["bg_card"])
        key_frame.pack(fill="x", pady=(0, 8))
        tk.Label(key_frame, text="DashScope API Key", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        dash_key_entry = tk.Entry(key_frame, font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
        dash_key_entry.pack(fill="x", pady=(3, 0), ipady=4)
        if saved.get("dashKey"): dash_key_entry.insert(0, saved["dashKey"])

        show_key_var = tk.BooleanVar(value=False)
        def toggle_dash_key(): dash_key_entry.config(show="" if show_key_var.get() else "●")
        tk.Checkbutton(key_frame, text="显示密钥", variable=show_key_var, command=toggle_dash_key, bg=COLORS["bg_card"], fg=COLORS["text_muted"], selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # Mode tabs: 文生视频 / 图生视频
        mode_frame = tk.Frame(content, bg=COLORS["bg_card"])
        mode_frame.pack(fill="x", pady=(0, 8))

        mode_var = tk.StringVar(value="t2v")
        t2v_btn = tk.Button(mode_frame, text="📝 文生视频", font=("Microsoft YaHei UI", 10, "bold"), bg=COLORS["accent_gen"], fg="white", relief="flat", cursor="hand2", padx=16, pady=3)
        i2v_btn = tk.Button(mode_frame, text="🖼 图生视频", font=("Microsoft YaHei UI", 10, "bold"), bg=COLORS["bg_input"], fg=COLORS["text"], relief="flat", cursor="hand2", padx=16, pady=3)
        t2v_btn.pack(side="left", padx=(0, 8))
        i2v_btn.pack(side="left")

        # Image upload row (only for i2v)
        i2v_row = tk.Frame(content, bg=COLORS["bg_card"])
        upload_btn = tk.Button(i2v_row, text="📷 上传参考图", font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text_muted"], relief="flat", cursor="hand2", activebackground=COLORS["bg_hover"])
        upload_btn.pack(side="left", padx=(0, 4))
        upload_info = tk.Label(i2v_row, text="", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["success"])
        upload_info.pack(side="left", padx=(0, 4))
        upload_clear = tk.Button(i2v_row, text="✕", font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["danger"], relief="flat", cursor="hand2", width=3)
        # i2v_row hidden initially
        i2v_image_path = [None]

        def switch_mode(m):
            mode_var.set(m)
            if m == "t2v":
                t2v_btn.config(bg=COLORS["accent_gen"], fg="white")
                i2v_btn.config(bg=COLORS["bg_input"], fg=COLORS["text"])
                i2v_row.pack_forget()
            else:
                i2v_btn.config(bg=COLORS["accent_gen"], fg="white")
                t2v_btn.config(bg=COLORS["bg_input"], fg=COLORS["text"])
                i2v_row.pack(fill="x", pady=(0, 8))

        t2v_btn.config(command=lambda: switch_mode("t2v"))
        i2v_btn.config(command=lambda: switch_mode("i2v"))

        def pick_image():
            from tkinter import filedialog
            fpath = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择参考图")
            if fpath:
                i2v_image_path[0] = fpath
                upload_info.config(text=f"✓ {os.path.basename(fpath)}")
                upload_clear.pack(side="left", padx=(0, 4))

        def clear_image():
            i2v_image_path[0] = None
            upload_info.config(text="")
            upload_clear.pack_forget()

        upload_btn.config(command=pick_image)
        upload_clear.config(command=clear_image)

        # Options row
        opt_row = tk.Frame(content, bg=COLORS["bg_card"])
        opt_row.pack(fill="x", pady=(0, 8))

        tk.Label(opt_row, text="分辨率", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=(0, 4))
        res_var = tk.StringVar(value="720P")
        ttk.Combobox(opt_row, textvariable=res_var, values=["720P", "1080P"], state="readonly", font=("Segoe UI", 9), width=8).pack(side="left", padx=(0, 16))

        tk.Label(opt_row, text="时长", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=(0, 4))
        dur_var = tk.StringVar(value="5")
        ttk.Combobox(opt_row, textvariable=dur_var, values=["5", "10"], state="readonly", font=("Segoe UI", 9), width=5).pack(side="left", padx=(0, 16))

        tk.Label(opt_row, text="比例", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=(0, 4))
        ratio_var = tk.StringVar(value="16:9")
        ttk.Combobox(opt_row, textvariable=ratio_var, values=["16:9", "9:16", "1:1", "4:3", "3:4"], state="readonly", font=("Segoe UI", 9), width=8).pack(side="left")

        # Prompt
        tk.Label(content, text="提示词", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(anchor="w")
        prompt_text = tk.Text(content, font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", height=3, wrap="word")
        prompt_text.pack(fill="x", pady=(3, 10), ipady=3)

        # Generate button + status
        btn_row = tk.Frame(content, bg=COLORS["bg_card"])
        btn_row.pack(fill="x", pady=(0, 10))
        gen_btn = tk.Button(btn_row, text="🎬 生成视频", font=("Microsoft YaHei UI", 11, "bold"), bg=COLORS["accent_gen"], fg="white", relief="flat", cursor="hand2", padx=24, pady=6, activebackground=COLORS["accent_gen_hover"], activeforeground="white")
        gen_btn.pack(side="left", padx=(0, 12))
        status_label = tk.Label(btn_row, text="", font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["accent"])
        status_label.pack(side="left")

        # Video display area
        vid_frame = tk.Frame(content, bg=COLORS["bg_input"], height=10, bd=1, relief="solid")
        vid_frame.pack(fill="both", expand=True)
        vid_frame.pack_propagate(False)

        vid_placeholder = tk.Label(vid_frame, text="点击「生成视频」开始\n支持文生视频和图生视频", font=("Segoe UI", 10), bg=COLORS["bg_input"], fg=COLORS["text_muted"])
        vid_placeholder.pack(expand=True)

        # State
        self._vid_data = None

        def save_video_config():
            cfg = {"dashKey": dash_key_entry.get().strip()}
            with open(vid_config_path, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2)

        def do_generate():
            dash_key = dash_key_entry.get().strip()
            prompt = prompt_text.get("1.0", "end-1c").strip()
            mode = mode_var.get()
            resolution = res_var.get()
            duration = dur_var.get()
            ratio = ratio_var.get()

            if not dash_key: messagebox.showerror("错误", "请输入 DashScope API Key"); return
            if not prompt: messagebox.showerror("错误", "请输入提示词"); return
            if mode == "i2v" and not i2v_image_path[0]: messagebox.showerror("错误", "图生视频需要上传参考图"); return

            save_video_config()
            gen_btn.config(state="disabled", text="⏳ 提交中...")
            status_label.config(text="正在提交任务...", fg=COLORS["accent"])

            def gen_thread():
                try:
                    # Build request body
                    if mode == "t2v":
                        body = {
                            "model": "happyhorse-1.0-t2v",
                            "input": {"prompt": prompt},
                            "parameters": {"resolution": resolution, "ratio": ratio, "duration": int(duration)}
                        }
                    else:
                        # Read image and convert to base64 data URL or use URL
                        img_path = i2v_image_path[0]
                        with open(img_path, "rb") as f: img_data = f.read()
                        img_b64 = base64.b64encode(img_data).decode("utf-8")
                        # Detect mime type
                        ext = os.path.splitext(img_path)[1].lower()
                        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".bmp": "image/bmp"}
                        mime = mime_map.get(ext, "image/png")
                        data_url = f"data:{mime};base64,{img_b64}"

                        body = {
                            "model": "happyhorse-1.0-i2v",
                            "input": {
                                "prompt": prompt,
                                "media": [{"type": "first_frame", "url": data_url}]
                            },
                            "parameters": {"resolution": resolution, "duration": int(duration)}
                        }

                    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
                    req_data = json.dumps(body).encode("utf-8")
                    req = urllib.request.Request(url, data=req_data, headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {dash_key}",
                        "X-DashScope-Async": "enable"
                    })

                    self.root.after(0, lambda: status_label.config(text="正在提交任务...", fg=COLORS["accent"]))
                    resp = urllib.request.urlopen(req, timeout=60)
                    resp_data = json.loads(resp.read().decode("utf-8"))

                    task_id = resp_data.get("output", {}).get("task_id")
                    if not task_id:
                        err_msg = resp_data.get("message", str(resp_data))
                        self.root.after(0, lambda: status_label.config(text=f"✗ 提交失败: {err_msg}", fg=COLORS["danger"]))
                        return

                    self.root.after(0, lambda: status_label.config(text=f"任务已提交 (ID: {task_id[:8]}...)，轮询中...", fg=COLORS["accent"]))

                    # Poll for result
                    poll_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
                    max_attempts = 120  # up to ~10 minutes
                    for attempt in range(max_attempts):
                        time.sleep(5)
                        poll_req = urllib.request.Request(poll_url, headers={"Authorization": f"Bearer {dash_key}"})
                        poll_resp = urllib.request.urlopen(poll_req, timeout=30)
                        poll_data = json.loads(poll_resp.read().decode("utf-8"))
                        task_status = poll_data.get("output", {}).get("task_status", "")

                        if task_status == "SUCCEEDED":
                            # Get video URL from results
                            results = poll_data.get("output", {}).get("video_url") or poll_data.get("output", {}).get("results", [])
                            video_url = None
                            if isinstance(results, str):
                                video_url = results
                            elif isinstance(results, list) and len(results) > 0:
                                video_url = results[0].get("url")

                            if not video_url:
                                # Try other response structures
                                video_url = poll_data.get("output", {}).get("video_url")
                            if not video_url:
                                self.root.after(0, lambda: status_label.config(text="✗ 未获取到视频地址", fg=COLORS["danger"]))
                                return

                            self.root.after(0, lambda: status_label.config(text="正在下载视频...", fg=COLORS["accent"]))
                            video_bytes = urllib.request.urlopen(video_url, timeout=120).read()
                            self._vid_data = video_bytes

                            def show_result():
                                for widget in vid_frame.winfo_children(): widget.destroy()
                                # Show video info + thumbnail placeholder
                                vid_info = tk.Frame(vid_frame, bg=COLORS["bg_input"])
                                vid_info.pack(expand=True)

                                tk.Label(vid_info, text="🎬", font=("Segoe UI Emoji", 40), bg=COLORS["bg_input"]).pack(pady=(10, 4))
                                tk.Label(vid_info, text="视频生成成功！", font=("Microsoft YaHei UI", 12, "bold"), bg=COLORS["bg_input"], fg=COLORS["success"]).pack()
                                tk.Label(vid_info, text=f"大小: {len(video_bytes)//1024//1024} MB", font=("Segoe UI", 9), bg=COLORS["bg_input"], fg=COLORS["text_muted"]).pack(pady=(2, 6))

                                bottom_bar = tk.Frame(vid_frame, bg=COLORS["bg_card"], height=40)
                                bottom_bar.pack(fill="x", side="bottom", pady=(4, 0))

                                def save_to_file():
                                    from tkinter import filedialog
                                    filepath = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 视频", "*.mp4")], initialfile=f"video-{int(time.time())}.mp4", parent=self.root)
                                    if filepath:
                                        with open(filepath, "wb") as f: f.write(self._vid_data)
                                        status_label.config(text=f"✓ 已保存: {os.path.basename(filepath)}", fg=COLORS["success"])

                                def play_video():
                                    import tempfile
                                    tmp = os.path.join(tempfile.gettempdir(), f"openclaw_video_{int(time.time())}.mp4")
                                    with open(tmp, "wb") as f: f.write(self._vid_data)
                                    os.startfile(tmp)

                                tk.Button(bottom_bar, text="💾 保存视频", font=("Segoe UI", 9, "bold"), bg=COLORS["accent_gen"], fg="white", relief="flat", cursor="hand2", command=save_to_file).pack(side="left", padx=8, pady=4)
                                tk.Button(bottom_bar, text="▶ 播放视频", font=("Segoe UI", 9, "bold"), bg=COLORS["success"], fg="white", relief="flat", cursor="hand2", command=play_video).pack(side="left", padx=4, pady=4)
                                status_label.config(text="✓ 生成成功", fg=COLORS["success"])

                            self.root.after(0, show_result)
                            return

                        elif task_status == "FAILED":
                            err_msg = poll_data.get("output", {}).get("message", "生成失败")
                            self.root.after(0, lambda: status_label.config(text=f"✗ {err_msg}", fg=COLORS["danger"]))
                            return

                        # Still processing
                        elapsed = (attempt + 1) * 5
                        self.root.after(0, lambda s=task_status, t=elapsed: status_label.config(text=f"状态: {s}... ({t}s)", fg=COLORS["accent"]))

                    self.root.after(0, lambda: status_label.config(text="✗ 超时，请稍后重试", fg=COLORS["danger"]))

                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read().decode("utf-8")
                        self.append_log(f"[AI视频] HTTP {e.code}: {err_body}\n")
                        err_msg = json.loads(err_body).get("message", str(e))
                    except: err_msg = f"HTTP {e.code}"
                    self.root.after(0, lambda: status_label.config(text=f"✗ {err_msg}", fg=COLORS["danger"]))
                except Exception as e:
                    self.append_log(f"[AI视频] 错误: {str(e)}\n")
                    self.root.after(0, lambda: status_label.config(text=f"✗ {str(e)}", fg=COLORS["danger"]))
                finally:
                    self.root.after(0, lambda: gen_btn.config(state="normal", text="🎬 生成视频"))

            threading.Thread(target=gen_thread, daemon=True).start()

        gen_btn.config(command=do_generate)
        self._switch_right("video")

    def open_web(self):
        webbrowser.open("http://127.0.0.1:18790")

    def open_readme(self):
        webbrowser.open("https://heang.top/docs.html")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    OpenClawLauncher().run()
