"""Feishu channel configuration dialog."""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
import webbrowser
from tkinter import messagebox

from openclaw_launcher.constants import COLORS, FEISHU_APP_URL, FONTS
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.storage import add_unique, read_json, write_json
from openclaw_launcher.ui.components import button, entry, field_label, label


class FeishuConfigDialog:
    def __init__(self, parent: tk.Tk, paths: AppPaths, append_log):
        self.parent = parent
        self.paths = paths
        self.append_log = append_log
        self.window = tk.Toplevel(parent)
        self.window.title("飞书机器人")
        self.window.geometry("430x520")
        self.window.configure(bg=COLORS["surface"])
        self.window.transient(parent)
        self.window.grab_set()
        self._center(430, 520)
        self._build()

    def _center(self, width: int, height: int) -> None:
        self.window.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.window.geometry(f"+{x}+{y}")

    def _build(self) -> None:
        content = tk.Frame(self.window, bg=COLORS["surface"])
        content.pack(fill="both", expand=True, padx=24, pady=22)

        label(content, "飞书机器人", kind="title").pack(anchor="w")
        label(content, "安装插件并写入飞书通道配置。", kind="small", muted=True).pack(anchor="w", pady=(4, 18))

        plugin_path = os.path.join(self.paths.state_dir, "extensions", "openclaw-lark")
        plugin_installed = os.path.exists(plugin_path)
        config = read_json(self.paths.openclaw_config, {})
        current_appid = config.get("channels", {}).get("feishu", {}).get("appId") if isinstance(config, dict) else None

        status = tk.Frame(content, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        status.pack(fill="x", pady=(0, 16))
        if plugin_installed and current_appid:
            status_text = f"飞书已配置\nApp ID: {current_appid}"
            status_color = COLORS["success"]
        elif plugin_installed:
            status_text = "插件已安装，尚未填写应用信息"
            status_color = COLORS["warning"]
        else:
            status_text = "飞书插件未安装"
            status_color = COLORS["warning"]
        label(status, status_text, kind="body", bg=COLORS["surface_alt"], fg=status_color, justify="left").pack(anchor="w", padx=14, pady=12)

        if not plugin_installed:
            button(content, "安装飞书插件", self._install_lark, variant="primary").pack(anchor="w")
            label(content, "安装会打开一个命令窗口显示进度，完成后重新进入此弹窗即可配置。", kind="small", muted=True).pack(anchor="w", pady=(10, 0))
            return

        label(content, "应用信息", kind="section").pack(anchor="w", pady=(2, 8))
        label(content, "在飞书开放平台创建应用后复制 App ID 和 Secret。", kind="small", muted=True).pack(anchor="w", pady=(0, 8))
        button(content, "打开飞书开放平台", lambda: webbrowser.open(FEISHU_APP_URL)).pack(anchor="w", pady=(0, 14))

        field_label(content, "App ID").pack(anchor="w")
        self.appid_entry = entry(content)
        self.appid_entry.pack(fill="x", pady=(4, 12), ipady=7)
        if current_appid:
            self.appid_entry.insert(0, current_appid)

        field_label(content, "App Secret").pack(anchor="w")
        self.secret_entry = entry(content, show="●")
        self.secret_entry.pack(fill="x", pady=(4, 18), ipady=7)

        actions = tk.Frame(content, bg=COLORS["surface"])
        actions.pack(fill="x", side="bottom", pady=(16, 0))
        button(actions, "保存配置", self._save, variant="primary").pack(side="left", padx=(0, 8))
        button(actions, "取消", self.window.destroy).pack(side="left")

    def _install_lark(self) -> None:
        self.append_log("[飞书] 正在安装飞书插件...\n")
        try:
            self._clear_old_lark_config()
            env = self.paths.process_env()
            env["NPM_CONFIG_NODE_LINKER"] = "hoisted"
            self._ensure_hoisted_npmrc()

            npx_exe = os.path.join(self.paths.node_dir, "npx.cmd") if os.path.exists(os.path.join(self.paths.node_dir, "npx.cmd")) else "npx"
            bat_path = os.path.join(self.paths.base_path, "_install_lark.bat")
            node_exe = self.paths.node_exe
            pnpm_cli = self.paths.pnpm_cli
            if os.path.exists(node_exe) and os.path.exists(pnpm_cli):
                bat_content = self._install_bat_with_update(node_exe, pnpm_cli, npx_exe)
            else:
                bat_content = self._install_bat_only(npx_exe)
            with open(bat_path, "w", encoding="utf-8") as file:
                file.write(bat_content)
            subprocess.Popen(["cmd", "/k", bat_path], env=env, cwd=self.paths.base_path, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            messagebox.showinfo("飞书插件安装", "安装命令已执行，请在弹出的终端窗口中查看进度。\n安装完成后请重新打开此窗口。", parent=self.window)
        except Exception as error:
            self.append_log(f"[飞书] 安装失败: {error}\n")
            messagebox.showerror("安装失败", str(error), parent=self.window)

    def _clear_old_lark_config(self) -> None:
        config = read_json(self.paths.openclaw_config, {})
        if not isinstance(config, dict):
            return
        plugins = config.get("plugins", {})
        changed = False
        if isinstance(plugins, dict):
            entries = plugins.get("entries", {})
            if isinstance(entries, dict) and "openclaw-lark" in entries:
                del entries["openclaw-lark"]
                changed = True
            allow = plugins.get("allow", [])
            if isinstance(allow, list) and "openclaw-lark" in allow:
                allow.remove("openclaw-lark")
                changed = True
        if changed:
            write_json(self.paths.openclaw_config, config)
            self.append_log("[飞书] 已清理旧配置残留\n")

    def _ensure_hoisted_npmrc(self) -> None:
        npmrc_path = os.path.join(self.paths.base_path, ".npmrc")
        try:
            if os.path.exists(npmrc_path):
                with open(npmrc_path, "r", encoding="utf-8") as file:
                    if "node-linker" in file.read():
                        return
            with open(npmrc_path, "a", encoding="utf-8") as file:
                file.write("\nnode-linker=hoisted\n")
        except OSError:
            pass

    def _install_bat_with_update(self, node_exe: str, pnpm_cli: str, npx_exe: str) -> str:
        return f"""@echo off
chcp 65001 >nul
echo [1/2] Updating OpenClaw...
"{node_exe}" "{pnpm_cli}" add openclaw@latest
echo.
echo [2/2] Installing Lark Plugin...
"{npx_exe}" -y @larksuite/openclaw-lark install
{self._copy_peer_dependency_bat()}
echo.
echo Done!
pause
"""

    def _install_bat_only(self, npx_exe: str) -> str:
        return f"""@echo off
chcp 65001 >nul
echo Installing Lark Plugin...
"{npx_exe}" -y @larksuite/openclaw-lark install
{self._copy_peer_dependency_bat()}
echo.
echo Done!
pause
"""

    def _copy_peer_dependency_bat(self) -> str:
        return """echo.
echo Fixing symlink issue for exFAT...
if exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark" (
  if not exist "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" (
    mkdir "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" 2>nul
    xcopy "%~dp0node_modules\\openclaw" "%~dp0data\\.openclaw\\extensions\\openclaw-lark\\node_modules\\openclaw" /E /Y /Q >nul
    echo   Copied openclaw peerDependency.
  ) else (
    echo   Already exists, skipping.
  )
)
"""

    def _save(self) -> None:
        app_id = self.appid_entry.get().strip()
        secret = self.secret_entry.get().strip()
        if not app_id or not secret:
            messagebox.showerror("错误", "请输入 App ID 和 App Secret", parent=self.window)
            return
        config = read_json(self.paths.openclaw_config, {})
        if not isinstance(config, dict):
            config = {}
        config.setdefault("channels", {})["feishu"] = {
            "enabled": True,
            "appId": app_id,
            "appSecret": secret,
            "domain": "feishu",
            "connectionMode": "websocket",
            "requireMention": True,
            "dmPolicy": "open",
            "groupPolicy": "open",
            "streaming": True,
        }
        plugins = config.setdefault("plugins", {})
        allow = plugins.get("allow", [])
        if not isinstance(allow, list):
            allow = []
        plugins["allow"] = add_unique(allow, "openclaw-lark")
        plugins.setdefault("entries", {})["openclaw-lark"] = {"enabled": True}
        write_json(self.paths.openclaw_config, config)
        self.window.destroy()
        messagebox.showinfo("成功", f"飞书配置已保存。\nApp ID: {app_id}", parent=self.parent)

