#!/usr/bin/env python3
"""
OpenClaw Launcher 主题切换工具

用法:
    python theme_switch.py                    # 列出所有可用主题
    python theme_switch.py <商家ID>            # 切换到指定商家主题
    python theme_switch.py --restore           # 恢复到原始基准主题
    python theme_switch.py --list              # 列出所有可用主题
"""

import json
import os
import shutil
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(PROJECT_DIR, "themes")
REGISTRY_PATH = os.path.join(THEMES_DIR, "registry.json")
BACKUP_DIR = os.path.join(THEMES_DIR, "_base", "backup")


def load_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def list_themes():
    registry = load_registry()
    merchants = registry.get("merchants", {})
    if not merchants:
        print("暂无商家主题，使用 /openclaw-ui 创建第一个主题。")
        return
    print("可用主题:")
    for mid, info in merchants.items():
        active = info.get("active_version", "v1")
        versions = list(info.get("versions", {}).keys())
        print(f"  {mid:20s} | {info.get('name', '?'):20s} | 主色: {info.get('primary_color', '?')} | 版本: {', '.join(versions)} | 当前: {active}")


def switch_theme(merchant_id):
    registry = load_registry()
    merchants = registry.get("merchants", {})
    if merchant_id not in merchants:
        print(f"错误: 找不到商家 '{merchant_id}'")
        list_themes()
        sys.exit(1)

    merchant_dir = os.path.join(THEMES_DIR, "merchants", merchant_id)
    constants_src = os.path.join(merchant_dir, "constants.py")
    logo_src = os.path.join(merchant_dir, "logo.ico")
    logo_sq_src = os.path.join(merchant_dir, "logo_square.ico")

    if not os.path.exists(constants_src):
        print(f"错误: {merchant_id} 没有 constants.py")
        sys.exit(1)

    # 切换
    constants_dst = os.path.join(PROJECT_DIR, "constants.py")
    shutil.copy2(constants_src, constants_dst)

    if os.path.exists(logo_src):
        shutil.copy2(logo_src, os.path.join(PROJECT_DIR, "logo.ico"))
    if os.path.exists(logo_sq_src):
        shutil.copy2(logo_sq_src, os.path.join(PROJECT_DIR, "logo_square.ico"))

    info = merchants[merchant_id]
    print(f"已切换到主题: {info['name']} ({info['primary_color']})")


def restore_base():
    """恢复到原始基准主题"""
    files = {
        "constants.py.bak": "constants.py",
        "logo.ico.bak": "logo.ico",
        "logo_square.ico.bak": "logo_square.ico",
    }
    for src_name, dst_name in files.items():
        src = os.path.join(BACKUP_DIR, src_name)
        dst = os.path.join(PROJECT_DIR, dst_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
    print("已恢复到原始基准主题 (OpenClaw)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or "--list" in args:
        list_themes()
    elif "--restore" in args:
        restore_base()
    else:
        switch_theme(args[0])
