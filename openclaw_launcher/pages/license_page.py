"""License activation page."""

from __future__ import annotations

import threading
import tkinter as tk

from openclaw_launcher.constants import BRAND, COLORS, FONTS
from openclaw_launcher.license_manager import LicenseError, LicenseManager
from openclaw_launcher.ui.components import button, entry, label


class LicensePage:
    name = "license"

    def __init__(self, parent: tk.Misc, root: tk.Tk, manager: LicenseManager, on_activated):
        self.root = root
        self.manager = manager
        self.on_activated = on_activated
        self.frame = tk.Frame(parent, bg=COLORS["surface"])
        self._build()
        self.refresh()

    def _build(self) -> None:
        wrap = tk.Frame(self.frame, bg=COLORS["surface"])
        wrap.pack(fill="both", expand=True, padx=44, pady=44)

        label(wrap, "授权管理", kind="title").pack(anchor="w")
        label(wrap, "输入授权码后解锁启动服务、AI 生图、AI 视频和广告视频工作台。", kind="body", muted=True).pack(anchor="w", pady=(8, 26))

        card = tk.Frame(wrap, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=COLORS["surface_alt"])
        inner.pack(fill="x", padx=22, pady=20)

        self.state_label = label(inner, "", kind="section", bg=COLORS["surface_alt"])
        self.state_label.pack(anchor="w", pady=(0, 10))

        tk.Label(inner, text="授权码", font=FONTS["small"], bg=COLORS["surface_alt"], fg=COLORS["text_muted"]).pack(anchor="w")
        self.code_input_shell = tk.Frame(
            inner,
            bg=COLORS["code_input_bg"],
            highlightbackground=COLORS["accent"],
            highlightcolor=COLORS["accent"],
            highlightthickness=2,
        )
        self.code_input_shell.pack(fill="x", pady=(7, 6))
        self.code_entry = entry(
            self.code_input_shell,
            bg=COLORS["code_input_bg"],
            font=FONTS["license_code"],
            insertbackground=COLORS["accent"],
            borderwidth=0,
        )
        self.code_entry.pack(fill="x", padx=14, pady=11, ipady=2)
        self.code_entry.bind("<FocusIn>", lambda _event: self._set_code_focus(True))
        self.code_entry.bind("<FocusOut>", lambda _event: self._set_code_focus(False))
        label(
            inner,
            "格式示例：OC-PRO-XXXX-XXXX-XXXX-XXXX",
            kind="small",
            bg=COLORS["surface_alt"],
            fg=COLORS["accent_ink"],
        ).pack(anchor="w", pady=(0, 13))

        action = tk.Frame(inner, bg=COLORS["surface_alt"])
        action.pack(fill="x")
        self.activate_btn = button(action, "在线激活", self.activate, variant="primary")
        self.activate_btn.pack(side="left", padx=(0, 10))
        button(action, "刷新状态", self.refresh).pack(side="left")

        self.info_label = label(inner, "", kind="small", muted=True, bg=COLORS["surface_alt"], justify="left")
        self.info_label.pack(anchor="w", pady=(16, 0))

        install = tk.Frame(wrap, bg=COLORS["surface"])
        install.pack(fill="x", pady=(18, 0))
        label(install, f"安装 ID：{self.manager.get_install_id()}", kind="small", muted=True).pack(anchor="w")

    def _set_code_focus(self, focused: bool) -> None:
        if focused:
            self.code_input_shell.config(highlightbackground=COLORS["warning"], highlightcolor=COLORS["warning"])
        else:
            self.code_input_shell.config(highlightbackground=COLORS["accent"], highlightcolor=COLORS["accent"])

    def refresh(self) -> None:
        license_data = self.manager.current_license()
        if license_data:
            self.state_label.config(text="已授权", fg=COLORS["success"])
            features = " / ".join(license_data.get("features", []))
            self.info_label.config(
                text=f"客户：{license_data.get('licensee', '未命名')}\n版本：{license_data.get('edition', 'pro')}\n到期：{license_data.get('expires', '永久')}\n功能：{features}",
                fg=COLORS["text_muted"],
            )
            self.activate_btn.config(text="重新激活")
        else:
            self.state_label.config(text="未授权", fg=COLORS["danger"])
            self.info_label.config(text="未授权状态下只能打开授权页、配置页和帮助文档。", fg=COLORS["text_muted"])
            self.activate_btn.config(text="在线激活")

    def activate(self) -> None:
        code = self.code_entry.get().strip()
        self.activate_btn.config(state="disabled", text="激活中...")
        self.info_label.config(text="正在连接授权服务器...", fg=COLORS["accent"])

        def worker() -> None:
            try:
                license_data = self.manager.activate(code)
                self.root.after(0, self._activated, license_data)
            except LicenseError as error:
                self.root.after(0, self._failed, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _activated(self, license_data: dict) -> None:
        self.activate_btn.config(state="normal")
        self.refresh()
        self.info_label.config(text=f"激活成功：{license_data.get('licensee', '客户')}", fg=COLORS["success"])
        self.on_activated()

    def _failed(self, message: str) -> None:
        self.activate_btn.config(state="normal", text="在线激活")
        self.info_label.config(text=message, fg=COLORS["danger"])
