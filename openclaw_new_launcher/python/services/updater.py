"""OpenClaw package update helpers."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable

from core.paths import AppPaths

UiCall = Callable[..., None]
LogCall = Callable[[str], None]


class OpenClawUpdater:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    def current_version(self) -> str:
        package_json = os.path.join(self.paths.base_path, "node_modules", "openclaw", "package.json")
        if not os.path.exists(package_json):
            return "未知"
        try:
            with open(package_json, "r", encoding="utf-8") as file:
                return json.load(file).get("version", "未知")
        except Exception:
            return "未知"

    def latest_version(self) -> tuple[str | None, str | None]:
        node_exe = self.paths.node_exe
        pnpm_cli = self.paths.pnpm_cli
        if not os.path.exists(node_exe):
            return None, "找不到 Node.js"
        if not os.path.exists(pnpm_cli):
            return None, "找不到 pnpm"
        try:
            result = subprocess.run(
                [node_exe, pnpm_cli, "view", "openclaw", "version"],
                capture_output=True,
                text=True,
                cwd=self.paths.base_path,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip(), None
            return None, result.stderr.strip() or "网络错误"
        except subprocess.TimeoutExpired:
            return None, "请求超时"
        except Exception as error:
            return None, str(error)

    def update_async(self, append_log: LogCall, ui_call: UiCall, on_done: Callable[[bool, str], None]) -> None:
        def worker():
            node_exe = self.paths.node_exe
            pnpm_cli = self.paths.pnpm_cli
            if not os.path.exists(node_exe) or not os.path.exists(pnpm_cli):
                ui_call(on_done, False, "找不到 Node.js 或 pnpm")
                return
            try:
                process = subprocess.Popen(
                    [node_exe, pnpm_cli, "add", "openclaw@latest"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding="utf-8",
                    errors="replace",
                    cwd=self.paths.base_path,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        if not line and process.poll() is not None:
                            break
                        if line:
                            ui_call(append_log, f"  {line}")
                exit_code = process.wait()
                if exit_code == 0:
                    ui_call(on_done, True, self.current_version())
                else:
                    ui_call(on_done, False, "请检查网络连接后重试")
            except Exception as error:
                ui_call(on_done, False, str(error))

        threading.Thread(target=worker, daemon=True).start()

