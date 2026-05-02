"""API provider configuration dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from openclaw_launcher.constants import COLORS, FONTS, PROVIDERS
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.storage import read_json, write_json
from openclaw_launcher.ui.components import button, entry, field_label, label


class ApiConfigDialog:
    def __init__(self, parent: tk.Tk, paths: AppPaths, on_saved=None):
        self.parent = parent
        self.paths = paths
        self.on_saved = on_saved
        self.window = tk.Toplevel(parent)
        self.window.title("API 配置")
        self.window.geometry("400x520")
        self.window.configure(bg=COLORS["surface"])
        self.window.transient(parent)
        self.window.grab_set()
        self._center(400, 520)
        self._build()

    def _center(self, width: int, height: int) -> None:
        self.window.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.window.geometry(f"+{x}+{y}")

    def _build(self) -> None:
        content = tk.Frame(self.window, bg=COLORS["surface"])
        content.pack(fill="both", expand=True, padx=24, pady=22)

        label(content, "API 密钥配置", kind="title").pack(anchor="w")
        label(content, "连接 OpenClaw 默认模型，不会清空已有配置。", kind="small", muted=True).pack(anchor="w", pady=(4, 18))

        field_label(content, "AI 服务商").pack(anchor="w")
        self.provider_var = tk.StringVar(value="Heang AI")
        provider_combo = ttk.Combobox(content, textvariable=self.provider_var, values=list(PROVIDERS.keys()), state="readonly", style="Launcher.TCombobox", font=FONTS["small"])
        provider_combo.pack(fill="x", pady=(4, 12), ipady=5)

        field_label(content, "API URL").pack(anchor="w")
        self.url_entry = entry(content)
        self.url_entry.pack(fill="x", pady=(4, 12), ipady=7)

        field_label(content, "API 密钥").pack(anchor="w")
        self.key_entry = entry(content, show="●")
        self.key_entry.pack(fill="x", pady=(4, 8), ipady=7)

        self.show_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            content,
            text="显示密钥",
            variable=self.show_var,
            command=self._toggle_key,
            bg=COLORS["surface"],
            fg=COLORS["text_muted"],
            selectcolor=COLORS["input"],
            activebackground=COLORS["surface"],
            font=FONTS["small"],
        ).pack(anchor="w", pady=(0, 12))

        field_label(content, "模型名称（可选）").pack(anchor="w")
        self.model_entry = entry(content)
        self.model_entry.pack(fill="x", pady=(4, 18), ipady=7)

        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)
        self.provider_var.trace_add("write", lambda *_: self._on_provider_change())
        self._on_provider_change()

        actions = tk.Frame(content, bg=COLORS["surface"])
        actions.pack(fill="x", side="bottom", pady=(16, 0))
        button(actions, "保存配置", self._save, variant="primary").pack(side="left", padx=(0, 8))
        button(actions, "取消", self.window.destroy).pack(side="left")

    def _toggle_key(self) -> None:
        self.key_entry.config(show="" if self.show_var.get() else "●")

    def _on_provider_change(self, _event=None) -> None:
        provider = self.provider_var.get()
        config = PROVIDERS.get(provider, {})
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, config.get("url", ""))
        self.model_entry.delete(0, tk.END)
        models = config.get("models", [])
        if models:
            self.model_entry.insert(0, models[0])

    def _save(self) -> None:
        provider = self.provider_var.get()
        api_key = self.key_entry.get().strip()
        api_url = self.url_entry.get().strip()
        model = self.model_entry.get().strip()
        if not api_key:
            messagebox.showerror("错误", "请输入 API 密钥", parent=self.window)
            return

        profile_key = "custom" if provider == "自定义" else provider.lower().replace(" ", "_")
        auth_config = read_json(self.paths.auth_profiles, {"version": 1, "profiles": {}})
        if not isinstance(auth_config, dict):
            auth_config = {"version": 1, "profiles": {}}
        auth_config["version"] = auth_config.get("version", 1)
        auth_config.setdefault("profiles", {})[profile_key] = {"type": "token", "provider": profile_key, "token": api_key}
        write_json(self.paths.auth_profiles, auth_config)

        config = read_json(self.paths.openclaw_config, {})
        if not isinstance(config, dict):
            config = {}
        model_id = model or "default"
        model_name = model or provider
        provider_config = {
            "api": "openai-completions",
            "models": [{"id": model_id, "name": model_name, "contextWindow": 128000, "maxTokens": 4096}],
        }
        if api_url:
            provider_config["baseUrl"] = api_url
        config.setdefault("models", {}).setdefault("providers", {})[profile_key] = provider_config
        config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = f"{profile_key}/{model_id}"
        write_json(self.paths.openclaw_config, config)

        if self.on_saved:
            self.on_saved()
        self.window.destroy()
        messagebox.showinfo("成功", f"API 密钥已保存。\n服务商：{provider}\n模型：{model_name}")

