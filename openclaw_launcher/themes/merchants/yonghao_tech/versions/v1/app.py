"""Main tkinter application shell."""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox

from PIL import Image, ImageTk

from openclaw_launcher.constants import APP_NAME, APP_PORT, BRAND, COLORS, FONTS, HELP_URL
from openclaw_launcher.dialogs.api_config import ApiConfigDialog
from openclaw_launcher.dialogs.feishu_config import FeishuConfigDialog
from openclaw_launcher.license_manager import LicenseManager
from openclaw_launcher.pages.image_page import ImagePage
from openclaw_launcher.pages.license_page import LicensePage
from openclaw_launcher.pages.storyboard_page import StoryboardPage
from openclaw_launcher.pages.video_page import VideoPage
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.services.process import OpenClawProcessService
from openclaw_launcher.services.updater import OpenClawUpdater
from openclaw_launcher.ui.components import button, configure_ttk_style, label
from openclaw_launcher.ui.nav_button import NavButton


class OpenClawLauncher:
    def __init__(self):
        self._set_windows_app_id()
        self.paths = AppPaths.discover()
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1120x740")
        self.root.minsize(940, 620)
        self.root.configure(bg=COLORS["app_bg"])
        configure_ttk_style(self.root)

        self.nav_buttons: dict[str, NavButton] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.page_objects: dict[str, object] = {}
        self.current_page = "terminal"
        self.protected_pages = {"storyboard": "storyboard", "image": "image", "video": "video"}
        self.license_manager = LicenseManager(self.paths)

        self._build_ui()
        self.process_service = OpenClawProcessService(self.paths, self.append_log, self._ui_call)
        self.updater = OpenClawUpdater(self.paths)
        self.center_window()
        self.check_config()
        if not self.license_manager.is_authorized():
            self.switch_page("license")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _set_windows_app_id(self) -> None:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(BRAND["app_user_model_id"])
        except Exception:
            pass

    def _build_ui(self) -> None:
        self._load_icon()
        shell = tk.Frame(self.root, bg=COLORS["app_bg"])
        shell.pack(fill="both", expand=True, padx=20, pady=20)

        self.sidebar = tk.Frame(shell, bg=COLORS["sidebar_bg"], width=300, highlightbackground=COLORS["border"], highlightthickness=1)
        self.sidebar.pack(side="left", fill="y", padx=(0, 18))
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        self.right_frame = tk.Frame(shell, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        self.right_frame.pack(side="right", fill="both", expand=True)
        self._build_terminal_page()
        self.switch_page("terminal")

    def _draw_brand_logo(self, canvas):
        """Draw a code-based brand logo: rounded-square with 'YH' initials."""
        accent = COLORS["accent"]
        accent_soft = COLORS["accent_soft"]
        w, h = 48, 48
        canvas.configure(width=w, height=h)
        # Background rounded rect
        canvas.create_rounded_rect = lambda x1, y1, x2, y2, r, **kw: canvas.create_polygon(
            [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
             x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1],
            smooth=True, **kw
        )
        canvas.create_rounded_rect(2, 2, w-2, h-2, 10, fill=accent, outline="")
        # YH text in center
        canvas.create_text(w//2, h//2, text="YH", font=("Microsoft YaHei UI", 16, "bold"), fill="white")

    def _load_icon(self) -> None:
        try:
            icon_path = self.paths.resource_path("logo.ico")
            if not os.path.exists(icon_path):
                icon_path = self.paths.resource_path("logo_square.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(default=icon_path)
                image = Image.open(icon_path)
                image.thumbnail((54, 54), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(image)
            else:
                self.logo_photo = None
        except Exception:
            self.logo_photo = None

    def _build_sidebar(self) -> None:
        inner = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"])
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        brand = tk.Frame(inner, bg=COLORS["sidebar_bg"])
        brand.pack(fill="x", pady=(0, 12))
        logo_canvas = tk.Canvas(brand, width=48, height=48, bg=COLORS["sidebar_bg"], highlightthickness=0)
        logo_canvas.pack(side="left", padx=(0, 12))
        self._draw_brand_logo(logo_canvas)
        brand_text = tk.Frame(brand, bg=COLORS["sidebar_bg"])
        brand_text.pack(side="left", fill="x", expand=True)
        tk.Label(brand_text, text=BRAND["name"], font=FONTS["display"], bg=COLORS["sidebar_bg"], fg=COLORS["text"]).pack(anchor="w")
        tk.Label(brand_text, text=BRAND["subtitle"], font=FONTS["small"], bg=COLORS["sidebar_bg"], fg=COLORS["text_muted"]).pack(anchor="w", pady=(2, 0))

        self.start_btn = NavButton(inner, "启动服务", f"本地网关 {APP_PORT}", command=self.start_openclaw, primary=True)
        self.start_btn.pack(fill="x", pady=(0, 8))

        nav_area = tk.Frame(inner, bg=COLORS["sidebar_bg"])
        nav_area.pack(fill="both", expand=True)
        nav_body = tk.Frame(nav_area, bg=COLORS["sidebar_bg"])
        nav_canvas = tk.Canvas(nav_body, bg=COLORS["sidebar_bg"], highlightthickness=0, bd=0)
        nav_scroll = tk.Scrollbar(
            nav_body,
            orient="vertical",
            command=nav_canvas.yview,
            width=14,
            troughcolor=COLORS["surface_alt"],
            bg=COLORS["border_strong"],
            activebackground=COLORS["accent"],
        )
        nav_content = tk.Frame(nav_canvas, bg=COLORS["sidebar_bg"])
        nav_window = nav_canvas.create_window((0, 0), window=nav_content, anchor="nw")
        nav_canvas.configure(yscrollcommand=nav_scroll.set)

        scroll_up = tk.Button(
            nav_area,
            text="▲ 上滑",
            command=lambda: nav_canvas.yview_scroll(-5, "units"),
            font=FONTS["small"],
            bg=COLORS["surface_alt"],
            fg=COLORS["accent_ink"],
            activebackground=COLORS["accent_soft"],
            activeforeground=COLORS["accent_ink"],
            relief="flat",
            cursor="hand2",
            pady=2,
        )
        scroll_down = tk.Button(
            nav_area,
            text="▼ 下滑",
            command=lambda: nav_canvas.yview_scroll(5, "units"),
            font=FONTS["small"],
            bg=COLORS["surface_alt"],
            fg=COLORS["accent_ink"],
            activebackground=COLORS["accent_soft"],
            activeforeground=COLORS["accent_ink"],
            relief="flat",
            cursor="hand2",
            pady=2,
        )
        scroll_up.pack(fill="x", pady=(0, 4))
        nav_body.pack(fill="both", expand=True)
        nav_canvas.pack(side="left", fill="both", expand=True)
        nav_scroll.pack(side="right", fill="y")
        scroll_down.pack(fill="x", pady=(4, 0))

        def update_scroll_region(_event=None):
            nav_canvas.configure(scrollregion=nav_canvas.bbox("all"))

        def update_content_width(event):
            nav_canvas.itemconfigure(nav_window, width=event.width)

        def bind_mousewheel(_event=None):
            nav_canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event=None):
            nav_canvas.unbind_all("<MouseWheel>")

        def on_mousewheel(event):
            nav_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        nav_content.bind("<Configure>", update_scroll_region)
        nav_canvas.bind("<Configure>", update_content_width)
        nav_canvas.bind("<Enter>", bind_mousewheel)
        nav_canvas.bind("<Leave>", unbind_mousewheel)

        self._sidebar_caption(nav_content, "工作台")
        self._nav(nav_content, "terminal", "服务日志", "查看运行状态", "LOG", lambda: self.switch_page("terminal"))
        self._nav(nav_content, "storyboard", "广告视频", "分镜/首尾帧/九宫格", "AD", lambda: self.switch_page("storyboard"), accent=True)
        self._nav(nav_content, "image", "AI 生图", "生成/编辑图片", "IMG", lambda: self.switch_page("image"), accent=True)
        self._nav(nav_content, "video", "AI 视频", "文生/图生视频", "VID", lambda: self.switch_page("video"), accent=True)

        self._sidebar_caption(nav_content, "配置")
        self._nav(nav_content, "license", "授权码", "在线激活解锁", "LIC", lambda: self.switch_page("license"))
        self._nav(nav_content, "api", "API 配置", "设置模型密钥", "KEY", self.show_api_config)
        self._nav(nav_content, "feishu", "飞书机器人", "绑定消息通道", "BOT", self.show_feishu_config)
        self._nav(nav_content, "weixin", "微信绑定", "扫码登录微信", "WX", self.bind_weixin)

        self._sidebar_caption(nav_content, "维护")
        self._nav(nav_content, "web", "网页界面", "打开本地控制台", "WEB", self.open_web)
        self._nav(nav_content, "update", "检查更新", "更新 OpenClaw", "UP", self.check_update)
        self._nav(nav_content, "help", "帮助文档", "查看使用说明", "DOC", self.open_readme)

        footer = tk.Frame(inner, bg=COLORS["sidebar_bg"])
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        self.stop_btn = NavButton(footer, "停止服务", "结束当前网关进程", "STOP", self.stop_openclaw, danger=True)
        self.stop_btn.pack(fill="x", pady=(0, 12))

        status = tk.Frame(footer, bg=COLORS["sidebar_bg"])
        status.pack(fill="x")
        self.status_canvas = tk.Canvas(status, width=10, height=10, bg=COLORS["sidebar_bg"], highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(2, 8))
        self.status_dot = self.status_canvas.create_oval(1, 1, 9, 9, fill=COLORS["warning"], outline="")
        self.status_label = tk.Label(status, text="未配置", font=FONTS["small"], bg=COLORS["sidebar_bg"], fg=COLORS["text_muted"])
        self.status_label.pack(side="left")

    def _sidebar_caption(self, parent: tk.Misc, text: str) -> None:
        tk.Label(parent, text=text, font=FONTS["sidebar_caption"], bg=COLORS["sidebar_bg"], fg=COLORS["text_subtle"]).pack(anchor="w", pady=(8, 4), padx=4)

    def _nav(self, parent: tk.Misc, key: str, text: str, desc: str, icon: str, command, *, accent: bool = False) -> NavButton:
        nav = NavButton(parent, text, desc, icon, command, accent=accent)
        nav.pack(fill="x", pady=2)
        self.nav_buttons[key] = nav
        return nav

    def _build_terminal_page(self) -> None:
        frame = tk.Frame(self.right_frame, bg=COLORS["terminal_bg"])
        self.pages["terminal"] = frame

        header = tk.Frame(frame, bg=COLORS["terminal_header"], height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        dots = tk.Frame(header, bg=COLORS["terminal_header"])
        dots.pack(side="left", padx=18, pady=21)
        for color in [COLORS["terminal_dot_red"], COLORS["terminal_dot_yellow"], COLORS["terminal_dot_green"]]:
            dot = tk.Canvas(dots, width=11, height=11, bg=COLORS["terminal_header"], highlightthickness=0)
            dot.create_oval(0, 0, 11, 11, fill=color, outline="")
            dot.pack(side="left", padx=3)
        tk.Label(header, text=BRAND["terminal_header"], font=FONTS["section"], bg=COLORS["terminal_header"], fg=COLORS["terminal_label"]).pack(side="left", padx=10)
        tk.Label(header, text=f"127.0.0.1:{APP_PORT}", font=FONTS["small"], bg=COLORS["terminal_header"], fg=COLORS["terminal_label_muted"]).pack(side="left", padx=8)
        tk.Button(
            header,
            text="打开网页",
            command=self.open_web,
            font=FONTS["small"],
            bg=COLORS["terminal_button_bg"],
            fg=COLORS["terminal_label"],
            activebackground=COLORS["terminal_button_hover"],
            activeforeground=COLORS["terminal_button_text"],
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=5,
        ).pack(side="right", padx=14, pady=14)

        self.log_text = tk.Text(
            frame,
            bg=COLORS["terminal_bg"],
            fg=COLORS["terminal_text"],
            font=FONTS["mono"],
            wrap="none",
            relief="flat",
            padx=18,
            pady=18,
            insertbackground=COLORS["terminal_text"],
            selectbackground=COLORS["terminal_selection"],
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.bind("<Key>", self._log_key_filter)
        scrollbar = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def _log_key_filter(self, event):
        if event.state & 0x4 and event.keysym in ("c", "a", "C", "A"):
            return None
        return "break"

    def center_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def switch_page(self, target: str) -> None:
        feature = self.protected_pages.get(target)
        if feature and not self.license_manager.is_authorized(feature):
            messagebox.showinfo("需要授权", "请先输入授权码完成在线激活。")
            target = "license"
        if target in {"license", "storyboard", "image", "video"} and target not in self.pages:
            self._create_lazy_page(target)
        if target not in self.pages:
            target = "terminal"

        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[target].pack(fill="both", expand=True)
        self.current_page = target
        for key, nav in self.nav_buttons.items():
            nav.set_active(key == target)

    def _create_lazy_page(self, target: str) -> None:
        if target == "license":
            page = LicensePage(self.right_frame, self.root, self.license_manager, self._on_license_activated)
        elif target == "storyboard":
            page = StoryboardPage(self.right_frame, self.root, self.paths, self.append_log)
        elif target == "image":
            page = ImagePage(self.right_frame, self.root, self.paths, self.append_log)
        elif target == "video":
            page = VideoPage(self.right_frame, self.root, self.paths, self.append_log)
        else:
            return
        self.page_objects[target] = page
        self.pages[target] = page.frame

    def check_config(self) -> None:
        if not self.license_manager.is_authorized():
            self.status_canvas.itemconfig(self.status_dot, fill=COLORS["danger"])
            self.status_label.config(text="未授权")
        elif os.path.exists(self.paths.auth_profiles):
            self.status_canvas.itemconfig(self.status_dot, fill=COLORS["success"])
            self.status_label.config(text="API 已配置")
        else:
            self.status_canvas.itemconfig(self.status_dot, fill=COLORS["warning"])
            self.status_label.config(text="未配置 API")

    def append_log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def _ui_call(self, func, *args) -> None:
        self.root.after(0, func, *args)

    def start_openclaw(self) -> None:
        if not self.license_manager.is_authorized("openclaw"):
            messagebox.showinfo("需要授权", "请先输入授权码完成在线激活。")
            self.switch_page("license")
            return
        try:
            self.process_service.start(on_exit=self._on_process_exit)
            self.status_canvas.itemconfig(self.status_dot, fill=COLORS["success"])
            self.status_label.config(text="服务运行中")
            self.root.after(3000, self.open_web)
        except RuntimeError as error:
            messagebox.showinfo("提示", str(error))
        except Exception as error:
            self.append_log(f"[Error] {traceback.format_exc()}\n")
            messagebox.showerror("启动失败", str(error))

    def _on_process_exit(self, _exit_code: int | None = None) -> None:
        self.check_config()

    def stop_openclaw(self) -> None:
        try:
            message = self.process_service.stop()
            self.check_config()
            if message == "服务未启动":
                messagebox.showinfo("提示", message)
        except Exception as error:
            self.append_log(f"[Error: {error}]\n")
            messagebox.showerror("停止失败", str(error))

    def show_api_config(self) -> None:
        ApiConfigDialog(self.root, self.paths, self.check_config)

    def show_feishu_config(self) -> None:
        FeishuConfigDialog(self.root, self.paths, self.append_log)

    def bind_weixin(self) -> None:
        try:
            plugin_path = os.path.join(self.paths.state_dir, "extensions", "openclaw-weixin")
            plugin_installed = os.path.exists(plugin_path) and os.path.exists(os.path.join(plugin_path, "package.json"))
            node_exe = self.paths.node_exe
            openclaw_mjs = self.paths.openclaw_mjs
            if not os.path.exists(node_exe):
                messagebox.showerror("错误", f"找不到 Node.js：\n{node_exe}")
                return
            if not os.path.exists(openclaw_mjs):
                messagebox.showerror("错误", f"找不到 OpenClaw：\n{openclaw_mjs}")
                return
            env = self.paths.process_env()
            if plugin_installed:
                self.append_log("[微信] 启动登录流程...\n")
                command = f'"{node_exe}" "{openclaw_mjs}" channels login --channel openclaw-weixin'
            elif messagebox.askyesno("微信绑定", "微信插件未安装，是否现在安装？"):
                self.append_log("[微信] 正在安装插件...\n")
                command = (
                    f'"{node_exe}" "{openclaw_mjs}" plugins install @tencent-weixin/openclaw-weixin '
                    f'& "{node_exe}" "{openclaw_mjs}" config set plugins.entries.openclaw-weixin.enabled true '
                    f'& "{node_exe}" "{openclaw_mjs}" channels login --channel openclaw-weixin'
                )
            else:
                return
            subprocess.Popen(["cmd", "/k", command], env=env, cwd=self.paths.base_path, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as error:
            self.append_log(f"[微信错误] {error}\n")
            messagebox.showerror("微信绑定失败", str(error))

    def check_update(self) -> None:
        self.append_log("\n[更新] 正在检查更新...\n")

        def worker() -> None:
            current = self.updater.current_version()
            latest, error = self.updater.latest_version()
            self.root.after(0, self._handle_update_check, current, latest, error)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_check(self, current: str, latest: str | None, error: str | None) -> None:
        if error:
            self.append_log(f"[更新] 失败: {error}\n")
            messagebox.showerror("检查更新", f"失败：\n{error}")
            return
        if current == latest:
            self.append_log("[更新] 已是最新版本\n")
            messagebox.showinfo("检查更新", f"已是最新版本。\n\n当前: {current}")
            return
        if messagebox.askyesno("发现新版本", f"当前: {current}\n最新: {latest}\n\n是否更新？"):
            self._do_update()

    def _do_update(self) -> None:
        self.append_log("\n[更新] 开始更新 OpenClaw...\n")

        def done(success: bool, message: str) -> None:
            if success:
                self.append_log(f"\n[更新] 完成: {message}\n")
                messagebox.showinfo("更新成功", f"新版本: {message}")
            else:
                self.append_log(f"\n[更新] 失败: {message}\n")
                messagebox.showwarning("更新失败", message)

        self.updater.update_async(self.append_log, self._ui_call, done)

    def open_web(self) -> None:
        if not self.license_manager.is_authorized("openclaw"):
            messagebox.showinfo("需要授权", "请先输入授权码完成在线激活。")
            self.switch_page("license")
            return
        webbrowser.open(f"http://127.0.0.1:{APP_PORT}")

    def open_readme(self) -> None:
        webbrowser.open(HELP_URL)

    def _on_license_activated(self) -> None:
        self.check_config()
        self.switch_page("terminal")

    def close(self) -> None:
        if self.process_service.running:
            self.process_service.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
