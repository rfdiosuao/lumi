"""OpenClaw gateway process management."""

from __future__ import annotations

import os
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable

from core.constants import APP_PORT
from core.paths import AppPaths

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

        storage_check = self._storage_health_check(write_test=True)
        if storage_check["status"] == "fail":
            raise RuntimeError(
                "运行磁盘/U盘检测失败："
                f"{storage_check['message']}\n{storage_check.get('detail', '')}\n"
                "请先重新插拔U盘、备份数据，或把安装包复制到健康磁盘后再启动。"
            )
        if storage_check["status"] == "warn":
            self.append_log(
                "[OpenClaw] Storage warning: "
                f"{storage_check['message']} | {storage_check.get('detail', '')}\n"
            )

        killed = self._stop_registered_gateway()
        killed += self._kill_clawpanel_processes()
        killed += self._kill_openclaw_gateway_processes()
        killed += self._kill_port_processes(APP_PORT)
        if killed:
            self.append_log(f"[OpenClaw] Cleared {killed} stale gateway/listener process(es).\n")

        config_changed, config_backup = self._ensure_openclaw_config()
        if config_changed:
            if config_backup:
                self.append_log(f"[OpenClaw] Rebuilt invalid openclaw.json, backup: {config_backup}\n")
            else:
                self.append_log("[OpenClaw] Rebuilt or normalized openclaw.json.\n")

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

        def file_check(check_id: str, label: str, path: str, required: bool = True, repairable: bool = False) -> None:
            exists = os.path.exists(path)
            checks.append({
                "id": check_id,
                "label": label,
                "status": "ok" if exists else ("fail" if required else "warn"),
                "message": "已找到" if exists else ("缺失，可能导致启动失败" if required else "未找到，一键修复会尝试补齐"),
                "detail": path,
                "repairable": repairable and not exists,
            })

        file_check("base_path", "安装目录", self.paths.base_path)
        checks.append(self._storage_health_check(write_test=True))
        file_check("node", "Node.js 运行时", self.paths.node_exe)
        file_check("start_js", "OpenClaw 启动脚本", self.paths.find_file("start.js", ("back", "backup", "")))
        file_check("openclaw_core", "OpenClaw 本体", self.paths.openclaw_mjs)
        file_check("data_dir", "数据目录", self.paths.data_dir, required=False, repairable=True)
        checks.append(self._openclaw_config_check())

        port_listeners = self._port_listeners(APP_PORT)
        expected_pid = str(self.process.pid) if self.process and self.process.poll() is None else None
        unexpected = [item for item in port_listeners if str(item.get("pid")) != expected_pid]
        if port_listeners:
            checks.append({
                "id": "port_18790",
                "label": "本地端口 18790",
                "status": "ok" if expected_pid and not unexpected else "warn",
                "message": "当前服务正在监听" if expected_pid and not unexpected else "端口被其他进程占用，一键修复可释放",
                "detail": "; ".join(self._format_process(item) for item in port_listeners),
                "repairable": not expected_pid or bool(unexpected),
            })
        else:
            checks.append({
                "id": "port_18790",
                "label": "本地端口 18790",
                "status": "ok",
                "message": "端口空闲，可以启动服务",
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
            "detail": os.path.join(os.path.dirname(self.paths.openclaw_mjs), "package.json"),
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
            if self._kill_pid(str(self.process.pid)):
                stopped_current = 1
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            self.running = False
            self.process = None
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

        config_changed, config_backup = self._ensure_openclaw_config()
        actions.append({
            "label": "修复 OpenClaw 基础配置",
            "status": "ok",
            "message": (
                f"已备份损坏配置并重建：{config_backup}"
                if config_backup else
                ("已补齐/重建 openclaw.json" if config_changed else "无需处理")
            ),
            "count": 1 if config_changed else 0,
        })

        storage_check = self._storage_health_check(write_test=True)
        actions.append({
            "label": "检测运行磁盘 / U盘健康",
            "status": storage_check["status"],
            "message": storage_check["message"],
            "count": 0,
        })

        return {
            "actions": actions,
            "diagnostics": self.diagnose_environment(),
        }

    @staticmethod
    def _default_openclaw_config() -> dict:
        return {
            "gateway": {
                "auth": {"mode": "none"},
                "bind": "loopback",
            }
        }

    def _openclaw_config_check(self) -> dict:
        path = self.paths.openclaw_config
        if not os.path.exists(path):
            return {
                "id": "openclaw_config",
                "label": "OpenClaw 基础配置",
                "status": "warn",
                "message": "配置文件缺失，一键修复或启动服务时会自动重建",
                "detail": path,
                "repairable": True,
            }
        try:
            config = self._read_openclaw_config()
            if self._normalize_openclaw_config(config):
                return {
                    "id": "openclaw_config",
                    "label": "OpenClaw 基础配置",
                    "status": "warn",
                    "message": "配置文件可读取，但缺少基础 gateway 配置",
                    "detail": path,
                    "repairable": True,
                }
            return {
                "id": "openclaw_config",
                "label": "OpenClaw 基础配置",
                "status": "ok",
                "message": "配置文件格式正常",
                "detail": path,
                "repairable": False,
            }
        except Exception as error:
            return {
                "id": "openclaw_config",
                "label": "OpenClaw 基础配置",
                "status": "fail",
                "message": "配置文件格式损坏，一键修复会备份后重建",
                "detail": f"{path} ({error})",
                "repairable": True,
            }

    def _read_openclaw_config(self) -> dict:
        with open(self.paths.openclaw_config, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("root value is not an object")
        return config

    def _normalize_openclaw_config(self, config: dict) -> bool:
        changed = False
        gateway = config.get("gateway")
        if not isinstance(gateway, dict):
            gateway = {}
            config["gateway"] = gateway
            changed = True
        auth = gateway.get("auth")
        if not isinstance(auth, dict):
            auth = {}
            gateway["auth"] = auth
            changed = True
        if not auth.get("mode"):
            auth["mode"] = "none"
            changed = True
        if not gateway.get("bind"):
            gateway["bind"] = "loopback"
            changed = True
        return changed

    def _write_openclaw_config(self, config: dict) -> None:
        os.makedirs(os.path.dirname(self.paths.openclaw_config), exist_ok=True)
        with open(self.paths.openclaw_config, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)

    def _backup_invalid_openclaw_config(self) -> str | None:
        path = self.paths.openclaw_config
        if not os.path.exists(path):
            return None
        backup = f"{path}.bad-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            os.replace(path, backup)
            return backup
        except OSError:
            return None

    def _ensure_openclaw_config(self) -> tuple[bool, str | None]:
        if not os.path.exists(self.paths.openclaw_config):
            self._write_openclaw_config(self._default_openclaw_config())
            return True, None
        try:
            config = self._read_openclaw_config()
        except Exception:
            backup = self._backup_invalid_openclaw_config()
            self._write_openclaw_config(self._default_openclaw_config())
            return True, backup
        if self._normalize_openclaw_config(config):
            self._write_openclaw_config(config)
            return True, None
        return False, None

    def _storage_health_check(self, write_test: bool = False) -> dict:
        root = self._drive_root()
        detail_parts = [
            f"运行目录: {self.paths.base_path}",
            f"磁盘: {root}",
        ]
        problems: list[str] = []
        warnings: list[str] = []

        if not os.path.isdir(self.paths.base_path):
            return {
                "id": "storage_health",
                "label": "运行磁盘 / U盘健康",
                "status": "fail",
                "message": "安装目录不可访问",
                "detail": self.paths.base_path,
                "repairable": False,
            }

        drive_type = self._drive_type_label(root)
        if drive_type:
            detail_parts.append(f"类型: {drive_type}")
            if drive_type == "不可访问":
                problems.append("磁盘不可访问")

        try:
            usage = shutil.disk_usage(root if root and os.path.exists(root) else self.paths.base_path)
            free_mb = usage.free / (1024 * 1024)
            detail_parts.append(f"可用空间: {free_mb:.0f} MB")
            if free_mb < 256:
                problems.append("可用空间低于 256MB")
            elif free_mb < 1024:
                warnings.append("可用空间低于 1GB")
        except Exception as error:
            warnings.append(f"无法读取剩余空间: {error}")

        if write_test:
            probe_path = ""
            try:
                probe_dir = self.paths.launcher_dir
                os.makedirs(probe_dir, exist_ok=True)
                fd, probe_path = tempfile.mkstemp(prefix=".lumi-disk-check-", suffix=".tmp", dir=probe_dir)
                payload = f"lumi-disk-check:{time.time()}".encode("utf-8")
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                with open(probe_path, "rb") as handle:
                    if handle.read() != payload:
                        raise OSError("写入后读回内容不一致")
                os.remove(probe_path)
                detail_parts.append("读写测试: 通过")
            except Exception as error:
                problems.append(f"读写测试失败: {error}")
                detail_parts.append("读写测试: 失败")
            finally:
                if probe_path and os.path.exists(probe_path):
                    try:
                        os.remove(probe_path)
                    except OSError:
                        pass

        if problems:
            status = "fail"
            message = "；".join(problems)
        elif warnings:
            status = "warn"
            message = "；".join(warnings)
        else:
            status = "ok"
            message = "运行磁盘可访问，读写测试正常" if write_test else "运行磁盘可访问"

        return {
            "id": "storage_health",
            "label": "运行磁盘 / U盘健康",
            "status": status,
            "message": message,
            "detail": "；".join(detail_parts),
            "repairable": False,
        }

    def _drive_root(self) -> str:
        absolute = os.path.abspath(self.paths.base_path)
        drive, _ = os.path.splitdrive(absolute)
        if drive:
            return f"{drive}\\"
        return absolute

    @staticmethod
    def _drive_type_label(root: str) -> str:
        if os.name != "nt":
            return "当前系统磁盘"
        try:
            import ctypes

            drive_type = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        except Exception:
            return "未知"
        return {
            0: "未知",
            1: "不可访问",
            2: "可移动磁盘",
            3: "本地磁盘",
            4: "网络磁盘",
            5: "光盘",
            6: "内存盘",
        }.get(drive_type, f"类型 {drive_type}")

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
