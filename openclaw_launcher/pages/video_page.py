"""AI video generation page."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from openclaw_launcher.constants import COLORS, FONTS
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.services.video_api import DashScopeVideoClient, VideoApiError
from openclaw_launcher.storage import read_json, write_json
from openclaw_launcher.ui.components import button, entry, field_label, label, text_area


class VideoPage:
    name = "video"

    def __init__(self, parent: tk.Misc, root: tk.Tk, paths: AppPaths, append_log):
        self.root = root
        self.paths = paths
        self.append_log = append_log
        self.client = DashScopeVideoClient()
        self.frame = tk.Frame(parent, bg=COLORS["surface"])
        self.i2v_image_path: str | None = None
        self._vid_data: bytes | None = None
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self.frame, bg=COLORS["surface"], height=74)
        header.pack(fill="x")
        header.pack_propagate(False)
        label(header, "AI 视频", kind="title").pack(side="left", padx=24, pady=(17, 0), anchor="n")
        label(header, "文生视频与图生视频", kind="small", muted=True).pack(side="left", padx=(8, 0), pady=(25, 0), anchor="n")

        content = tk.Frame(self.frame, bg=COLORS["surface"])
        content.pack(fill="both", expand=True, padx=24, pady=(0, 22))
        saved = read_json(self.paths.video_config, {})

        form = tk.Frame(content, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        form.pack(fill="x", pady=(0, 14))
        form_inner = tk.Frame(form, bg=COLORS["surface_alt"])
        form_inner.pack(fill="x", padx=16, pady=14)

        field_label(form_inner, "DashScope API Key", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.key_entry = entry(form_inner, show="●")
        self.key_entry.pack(fill="x", pady=(4, 8), ipady=6)
        if saved.get("dashKey"):
            self.key_entry.insert(0, saved["dashKey"])

        self.show_key_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form_inner,
            text="显示密钥",
            variable=self.show_key_var,
            command=self._toggle_key,
            bg=COLORS["surface_alt"],
            fg=COLORS["text_muted"],
            selectcolor=COLORS["input"],
            activebackground=COLORS["surface_alt"],
            font=FONTS["small"],
        ).pack(anchor="w", pady=(0, 10))

        self.mode_var = tk.StringVar(value="t2v")
        mode_row = tk.Frame(form_inner, bg=COLORS["surface_alt"])
        mode_row.pack(fill="x", pady=(0, 10))
        self.t2v_btn = button(mode_row, "文生视频", lambda: self._switch_mode("t2v"), variant="primary")
        self.i2v_btn = button(mode_row, "图生视频", lambda: self._switch_mode("i2v"))
        self.t2v_btn.pack(side="left", padx=(0, 8))
        self.i2v_btn.pack(side="left")

        self.i2v_row = tk.Frame(form_inner, bg=COLORS["surface_alt"])
        self.upload_btn = button(self.i2v_row, "上传参考图", self._pick_image)
        self.upload_btn.pack(side="left", padx=(0, 8))
        self.upload_info = label(self.i2v_row, "", kind="small", bg=COLORS["surface_alt"], fg=COLORS["success"])
        self.upload_info.pack(side="left")
        self.upload_clear = button(self.i2v_row, "清除", self._clear_image)

        opt_row = tk.Frame(form_inner, bg=COLORS["surface_alt"])
        opt_row.pack(fill="x", pady=(0, 10))
        field_label(opt_row, "分辨率", bg=COLORS["surface_alt"]).pack(side="left", padx=(0, 8))
        self.res_var = tk.StringVar(value="720P")
        ttk.Combobox(opt_row, textvariable=self.res_var, values=["720P", "1080P"], state="readonly", style="Launcher.TCombobox", font=FONTS["small"], width=8).pack(side="left", padx=(0, 14))
        field_label(opt_row, "时长", bg=COLORS["surface_alt"]).pack(side="left", padx=(0, 8))
        self.dur_var = tk.StringVar(value="5")
        ttk.Combobox(opt_row, textvariable=self.dur_var, values=["5", "10"], state="readonly", style="Launcher.TCombobox", font=FONTS["small"], width=5).pack(side="left", padx=(0, 14))
        field_label(opt_row, "比例", bg=COLORS["surface_alt"]).pack(side="left", padx=(0, 8))
        self.ratio_var = tk.StringVar(value="16:9")
        ttk.Combobox(opt_row, textvariable=self.ratio_var, values=["16:9", "9:16", "1:1", "4:3", "3:4"], state="readonly", style="Launcher.TCombobox", font=FONTS["small"], width=8).pack(side="left")

        field_label(form_inner, "提示词", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.prompt_text = text_area(form_inner, height=3)
        self.prompt_text.pack(fill="x", pady=(4, 0))

        action_row = tk.Frame(content, bg=COLORS["surface"])
        action_row.pack(fill="x", pady=(0, 12))
        self.generate_btn = button(action_row, "生成视频", self._generate, variant="primary")
        self.generate_btn.pack(side="left", padx=(0, 12))
        self.status_label = label(action_row, "", kind="small")
        self.status_label.pack(side="left", pady=8)

        self.preview = tk.Frame(content, bg=COLORS["input"], highlightbackground=COLORS["border"], highlightthickness=1)
        self.preview.pack(fill="both", expand=True)
        self.preview.pack_propagate(False)
        label(self.preview, "生成结果会显示在这里\n完成后可保存或调用系统播放器预览", kind="body", muted=True, bg=COLORS["input"], justify="center").pack(expand=True)

    def _toggle_key(self) -> None:
        self.key_entry.config(show="" if self.show_key_var.get() else "●")

    def _switch_mode(self, mode: str) -> None:
        self.mode_var.set(mode)
        if mode == "t2v":
            self.t2v_btn.config(bg=COLORS["accent"], fg="white")
            self.i2v_btn.config(bg=COLORS["input"], fg=COLORS["text"])
            self.i2v_row.pack_forget()
        else:
            self.i2v_btn.config(bg=COLORS["accent"], fg="white")
            self.t2v_btn.config(bg=COLORS["input"], fg=COLORS["text"])
            self.i2v_row.pack(fill="x", pady=(0, 10))

    def _pick_image(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择参考图")
        if not path:
            return
        self.i2v_image_path = path
        self.upload_info.config(text=os.path.basename(path))
        self.upload_clear.pack(side="left", padx=(8, 0))

    def _clear_image(self) -> None:
        self.i2v_image_path = None
        self.upload_info.config(text="")
        self.upload_clear.pack_forget()

    def _set_status(self, text: str, kind: str = "accent") -> None:
        self.status_label.config(text=text, fg=COLORS.get(kind, COLORS["accent"]))

    def _save_config(self) -> None:
        write_json(self.paths.video_config, {"dashKey": self.key_entry.get().strip()})

    def _generate(self) -> None:
        dash_key = self.key_entry.get().strip()
        prompt = self.prompt_text.get("1.0", "end-1c").strip()
        mode = self.mode_var.get()
        if not dash_key:
            messagebox.showerror("错误", "请输入 DashScope API Key")
            return
        if not prompt:
            messagebox.showerror("错误", "请输入提示词")
            return
        if mode == "i2v" and not self.i2v_image_path:
            messagebox.showerror("错误", "图生视频需要上传参考图")
            return

        self._save_config()
        self.generate_btn.config(state="disabled", text="提交中...")
        self._set_status("正在提交任务...")

        def status_from_thread(text: str, kind: str) -> None:
            self.root.after(0, self._set_status, text, kind)

        def worker() -> None:
            try:
                video_bytes = self.client.generate(
                    dash_key,
                    prompt,
                    mode,
                    self.res_var.get(),
                    int(self.dur_var.get()),
                    self.ratio_var.get(),
                    self.i2v_image_path,
                    status_from_thread,
                )
                self.root.after(0, self._show_result, video_bytes)
            except VideoApiError as error:
                message = str(error)
                self.append_log(f"[AI视频] {message}\n")
                self.root.after(0, self._set_status, f"失败：{message}", "danger")
            finally:
                self.root.after(0, lambda: self.generate_btn.config(state="normal", text="生成视频"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, video_bytes: bytes) -> None:
        self._vid_data = video_bytes
        for widget in self.preview.winfo_children():
            widget.destroy()
        body = tk.Frame(self.preview, bg=COLORS["input"])
        body.pack(expand=True)
        label(body, "视频生成成功", kind="title", bg=COLORS["input"], fg=COLORS["success"]).pack(pady=(8, 4))
        label(body, f"大小：{len(video_bytes) // 1024 // 1024} MB", kind="small", muted=True, bg=COLORS["input"]).pack()

        footer = tk.Frame(self.preview, bg=COLORS["surface"], height=42)
        footer.pack(fill="x", side="bottom")
        button(footer, "保存视频", self._save_video, variant="primary").pack(side="left", padx=10, pady=6)
        button(footer, "播放视频", self._play_video, variant="success").pack(side="left", padx=4, pady=6)
        self._set_status("生成成功", "success")

    def _save_video(self) -> None:
        if not self._vid_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 视频", "*.mp4")], initialfile=f"video-{int(time.time())}.mp4", parent=self.root)
        if not path:
            return
        with open(path, "wb") as file:
            file.write(self._vid_data)
        self._set_status(f"已保存：{os.path.basename(path)}", "success")

    def _play_video(self) -> None:
        if not self._vid_data:
            return
        path = os.path.join(tempfile.gettempdir(), f"openclaw_video_{int(time.time())}.mp4")
        with open(path, "wb") as file:
            file.write(self._vid_data)
        os.startfile(path)

