# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess, os, webbrowser, sys, json, ctypes, re, threading
from PIL import Image, ImageTk
import io
import base64

# 设置 Windows AppUserModelID，确保任务栏显示正确的 exe 图标
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenClaw.Launcher.USB")
except Exception:
    pass

# ========== Base64 encoded logo ==========
LOGO_BASE64 = """
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"""

# ========== U盘绑定检测 ==========
def get_usb_serial():
    """获取当前U盘的序列号（多种方法尝试）"""
    try:
        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(base_path) == "OpenClaw启动":
            base_path = os.path.dirname(base_path)

        drive = os.path.splitdrive(os.path.abspath(base_path))[0]
        if not drive:
            return None

        drive_letter = drive.rstrip(':')

        # 方法1: 使用 PowerShell（推荐，WMIC在Win11可能被弃用）
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 f"(Get-Volume -DriveLetter {drive_letter}).SerialNumber"],
                capture_output=True, text=True, shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            serial = result.stdout.strip()
            if serial and serial not in ['', 'SerialNumber']:
                return serial.upper()
        except Exception as e:
            print(f"PowerShell method failed: {e}")

        # 方法2: 使用 WMIC 命令（备用）
        try:
            result = subprocess.run(
                f'wmic logicaldisk where "DeviceID=\'{drive_letter}:\'" get VolumeSerialNumber /value',
                capture_output=True, text=True, shell=True
            )
            match = re.search(r'VolumeSerialNumber=(\S+)', result.stdout)
            if match:
                return match.group(1).strip().upper()
        except Exception as e:
            print(f"WMIC method failed: {e}")

        # 方法3: 使用WMI接口（Python直接调用）
        try:
            import wmi
            c = wmi.WMI()
            for disk in c.Win32_LogicalDisk(DriveType=2):  # removable
                if disk.DeviceID == f"{drive_letter}:":
                    if disk.VolumeSerialNumber:
                        return disk.VolumeSerialNumber.upper()
        except Exception as e:
            print(f"WMI Python method failed: {e}")

        # 方法4: 通过物理磁盘获取序列号（最可靠但最复杂）
        try:
            # 先找到驱动器对应的物理磁盘
            result = subprocess.run(
                ['powershell', '-Command',
                 f"Get-Disk | Where-Object {{$_.Location -like '*{drive_letter}*'}} | Select-Object -ExpandProperty SerialNumber"],
                capture_output=True, text=True, shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            serial = result.stdout.strip()
            if serial:
                return serial.upper()
        except Exception as e:
            print(f"Physical disk method failed: {e}")

        return None
    except Exception as e:
        print(f"Error getting USB serial: {e}")
        return None

def is_removable_drive(path):
    """检测路径是否在可移动驱动器（U盘）上"""
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return False
    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
    # DRIVE_REMOVABLE = 2, 有些大容量USB可能显示为 DRIVE_FIXED = 3
    # 所以我们同时检查是否是外部连接的磁盘
    if drive_type == 2:
        return True

    # 对于被识别为固定磁盘的USB，尝试通过PowerShell检测
    try:
        drive_letter = drive.rstrip(':')
        result = subprocess.run(
            ['powershell', '-Command',
             f"(Get-Disk | Where-Object {{$_.Location -match '{drive_letter}'}}).BusType"],
            capture_output=True, text=True, shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        bus_type = result.stdout.strip().lower()
        # USB类型的总线
        if bus_type in ['usb', 'usbmassstorage']:
            return True
    except:
        pass

    # 最后检查驱动器是否可以从系统安全移除（有"安全删除硬件"选项）
    try:
        result = subprocess.run(
            ['powershell', '-Command',
             f"Get-Volume -DriveLetter {drive_letter} | Get-Disk | Select-Object -ExpandProperty IsRemovable"],
            capture_output=True, text=True, shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        is_removable = result.stdout.strip().lower()
        if is_removable == 'true':
            return True
    except:
        pass

    return False

def check_usb_binding():
    """检查U盘绑定状态"""
    base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(base_path) == "OpenClaw启动":
        base_path = os.path.dirname(base_path)

    # 检查是否是U盘
    if not is_removable_drive(base_path):
        root = tk.Tk()
        root.withdraw()
        drive = os.path.splitdrive(base_path)[0]
        messagebox.showerror(
            "USB Only",
            f"This program can only run from a USB drive.\n\n"
            f"Current location: {base_path}\n"
            f"Drive: {drive} (Fixed Disk)\n\n"
            f"Please copy this folder to a USB drive and try again."
        )
        sys.exit(1)

    # 获取当前U盘序列号
    current_serial = get_usb_serial()
    if not current_serial:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Error",
            "Failed to get USB serial number.\n\n"
            "Possible solutions:\n"
            "1. Try a different USB port (prefer USB 2.0)\n"
            "2. Run as Administrator\n"
            "3. Check if PowerShell is available\n"
            "4. Try another USB drive\n\n"
            "If this is a large capacity USB drive (>32GB), "
            "it may be recognized as a fixed disk."
        )
        sys.exit(1)

    # 检查绑定文件
    bind_file = os.path.join(base_path, "data", ".openclaw", ".usb_bind")
    os.makedirs(os.path.dirname(bind_file), exist_ok=True)

    if os.path.exists(bind_file):
        # 已绑定，检查序列号
        try:
            with open(bind_file, "r") as f:
                bound_serial = f.read().strip()

            if current_serial != bound_serial:
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "USB Mismatch",
                    f"This program is bound to a different USB drive.\n\n"
                    f"Expected: {bound_serial}\n"
                    f"Current: {current_serial}\n\n"
                    f"This copy can only run on the original USB drive."
                )
                sys.exit(1)
        except Exception as e:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error", f"Failed to read binding: {e}")
            sys.exit(1)
    else:
        # 未绑定，请求绑定
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askyesno(
            "First Run - USB Binding",
            f"This is the first time running on this USB drive.\n\n"
            f"USB Serial: {current_serial}\n\n"
            f"Bind this program to this USB drive?\n\n"
            f"After binding, this program will only work on this USB drive."
        )

        if result:
            try:
                with open(bind_file, "w") as f:
                    f.write(current_serial)
                # 设置隐藏属性
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(bind_file, 2)  # FILE_ATTRIBUTE_HIDDEN = 2
                except:
                    pass
                messagebox.showinfo("Success", f"USB binding successful!\n\nBound to: {current_serial}\n\nThis program is now locked to this USB drive.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save binding: {e}")
                sys.exit(1)
        else:
            messagebox.showinfo("Cancelled", "USB binding cancelled. Program will exit.")
            sys.exit(1)

    return base_path

# 启动时立即检测
BASE_PATH = check_usb_binding()

# AI Provider presets
PROVIDERS = {
    "Heang AI": {"url": "http://111.170.36.121:3000/v1", "models": ["kimi-k2.5", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "OpenAI": {"url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "Claude": {"url": "https://api.anthropic.com/v1", "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]},
    "DeepSeek": {"url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-coder"]},
    "智谱AI": {"url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4", "glm-4-flash"]},
    "Moonshot": {"url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k"]},
    "自定义": {"url": "", "models": []},
}

# Modern color scheme
COLORS = {
    "bg_dark": "#121212",        # Slightly lighter dark background
    "bg_card": "#1E1E1E",        # Card background
    "bg_hover": "#2C2C2C",       # Hover state
    "bg_terminal": "#000000",    # True black for terminal
    "accent": "#3B82F6",         # Modern blue
    "accent_hover": "#60A5FA",   # Lighter blue for hover
    "success": "#10B981",        # Green
    "warning": "#F59E0B",        # Yellow
    "danger": "#EF4444",         # Red
    "text": "#F3F4F6",           # Off-white text
    "text_muted": "#9CA3AF",     # Gray text
    "border": "#374151",         # Border color
    "gradient_start": "#3B82F6", # Blue
    "gradient_end": "#8B5CF6",   # Purple
}

class ModernButton(tk.Canvas):
    """Modern button with hover effects"""
    def __init__(self, parent, text, desc="", icon="", command=None, primary=False, danger=False, **kwargs):
        super().__init__(parent, height=56, bg=COLORS["bg_dark"], highlightthickness=0, **kwargs)
        self.text = text
        self.desc = desc
        self.icon = icon
        self.command = command
        self.primary = primary
        self.danger = danger
        self.hovered = False
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
        h = 56  # Increased height for better proportions
        if self.primary:
            bg = COLORS["accent_hover"] if self.hovered else COLORS["accent"]
        elif self.danger:
            bg = "#DC2626" if self.hovered else COLORS["danger"]
        else:
            bg = COLORS["bg_hover"] if self.hovered else COLORS["bg_card"]
        radius = 10  # Slightly rounder corners
        self._round_rect(0, 0, w, h, radius, fill=bg, outline=COLORS["border"] if not self.primary and not self.danger else "")
        x_offset = 20
        if self.primary:
            self.create_polygon(20, 19, 20, 37, 34, 28, fill="white", outline="")
            x_offset = 46
        elif self.icon:
            self.create_text(24, 28, text=self.icon, font=("Segoe UI Emoji", 15), fill=COLORS["accent"])
            x_offset = 48
            
        # Adjust text position based on whether there's a description
        y_text = 20 if self.desc else 28
        self.create_text(x_offset, y_text, text=self.text, anchor="w", font=("Microsoft YaHei UI", 11, "bold"), fill="white" if (self.primary or self.danger) else COLORS["text"])
        if self.desc:
            self.create_text(x_offset, 38, text=self.desc, anchor="w", font=("Microsoft YaHei UI", 9), fill="#DBEAFE" if self.primary else COLORS["text_muted"])

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)


class OpenClawLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OpenClaw")
        self.root.geometry("1024x720")
        self.root.minsize(900, 600)  # 设置最小窗口大小
        self.root.resizable(True, True)  # 允许调整窗口大小
        self.root.configure(bg=COLORS["bg_dark"])
        self.base_path = BASE_PATH
        self.node_path = self._find_node()
        self.process = None  # Subprocess handle
        self.running = False  # Service running state
        self.setup_ui()
        self.center_window()
        self.check_config()

    def _find_node(self):
        for p in [os.path.join(self.base_path, "SystemData", ".core", "node"), os.path.join(self.base_path, "node")]:
            if os.path.exists(os.path.join(p, "node.exe")):
                return p
        return os.path.join(self.base_path, "node")

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
        """获取资源文件路径，支持打包后和开发环境"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后，资源在临时目录 sys._MEIPASS
            return os.path.join(sys._MEIPASS, filename)
        else:
            # 开发环境
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

    def setup_ui(self):
        # Main container with two columns
        main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        main.pack(fill="both", expand=True)

        # Left panel (320px) - Buttons
        left_frame = tk.Frame(main, bg=COLORS["bg_dark"], width=320)
        left_frame.pack(side="left", fill="y", padx=24, pady=24)
        left_frame.pack_propagate(False)

        # Logo & Window Icon - 优先使用 .ico 文件
        try:
            # 尝试加载打包进 exe 的 Gzlogo.ico
            ico_path = self._get_resource_path("Gzlogo.ico")
            if os.path.exists(ico_path):
                # 先设置 iconbitmap（Windows 任务栏和标题栏图标）
                self.root.iconbitmap(default=ico_path)
                # 加载用于界面显示的 logo
                logo_image = Image.open(ico_path)
                logo_image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
            else:
                # 回退到 base64 内嵌图标
                logo_data = base64.b64decode(LOGO_BASE64)
                logo_image = Image.open(io.BytesIO(logo_data))
                logo_image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                self.root.iconphoto(True, self.logo_photo)

            tk.Label(left_frame, image=self.logo_photo, bg=COLORS["bg_dark"]).pack(pady=(0, 12))
        except Exception as e:
            print(f"Failed to load logo: {e}")
            # Fallback to emoji logo
            logo_canvas = tk.Canvas(left_frame, width=64, height=64, bg=COLORS["bg_dark"], highlightthickness=0)
            logo_canvas.pack(pady=(0, 12))
            for i in range(32):
                r, c = 32-i, self._interpolate_color(COLORS["gradient_start"], COLORS["gradient_end"], i/32)
                logo_canvas.create_oval(32-r, 32-r, 32+r, 32+r, fill=c, outline="")
            logo_canvas.create_text(32, 32, text="🦞", font=("Segoe UI Emoji", 24))

        tk.Label(left_frame, text="OpenClaw", font=("Microsoft YaHei UI", 22, "bold"), bg=COLORS["bg_dark"], fg=COLORS["text"]).pack()
        tk.Label(left_frame, text="个人AI助手 · U盘便携版", font=("Microsoft YaHei UI", 10), bg=COLORS["bg_dark"], fg=COLORS["accent"]).pack(pady=(4, 24))

        btn_frame = tk.Frame(left_frame, bg=COLORS["bg_dark"])
        btn_frame.pack(fill="x")
        self.start_btn = ModernButton(btn_frame, "启动服务", command=self.start_openclaw, primary=True)
        self.start_btn.pack(fill="x", pady=4)
        ModernButton(btn_frame, "API配置", "设置API密钥", "🔑", self.show_api_config).pack(fill="x", pady=4)
        ModernButton(btn_frame, "飞书机器人", "绑定消息通道", "🤖", self.show_feishu_config).pack(fill="x", pady=4)
        ModernButton(btn_frame, "微信绑定", "扫码登录微信", "💬", self.bind_weixin).pack(fill="x", pady=4)
        ModernButton(btn_frame, "网页界面", "127.0.0.1:18790", "🌐", self.open_web).pack(fill="x", pady=4)
        ModernButton(btn_frame, "检查更新", "更新OpenClaw版本", "⬆", self.check_update).pack(fill="x", pady=4)
        ModernButton(btn_frame, "帮助", "使用说明", "📖", self.open_readme).pack(fill="x", pady=4)
        
        # Add some flexible space before the stop button
        tk.Frame(btn_frame, bg=COLORS["bg_dark"], height=10).pack(fill="x")
        
        self.stop_btn = ModernButton(btn_frame, "退出OpenClaw", "停止服务并退出", "⏹", self.stop_openclaw, danger=True)
        self.stop_btn.pack(fill="x", pady=4)

        # Status bar at bottom of left panel
        status_frame = tk.Frame(left_frame, bg=COLORS["bg_dark"])
        status_frame.pack(side="bottom", fill="x", pady=(15, 0))
        self.status_canvas = tk.Canvas(status_frame, width=12, height=12, bg=COLORS["bg_dark"], highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(0, 8))
        self.status_dot = self.status_canvas.create_oval(2, 2, 10, 10, fill=COLORS["warning"], outline="")
        self.status_label = tk.Label(status_frame, text="未配置", font=("Microsoft YaHei UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"])
        self.status_label.pack(side="left")

        # Right panel (640px) - Terminal
        right_frame = tk.Frame(main, bg=COLORS["bg_terminal"], width=640)
        right_frame.pack(side="right", fill="both", expand=True, padx=(0, 24), pady=24)
        right_frame.pack_propagate(False)

        # Terminal header (styled like a Mac window)
        term_header = tk.Frame(right_frame, bg=COLORS["bg_card"], height=36)
        term_header.pack(fill="x")
        term_header.pack_propagate(False)
        
        # Mac-style buttons
        mac_btns = tk.Frame(term_header, bg=COLORS["bg_card"])
        mac_btns.pack(side="left", padx=12, pady=12)
        btn1 = tk.Canvas(mac_btns, width=12, height=12, bg=COLORS["bg_card"], highlightthickness=0)
        btn1.create_oval(0, 0, 12, 12, fill="#FF5F56", outline="")
        btn1.pack(side="left", padx=3)
        
        btn2 = tk.Canvas(mac_btns, width=12, height=12, bg=COLORS["bg_card"], highlightthickness=0)
        btn2.create_oval(0, 0, 12, 12, fill="#FFBD2E", outline="")
        btn2.pack(side="left", padx=3)
        
        btn3 = tk.Canvas(mac_btns, width=12, height=12, bg=COLORS["bg_card"], highlightthickness=0)
        btn3.create_oval(0, 0, 12, 12, fill="#27C93F", outline="")
        btn3.pack(side="left", padx=3)
        
        tk.Label(term_header, text=" Service Log", font=("Consolas", 10), bg=COLORS["bg_card"], fg=COLORS["text_muted"]).pack(side="left", padx=10)

        # Terminal content - interactive command terminal
        self.log_text = tk.Text(right_frame, bg=COLORS["bg_terminal"], fg="#00FF41",
                                font=("Consolas", 11), wrap="none",
                                relief="flat", padx=16, pady=16,
                                insertbackground="#00FF41", selectbackground="#1A4A28")
        self.log_text.pack(fill="both", expand=True)

        # Simple command execution - Enter runs command
        self.log_text.insert("end", "> ")
        self.log_text.focus_set()

        def on_enter(event):
            # Get all text, find last line after last ">"
            all_text = self.log_text.get("1.0", "end")
            lines = all_text.split("\n")
            # Find last line that starts with > or after it
            cmd = ""
            for line in reversed(lines):
                if line.startswith("> "):
                    cmd = line[2:].strip()
                    break
                elif line.strip() and not line.startswith(">"):
                    cmd = line.strip()
                    break

            if cmd and cmd != ">":
                self.log_text.insert("end", "\n")
                # Run command
                try:
                    proc = subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        cwd=self.base_path,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    raw = proc.communicate()[0]
                    # 先尝试UTF-8解码，失败则用GBK
                    try:
                        out = raw.decode('utf-8')
                    except:
                        out = raw.decode('gbk', errors='replace')
                    if out:
                        self.log_text.insert("end", out)
                    self.log_text.insert("end", f"\n[Exit: {proc.returncode}]\n> ")
                except Exception as e:
                    self.log_text.insert("end", f"\n[Error: {e}]\n> ")
            else:
                self.log_text.insert("end", "\n> ")
            self.log_text.see("end")
            return "break"

        self.log_text.bind("<Return>", on_enter)

        # Scrollbar
        scrollbar = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

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
            self.status_label.config(text="未配置 - 请点击API配置")

    def append_log(self, text):
        """Append text to terminal log"""
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def start_openclaw(self):
        """启动 OpenClaw"""
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
            self.append_log(f"[OpenClaw] Base: {self.base_path}\n")
            self.append_log(f"[OpenClaw] Node: {node_exe}\n")
            self.append_log(f"[OpenClaw] Script: {start_js}\n")
            self.append_log(f"[OpenClaw] Command: [{node_exe}, {start_js}]\n\n")

            # 启动进程，捕获输出（CREATE_NO_WINDOW防止弹出终端窗口）
            cmd = [node_exe, start_js]
            self.append_log(f"[Debug] subprocess.Popen args: {cmd}\n")

            self.process = subprocess.Popen(
                cmd,
                cwd=self.base_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )

            self.append_log(f"[Debug] Process started, PID: {self.process.pid}\n")
            self.running = True
            self.start_btn._draw()  # Redraw button to update visual state

            # 启动线程读取输出
            threading.Thread(target=self._read_output, daemon=True).start()

            # 3秒后自动打开网页
            self.root.after(3000, self.open_web)

        except Exception as e:
            import traceback
            self.append_log(f"[Error] {type(e).__name__}: {str(e)}\n")
            self.append_log(f"[Error] Traceback:\n{traceback.format_exc()}\n")
            messagebox.showerror("启动失败", f"启动 OpenClaw 时出错：\n\n{str(e)}")

    def _read_output(self):
        """Thread to read subprocess output"""
        try:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break  # EOF
                self.root.after(0, self.append_log, line)
        except Exception as e:
            self.root.after(0, self.append_log, f"[Error reading output: {e}]\n")

        # Process ended, get exit code
        exit_code = self.process.poll()
        self.root.after(0, self._on_process_ended, exit_code)

    def _on_process_ended(self, exit_code=None):
        """Called when subprocess ends"""
        self.running = False
        if exit_code is None and self.process:
            exit_code = self.process.poll()
        self.append_log(f"\n[OpenClaw] Process ended (exit code: {exit_code})\n")

    def stop_openclaw(self):
        """停止 OpenClaw"""
        # 检查进程是否实际在运行
        if self.process and self.process.poll() is None:
            # 进程还在运行，使用taskkill终止整个进程树
            try:
                self.append_log("\n[OpenClaw] Stopping service...\n")
                pid = self.process.pid
                # 使用taskkill /T 终止进程树中的所有子进程
                subprocess.run(f'taskkill /F /T /PID {pid}', shell=True, capture_output=True)
                self.process.wait(timeout=5)
                self.running = False
                self.append_log("[OpenClaw] Service stopped.\n")
            except Exception as e:
                self.append_log(f"[Error stopping: {e}]\n")
        elif self.process:
            # 进程已退出，但可能有残留的子进程
            self.append_log("\n[OpenClaw] Cleaning up orphan processes...\n")
            # 尝试通过端口找到并终止进程
            try:
                subprocess.run('for /f "tokens=5" %a in (\'netstat -aon ^| findstr :18790\') do taskkill /F /PID %a', shell=True, capture_output=True)
            except:
                pass
            self.running = False
            self.process = None
            self.append_log("[OpenClaw] Done.\n")
        else:
            # 没有启动过
            messagebox.showinfo("提示", "服务未启动")

    def show_api_config(self):
        w = tk.Toplevel(self.root)
        w.title("API 密钥配置")
        w.geometry("320x450")
        w.configure(bg=COLORS["bg_dark"])
        w.transient(self.root)
        w.grab_set()
        w.update_idletasks()
        w.geometry(f"+{self.root.winfo_x() + (self.root.winfo_width() - 320) // 2}+{self.root.winfo_y() + (self.root.winfo_height() - 450) // 2}")

        content = tk.Frame(w, bg=COLORS["bg_dark"])
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(content, text="API 密钥配置", font=("Segoe UI", 14, "bold"), bg=COLORS["bg_dark"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 10))

        tk.Label(content, text="AI 服务商", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
        provider_var = tk.StringVar(value="Heang AI")
        provider_combo = ttk.Combobox(content, textvariable=provider_var, values=list(PROVIDERS.keys()), state="readonly", font=("Segoe UI", 9))
        provider_combo.pack(fill="x", pady=(3, 8), ipady=4)

        tk.Label(content, text="API URL", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
        url_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
        url_entry.pack(fill="x", pady=(3, 8), ipady=5)

        tk.Label(content, text="API 密钥", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
        key_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
        key_entry.pack(fill="x", pady=(3, 8), ipady=5)

        show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(content, text="显示密钥", variable=show_var, command=lambda: key_entry.config(show="" if show_var.get() else "●"), bg=COLORS["bg_dark"], fg=COLORS["text_muted"], selectcolor=COLORS["bg_card"], activebackground=COLORS["bg_dark"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        tk.Label(content, text="模型名称（可选）", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
        model_entry = tk.Entry(content, font=("Segoe UI", 9), bg=COLORS["bg_card"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
        model_entry.pack(fill="x", pady=(3, 10), ipady=5)

        def on_provider_change(e=None):
            provider = provider_combo.get()
            provider_data = PROVIDERS.get(provider, {})
            url = provider_data.get("url", "")
            models = provider_data.get("models", [])

            url_entry.delete(0, tk.END)
            url_entry.insert(0, url)
            model_entry.delete(0, tk.END)
            if models:
                model_entry.insert(0, models[0])
        provider_combo.bind("<<ComboboxSelected>>", on_provider_change)
        on_provider_change()

        def save_config():
            provider = provider_combo.get()
            api_key = key_entry.get().strip()
            api_url = url_entry.get().strip()
            model = model_entry.get().strip()
            if not api_key: return messagebox.showerror("错误", "请输入 API 密钥", parent=w)

            profile_key = "custom" if provider == "自定义" else provider.lower().replace(" ", "_")
            auth_file = os.path.join(self.base_path, "data", ".openclaw", "agents", "main", "agent", "auth-profiles.json")
            os.makedirs(os.path.dirname(auth_file), exist_ok=True)
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "profiles": {profile_key: {"type": "token", "provider": profile_key, "token": api_key}}}, f, indent=2)

            config_file = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
            existing_config = {}
            if os.path.exists(config_file):
                try: existing_config = json.load(open(config_file, "r", encoding="utf-8"))
                except: pass

            model_id = model or "default"
            provider_config = {"api": "openai-completions", "models": [{"id": model_id, "name": model or provider, "contextWindow": 128000, "maxTokens": 4096}]}
            if api_url: provider_config["baseUrl"] = api_url

            existing_config.setdefault("models", {}).setdefault("providers", {})[profile_key] = provider_config
            existing_config.setdefault("agents", {"defaults": {"model": {}}})["defaults"]["model"]["primary"] = f"{profile_key}/{model_id}"

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=2, ensure_ascii=False)

            self.check_config()
            w.destroy()
            messagebox.showinfo("成功", f"API 密钥已保存！\n服务商：{provider}\n模型：{model or provider}\n\n点击\"启动服务\"开始使用。")

        btn_frame = tk.Frame(content, bg=COLORS["bg_dark"])
        btn_frame.pack(fill="x", pady=(10, 0))

        tk.Button(btn_frame, text="✓ 保存", font=("Segoe UI", 10, "bold"), command=save_config, bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", width=10, height=1).pack(side="left")
        tk.Button(btn_frame, text="取消", font=("Segoe UI", 10), command=w.destroy, bg=COLORS["bg_card"], fg=COLORS["text"], relief="flat", cursor="hand2", width=10, height=1).pack(side="left", padx=(8, 0))

        def open_get_key():
            provider = provider_combo.get()
            urls = {
                "Heang AI": "https://api.heang.top",
                "OpenAI": "https://platform.openai.com/api-keys",
                "Claude": "https://console.anthropic.com/settings/keys",
                "DeepSeek": "https://platform.deepseek.com/api_keys",
                "智谱AI": "https://open.bigmodel.cn/usercenter/api-keys",
                "Moonshot": "https://platform.moonshot.cn/console/api-keys",
            }
            url = urls.get(provider, "")
            if url:
                webbrowser.open(url)
            else:
                messagebox.showinfo("提示", f"请自行搜索 {provider} 的 API 密钥获取方式")

        tk.Button(content, text="🔗 获取 API 密钥", font=("Segoe UI", 9), command=open_get_key, bg=COLORS["bg_card"], fg=COLORS["accent"], relief="flat", cursor="hand2").pack(pady=(10, 0))

    def show_feishu_config(self):
        w = tk.Toplevel(self.root)
        w.title("飞书机器人配置")
        w.geometry("320x350")
        w.configure(bg=COLORS["bg_dark"])
        w.transient(self.root)
        w.grab_set()
        w.update_idletasks()
        w.geometry(f"+{self.root.winfo_x() + (self.root.winfo_width() - 320) // 2}+{self.root.winfo_y() + (self.root.winfo_height() - 350) // 2}")

        content = tk.Frame(w, bg=COLORS["bg_dark"])
        content.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(content, text="飞书机器人配置", font=("Segoe UI", 14, "bold"), bg=COLORS["bg_dark"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 10))

        def check_feishu_config():
            config_path = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
            if os.path.exists(config_path):
                try:
                    import json
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    channels = config.get("channels", {})
                    feishu = channels.get("feishu", {})
                    if feishu.get("appId"):
                        return feishu.get("appId", "")
                except: pass
            return None

        plugin_path = os.path.join(self.base_path, "data", ".openclaw", "extensions", "openclaw-lark")
        plugin_installed = os.path.exists(plugin_path)
        current_appid = check_feishu_config()

        if current_appid:
            tk.Label(content, text=f"✅ 飞书已配置\nApp ID: {current_appid}", font=("Segoe UI", 10), bg=COLORS["bg_dark"], fg="#4ade80", justify="left").pack(anchor="w", pady=(0, 10))
        elif not plugin_installed:
            tk.Label(content, text="⚠️ 飞书插件未安装", font=("Segoe UI", 10), bg=COLORS["bg_dark"], fg="#fbbf24", justify="left").pack(anchor="w", pady=(0, 10))
        else:
            tk.Label(content, text="❌ 飞书应用未配置", font=("Segoe UI", 10), bg=COLORS["bg_dark"], fg="#f87171", justify="left").pack(anchor="w", pady=(0, 10))

        if plugin_installed:
            tk.Frame(content, height=1, bg=COLORS["border"]).pack(fill="x", pady=(10, 10))
            tk.Label(content, text="配置飞书应用（需要 App ID 和 Secret）", font=("Segoe UI", 10, "bold"), bg=COLORS["bg_dark"], fg=COLORS["text"]).pack(anchor="w", pady=(0, 3))
            tk.Label(content, text="1. 打开 open.feishu.cn/app\n2. 创建或选择应用\n3. 复制 App ID 和 Secret", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"], justify="left").pack(anchor="w", pady=(0, 8))

            tk.Button(content, text="🔗 打开飞书开放平台", font=("Segoe UI", 9), command=lambda: webbrowser.open("https://open.feishu.cn/app"), bg=COLORS["bg_card"], fg=COLORS["accent"], relief="flat", cursor="hand2").pack(anchor="w", pady=(0, 10))

            tk.Label(content, text="App ID", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
            appid_entry = tk.Entry(content, font=("Segoe UI", 10), bg=COLORS["bg_card"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat")
            appid_entry.pack(fill="x", pady=(3, 8), ipady=4)
            if current_appid:
                appid_entry.insert(0, current_appid)

            tk.Label(content, text="App Secret", font=("Segoe UI", 9), bg=COLORS["bg_dark"], fg=COLORS["text_muted"]).pack(anchor="w")
            secret_entry = tk.Entry(content, font=("Segoe UI", 10), bg=COLORS["bg_card"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", show="●")
            secret_entry.pack(fill="x", pady=(3, 10), ipady=4)

            def save_feishu_config():
                aid, sec = appid_entry.get().strip(), secret_entry.get().strip()
                if not aid or not sec:
                    return messagebox.showerror("错误", "请输入 App ID 和 App Secret", parent=w)

                config_path = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")
                try:
                    import json
                    config = {}
                    if os.path.exists(config_path):
                        with open(config_path, "r", encoding="utf-8") as f:
                            config = json.load(f)

                    if "channels" not in config:
                        config["channels"] = {}
                    config["channels"]["feishu"] = {
                        "enabled": True,
                        "appId": aid,
                        "appSecret": sec,
                        "domain": "feishu",
                        "connectionMode": "websocket",
                        "requireMention": True,
                        "dmPolicy": "open",
                        "groupPolicy": "open",
                        "streaming": True
                    }

                    if "plugins" not in config:
                        config["plugins"] = {}
                    config["plugins"]["allow"] = ["openclaw-lark"]
                    if "entries" not in config["plugins"]:
                        config["plugins"]["entries"] = {}
                    config["plugins"]["entries"]["openclaw-lark"] = {"enabled": True}

                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)

                    messagebox.showinfo("成功", f"飞书配置已保存！\n\nApp ID: {aid}\n\n请启动/重启 OpenClaw 使配置生效。", parent=w)
                    w.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"保存配置失败：\n{e}", parent=w)

            tk.Button(content, text="✓ 保存", font=("Segoe UI", 10, "bold"), command=save_feishu_config, bg=COLORS["accent"], fg="white", relief="flat", cursor="hand2", width=10, height=1).pack(side="left")
            tk.Button(content, text="取消", font=("Segoe UI", 10), command=w.destroy, bg=COLORS["bg_card"], fg=COLORS["text"], relief="flat", cursor="hand2", width=10, height=1).pack(side="left", padx=(8, 0))

    def bind_weixin(self):
        """微信扫码绑定 - 检测并自动安装"""
        try:
            # 检测插件是否已安装
            plugin_path = os.path.join(self.base_path, "data", ".openclaw", "extensions", "openclaw-weixin")
            plugin_installed = os.path.exists(plugin_path) and os.path.exists(os.path.join(plugin_path, "package.json"))

            node_exe = os.path.join(self.node_path, "node.exe")
            if not os.path.exists(node_exe):
                return messagebox.showerror("错误", f"找不到 Node.js：\n{node_exe}")

            openclaw_mjs = os.path.join(self.base_path, "node_modules", "openclaw", "openclaw.mjs")
            if not os.path.exists(openclaw_mjs):
                return messagebox.showerror("错误", f"找不到 OpenClaw：\n{openclaw_mjs}")

            env = os.environ.copy()
            env["OPENCLAW_STATE_DIR"] = os.path.join(self.base_path, "data", ".openclaw")
            env["OPENCLAW_CONFIG_PATH"] = os.path.join(self.base_path, "data", ".openclaw", "openclaw.json")

            if plugin_installed:
                # 已安装，直接登录
                self.append_log("[微信] 插件已安装，启动登录流程...\n")
                subprocess.Popen(
                    ["cmd", "/k", node_exe, openclaw_mjs, "channels", "login", "--channel", "openclaw-weixin"],
                    env=env, cwd=self.base_path,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # 未安装，询问用户
                self.append_log("[微信] 插件未安装\n")
                result = messagebox.askyesno("微信绑定", "微信插件未安装，是否现在安装？\n\n安装需要几秒钟时间。")
                if result:
                    self.append_log("[微信] 正在安装插件...\n")
                    # 安装 + 启用 + 登录（一条命令链）
                    subprocess.Popen(
                        ["cmd", "/k",
                         node_exe, openclaw_mjs, "plugins", "install", "@tencent-weixin/openclaw-weixin",
                         "&", node_exe, openclaw_mjs, "config", "set", "plugins.entries.openclaw-weixin.enabled", "true",
                         "&", node_exe, openclaw_mjs, "channels", "login", "--channel", "openclaw-weixin"],
                        env=env, cwd=self.base_path,
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
        except Exception as e:
            self.append_log(f"[微信错误] {str(e)}\n")

    def _find_pnpm_cli(self):
        """查找 pnpm.cjs 路径"""
        candidates = [
            os.path.join(self.node_path, "node_modules", "pnpm", "bin", "pnpm.cjs"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]

    def _get_current_version(self):
        """获取当前 OpenClaw 版本"""
        package_json = os.path.join(self.base_path, "node_modules", "openclaw", "package.json")
        if os.path.exists(package_json):
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("version", "未知")
            except:
                pass
        return "未知"

    def _get_latest_version(self):
        """获取最新版本号（通过 pnpm view）"""
        try:
            node_exe = os.path.join(self.node_path, "node.exe")
            pnpm_cli = self._find_pnpm_cli()

            if not os.path.exists(node_exe):
                return None, "找不到 Node.js"

            if not os.path.exists(pnpm_cli):
                return None, "找不到 pnpm"

            result = subprocess.run(
                [node_exe, pnpm_cli, "view", "openclaw", "version"],
                capture_output=True, text=True,
                cwd=self.base_path,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=30
            )

            if result.returncode == 0:
                return result.stdout.strip(), None
            return None, result.stderr.strip() or "网络错误"
        except subprocess.TimeoutExpired:
            return None, "请求超时"
        except Exception as e:
            return None, str(e)

    def check_update(self):
        """检查并更新 OpenClaw"""
        self.append_log("\n[更新] 正在检查更新...\n")

        current = self._get_current_version()
        self.append_log(f"[更新] 当前版本: {current}\n")

        latest, error = self._get_latest_version()

        if error:
            self.append_log(f"[更新] 获取最新版本失败: {error}\n")
            messagebox.showerror("检查更新", f"获取最新版本失败：\n{error}")
            return

        self.append_log(f"[更新] 最新版本: {latest}\n")

        if current == latest:
            self.append_log("[更新] 已是最新版本！\n")
            messagebox.showinfo("检查更新", f"当前已是最新版本！\n\n当前版本: {current}")
            return

        result = messagebox.askyesno(
            "发现新版本",
            f"发现新版本！\n\n当前版本: {current}\n最新版本: {latest}\n\n是否立即更新？\n\n注意：更新过程中请勿关闭启动器。"
        )

        if result:
            self._do_update(latest)

    def _do_update(self, target_version):
        """执行更新（后台线程，避免阻塞界面）"""
        self.append_log(f"\n[更新] 开始更新到 {target_version}...\n")

        def update_thread():
            try:
                node_exe = os.path.join(self.node_path, "node.exe")
                pnpm_cli = self._find_pnpm_cli()

                if not os.path.exists(node_exe):
                    self.root.after(0, messagebox.showerror, "更新失败", "找不到 Node.js")
                    return
                if not os.path.exists(pnpm_cli):
                    self.root.after(0, messagebox.showerror, "更新失败", "找不到 pnpm")
                    return

                self.root.after(0, self.append_log, f"[更新] Node: {node_exe}\n")
                self.root.after(0, self.append_log, f"[更新] pnpm: {pnpm_cli}\n")
                self.root.after(0, self.append_log, f"[更新] 执行: pnpm add openclaw@latest\n\n")

                process = subprocess.Popen(
                    [node_exe, pnpm_cli, "add", "openclaw@latest"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding='utf-8', errors='replace',
                    cwd=self.base_path,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        self.root.after(0, self.append_log, f"  {line}")

                exit_code = process.wait()

                if exit_code == 0:
                    new_version = self._get_current_version()
                    self.root.after(0, self.append_log, f"\n[更新] 更新完成！新版本: {new_version}\n")
                    self.root.after(0, messagebox.showinfo, "更新成功", f"更新成功！\n\n新版本: {new_version}")
                else:
                    self.root.after(0, self.append_log, f"\n[更新] 更新失败，退出码: {exit_code}\n")
                    self.root.after(0, messagebox.showwarning, "更新失败", "自动更新失败，请检查网络连接后重试。")

            except Exception as e:
                self.root.after(0, self.append_log, f"\n[更新错误] {str(e)}\n")
                self.root.after(0, messagebox.showerror, "更新失败", f"更新过程中出错：\n{str(e)}")

        threading.Thread(target=update_thread, daemon=True).start()

    def open_web(self): webbrowser.open("http://127.0.0.1:18790")
    def open_readme(self): webbrowser.open("https://heang.top/docs.html")
    def run(self): self.root.mainloop()

if __name__ == "__main__":
    OpenClawLauncher().run()