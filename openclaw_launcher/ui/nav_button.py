"""Canvas-based sidebar navigation button."""

from __future__ import annotations

import tkinter as tk

from openclaw_launcher.constants import COLORS, FONTS


class NavButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text: str,
        desc: str = "",
        icon: str = "",
        command=None,
        *,
        primary: bool = False,
        danger: bool = False,
        accent: bool = False,
        height: int = 50,
        **kwargs,
    ):
        super().__init__(parent, height=height, bg=COLORS["sidebar_bg"], highlightthickness=0, **kwargs)
        self.button_height = height
        self.text = text
        self.desc = desc
        self.icon = icon
        self.command = command
        self.primary = primary
        self.danger = danger
        self.accent = accent
        self.hovered = False
        self.active = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._draw)
        self.configure(cursor="hand2")

    def set_active(self, active: bool) -> None:
        self.active = active
        self._draw()

    def _on_enter(self, _event):
        self.hovered = True
        self._draw()

    def _on_leave(self, _event):
        self.hovered = False
        self._draw()

    def _on_click(self, _event):
        if self.command:
            self.command()

    def _draw(self, _event=None):
        self.delete("all")
        width = max(self.winfo_width(), 10)
        height = self.button_height
        if self.danger:
            bg = COLORS["danger_hover"] if self.hovered else COLORS["danger"]
            fg = "white"
            muted = COLORS["danger_muted"]
            marker = "white"
        elif self.primary:
            bg = COLORS["accent_hover"] if self.hovered else COLORS["accent"]
            fg = "white"
            muted = COLORS["primary_muted"]
            marker = "white"
        elif self.active or self.accent:
            bg = COLORS["accent_soft"] if not self.hovered else COLORS["accent_hover_light"]
            fg = COLORS["accent_ink"]
            muted = COLORS["accent_ink"]
            marker = COLORS["accent"]
        else:
            bg = COLORS["hover"] if self.hovered else COLORS["surface"]
            fg = COLORS["text"]
            muted = COLORS["text_muted"]
            marker = COLORS["border_strong"]

        self._round_rect(0, 0, width, height, 12, fill=bg, outline="")
        if self.active:
            self._round_rect(0, 10, 4, height - 10, 2, fill=COLORS["accent"], outline="")

        x = 18
        if self.primary:
            self.create_polygon(20, height // 2 - 10, 20, height // 2 + 10, 36, height // 2, fill="white", outline="")
            x = 50
        elif self.icon:
            self.create_text(25, height // 2, text=self.icon, font=FONTS["section"], fill=marker)
            x = 50

        title_y = 18 if self.desc else height // 2
        self.create_text(x, title_y, text=self.text, anchor="w", font=FONTS["section"], fill=fg)
        if self.desc:
            self.create_text(x, 35, text=self.desc, anchor="w", font=FONTS["small"], fill=muted)

    def _round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)
