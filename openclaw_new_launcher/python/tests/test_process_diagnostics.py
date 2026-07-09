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


class MinimalDiagnosticProcessService(OpenClawProcessService):
    def _storage_health_check(self, *, write_test: bool = False) -> dict:
        return {"id": "storage_health", "label": "storage", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _openclaw_config_check(self) -> dict:
        return {"id": "openclaw_config", "label": "config", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _webview2_check(self) -> dict:
        return {"id": "webview2", "label": "webview2", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _python_runtime_check(self) -> dict:
        return {"id": "python_runtime", "label": "python", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _portable_integrity_check(self) -> dict:
        return {"id": "portable_integrity", "label": "portable", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _security_software_block_check(self) -> dict:
        return {"id": "security_software_block", "label": "security", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _runtime_context_check(self) -> dict:
        return {"id": "runtime_context", "label": "runtime", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _phone_agent_apk_check(self) -> dict:
        return {"id": "phone_agent_apk", "label": "apk", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _member_gateway_check(self) -> dict:
        return {"id": "member_gateway", "label": "gateway", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _core_service_snapshot_check(self) -> dict:
        return {"id": "core_service_snapshot", "label": "core", "status": "ok", "message": "ok", "detail": "ok", "repairable": False}

    def _port_listeners(self, _port: int) -> list[dict]:
        return []

    def _port_range_listeners(self, _start_port: int, _end_port: int, *, exclude_pids=None) -> list[dict]:
        return []

    def _openclaw_gateway_processes(self) -> list[dict]:
        return []

    def _clawpanel_processes(self) -> list[dict]:
        return []

    def _detect_openclaw_version(self) -> str | None:
        return "test"


class ProcessDiagnosticsRepairTests(unittest.TestCase):
    def test_phone_adb_doctor_reports_missing_adb_with_repair_instructions(self) -> None:
        import services.process as process_module

        with tempfile.TemporaryDirectory() as temp_dir:
            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )

            original_which = process_module.shutil.which
            process_module.shutil.which = lambda name: None if name in {"adb", "adb.exe"} else original_which(name)
            try:
                result = service.phone_adb_doctor()
            finally:
                process_module.shutil.which = original_which

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "missing_adb")
        self.assertIn("platform-tools", " ".join(result["instructions"]))

    def test_phone_adb_doctor_wakes_and_launches_apkclaw_when_device_is_ready(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], _timeout_sec: int) -> FakeCompletedProcess:
            calls.append(command)
            if command[1:] == ["devices", "-l"]:
                return FakeCompletedProcess(returncode=0, stdout="List of devices attached\nemulator-5554\tdevice product:sdk\n")
            return FakeCompletedProcess(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as temp_dir:
            adb_dir = os.path.join(temp_dir, "platform-tools")
            os.makedirs(adb_dir)
            adb_path = os.path.join(adb_dir, "adb.exe")
            with open(adb_path, "wb") as file:
                file.write(b"fake adb")

            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=fake_runner,
            )

            result = service.phone_adb_doctor(serial="emulator-5554")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        flattened = [" ".join(command) for command in calls]
        self.assertTrue(any("KEYCODE_WAKEUP" in command for command in flattened))
        self.assertTrue(any("KEYCODE_HOME" in command for command in flattened))
        self.assertTrue(any("monkey -p com.apk.claw.android" in command for command in flattened))

    def test_phone_adb_doctor_does_not_fallback_to_wrong_device_when_serial_is_missing(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], _timeout_sec: int) -> FakeCompletedProcess:
            calls.append(command)
            if command[1:] == ["devices", "-l"]:
                return FakeCompletedProcess(returncode=0, stdout="List of devices attached\nphone-a\tdevice product:test\n")
            return FakeCompletedProcess(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as temp_dir:
            adb_dir = os.path.join(temp_dir, "platform-tools")
            os.makedirs(adb_dir)
            with open(os.path.join(adb_dir, "adb.exe"), "wb") as file:
                file.write(b"fake adb")

            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=fake_runner,
            )

            result = service.phone_adb_doctor(serial="phone-b")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "device_not_found")
        flattened = [" ".join(command) for command in calls]
        self.assertFalse(any("KEYCODE_WAKEUP" in command for command in flattened))
        self.assertFalse(any("monkey -p" in command for command in flattened))

    def test_phone_adb_doctor_requires_serial_when_multiple_devices_exist(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str], _timeout_sec: int) -> FakeCompletedProcess:
            calls.append(command)
            if command[1:] == ["devices", "-l"]:
                return FakeCompletedProcess(
                    returncode=0,
                    stdout="List of devices attached\nphone-a\tdevice product:test\nphone-b\tdevice product:test\n",
                )
            return FakeCompletedProcess(returncode=0, stdout="")

        with tempfile.TemporaryDirectory() as temp_dir:
            adb_dir = os.path.join(temp_dir, "platform-tools")
            os.makedirs(adb_dir)
            with open(os.path.join(adb_dir, "adb.exe"), "wb") as file:
                file.write(b"fake adb")

            service = TestableProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=fake_runner,
            )

            result = service.phone_adb_doctor()

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "multiple_devices")
        self.assertEqual([device["serial"] for device in result["devices"]], ["phone-a", "phone-b"])
        flattened = [" ".join(command) for command in calls]
        self.assertFalse(any("KEYCODE_WAKEUP" in command for command in flattened))
        self.assertFalse(any("monkey -p" in command for command in flattened))

    def test_diagnostics_use_system_node_and_npm_as_prerequisite_fallback(self) -> None:
        import services.process as process_module

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MinimalDiagnosticProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )
            fake_tools = {
                "node": os.path.join(temp_dir, "system-node", "node.exe"),
                "node.exe": os.path.join(temp_dir, "system-node", "node.exe"),
                "npm": os.path.join(temp_dir, "system-node", "npm.cmd"),
                "npm.cmd": os.path.join(temp_dir, "system-node", "npm.cmd"),
            }

            original_which = process_module.shutil.which
            process_module.shutil.which = lambda name: fake_tools.get(name) or original_which(name)
            try:
                checks = {item["id"]: item for item in service.diagnose_environment()["checks"]}
            finally:
                process_module.shutil.which = original_which

        self.assertEqual(checks["node"]["status"], "ok")
        self.assertIn("system-node", checks["node"]["detail"])
        self.assertEqual(checks["npm"]["status"], "ok")
        self.assertIn("system-node", checks["npm"]["detail"])

    def test_diagnostics_mark_node_and_npm_repairable_when_no_runtime_exists(self) -> None:
        import services.process as process_module

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MinimalDiagnosticProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )

            original_which = process_module.shutil.which
            process_module.shutil.which = lambda name: None if name in {"node", "node.exe", "npm", "npm.cmd", "npm.exe"} else original_which(name)
            try:
                checks = {item["id"]: item for item in service.diagnose_environment()["checks"]}
            finally:
                process_module.shutil.which = original_which

        self.assertEqual(checks["node"]["status"], "fail")
        self.assertTrue(checks["node"]["repairable"])
        self.assertEqual(checks["npm"]["status"], "fail")
        self.assertTrue(checks["npm"]["repairable"])

    def test_diagnostics_mark_git_git_bash_and_uv_repairable_for_blank_windows_user(self) -> None:
        import services.process as process_module

        with tempfile.TemporaryDirectory() as temp_dir:
            service = MinimalDiagnosticProcessService(
                AppPaths(temp_dir),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )

            original_which = process_module.shutil.which
            old_program_files = os.environ.get("ProgramFiles")
            old_program_files_x86 = os.environ.get("ProgramFiles(x86)")
            os.environ["ProgramFiles"] = os.path.join(temp_dir, "ProgramFiles")
            os.environ["ProgramFiles(x86)"] = os.path.join(temp_dir, "ProgramFilesX86")
            process_module.shutil.which = (
                lambda name: None
                if name in {"git", "git.exe", "bash", "bash.exe", "uv", "uv.exe"}
                else original_which(name)
            )
            try:
                checks = {item["id"]: item for item in service.diagnose_environment()["checks"]}
            finally:
                process_module.shutil.which = original_which
                if old_program_files is None:
                    os.environ.pop("ProgramFiles", None)
                else:
                    os.environ["ProgramFiles"] = old_program_files
                if old_program_files_x86 is None:
                    os.environ.pop("ProgramFiles(x86)", None)
                else:
                    os.environ["ProgramFiles(x86)"] = old_program_files_x86

        self.assertEqual(checks["git"]["status"], "fail")
        self.assertTrue(checks["git"]["repairable"])
        self.assertEqual(checks["git_bash"]["status"], "fail")
        self.assertTrue(checks["git_bash"]["repairable"])
        self.assertEqual(checks["uv"]["status"], "warn")
        self.assertTrue(checks["uv"]["repairable"])

    def test_diagnostics_find_git_bash_next_to_custom_git_path(self) -> None:
        import services.process as process_module

        with tempfile.TemporaryDirectory() as temp_dir:
            git_root = os.path.join(temp_dir, "CustomGit")
            git_cmd = os.path.join(git_root, "cmd")
            git_bin = os.path.join(git_root, "bin")
            os.makedirs(git_cmd)
            os.makedirs(git_bin)
            git_exe = os.path.join(git_cmd, "git.exe")
            bash_exe = os.path.join(git_bin, "bash.exe")
            with open(git_exe, "wb") as file:
                file.write(b"git")
            with open(bash_exe, "wb") as file:
                file.write(b"bash")

            service = MinimalDiagnosticProcessService(
                AppPaths(os.path.join(temp_dir, "app")),
                append_log=lambda _text: None,
                ui_call=lambda *_args: None,
                command_runner=lambda _command, _timeout_sec: FakeCompletedProcess(returncode=0),
            )

            original_which = process_module.shutil.which
            process_module.shutil.which = (
                lambda name: git_exe
                if name in {"git", "git.exe"}
                else None if name in {"bash", "bash.exe", "uv", "uv.exe"} else original_which(name)
            )
            try:
                checks = {item["id"]: item for item in service.diagnose_environment()["checks"]}
            finally:
                process_module.shutil.which = original_which

        self.assertEqual(checks["git"]["status"], "ok")
        self.assertEqual(checks["git_bash"]["status"], "ok")
        self.assertIn("CustomGit", checks["git_bash"]["detail"])

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

    def test_portable_integrity_accepts_packaged_up_scripts_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            required_files = [
                os.path.join("_up_", "node-runtime", "node.exe"),
                "start.js",
                os.path.join("_up_", "python", "bridge.py"),
                os.path.join("_up_", "scripts", "openclaw-image-phone.mjs"),
                os.path.join("_up_", "scripts", "openclaw-phone-video.mjs"),
                os.path.join("_up_", "scripts", "openclaw-phone-vision.mjs"),
                os.path.join("_up_", "scripts", "verify-phone-agent.ps1"),
                os.path.join("_up_", "openclaw-workspace", "AGENTS.md"),
                os.path.join("_up_", "openclaw-workspace", "SOUL.md"),
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
