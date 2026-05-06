"""OpenClaw gateway process management."""

from __future__ import annotations

import os
import json
import socket
import subprocess
import threading
import time
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

        killed = self._stop_registered_gateway()
        killed += self._kill_clawpanel_processes()
        killed += self._kill_openclaw_gateway_processes()
        killed += self._kill_port_processes(APP_PORT)
        if killed:
            self.append_log(f"[OpenClaw] Cleared {killed} stale gateway/listener process(es).\n")

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
        try:
            self._wait_until_ready(APP_PORT, timeout=120.0)
            self.append_log(f"[OpenClaw] Ready: http://127.0.0.1:{APP_PORT}\n")
        except Exception:
            self.append_log("[OpenClaw] Startup did not become ready; cleaning up process tree.\n")
            if self.process and self.process.poll() is None:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                    capture_output=True,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            self.running = False
            self.process = None
            raise

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
            killed = self._kill_openclaw_gateway_processes()
            killed += self._kill_port_processes(APP_PORT)
            self.running = False
            self.process = None
            return f"已清理 {killed} 个端口占用进程" if killed else "没有运行中的服务"
        return "服务未启动"

    def diagnose_environment(self) -> dict:
        """Return customer-facing environment checks for the launcher."""
        checks: list[dict] = []

        def file_check(check_id: str, label: str, path: str, required: bool = True) -> None:
            exists = os.path.exists(path)
            checks.append({
                "id": check_id,
                "label": label,
                "status": "ok" if exists else ("fail" if required else "warn"),
                "message": "已找到" if exists else ("缺失，可能导致启动失败" if required else "未找到，可在首次启动时自动生成"),
                "detail": path,
                "repairable": False,
            })

        file_check("base_path", "安装目录", self.paths.base_path)
        file_check("node", "Node.js 运行时", self.paths.node_exe)
        file_check("start_js", "OpenClaw 启动脚本", self.paths.find_file("start.js", ("back", "backup", "")))
        file_check("openclaw_core", "OpenClaw 本体", self.paths.openclaw_mjs)
        file_check("data_dir", "数据目录", self.paths.data_dir, required=False)
        file_check("openclaw_config", "OpenClaw 配置文件", self.paths.openclaw_config, required=False)

        port_listeners = self._port_listeners(APP_PORT)
        expected_pid = str(self.process.pid) if self.process and self.process.poll() is None else None
        unexpected = [item for item in port_listeners if str(item.get("pid")) != expected_pid]
        if port_listeners:
            checks.append({
                "id": "port_18790",
                "label": "本地端口 18790",
                "status": "ok" if expected_pid and not unexpected else "warn",
                "message": "当前服务正在监听" if expected_pid and not unexpected else "端口已被进程占用",
                "detail": "; ".join(self._format_process(item) for item in port_listeners),
                "repairable": not expected_pid or bool(unexpected),
            })
        else:
            checks.append({
                "id": "port_18790",
                "label": "本地端口 18790",
                "status": "ok",
                "message": "端口空闲，可启动服务",
                "detail": "127.0.0.1:18790",
                "repairable": False,
            })

        bridge_listeners = self._port_range_listeners(18791, 18950, exclude_pids={str(os.getpid())})
        checks.append({
            "id": "bridge_ports",
            "label": "Bridge 管理端口",
            "status": "warn" if bridge_listeners else "ok",
            "message": f"发现 {len(bridge_listeners)} 个旧 Bridge 占用" if bridge_listeners else "未发现旧 Bridge 占用",
            "detail": "; ".join(self._format_process(item) for item in bridge_listeners) or "127.0.0.1:18791-18950",
            "repairable": bool(bridge_listeners),
        })

        stale_gateways = self._openclaw_gateway_processes()
        clawpanels = self._clawpanel_processes()
        stale_count = len(stale_gateways) + len(clawpanels)
        checks.append({
            "id": "stale_process",
            "label": "残留 OpenClaw/ClawPanel 进程",
            "status": "warn" if stale_count else "ok",
            "message": f"发现 {stale_count} 个残留进程" if stale_count else "未发现残留进程",
            "detail": "; ".join(self._format_process(item) for item in (stale_gateways + clawpanels)) or "clean",
            "repairable": stale_count > 0,
        })

        version = self._openclaw_version()
        checks.append({
            "id": "openclaw_version",
            "label": "OpenClaw 版本",
            "status": "ok" if version != "unknown" else "warn",
            "message": version if version != "unknown" else "未能读取版本号",
            "detail": os.path.join(self.paths.base_path, "node_modules", "openclaw", "package.json"),
            "repairable": False,
        })

        return {
            "basePath": self.paths.base_path,
            "serviceRunning": self.running and self.process is not None and self.process.poll() is None,
            "servicePid": self.process.pid if self.process and self.process.poll() is None else None,
            "checks": checks,
        }

    def repair_environment(self) -> dict:
        """Clear stale runtime state that commonly blocks customer startup."""
        actions: list[dict] = []

        def record(label: str, count: int) -> None:
            actions.append({
                "label": label,
                "status": "ok",
                "message": f"已处理 {count} 项" if count else "无需处理",
                "count": count,
            })

        stopped_current = 0
        if self.process and self.process.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            self.running = False
            self.process = None
            stopped_current = 1
        record("停止当前 OpenClaw 服务", stopped_current)
        record("停止已注册的 OpenClaw Gateway 任务", self._stop_registered_gateway())
        record("清理 ClawPanel 残留进程", self._kill_clawpanel_processes())
        record("清理 OpenClaw Gateway 残留进程", self._kill_openclaw_gateway_processes())
        record("释放 18790 端口", self._kill_port_processes(APP_PORT))
        record("释放旧 Bridge 端口", self._kill_port_range_processes(18791, 18950, exclude_pids={str(os.getpid())}))

        created = 0
        for path in (
            self.paths.data_dir,
            self.paths.state_dir,
            os.path.dirname(self.paths.auth_profiles),
        ):
            if not os.path.isdir(path):
                os.makedirs(path, exist_ok=True)
                created += 1
        record("补齐基础数据目录", created)

        if not os.path.exists(self.paths.openclaw_config):
            with open(self.paths.openclaw_config, "w", encoding="utf-8") as handle:
                json.dump({
                    "gateway": {
                        "auth": {"mode": "none"},
                        "bind": "loopback",
                    }
                }, handle, ensure_ascii=False, indent=2)
            actions.append({
                "label": "重建 OpenClaw 基础配置",
                "status": "ok",
                "message": "已创建 data/.openclaw/openclaw.json",
                "count": 1,
            })

        return {
            "actions": actions,
            "diagnostics": self.diagnose_environment(),
        }

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
        stdout = result.stdout or ""
        for line in stdout.splitlines():
            if marker not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if parts:
                pids.add(parts[-1])
        killed = 0
        for pid in pids:
            if self._kill_pid(pid):
                killed += 1
        return killed

    def _kill_port_range_processes(self, start: int, end: int, exclude_pids: set[str] | None = None) -> int:
        exclude_pids = exclude_pids or set()
        listeners = self._port_range_listeners(start, end, exclude_pids=exclude_pids)
        pids = {str(item.get("pid")) for item in listeners if str(item.get("pid", "")).isdigit()}
        killed = 0
        for pid in pids:
            if pid in exclude_pids:
                continue
            if self._kill_pid(pid):
                killed += 1
        return killed

    def _stop_registered_gateway(self) -> int:
        completed = subprocess.run(
            ["schtasks", "/End", "/TN", "OpenClaw Gateway"],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return 1 if completed.returncode == 0 else 0

    def _port_listeners(self, port: int) -> list[dict[str, str]]:
        try:
            result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            return []
        pids: set[str] = set()
        marker = f":{port}"
        for line in (result.stdout or "").splitlines():
            if marker not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
        return self._describe_pids(pids)

    def _port_range_listeners(self, start: int, end: int, exclude_pids: set[str] | None = None) -> list[dict[str, str]]:
        exclude_pids = exclude_pids or set()
        try:
            result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            return []
        pids: set[str] = set()
        for line in (result.stdout or "").splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5 or not parts[-1].isdigit():
                continue
            local = parts[1]
            if any(local.endswith(f":{port}") for port in range(start, end + 1)) and parts[-1] not in exclude_pids:
                pids.add(parts[-1])
        return self._describe_pids(pids)

    def _clawpanel_processes(self) -> list[dict[str, str]]:
        command = (
            "$ErrorActionPreference='SilentlyContinue'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -ieq 'clawpanel.exe' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return []
        pids = {line.strip() for line in (result.stdout or "").splitlines() if line.strip().isdigit()}
        return self._describe_pids(pids)

    def _openclaw_gateway_processes(self) -> list[dict[str, str]]:
        command = (
            "$ErrorActionPreference='SilentlyContinue'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and "
            "$_.CommandLine -match 'openclaw' -and $_.CommandLine -match '\\bgateway\\b' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return []
        pids = {line.strip() for line in (result.stdout or "").splitlines() if line.strip().isdigit()}
        if self.process:
            pids.discard(str(self.process.pid))
        return self._describe_pids(pids)

    def _describe_pids(self, pids: set[str]) -> list[dict[str, str]]:
        processes: list[dict[str, str]] = []
        for pid in sorted(pids):
            if not pid.isdigit():
                continue
            command = (
                "$ErrorActionPreference='SilentlyContinue'; "
                f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\"; "
                "if ($p) { Write-Output ($p.ProcessId.ToString() + \"`t\" + $p.Name + \"`t\" + ($p.CommandLine -replace \"`r|`n\", \" \")) }"
            )
            try:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                    capture_output=True,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                continue
            for line in (result.stdout or "").splitlines():
                parts = line.split("\t", 2)
                if len(parts) >= 2:
                    processes.append({
                        "pid": parts[0],
                        "name": parts[1],
                        "command": parts[2] if len(parts) > 2 else "",
                    })
        return processes

    def _format_process(self, item: dict[str, str]) -> str:
        pid = item.get("pid", "?")
        name = item.get("name", "process")
        command = (item.get("command") or "").strip()
        if len(command) > 120:
            command = command[:117] + "..."
        return f"{name}({pid}) {command}".strip()

    def _openclaw_version(self) -> str:
        package_path = os.path.join(self.paths.base_path, "node_modules", "openclaw", "package.json")
        if not os.path.exists(package_path):
            return "unknown"
        try:
            with open(package_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return str(data.get("version") or "unknown")
        except Exception:
            return "unknown"

    def _kill_clawpanel_processes(self) -> int:
        command = (
            "$ErrorActionPreference='SilentlyContinue'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -ieq 'clawpanel.exe' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return 0
        pids = {line.strip() for line in (result.stdout or "").splitlines() if line.strip().isdigit()}
        killed = 0
        for pid in pids:
            if self._kill_pid(pid):
                killed += 1
        return killed

    def _kill_openclaw_gateway_processes(self) -> int:
        command = (
            "$ErrorActionPreference='SilentlyContinue'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and "
            "$_.CommandLine -match 'openclaw' -and $_.CommandLine -match '\\bgateway\\b' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return 0
        pids = {line.strip() for line in (result.stdout or "").splitlines() if line.strip().isdigit()}
        killed = 0
        for pid in pids:
            if self.process and str(self.process.pid) == pid:
                continue
            if self._kill_pid(pid):
                killed += 1
        return killed

    def _kill_pid(self, pid: str) -> bool:
        completed = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0

    def _wait_until_ready(self, port: int, timeout: float) -> None:
        deadline = time.time() + timeout
        next_log_at = time.time() + 10.0
        while time.time() < deadline:
            if self.process and self.process.poll() is not None:
                self.running = False
                raise RuntimeError("OpenClaw 启动后立即退出，请查看服务日志")
            if self._is_port_listening(port):
                return
            now = time.time()
            if now >= next_log_at:
                remaining = max(0, int(deadline - now))
                self.append_log(f"[OpenClaw] Waiting for 127.0.0.1:{port}... {remaining}s left\n")
                next_log_at = now + 10.0
            time.sleep(0.5)
        raise RuntimeError(f"OpenClaw 启动超时：端口 {port} 未就绪")

    def _is_port_listening(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            pass
        try:
            result = subprocess.run(["netstat", "-aon"], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            return False
        marker = f":{port}"
        return any(marker in line and "LISTENING" in line.upper() for line in (result.stdout or "").splitlines())
