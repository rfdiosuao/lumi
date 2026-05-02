"""OpenClaw gateway process management."""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable

from openclaw_launcher.constants import APP_PORT
from openclaw_launcher.paths import AppPaths

UiCall = Callable[..., None]
LogCall = Callable[[str], None]


class OpenClawProcessService:
    def __init__(self, paths: AppPaths, append_log: LogCall, ui_call: UiCall):
        self.paths = paths
        self.append_log = append_log
        self.ui_call = ui_call
        self.process: subprocess.Popen | None = None
        self.running = False

    def start(self, on_exit: Callable[[int | None], None] | None = None) -> None:
        if self.running:
            raise RuntimeError("服务已在运行中")
        node_exe = self.paths.node_exe
        if not os.path.exists(node_exe):
            raise FileNotFoundError(f"找不到 Node.js：\n{node_exe}")
        start_js = self.paths.find_file("start.js", ("back", "backup", ""))
        if not os.path.exists(start_js):
            raise FileNotFoundError(f"找不到启动脚本：\n{start_js}")

        env = self.paths.process_env()
        self.append_log("[OpenClaw] Starting service...\n")
        self.append_log(f"[OpenClaw] Node: {node_exe}\n")
        self.append_log(f"[OpenClaw] Script: {start_js}\n\n")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.process = subprocess.Popen(
            [node_exe, start_js],
            cwd=self.paths.base_path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation_flags,
        )
        self.running = True
        self.append_log(f"[OpenClaw] PID: {self.process.pid}\n")
        threading.Thread(target=self._read_output, args=(self.process, on_exit), daemon=True).start()

    def stop(self) -> str:
        if self.process and self.process.poll() is None:
            pid = self.process.pid
            self.append_log("\n[OpenClaw] Stopping...\n")
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            self.running = False
            self.append_log("[OpenClaw] Stopped.\n")
            return "服务已停止"
        if self.process:
            self.append_log("\n[OpenClaw] Cleaning up stale port listeners...\n")
            killed = self._kill_port_processes(APP_PORT)
            self.running = False
            self.process = None
            return f"已清理 {killed} 个端口占用进程" if killed else "没有运行中的服务"
        return "服务未启动"

    def _read_output(self, process: subprocess.Popen, on_exit: Callable[[int | None], None] | None) -> None:
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    self.ui_call(self.append_log, line)
        except Exception as error:
            self.ui_call(self.append_log, f"[Error: {error}]\n")
        exit_code = process.poll()
        self.running = False
        self.ui_call(self.append_log, f"\n[OpenClaw] Process ended (exit: {exit_code})\n")
        if on_exit:
            self.ui_call(on_exit, exit_code)

    def _kill_port_processes(self, port: int) -> int:
        try:
            result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            return 0
        pids: set[str] = set()
        marker = f":{port}"
        for line in result.stdout.splitlines():
            if marker not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if parts:
                pids.add(parts[-1])
        killed = 0
        for pid in pids:
            completed = subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, text=True)
            if completed.returncode == 0:
                killed += 1
        return killed

