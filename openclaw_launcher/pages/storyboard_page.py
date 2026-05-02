"""Storyboard workspace for short ad video production."""

from __future__ import annotations

import io
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from openclaw_launcher.constants import COLORS, FONTS
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.services.image_api import ImageApiClient, ImageApiError
from openclaw_launcher.services.video_api import DashScopeVideoClient, VideoApiError
from openclaw_launcher.storage import read_json, write_json
from openclaw_launcher.ui.components import button, entry, field_label, label, text_area


VIEW_KEYS = [("front", "正面"), ("side", "侧面"), ("back", "背面")]
CHECK_KEYS = [
    ("product_stable", "产品不变形"),
    ("logo_clear", "Logo / 包装清晰"),
    ("selling_point", "卖点一眼可懂"),
    ("frame_flow", "首尾帧连贯"),
    ("crop_ready", "构图适合投放"),
]


class StoryboardPage:
    name = "storyboard"

    def __init__(self, parent: tk.Misc, root: tk.Tk, paths: AppPaths, append_log):
        self.root = root
        self.paths = paths
        self.append_log = append_log
        self.image_client = ImageApiClient()
        self.video_client = DashScopeVideoClient()
        self.frame = tk.Frame(parent, bg=COLORS["surface"])
        self.project = self._load_project()
        self.current_index = 0
        self.candidates: list[bytes] = []
        self.candidate_photos: list[ImageTk.PhotoImage] = []
        self.selected_candidate: int | None = None
        self.product_photos: dict[str, ImageTk.PhotoImage] = {}
        self.frame_photos: dict[str, ImageTk.PhotoImage] = {}
        self._build()
        self._refresh_scene_list()
        self._load_scene(0)

    def _default_project(self) -> dict:
        return {
            "title": "U盘小广告视频",
            "product_views": {"front": "", "side": "", "back": ""},
            "scenes": [
                {
                    "id": int(time.time()),
                    "title": "开场钩子",
                    "selling_point": "3 秒讲清产品亮点",
                    "duration": "5",
                    "ratio": "9:16",
                    "camera": "缓慢推进",
                    "prompt": "产品置于干净桌面，光线明亮，画面突出便携、可靠、高级感，小广告视频开场镜头",
                    "negative": "低清晰度，变形，杂乱背景，错误文字，手指遮挡，品牌错乱",
                    "first_frame": "",
                    "last_frame": "",
                    "video": "",
                    "checks": {key: False for key, _text in CHECK_KEYS},
                }
            ],
        }

    def _load_project(self) -> dict:
        project = read_json(self.paths.storyboard_project, None)
        if not isinstance(project, dict) or not project.get("scenes"):
            project = self._default_project()
        project.setdefault("product_views", {"front": "", "side": "", "back": ""})
        project.setdefault("scenes", [])
        return project

    def _build(self) -> None:
        os.makedirs(self.paths.storyboard_assets, exist_ok=True)
        header = tk.Frame(self.frame, bg=COLORS["surface"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        label(header, "广告视频工作台", kind="title").pack(side="left", padx=22, pady=(16, 0), anchor="n")
        label(header, "分镜、三视图、首尾帧、九宫格候选", kind="small", muted=True).pack(side="left", padx=(10, 0), pady=(25, 0), anchor="n")
        button(header, "保存项目", self._save_project, variant="primary").pack(side="right", padx=22, pady=16)

        body = tk.Frame(self.frame, bg=COLORS["surface"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=0, minsize=215)
        body.grid_columnconfigure(1, weight=1, minsize=360)
        body.grid_columnconfigure(2, weight=0, minsize=280)
        body.grid_rowconfigure(0, weight=1)

        self._build_left(body)
        self._build_center(body)
        self._build_right(body)

    def _build_left(self, parent: tk.Misc) -> None:
        panel = tk.Frame(parent, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        panel.grid_propagate(False)

        top = tk.Frame(panel, bg=COLORS["surface_alt"])
        top.pack(fill="x", padx=12, pady=12)
        label(top, "分镜列表", kind="section", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.scene_list = tk.Listbox(
            panel,
            font=FONTS["small"],
            bg=COLORS["surface"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            relief="flat",
            activestyle="none",
            height=12,
        )
        self.scene_list.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.scene_list.bind("<<ListboxSelect>>", self._on_scene_select)

        actions = tk.Frame(panel, bg=COLORS["surface_alt"])
        actions.pack(fill="x", padx=12, pady=(0, 12))
        button(actions, "新增", self._add_scene).pack(side="left", padx=(0, 6), fill="x", expand=True)
        button(actions, "复制", self._duplicate_scene).pack(side="left", padx=(0, 6), fill="x", expand=True)
        button(actions, "删除", self._delete_scene, variant="danger").pack(side="left", fill="x", expand=True)

        hint = tk.Frame(panel, bg=COLORS["surface_alt"])
        hint.pack(fill="x", padx=12, pady=(0, 14))
        label(hint, "建议：每条广告 3-5 个镜头，先定首尾帧，再生成视频。", kind="small", muted=True, bg=COLORS["surface_alt"], wraplength=175, justify="left").pack(anchor="w")

    def _build_center(self, parent: tk.Misc) -> None:
        panel = tk.Frame(parent, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        panel.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        product = tk.Frame(panel, bg=COLORS["surface"])
        product.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 10))
        label(product, "产品三视图", kind="section").pack(anchor="w")
        views = tk.Frame(product, bg=COLORS["surface"])
        views.pack(fill="x", pady=(8, 0))
        self.view_boxes: dict[str, tk.Label] = {}
        for key, title in VIEW_KEYS:
            box = tk.Frame(views, bg=COLORS["input"], highlightbackground=COLORS["border"], highlightthickness=1)
            box.pack(side="left", fill="both", expand=True, padx=(0, 8))
            img = tk.Label(box, text=title, font=FONTS["small"], bg=COLORS["input"], fg=COLORS["text_muted"], width=12, height=4)
            img.pack(fill="both", expand=True, padx=6, pady=6)
            img.bind("<Button-1>", lambda _event, k=key: self._pick_product_view(k))
            self.view_boxes[key] = img

        frames = tk.Frame(panel, bg=COLORS["surface"])
        frames.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        label(frames, "首尾帧", kind="section").pack(anchor="w")
        frame_row = tk.Frame(frames, bg=COLORS["surface"])
        frame_row.pack(fill="x", pady=(8, 0))
        self.frame_boxes: dict[str, tk.Label] = {}
        for key, title in [("first_frame", "首帧"), ("last_frame", "尾帧")]:
            box = tk.Frame(frame_row, bg=COLORS["input"], highlightbackground=COLORS["border"], highlightthickness=1)
            box.pack(side="left", fill="both", expand=True, padx=(0, 8))
            img = tk.Label(box, text=title, font=FONTS["section"], bg=COLORS["input"], fg=COLORS["text_muted"], height=6)
            img.pack(fill="both", expand=True, padx=8, pady=8)
            img.bind("<Button-1>", lambda _event, slot=key: self._pick_scene_frame(slot))
            self.frame_boxes[key] = img

        grid = tk.Frame(panel, bg=COLORS["surface"])
        grid.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_rowconfigure(2, weight=1)
        label(grid, "九宫格候选", kind="section").grid(row=0, column=0, sticky="w")
        tools = tk.Frame(grid, bg=COLORS["surface"])
        tools.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        button(tools, "生成九宫格", self._generate_candidates, variant="primary").pack(side="left", padx=(0, 8))
        button(tools, "设为首帧", lambda: self._assign_candidate("first_frame")).pack(side="left", padx=(0, 8))
        button(tools, "设为尾帧", lambda: self._assign_candidate("last_frame")).pack(side="left")
        self.candidate_status = label(tools, "", kind="small", muted=True)
        self.candidate_status.pack(side="left", padx=10)

        self.grid_frame = tk.Frame(grid, bg=COLORS["surface"])
        self.grid_frame.grid(row=2, column=0, sticky="nsew")
        self.grid_cells: list[tk.Label] = []
        for row in range(3):
            self.grid_frame.grid_rowconfigure(row, weight=1)
            for col in range(3):
                self.grid_frame.grid_columnconfigure(col, weight=1)
                idx = row * 3 + col
                cell = tk.Label(
                    self.grid_frame,
                    text=str(idx + 1),
                    font=FONTS["section"],
                    bg=COLORS["input"],
                    fg=COLORS["text_subtle"],
                    highlightbackground=COLORS["border"],
                    highlightthickness=1,
                    cursor="hand2",
                )
                cell.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
                cell.bind("<Button-1>", lambda _event, i=idx: self._select_candidate(i))
                self.grid_cells.append(cell)

    def _build_right(self, parent: tk.Misc) -> None:
        panel = tk.Frame(parent, bg=COLORS["surface_alt"], highlightbackground=COLORS["border"], highlightthickness=1)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.grid_propagate(False)
        content = tk.Frame(panel, bg=COLORS["surface_alt"])
        content.pack(fill="both", expand=True, padx=14, pady=14)

        label(content, "镜头参数", kind="section", bg=COLORS["surface_alt"]).pack(anchor="w", pady=(0, 10))
        field_label(content, "镜头标题", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.title_entry = entry(content)
        self.title_entry.pack(fill="x", pady=(4, 8), ipady=5)

        field_label(content, "卖点", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.selling_entry = entry(content)
        self.selling_entry.pack(fill="x", pady=(4, 8), ipady=5)

        opts = tk.Frame(content, bg=COLORS["surface_alt"])
        opts.pack(fill="x", pady=(0, 8))
        self.duration_var = tk.StringVar(value="5")
        self.ratio_var = tk.StringVar(value="9:16")
        self.camera_var = tk.StringVar(value="缓慢推进")
        self._combo(opts, "时长", self.duration_var, ["3", "5", "8", "10"], width=5).pack(side="left", padx=(0, 8))
        self._combo(opts, "比例", self.ratio_var, ["9:16", "16:9", "1:1", "4:3"], width=7).pack(side="left", padx=(0, 8))
        self._combo(opts, "运镜", self.camera_var, ["缓慢推进", "平移", "环绕", "静物特写", "拉远"], width=9).pack(side="left")

        field_label(content, "画面提示词", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.prompt_text = text_area(content, height=5)
        self.prompt_text.pack(fill="x", pady=(4, 8))

        field_label(content, "负面词", bg=COLORS["surface_alt"]).pack(anchor="w")
        self.negative_text = text_area(content, height=3)
        self.negative_text.pack(fill="x", pady=(4, 10))

        label(content, "质量检查", kind="section", bg=COLORS["surface_alt"]).pack(anchor="w", pady=(0, 6))
        self.check_vars: dict[str, tk.BooleanVar] = {}
        for key, text in CHECK_KEYS:
            var = tk.BooleanVar(value=False)
            self.check_vars[key] = var
            tk.Checkbutton(
                content,
                text=text,
                variable=var,
                bg=COLORS["surface_alt"],
                fg=COLORS["text_muted"],
                selectcolor=COLORS["input"],
                activebackground=COLORS["surface_alt"],
                font=FONTS["small"],
            ).pack(anchor="w")

        video_actions = tk.Frame(content, bg=COLORS["surface_alt"])
        video_actions.pack(fill="x", side="bottom", pady=(12, 0))
        button(video_actions, "保存镜头", self._save_current_scene).pack(side="left", padx=(0, 8))
        button(video_actions, "生成镜头视频", self._generate_scene_video, variant="primary").pack(side="left")
        self.video_status = label(content, "", kind="small", muted=True, bg=COLORS["surface_alt"])
        self.video_status.pack(side="bottom", anchor="w", pady=(0, 8))

    def _combo(self, parent: tk.Misc, title: str, variable: tk.StringVar, values: list[str], width: int) -> tk.Frame:
        frame = tk.Frame(parent, bg=COLORS["surface_alt"])
        field_label(frame, title, bg=COLORS["surface_alt"]).pack(anchor="w")
        ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", style="Launcher.TCombobox", font=FONTS["small"], width=width).pack(fill="x", pady=(4, 0))
        return frame

    def _refresh_scene_list(self) -> None:
        self.scene_list.delete(0, tk.END)
        for index, scene in enumerate(self.project["scenes"], start=1):
            self.scene_list.insert(tk.END, f"{index:02d}  {scene.get('title', '未命名镜头')}")
        if self.project["scenes"]:
            self.scene_list.selection_clear(0, tk.END)
            self.scene_list.selection_set(self.current_index)

    def _on_scene_select(self, _event=None) -> None:
        if not self.scene_list.curselection():
            return
        self._save_current_scene(silent=True)
        self._load_scene(self.scene_list.curselection()[0])

    def _load_scene(self, index: int) -> None:
        if not self.project["scenes"]:
            return
        self.current_index = max(0, min(index, len(self.project["scenes"]) - 1))
        scene = self._current_scene()
        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, scene.get("title", ""))
        self.selling_entry.delete(0, tk.END)
        self.selling_entry.insert(0, scene.get("selling_point", ""))
        self.duration_var.set(scene.get("duration", "5"))
        self.ratio_var.set(scene.get("ratio", "9:16"))
        self.camera_var.set(scene.get("camera", "缓慢推进"))
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", scene.get("prompt", ""))
        self.negative_text.delete("1.0", tk.END)
        self.negative_text.insert("1.0", scene.get("negative", ""))
        checks = scene.get("checks", {})
        for key, var in self.check_vars.items():
            var.set(bool(checks.get(key, False)))
        self._refresh_product_views()
        self._refresh_scene_frames()
        self.candidates = []
        self.selected_candidate = None
        self._refresh_candidates()

    def _current_scene(self) -> dict:
        return self.project["scenes"][self.current_index]

    def _save_current_scene(self, silent: bool = False) -> None:
        if not self.project["scenes"]:
            return
        scene = self._current_scene()
        scene["title"] = self.title_entry.get().strip() or "未命名镜头"
        scene["selling_point"] = self.selling_entry.get().strip()
        scene["duration"] = self.duration_var.get()
        scene["ratio"] = self.ratio_var.get()
        scene["camera"] = self.camera_var.get()
        scene["prompt"] = self.prompt_text.get("1.0", "end-1c").strip()
        scene["negative"] = self.negative_text.get("1.0", "end-1c").strip()
        scene["checks"] = {key: var.get() for key, var in self.check_vars.items()}
        self._refresh_scene_list()
        if not silent:
            self._save_project()

    def _save_project(self) -> None:
        self._save_current_scene(silent=True)
        os.makedirs(self.paths.storyboard_dir, exist_ok=True)
        write_json(self.paths.storyboard_project, self.project)
        self.candidate_status.config(text="项目已保存", fg=COLORS["success"])

    def _add_scene(self) -> None:
        self._save_current_scene(silent=True)
        index = len(self.project["scenes"]) + 1
        scene = self._default_project()["scenes"][0]
        scene["id"] = int(time.time() * 1000)
        scene["title"] = f"镜头 {index}"
        scene["prompt"] = "产品清晰可见，画面简洁，突出一个卖点，适合短视频广告"
        self.project["scenes"].append(scene)
        self.current_index = len(self.project["scenes"]) - 1
        self._refresh_scene_list()
        self._load_scene(self.current_index)

    def _duplicate_scene(self) -> None:
        self._save_current_scene(silent=True)
        scene = dict(self._current_scene())
        scene["id"] = int(time.time() * 1000)
        scene["title"] = f"{scene.get('title', '镜头')} 副本"
        scene["checks"] = dict(scene.get("checks", {}))
        self.project["scenes"].insert(self.current_index + 1, scene)
        self.current_index += 1
        self._refresh_scene_list()
        self._load_scene(self.current_index)

    def _delete_scene(self) -> None:
        if len(self.project["scenes"]) <= 1:
            messagebox.showinfo("提示", "至少保留一个镜头")
            return
        if not messagebox.askyesno("删除镜头", "确定删除当前镜头？"):
            return
        self.project["scenes"].pop(self.current_index)
        self.current_index = max(0, self.current_index - 1)
        self._refresh_scene_list()
        self._load_scene(self.current_index)

    def _asset_path(self, filename: str) -> str:
        os.makedirs(self.paths.storyboard_assets, exist_ok=True)
        return os.path.join(self.paths.storyboard_assets, filename)

    def _copy_asset(self, source: str, name: str) -> str:
        ext = os.path.splitext(source)[1] or ".png"
        target = self._asset_path(f"{name}{ext}")
        if os.path.abspath(source) == os.path.abspath(target):
            return target
        shutil.copy2(source, target)
        return target

    def _pick_product_view(self, key: str) -> None:
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择产品视图")
        if not path:
            return
        self.project["product_views"][key] = self._copy_asset(path, f"product_{key}")
        self._refresh_product_views()
        self._save_project()

    def _pick_scene_frame(self, slot: str) -> None:
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")], title="选择首尾帧")
        if not path:
            return
        scene = self._current_scene()
        scene[slot] = self._copy_asset(path, f"scene_{scene['id']}_{slot}")
        self._refresh_scene_frames()
        self._save_project()

    def _refresh_product_views(self) -> None:
        for key, title in VIEW_KEYS:
            self._set_image_label(self.view_boxes[key], self.project.get("product_views", {}).get(key, ""), title, self.product_photos, key, (130, 88))

    def _refresh_scene_frames(self) -> None:
        scene = self._current_scene()
        self._set_image_label(self.frame_boxes["first_frame"], scene.get("first_frame", ""), "首帧", self.frame_photos, "first_frame", (210, 120))
        self._set_image_label(self.frame_boxes["last_frame"], scene.get("last_frame", ""), "尾帧", self.frame_photos, "last_frame", (210, 120))

    def _set_image_label(self, widget: tk.Label, path: str, fallback: str, store: dict[str, ImageTk.PhotoImage], key: str, size: tuple[int, int]) -> None:
        if path and os.path.exists(path):
            image = Image.open(path)
            image.thumbnail(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            store[key] = photo
            widget.config(image=photo, text="")
        else:
            widget.config(image="", text=fallback)

    def _compose_candidate_prompt(self) -> str:
        scene = self._current_scene()
        product_bits = []
        for key, title in VIEW_KEYS:
            if self.project.get("product_views", {}).get(key):
                product_bits.append(title)
        product_context = f"参考产品{','.join(product_bits)}三视图，保持产品外观一致。" if product_bits else "保持产品主体稳定一致。"
        return (
            f"{product_context}\n"
            f"广告镜头：{scene.get('title', '')}\n"
            f"卖点：{scene.get('selling_point', '')}\n"
            f"运镜：{scene.get('camera', '')}\n"
            f"画面：{scene.get('prompt', '')}\n"
            f"要求：商业广告关键帧，主体清晰，构图完整，适合{scene.get('ratio', '9:16')}短视频投放。\n"
            f"避免：{scene.get('negative', '')}"
        )

    def _generate_candidates(self) -> None:
        self._save_current_scene(silent=True)
        config = read_json(self.paths.image_config, {})
        base_url = config.get("baseUrl", "").strip().rstrip("/") if isinstance(config, dict) else ""
        api_key = config.get("apiKey", "").strip() if isinstance(config, dict) else ""
        if not base_url:
            messagebox.showerror("缺少生图配置", "请先在 AI 生图页面填写并保存中转站地址。")
            return
        self.candidate_status.config(text="正在生成九宫格...", fg=COLORS["accent"])
        for cell in self.grid_cells:
            cell.config(image="", text="...", highlightbackground=COLORS["border"])
        prompt = self._compose_candidate_prompt()

        def worker() -> None:
            try:
                images = self.image_client.generate_many(base_url, api_key, prompt, "1024x1024", count=9)
                self.root.after(0, self._show_candidates, images)
            except ImageApiError as error:
                message = str(error)
                self.append_log(f"[分镜九宫格] {message}\n")
                self.root.after(0, lambda: self.candidate_status.config(text=f"失败：{message}", fg=COLORS["danger"]))

        threading.Thread(target=worker, daemon=True).start()

    def _show_candidates(self, images: list[bytes]) -> None:
        self.candidates = images
        self.selected_candidate = None
        self._refresh_candidates()
        self.candidate_status.config(text=f"已生成 {len(images)} 张候选", fg=COLORS["success"])

    def _refresh_candidates(self) -> None:
        self.candidate_photos = []
        for index, cell in enumerate(self.grid_cells):
            if index < len(self.candidates):
                image = Image.open(io.BytesIO(self.candidates[index]))
                image.thumbnail((155, 110), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.candidate_photos.append(photo)
                cell.config(image=photo, text="", highlightbackground=COLORS["accent"] if index == self.selected_candidate else COLORS["border"])
            else:
                cell.config(image="", text=str(index + 1), highlightbackground=COLORS["border"])

    def _select_candidate(self, index: int) -> None:
        if index >= len(self.candidates):
            return
        self.selected_candidate = index
        self._refresh_candidates()
        self.candidate_status.config(text=f"已选择候选 {index + 1}", fg=COLORS["accent"])

    def _assign_candidate(self, slot: str) -> None:
        if self.selected_candidate is None or self.selected_candidate >= len(self.candidates):
            messagebox.showinfo("提示", "请先点击选择一张候选图")
            return
        scene = self._current_scene()
        path = self._asset_path(f"scene_{scene['id']}_{slot}_{int(time.time())}.png")
        with open(path, "wb") as file:
            file.write(self.candidates[self.selected_candidate])
        scene[slot] = path
        self._refresh_scene_frames()
        self._save_project()

    def _generate_scene_video(self) -> None:
        self._save_current_scene(silent=True)
        scene = self._current_scene()
        if not scene.get("first_frame") or not os.path.exists(scene["first_frame"]):
            messagebox.showerror("缺少首帧", "请先为当前镜头设置首帧。")
            return
        video_config = read_json(self.paths.video_config, {})
        dash_key = video_config.get("dashKey", "").strip() if isinstance(video_config, dict) else ""
        if not dash_key:
            messagebox.showerror("缺少视频配置", "请先在 AI 视频页面填写并保存 DashScope API Key。")
            return
        prompt = self._compose_candidate_prompt()
        self.video_status.config(text="正在生成镜头视频...", fg=COLORS["accent"])

        def status(text: str, kind: str) -> None:
            self.root.after(0, lambda: self.video_status.config(text=text, fg=COLORS.get(kind, COLORS["accent"])))

        def worker() -> None:
            try:
                video = self.video_client.generate(
                    dash_key,
                    prompt,
                    "i2v",
                    "720P",
                    int(scene.get("duration", "5")),
                    scene.get("ratio", "9:16"),
                    scene["first_frame"],
                    status,
                )
                path = self._asset_path(f"scene_{scene['id']}_video_{int(time.time())}.mp4")
                with open(path, "wb") as file:
                    file.write(video)
                scene["video"] = path
                self.root.after(0, self._on_video_done, path)
            except VideoApiError as error:
                message = str(error)
                self.append_log(f"[分镜视频] {message}\n")
                self.root.after(0, lambda: self.video_status.config(text=f"失败：{message}", fg=COLORS["danger"]))

        threading.Thread(target=worker, daemon=True).start()

    def _on_video_done(self, path: str) -> None:
        self._save_project()
        self.video_status.config(text=f"镜头视频已保存：{os.path.basename(path)}", fg=COLORS["success"])
