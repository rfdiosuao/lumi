"""Small tkinter component helpers used across launcher screens."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from openclaw_launcher.constants import COLORS, FONTS


def configure_ttk_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Launcher.TCombobox",
        fieldbackground=COLORS["input"],
        background=COLORS["surface"],
        foreground=COLORS["text"],
        arrowcolor=COLORS["accent"],
        bordercolor=COLORS["border"],
        lightcolor=COLORS["border"],
        darkcolor=COLORS["border"],
        padding=4,
    )
    style.map("Launcher.TCombobox", fieldbackground=[("readonly", COLORS["input"])])


def label(parent: tk.Misc, text: str, *, kind: str = "body", muted: bool = False, bg: str | None = None, fg: str | None = None, **kwargs) -> tk.Label:
    fg = fg or (COLORS["text_muted"] if muted else COLORS["text"])
    return tk.Label(parent, text=text, font=FONTS.get(kind, FONTS["body"]), bg=bg or COLORS["surface"], fg=fg, **kwargs)


def field_label(parent: tk.Misc, text: str, *, bg: str | None = None) -> tk.Label:
    return label(parent, text, kind="small", muted=True, bg=bg)


def entry(parent: tk.Misc, *, show: str = "", **kwargs) -> tk.Entry:
    font = kwargs.pop("font", FONTS["body"])
    bg = kwargs.pop("bg", COLORS["input"])
    fg = kwargs.pop("fg", COLORS["text"])
    insertbackground = kwargs.pop("insertbackground", COLORS["text"])
    relief = kwargs.pop("relief", "flat")
    return tk.Entry(
        parent,
        font=font,
        bg=bg,
        fg=fg,
        insertbackground=insertbackground,
        relief=relief,
        show=show,
        **kwargs,
    )


def text_area(parent: tk.Misc, *, height: int = 3) -> tk.Text:
    return tk.Text(
        parent,
        font=FONTS["body"],
        bg=COLORS["input"],
        fg=COLORS["text"],
        insertbackground=COLORS["text"],
        relief="flat",
        height=height,
        wrap="word",
        padx=10,
        pady=8,
    )


def button(
    parent: tk.Misc,
    text: str,
    command=None,
    *,
    variant: str = "quiet",
    width: int | None = None,
    **kwargs,
) -> tk.Button:
    palette = {
        "primary": (COLORS["accent"], "white", COLORS["accent_hover"]),
        "danger": (COLORS["danger"], "white", COLORS["danger_hover"]),
        "success": (COLORS["success"], "white", COLORS["success"]),
        "quiet": (COLORS["input"], COLORS["text"], COLORS["hover"]),
    }
    bg, fg, active_bg = palette.get(variant, palette["quiet"])
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=FONTS["section"] if variant in {"primary", "danger", "success"} else FONTS["small"],
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=fg,
        relief="flat",
        cursor="hand2",
        width=width or 0,
        padx=14,
        pady=7,
        **kwargs,
    )
