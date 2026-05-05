"""Theme configuration manager with three-level fallback strategy.

Fallback chain:
1. data/theme.json -- cached from activation response (highest priority)
2. data/themes/{merchantId}/theme.json -- local theme package (offline fallback)
3. DEFAULT_THEME -- built-in default (fallback)
"""

from __future__ import annotations

import os
from typing import Any

from core.paths import AppPaths
from core.storage import read_json, write_json

DEFAULT_THEME: dict[str, Any] = {
    "name": "永浩科技主题",
    "colors": {
        "app_bg": "#F3F4F5",
        "sidebar_bg": "#F9F9FA",
        "surface": "#FFFFFF",
        "surface_alt": "#F6F7F8",
        "surface_deep": "#1C202A",
        "surface_deeper": "#14171E",
        "hover": "#EDEFF1",
        "input": "#F6F7F8",
        "border": "#DDDFE3",
        "border_strong": "#C1C4CC",
        "text": "#1E2A3A",
        "text_muted": "#64748B",
        "text_subtle": "#94A3B8",
        "accent": "#1A56DB",
        "accent_hover": "#1444AD",
        "accent_soft": "#E4E8F0",
        "accent_ink": "#0F327F",
        "success": "#059669",
        "warning": "#D97706",
        "danger": "#DC2626",
        "danger_hover": "#B91C1C",
        "terminal_bg": "#0F172A",
        "terminal_header": "#1E293B",
        "terminal_text": "#34D399",
    },
    "fonts": {
        "display": ["Microsoft YaHei UI", 21, "bold"],
        "title": ["Microsoft YaHei UI", 14, "bold"],
        "section": ["Microsoft YaHei UI", 10, "bold"],
        "body": ["Microsoft YaHei UI", 10],
        "small": ["Microsoft YaHei UI", 9],
        "mono": ["Consolas", 10],
    },
    "brand": {
        "name": "永浩科技",
        "subtitle": "智能AI服务平台",
        "app_user_model_id": "YonghaoTech.Launcher",
        "terminal_header": "Service Console",
    },
    "navItems": [
        {"key": "terminal", "label": "服务日志", "group": "工作台"},
        {"key": "storyboard", "label": "广告视频", "group": "工作台", "accent": True},
        {"key": "image", "label": "AI 生图", "group": "工作台", "accent": True},
        {"key": "video", "label": "AI 视频", "group": "工作台", "accent": True},
        {"key": "license", "label": "授权码", "group": "配置"},
        {"key": "api", "label": "API 配置", "group": "配置"},
        {"key": "feishu", "label": "飞书机器人", "group": "配置"},
        {"key": "web", "label": "网页界面", "group": "维护"},
        {"key": "update", "label": "检查更新", "group": "维护"},
        {"key": "help", "label": "帮助文档", "group": "维护"},
    ],
    "window": {
        "title": "永浩科技 - 智能AI服务平台",
        "width": 1200,
        "height": 800,
    },
}


def _validate_theme(theme: dict[str, Any]) -> dict[str, Any]:
    default = DEFAULT_THEME
    if not isinstance(theme, dict):
        return dict(default)
    result: dict[str, Any] = {}
    result["name"] = theme.get("name", default["name"])
    result["colors"] = dict(default["colors"])
    if isinstance(theme.get("colors"), dict):
        result["colors"].update(theme["colors"])
    result["fonts"] = dict(default["fonts"])
    if isinstance(theme.get("fonts"), dict):
        for k, v in theme["fonts"].items():
            if k in default["fonts"]:
                result["fonts"][k] = v
    result["brand"] = dict(default["brand"])
    if isinstance(theme.get("brand"), dict):
        result["brand"].update(theme["brand"])
    result["navItems"] = theme.get("navItems", default["navItems"])
    result["window"] = dict(default["window"])
    if isinstance(theme.get("window"), dict):
        result["window"].update(theme["window"])
    return result


class ThemeManager:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self._current_cache: dict[str, Any] | None = None

    def get_current(self, license_data: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._current_cache is not None:
            return self._current_cache

        theme = self._load_from_cache()
        if theme is not None:
            self._current_cache = theme
            return theme

        if license_data:
            theme = self._load_from_license(license_data)
            if theme is not None:
                self._current_cache = theme
                return theme

            merchant_id = license_data.get("merchantId")
            if merchant_id:
                theme = self._load_from_local_package(merchant_id)
                if theme is not None:
                    self._current_cache = theme
                    return theme

        self._current_cache = dict(DEFAULT_THEME)
        return self._current_cache

    def get_by_merchant(self, merchant_id: str) -> dict[str, Any] | None:
        if not merchant_id:
            return None
        return self._load_from_local_package(merchant_id)

    def list_themes(self) -> list[dict[str, Any]]:
        themes: list[dict[str, Any]] = []
        themes_dir = self.paths.themes_dir
        if not os.path.isdir(themes_dir):
            return themes
        for entry in sorted(os.listdir(themes_dir)):
            theme_path = os.path.join(themes_dir, entry, "theme.json")
            if os.path.isfile(theme_path):
                theme_data = read_json(theme_path, None)
                if isinstance(theme_data, dict):
                    theme_data["merchantId"] = entry
                    themes.append(theme_data)
        return themes

    def save_theme(self, theme_data: dict[str, Any]) -> None:
        validated = _validate_theme(theme_data)
        write_json(self.paths.theme_json, validated)
        self._current_cache = validated

    def invalidate_cache(self) -> None:
        self._current_cache = None

    def _load_from_cache(self) -> dict[str, Any] | None:
        theme_data = read_json(self.paths.theme_json, None)
        if isinstance(theme_data, dict) and theme_data.get("colors"):
            return _validate_theme(theme_data)
        return None

    def _load_from_license(self, license_data: dict[str, Any]) -> dict[str, Any] | None:
        brand_config = license_data.get("brandConfig") or license_data.get("theme")
        if isinstance(brand_config, dict) and brand_config.get("colors"):
            return _validate_theme(brand_config)
        return None

    def _load_from_local_package(self, merchant_id: str) -> dict[str, Any] | None:
        theme_path = self.paths.theme_file(merchant_id)
        if not os.path.isfile(theme_path):
            return None
        theme_data = read_json(theme_path, None)
        if isinstance(theme_data, dict) and theme_data.get("colors"):
            theme_data["merchantId"] = merchant_id
            return _validate_theme(theme_data)
        return None
