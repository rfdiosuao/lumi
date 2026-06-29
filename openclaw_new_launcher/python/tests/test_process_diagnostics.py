from __future__ import annotations

import os
import sys
import tempfile
import unittest
from dataclasses import dataclass


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.paths import AppPaths
from services.process import OpenClawProcessService


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class TestableProcessService(OpenClawProcessService):
    def _stop_registered_gateway(self) -> int:
        return 0

    def _kill_clawpanel_processes(self) -> int:
        return 0

    def _kill_openclaw_gateway_processes(self) -> int:
        return 0

    def _kill_port_processes(self, _port: int) -> int:
        return 0

    def _kill_port_range_processes(self, _start_port: int, _end_port: int, *, exclude_pids=None) -> int:
        return 0

    def _storage_health_check(self, *, write_test: bool = False) -> dict:
        return {
            "id": "storage",
            "label": "运行磁盘 / U盘健康",
            "status": "ok",
            "message": "写入测试通过",
            "detail": "test",
            "repairable": False,
        }

    def diagnose_environment(self) -> dict:
        return {
            "basePath": self.paths.base_path,
            "serviceRunning": False,
            "servicePid": None,
            "checks": [
                self._webview2_check(),
                {
                    "id": "node",
                    "label": "Node.js 运行时",
                    "status": "fail",
                    "message": "缺失，可能导致启动失败",
                    "detail": os.path.join(self.paths.base_path, "node", "node.exe"),
                    "repairable": False,
                },
                {
                    "id": "python_runtime",
                    "label": "Python / Bridge 运行时",
                    "status": "fail",
                    "message": "未找到 Python 运行时，Bridge 无法启动",
                    "detail": os.path.join(self.paths.base_path, "_up_", "python-runtime", "python.exe"),
                    "repairable": False,
                },
                {
                    "id": "git",
                    "label": "Git",
                    "status": "warn",
                    "message": "未找到；部分编程智能体的仓库能力会受限",
                    "detail": "Git for Windows",
                    "repairable": False,
                },
                {
                    "id": "uv",
                    "label": "uv",
                    "status": "warn",
                    "message": "未找到；Python 组件安装会使用备用流程",
                    "detail": "Python uv package manager",
                    "repairable": False,
                },
            ],
        }


class ProcessDiagnosticsRepairTests(unittest.TestCase):
    def test_portable_integrity_allows_online_package_without_openclaw_runtime_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            required_files = [
                os.path.join("node", "node.exe"),
                "start.js",
                os.path.join("_up_", "python", "bridge.py"),
                os.path.join("scripts", "openclaw-image-phone.mjs"),
                os.path.join("scripts", "openclaw-phone-video.mjs"),
                os.path.join("scripts", "openclaw-phone-vision.mjs"),
                os.path.join("scripts", "verify-phone-agent.ps1"),
                os.path.join("data", ".openclaw", "workspace", "AGENTS.md"),
                os.path.join("data", ".openclaw", "workspace", "SOUL.md"),
            ]
            for relative_path in required_files:
                full_path = os.path.join(temp_dir, relative_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as file:
                    file.write(b"ok")

            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )

            result = service._portable_integrity_check()

            self.assertEqual(result["status"], "ok")
            self.assertNotIn("openclaw.mjs", result["detail"])

    def test_repair_runs_bundled_webview2_installer_when_missing(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], _timeout_sec: int) -> FakeCompletedProcess:
            calls.append(command)
            return FakeCompletedProcess(returncode=0)

        with tempfile.TemporaryDirectory() as temp_dir:
            redist_dir = os.path.join(temp_dir, "redist")
            os.makedirs(redist_dir)
            installer = os.path.join(redist_dir, "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
            with open(installer, "wb") as file:
                file.write(b"fake webview2 installer")

            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=fake_runner,
            )
            service._webview2_check = lambda: {
                "id": "webview2",
                "label": "WebView2 Runtime",
                "status": "fail",
                "message": "未检测到 WebView2 Runtime，启动器窗口可能白屏或无法渲染",
                "detail": f"offline installer: {installer}",
                "repairable": True,
            }

            result = service.repair_environment()

            self.assertIn([installer, "/silent", "/install"], calls)
            webview_action = next(action for action in result["actions"] if action["label"] == "安装 WebView2 Runtime")
            self.assertEqual(webview_action["status"], "ok")
            self.assertIn("离线安装器", webview_action["message"])

    def test_repair_warns_when_critical_prerequisites_need_a_complete_portable_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )
            service._webview2_check = lambda: {
                "id": "webview2",
                "label": "WebView2 Runtime",
                "status": "ok",
                "message": "已检测到 WebView2 Runtime",
                "detail": "test",
                "repairable": False,
            }

            result = service.repair_environment()

            source_action = next(action for action in result["actions"] if action["label"] == "前置环境离线源检查")
            self.assertEqual(source_action["status"], "warn")
            self.assertIn("完整 LOOM 离线包", source_action["message"])
            self.assertIn("Node.js", source_action["message"])
            self.assertIn("Python", source_action["message"])
            self.assertIn("Git", source_action["message"])

    def test_repair_installs_missing_public_prerequisites_with_winget_and_uv(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], _timeout_sec: int) -> FakeCompletedProcess:
            calls.append(command)
            return FakeCompletedProcess(returncode=0, stdout="ok")

        with tempfile.TemporaryDirectory() as temp_dir:
            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=fake_runner,
            )
            service._webview2_check = lambda: {
                "id": "webview2",
                "label": "WebView2 Runtime",
                "status": "ok",
                "message": "已检测到 WebView2 Runtime",
                "detail": "test",
                "repairable": False,
            }

            result = service.repair_environment()

            self.assertIn(["winget", "--version"], calls)
            self.assertIn(
                [
                    "winget",
                    "install",
                    "--id",
                    "Git.Git",
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ],
                calls,
            )
            self.assertIn(
                [
                    "winget",
                    "install",
                    "--id",
                    "OpenJS.NodeJS.LTS",
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ],
                calls,
            )
            self.assertIn(
                [
                    "winget",
                    "install",
                    "--id",
                    "Python.Python.3.11",
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ],
                calls,
            )
            self.assertIn(
                [
                    "winget",
                    "install",
                    "--id",
                    "astral-sh.uv",
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ],
                calls,
            )
            self.assertFalse(any("irm" in " ".join(command).lower() or "iex" in " ".join(command).lower() for command in calls))
            action = next(action for action in result["actions"] if action["label"] == "安装公共前置环境")
            self.assertEqual(action["status"], "ok")


if __name__ == "__main__":
    unittest.main()
