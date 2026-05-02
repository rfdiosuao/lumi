"""Path discovery helpers for portable and packaged launcher layouts."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class AppPaths:
    base_path: str

    @classmethod
    def discover(cls) -> "AppPaths":
        base_path = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.basename(base_path) == "OpenClaw启动":
            base_path = os.path.dirname(base_path)
        return cls(base_path=base_path)

    def resource_path(self, filename: str) -> str:
        if getattr(sys, "frozen", False):
            return os.path.join(sys._MEIPASS, filename)
        return os.path.join(self.base_path, filename)

    def find_node_dir(self) -> str:
        candidates = [
            os.path.join(self.base_path, "SystemData", ".core", "node"),
            os.path.join(self.base_path, "node"),
        ]
        for path in candidates:
            if os.path.exists(os.path.join(path, "node.exe")):
                return path
        return candidates[-1]

    def find_file(self, filename: str, search_dirs: tuple[str, ...] = ("", "back", "backup", "SystemData")) -> str:
        for directory in search_dirs:
            path = os.path.join(self.base_path, directory, filename) if directory else os.path.join(self.base_path, filename)
            if os.path.exists(path):
                return path
        return os.path.join(self.base_path, filename)

    @property
    def node_dir(self) -> str:
        return self.find_node_dir()

    @property
    def node_exe(self) -> str:
        return os.path.join(self.node_dir, "node.exe")

    @property
    def pnpm_cli(self) -> str:
        return os.path.join(self.node_dir, "node_modules", "pnpm", "bin", "pnpm.cjs")

    @property
    def data_dir(self) -> str:
        return os.path.join(self.base_path, "data")

    @property
    def state_dir(self) -> str:
        return os.path.join(self.data_dir, ".openclaw")

    @property
    def openclaw_config(self) -> str:
        return os.path.join(self.state_dir, "openclaw.json")

    @property
    def auth_profiles(self) -> str:
        return os.path.join(self.state_dir, "agents", "main", "agent", "auth-profiles.json")

    @property
    def image_config(self) -> str:
        return os.path.join(self.base_path, "imgapi_config.json")

    @property
    def video_config(self) -> str:
        return os.path.join(self.base_path, "video_config.json")

    @property
    def storyboard_dir(self) -> str:
        return os.path.join(self.data_dir, "storyboards")

    @property
    def storyboard_project(self) -> str:
        return os.path.join(self.storyboard_dir, "ad_video_project.json")

    @property
    def storyboard_assets(self) -> str:
        return os.path.join(self.storyboard_dir, "assets")

    @property
    def license_file(self) -> str:
        return os.path.join(self.data_dir, "license.json")

    @property
    def install_id_file(self) -> str:
        return os.path.join(self.data_dir, "install_id.txt")

    @property
    def openclaw_mjs(self) -> str:
        return os.path.join(self.base_path, "node_modules", "openclaw", "openclaw.mjs")

    def process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["OPENCLAW_HOME"] = self.data_dir
        env["OPENCLAW_STATE_DIR"] = self.state_dir
        env["OPENCLAW_CONFIG_PATH"] = self.openclaw_config
        return env
