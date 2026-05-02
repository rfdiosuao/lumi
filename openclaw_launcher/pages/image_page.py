"""AI image generation page."""

from __future__ import annotations

import io
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from openclaw_launcher.constants import COLORS, FONTS, IMAGE_TRIPLE_TEMPLATES
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.services.image_api import ImageApiClient, ImageApiError
from openclaw_launcher.storage import read_json, write_json
from openclaw_launcher.ui.components import button, entry, field_label, label, text_area


class ImagePage:
    name = "image"

    def __init__(self, parent: tk.Misc, root: tk.Tk, paths: AppPaths, append_log):
        self.root = root
        self.paths = paths
        self.append_log = append_log
        self.client = ImageApiClient()
        self.frame = tk.Frame(parent, bg=COLORS["surface"])
        self.edit_image_path: str | None = None
        self._img_data: bytes | None = None
        self._img_photo: ImageTk.PhotoImage | None = None
        # triple generation state
        self._triple_generating = False
        self._triple_results: list[bytes | None] = [None, None, None]
        self._triple_photos: list[ImageTk.PhotoImage | None] = [None, None, None]
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self.frame, bg=COLORS["surface"], height=74)
        header.pack(fill="x")
        header.pack_propagate(False)
        label(header, "AI 生图", kind="title").pack(side="left", padx=24, pady=(17, 0), anchor="n")
        label(header, "生成或编辑图片", kind="small", muted=True).pack(side="left", padx=(8, 0), pady=(25, 0), anchor="n")

        content = tk.Frame(self.frame, bg=COLORS["surface"])
        content.pack(fill="both", expand=True, padx=24, pady=(0, 22))

        saved = read_json(self.paths.image_config, {})

        form = tk.Frame(content, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        form.pack(fill="x", pady=(0, 14))
        form_inner = tk.Frame(form, bg=COLORS["surface_alt"])
        form_inner.pack(fill="x", padx=16, pady=14)

        top_row = tk.Frame(form_inner, bg=COLORS["surface_alt"])
        top_row.pack(fill="x")
        url_col = tk.Frame(top_row, bg=COLORS["surface_alt"])
        url_col.pack(side="left", fill="x", expand=True, padx=(0, 10))
        key_col = tk.Frame(top_row, bg=COLORS["surface_alt"])
        key_col.pack(side="left", fill="x", expand=True)

        field_label(url_col, "中转站地址", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.url_entry = entry(url_col)
        self.url_entry.pack(fill="x", pady=(4, 0), ipady=6)
        if saved.get("baseUrl"):
            self.url_entry.insert(0, saved["baseUrl"])

        field_label(key_col, "API Key", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.key_entry = entry(key_col, show="●")
        self.key_entry.pack(fill="x", pady=(4, 0), ipady=6)
        if saved.get("apiKey"):
            self.key_entry.insert(0, saved["apiKey"])

        opt_row = tk.Frame(form_inner, bg=COLORS["surface_alt"])
        opt_row.pack(fill="x", pady=(12, 0))
        field_label(opt_row, "尺寸", bg=COLORS["surface_alt"]).pack(side="left", padx=(0, 8))
        self.size_var = tk.StringVar(value="1024x1024")
        ttk.Combobox(
            opt_row,
            textvariable=self.size_var,
            values=["1024x1024", "1024x1536", "1536x1024", "512x512"],
            state="readonly",
            style="Launcher.TCombobox",
            font=FONTS["small"],
            width=13,
        ).pack(side="left", padx=(0, 12))
        self.upload_btn = button(opt_row, "上传原图", self._pick_image)
        self.upload_btn.pack(side="left", padx=(0, 8))
        self.upload_info = label(opt_row, "", kind="small", bg=COLORS["surface_alt"], fg=COLORS["success"])
        self.upload_info.pack(side="left")
        self.upload_clear = button(opt_row, "清除", self._clear_image)

        field_label(form_inner, "提示词", bg=COLORS["surface_alt"]).pack(anchor="w", pady=(12, 0))
        self.prompt_text = text_area(form_inner, height=3)
        self.prompt_text.pack(fill="x", pady=(4, 0))

        action_row = tk.Frame(content, bg=COLORS["surface"])
        action_row.pack(fill="x", pady=(0, 12))
        self.generate_btn = button(action_row, "生成图片", self._generate, variant="primary")
        self.generate_btn.pack(side="left", padx=(0, 8))
        self.triple_btn = button(action_row, "一键三图", self._triple_generate, variant="success")
        self.triple_btn.pack(side="left", padx=(0, 12))
        self.status_label = label(action_row, "", kind="small")
        self.status_label.pack(side="left", pady=8)

        self.preview = tk.Frame(content, bg=COLORS["input"], highlightbackground=COLORS["border"], highlightthickness=1)
        self.preview.pack(fill="both", expand=True)
        self.preview.pack_propagate(False)
        label(self.preview, "生成结果会显示在这里\n点击图片可放大查看", kind="body", muted=True, bg=COLORS["input"], justify="center").pack(expand=True)

        # triple generation result area (hidden by default)
        self._triple_frame = tk.Frame(content, bg=COLORS["surface"])
        self._triple_frame.pack_forget()
        self._triple_cards: list[dict] = []
        self._build_triple_results_area()

    def _pick_image(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择原图")
        if not path:
            return
        self.edit_image_path = path
        self.upload_info.config(text=os.path.basename(path))
        self.upload_clear.pack(side="left", padx=(8, 0))
        self.generate_btn.config(text="编辑图片")

    def _clear_image(self) -> None:
        self.edit_image_path = None
        self.upload_info.config(text="")
        self.upload_clear.pack_forget()
        self.generate_btn.config(text="生成图片")

    def _save_config(self) -> None:
        write_json(self.paths.image_config, {"baseUrl": self.url_entry.get().strip().rstrip("/"), "apiKey": self.key_entry.get().strip()})

    def _set_status(self, text: str, kind: str = "accent") -> None:
        self.status_label.config(text=text, fg=COLORS.get(kind, COLORS["accent"]))

    def _generate(self) -> None:
        base_url = self.url_entry.get().strip().rstrip("/")
        api_key = self.key_entry.get().strip()
        prompt = self.prompt_text.get("1.0", "end-1c").strip()
        if not base_url:
            messagebox.showerror("错误", "请输入中转站地址")
            return
        if not prompt:
            messagebox.showerror("错误", "请输入提示词")
            return

        self._save_config()
        is_edit = self.edit_image_path is not None
        self._set_triple_button_state("disabled")
        self._set_status("正在编辑..." if is_edit else "正在生成，请稍候...")

        def worker() -> None:
            try:
                image_bytes = self.client.generate(base_url, api_key, prompt, self.size_var.get(), edit_image_path=self.edit_image_path)
                self.root.after(0, self._show_result, image_bytes)
            except ImageApiError as error:
                message = str(error)
                self.append_log(f"[AI生图] {message}\n")
                self.root.after(0, self._set_status, f"失败：{message}", "danger")
            finally:
                self.root.after(0, lambda: (self.generate_btn.config(state="normal", text="编辑图片" if is_edit else "生成图片"), self.triple_btn.config(state="normal")))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, image_bytes: bytes) -> None:
        self._img_data = image_bytes
        image = Image.open(io.BytesIO(image_bytes))
        max_width = max(self.preview.winfo_width() - 28, 400)
        max_height = max(self.preview.winfo_height() - 64, 240)
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        self._img_photo = ImageTk.PhotoImage(image)

        for widget in self.preview.winfo_children():
            widget.destroy()
        image_label = tk.Label(self.preview, image=self._img_photo, bg=COLORS["input"], cursor="hand2")
        image_label.pack(expand=True, pady=(8, 0))
        image_label.bind("<Button-1>", lambda _event: self._open_viewer(image_bytes))

        footer = tk.Frame(self.preview, bg=COLORS["surface"], height=42)
        footer.pack(fill="x", side="bottom")
        button(footer, "保存图片", self._save_image, variant="primary").pack(side="left", padx=10, pady=6)
        label(footer, "点击图片放大查看", kind="small", muted=True).pack(side="left", padx=8)
        self._set_status("生成成功", "success")

    def _save_image(self) -> None:
        if not self._img_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")], initialfile=f"image-{int(time.time())}.png", parent=self.root)
        if not path:
            return
        with open(path, "wb") as file:
            file.write(self._img_data)
        self._set_status(f"已保存：{os.path.basename(path)}", "success")

    def _open_viewer(self, image_bytes: bytes) -> None:
        viewer = tk.Toplevel(self.root)
        viewer.title("图片预览")
        viewer.configure(bg=COLORS["viewer_bg"])
        viewer.attributes("-topmost", True)
        viewer.state("zoomed")

        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((viewer.winfo_screenwidth() - 40, viewer.winfo_screenheight() - 90), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)

        top = tk.Frame(viewer, bg=COLORS["viewer_bar_bg"], height=44)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="图片预览", font=FONTS["section"], bg=COLORS["viewer_bar_bg"], fg="white").pack(side="left", padx=16)
        button(top, "保存", lambda: self._save_viewer_image(viewer, image_bytes), variant="primary").pack(side="right", padx=(4, 12), pady=6)
        button(top, "关闭", viewer.destroy).pack(side="right", padx=4, pady=6)

        image_label = tk.Label(viewer, image=photo, bg=COLORS["viewer_bg"])
        image_label.image = photo
        image_label.pack(expand=True)
        viewer.bind("<Escape>", lambda _event: viewer.destroy())

    def _save_viewer_image(self, viewer: tk.Toplevel, image_bytes: bytes) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")], initialfile=f"image-{int(time.time())}.png", parent=viewer)
        if path:
            with open(path, "wb") as file:
                file.write(image_bytes)

    # ─── Triple Generation (一键三图) ───

    def _build_triple_results_area(self) -> None:
        """Build the 1×3 horizontal result display area (hidden by default)."""
        cards_frame = tk.Frame(self._triple_frame, bg=COLORS["surface"])
        cards_frame.pack(fill="both", expand=True, padx=4, pady=(0, 12))

        self._triple_cards = []
        for idx, (tpl_name, _tpl_prompt) in enumerate(IMAGE_TRIPLE_TEMPLATES):
            card = tk.Frame(cards_frame, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=6, pady=4)

            # title
            title = label(card, tpl_name, kind="section", bg=COLORS["surface_alt"])
            title.pack(pady=(10, 6))

            # image canvas area
            img_container = tk.Frame(card, bg=COLORS["input"], highlightbackground=COLORS["border_strong"], highlightthickness=1)
            img_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            img_container.pack_propagate(False)
            img_container.config(height=180)

            placeholder = label(img_container, "等待生成", kind="small", muted=True, bg=COLORS["input"])
            placeholder.pack(expand=True)

            # status label
            status = label(card, "", kind="small", bg=COLORS["surface_alt"])
            status.pack(pady=(0, 8))

            # save button (hidden initially)
            save_btn = button(card, "保存", lambda i=idx: self._save_triple_image(i), variant="primary")
            save_btn.pack(pady=(0, 10))
            save_btn.pack_forget()

            self._triple_cards.append({
                "frame": card,
                "img_container": img_container,
                "placeholder": placeholder,
                "status": status,
                "save_btn": save_btn,
            })

        # triple status bar
        self._triple_status = label(self._triple_frame, "", kind="small")
        self._triple_status.pack(pady=(0, 12))

        # back to single button
        button(self._triple_frame, "← 返回单图模式", self._hide_triple_mode, variant="quiet").pack(side="left", padx=10, pady=(0, 12))

    def _show_triple_mode(self) -> None:
        self.preview.pack_forget()
        self._triple_frame.pack(fill="both", expand=True)

    def _hide_triple_mode(self) -> None:
        self._triple_frame.pack_forget()
        self.preview.pack(fill="both", expand=True)

    def _set_triple_button_state(self, state: str) -> None:
        self.generate_btn.config(state=state)
        self.triple_btn.config(state=state)

    def _triple_generate(self) -> None:
        base_url = self.url_entry.get().strip().rstrip("/")
        api_key = self.key_entry.get().strip()
        user_prompt = self.prompt_text.get("1.0", "end-1c").strip()
        if not base_url:
            messagebox.showerror("错误", "请输入中转站地址")
            return
        if not user_prompt:
            messagebox.showerror("错误", "请输入提示词")
            return

        self._save_config()
        self._set_triple_button_state("disabled")
        self._show_triple_mode()

        # reset all cards
        for card in self._triple_cards:
            for w in card["img_container"].winfo_children():
                w.destroy()
            label(card["img_container"], "等待生成", kind="small", muted=True, bg=COLORS["input"]).pack(expand=True)
            card["placeholder"] = card["img_container"].winfo_children()[0]
            card["status"].config(text="")
            card["save_btn"].pack_forget()
        self._triple_results = [None, None, None]
        self._triple_photos = [None, None, None]
        done_count = [0]
        self._triple_status.config(text="生成中: 0/3")

        # build 3 full prompts
        prompts = []
        for tpl_name, tpl_text in IMAGE_TRIPLE_TEMPLATES:
            full = f"{user_prompt}\n{tpl_text}"
            prompts.append((tpl_name, full))

        def worker() -> None:
            for idx, (_name, prompt) in enumerate(prompts):
                try:
                    result = self.client.generate(
                        base_url,
                        api_key,
                        prompt,
                        self.size_var.get(),
                    )
                    self._triple_results[idx] = result
                    self.root.after(0, self._show_triple_result, idx, result)
                except ImageApiError as err:
                    msg = str(err)
                    self.append_log(f"[AI生图-{IMAGE_TRIPLE_TEMPLATES[idx][0]}] {msg}\n")
                    self.root.after(0, self._show_triple_error, idx, msg)
                except Exception as err:
                    msg = str(err)
                    self.append_log(f"[AI生图-{IMAGE_TRIPLE_TEMPLATES[idx][0]}] {msg}\n")
                    self.root.after(0, self._show_triple_error, idx, msg)

                done_count[0] += 1
                done = done_count[0]
                success = sum(1 for r in self._triple_results if r is not None)
                if done == 3:
                    if success == 3:
                        self.root.after(0, self._set_triple_status, "生成完成: 3/3", "success")
                    elif success > 0:
                        self.root.after(0, self._set_triple_status, f"部分成功: {success}/3", "warning")
                    else:
                        self.root.after(0, self._set_triple_status, "生成失败", "danger")
                else:
                    self.root.after(0, self._set_triple_status, f"生成中: {done}/3", "accent")
                if done == 3:
                    self.root.after(0, self._set_triple_button_state, "normal")

        threading.Thread(target=worker, daemon=True).start()

    def _show_triple_result(self, idx: int, image_bytes: bytes) -> None:
        self._triple_results[idx] = image_bytes
        card = self._triple_cards[idx]

        for w in card["img_container"].winfo_children():
            w.destroy()

        image = Image.open(io.BytesIO(image_bytes))
        container_w = card["img_container"].winfo_width() or 280
        container_h = card["img_container"].winfo_height() or 180
        max_w = max(container_w - 16, 100)
        max_h = max(container_h - 16, 80)
        image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self._triple_photos[idx] = photo

        img_label = tk.Label(card["img_container"], image=photo, bg=COLORS["input"], cursor="hand2")
        img_label.pack(expand=True, pady=4)
        img_label.bind("<Button-1>", lambda _event, ib=image_bytes: self._open_viewer(ib))

        card["status"].config(text="生成成功", fg=COLORS["success"])
        card["save_btn"].pack(pady=(0, 10))

    def _show_triple_error(self, idx: int, message: str) -> None:
        card = self._triple_cards[idx]
        for w in card["img_container"].winfo_children():
            w.destroy()
        label(card["img_container"], f"失败", kind="small", bg=COLORS["input"], fg=COLORS["danger"]).pack(expand=True)
        card["status"].config(text=message, fg=COLORS["danger"])

    def _set_triple_status(self, text: str, kind: str = "accent") -> None:
        self._triple_status.config(text=text, fg=COLORS.get(kind, COLORS["accent"]))

    def _save_triple_image(self, idx: int) -> None:
        data = self._triple_results[idx]
        if not data:
            return
        tpl_name = IMAGE_TRIPLE_TEMPLATES[idx][0]
        prefix = {"主图": "main", "白底图": "white_bg", "详情图": "detail"}.get(tpl_name, "image")
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
            initialfile=f"{prefix}-{int(time.time())}.png",
            parent=self.root,
        )
        if not path:
            return
        with open(path, "wb") as f:
            f.write(data)
        self._triple_cards[idx]["status"].config(text=f"已保存：{os.path.basename(path)}", fg=COLORS["success"])

