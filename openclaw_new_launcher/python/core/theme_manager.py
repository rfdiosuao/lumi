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
        {"key": "weixin", "label": "微信机器人", "group": "配置"},
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


def _normalize_nav_items(items: Any) -> list[dict[str, Any]]:
    default_items = DEFAULT_THEME["navItems"]
    default_by_key = {item["key"]: item for item in default_items}
    source = items if isinstance(items, list) and items else default_items
    normalized: list[dict[str, Any]] = []
    for item in source:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key == "delivery" or key not in default_by_key:
            continue
        merged = dict(default_by_key[key])
        if "accent" in item:
            merged["accent"] = bool(item["accent"])
        normalized.append(merged)
    result = normalized or list(default_items)
    if not any(item.get("key") == "weixin" for item in result):
        weixin_item = default_by_key.get("weixin")
        if weixin_item:
            insert_index = len(result)
            for index, item in enumerate(result):
                if item.get("key") == "feishu":
                    insert_index = index + 1
                    break
            result.insert(insert_index, dict(weixin_item))
    return result


def _is_external_asset(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("data:", "blob:", "http://", "https://", "asset:", "tauri:"))


def _resolve_brand_assets(brand: dict[str, Any], base_dir: str | None) -> None:
    logo_value = brand.get("logoUrl") or brand.get("logo")
    if not isinstance(logo_value, str) or not logo_value.strip():
        return
    logo_value = logo_value.strip()
    if base_dir and not os.path.isabs(logo_value) and not _is_external_asset(logo_value):
        resolved = os.path.abspath(os.path.join(base_dir, logo_value))
        if not os.path.exists(resolved):
            filename = os.path.basename(logo_value)
            fallback_candidates = [
                os.path.join(base_dir, "themes", "default", filename),
                os.path.join(base_dir, "themes", "yonghao_tech", filename),
            ]
            resolved = next((path for path in fallback_candidates if os.path.exists(path)), resolved)
        logo_value = resolved
    brand["logoUrl"] = logo_value


def _normalize_mode_colors(theme: dict[str, Any], default_colors: dict[str, Any]) -> dict[str, dict[str, Any]]:
    modes: dict[str, dict[str, Any]] = {}
    raw_modes = theme.get("modes")
    if not isinstance(raw_modes, dict):
        return modes
    for mode in ("light", "dark"):
        raw_colors = raw_modes.get(mode)
        if isinstance(raw_colors, dict):
            modes[mode] = {k: v for k, v in raw_colors.items() if k in default_colors}
    return modes


def _validate_theme(theme: dict[str, Any], base_dir: str | None = None) -> dict[str, Any]:
    default = DEFAULT_THEME
    if not isinstance(theme, dict):
        return dict(default)
    result: dict[str, Any] = {}
    result["name"] = theme.get("name", default["name"])
    result["colors"] = dict(default["colors"])
    if isinstance(theme.get("colors"), dict):
        result["colors"].update(theme["colors"])
    result["modes"] = _normalize_mode_colors(theme, default["colors"])
    result["fonts"] = dict(default["fonts"])
    if isinstance(theme.get("fonts"), dict):
        for k, v in theme["fonts"].items():
            if k in default["fonts"]:
                result["fonts"][k] = v
    result["brand"] = dict(default["brand"])
    if isinstance(theme.get("brand"), dict):
        result["brand"].update(theme["brand"])
    _resolve_brand_assets(result["brand"], base_dir)
    result["navItems"] = _normalize_nav_items(theme.get("navItems"))
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

        theme = self._load_from_local_package("default")
        if theme is not None:
            self._current_cache = theme
            return theme

        self._current_cache = _validate_theme(DEFAULT_THEME)
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
                theme_data = self._load_from_theme_file(theme_path, entry)
                if isinstance(theme_data, dict):
                    themes.append(theme_data)
        return themes

    def save_theme(self, theme_data: dict[str, Any]) -> None:
        validated = _validate_theme(theme_data, self.paths.data_dir)
        write_json(self.paths.theme_json, validated)
        self._current_cache = validated

    def invalidate_cache(self) -> None:
        self._current_cache = None

    def _load_from_cache(self) -> dict[str, Any] | None:
        theme_data = read_json(self.paths.theme_json, None)
        if self._looks_like_theme(theme_data):
            return _validate_theme(theme_data, self.paths.data_dir)
        return None

    def _load_from_license(self, license_data: dict[str, Any]) -> dict[str, Any] | None:
        brand_config = license_data.get("brandConfig") or license_data.get("theme")
        if self._looks_like_theme(brand_config):
            return _validate_theme(brand_config)
        return None

    def _load_from_local_package(self, merchant_id: str) -> dict[str, Any] | None:
        theme_path = self.paths.theme_file(merchant_id)
        if not os.path.isfile(theme_path):
            return None
        return self._load_from_theme_file(theme_path, merchant_id)

    def _load_from_theme_file(self, theme_path: str, merchant_id: str | None = None) -> dict[str, Any] | None:
        theme_data = read_json(theme_path, None)
        if self._looks_like_theme(theme_data):
            if merchant_id:
                theme_data["merchantId"] = merchant_id
            return _validate_theme(theme_data, os.path.dirname(theme_path))
        return None

    @staticmethod
    def _looks_like_theme(theme_data: Any) -> bool:
        return (
            isinstance(theme_data, dict)
            and (
                isinstance(theme_data.get("colors"), dict)
                or isinstance(theme_data.get("modes"), dict)
                or isinstance(theme_data.get("brand"), dict)
                or isinstance(theme_data.get("window"), dict)
            )
        )
