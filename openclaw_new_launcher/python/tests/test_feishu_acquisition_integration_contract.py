from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

REPO_ROOT = os.path.dirname(PYTHON_DIR)


class FeishuAcquisitionIntegrationContractTests(unittest.TestCase):
    def test_doctor_reports_missing_cli_without_installing(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "",
            )
            doctor = integration.doctor()
            install = integration.install_cli(confirmed=False)

        self.assertFalse(doctor["cli"]["installed"])
        self.assertEqual(doctor["cli"]["installCommand"], "npm install -g @larksuite/cli@latest")
        self.assertTrue(install["requiresConfirmation"])
        self.assertFalse(install["executed"])

    def test_login_guide_uses_non_blocking_device_flow_and_qr_payload(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        calls: list[list[str]] = []

        def fake_runner(args: list[str], **_kwargs):
            calls.append(args)
            if args[:3] == ["lark-cli", "auth", "login"]:
                return {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "verification_uri": "https://example.feishu.cn/device",
                            "verification_uri_complete": "https://example.feishu.cn/device?code=ABCD",
                            "user_code": "ABCD",
                            "device_code": "device-secret",
                        }
                    ),
                    "stderr": "",
                }
            if args[:3] == ["lark-cli", "auth", "qrcode"]:
                return {"returncode": 0, "stdout": "ASCII-QR", "stderr": ""}
            return {"returncode": 0, "stdout": "{}", "stderr": ""}

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "lark-cli",
                runner=fake_runner,
            )
            guide = integration.start_login()

        self.assertIn(["lark-cli", "auth", "login", "--recommend", "--no-wait", "--json"], calls)
        self.assertEqual(guide["loginUrl"], "https://example.feishu.cn/device?code=ABCD")
        self.assertEqual(guide["userCode"], "ABCD")
        self.assertIn("ASCII-QR", guide["qrAscii"])
        serialized = json.dumps(guide, ensure_ascii=False)
        self.assertNotIn("device-secret", serialized)

    def test_bind_table_and_status_are_local_and_redacted(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        def fake_runner(args: list[str], **_kwargs):
            if args[:3] == ["lark-cli", "auth", "status"]:
                return {"returncode": 0, "stdout": '{"identities":{"user":{"available":true,"status":"ready"},"bot":{"available":true,"status":"ready"}}}', "stderr": ""}
            return {"returncode": 0, "stdout": "{}", "stderr": ""}

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "lark-cli",
                runner=fake_runner,
            )
            bound = integration.bind_table(
                {
                    "url": "https://example.feishu.cn/base/appABC?table=tblXYZ&token=secret-token",
                    "baseToken": "appABC",
                    "tableId": "tblXYZ",
                }
            )
            status = integration.status()

        serialized = json.dumps({"bound": bound, "status": status}, ensure_ascii=False)
        self.assertTrue(status["connected"])
        self.assertEqual(status["table"]["baseToken"], "appABC")
        self.assertEqual(status["table"]["tableId"], "tblXYZ")
        self.assertNotIn("secret-token", serialized)

    def test_status_requires_user_login_for_user_scoped_table_writes(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        def fake_runner(args: list[str], **_kwargs):
            if args[:3] == ["lark-cli", "auth", "status"]:
                return {"returncode": 0, "stdout": '{"identities":{"bot":{"available":true,"status":"ready"}},"identity":"bot"}', "stderr": ""}
            return {"returncode": 0, "stdout": "{}", "stderr": ""}

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "lark-cli",
                runner=fake_runner,
            )
            bound = integration.bind_table({"baseToken": "appABC", "tableId": "tblXYZ", "url": "https://example.feishu.cn/base/appABC"})
            status = integration.status()

        self.assertFalse(bound["status"]["connected"])
        self.assertFalse(status["connected"])
        self.assertTrue(status["auth"]["botReady"])
        self.assertFalse(status["auth"]["loggedIn"])

    def test_write_success_marks_local_lead_synced(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        def fake_runner(args: list[str], **_kwargs):
            if args[:3] == ["lark-cli", "auth", "status"]:
                return {"returncode": 0, "stdout": '{"identities":{"user":{"available":true,"status":"ready"}}}', "stderr": ""}
            self.assertIn("+record-upsert", args)
            self.assertIn("--base-token", args)
            self.assertIn("--table-id", args)
            return {"returncode": 0, "stdout": '{"record_id":"rec123"}', "stderr": ""}

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "lark-cli",
                runner=fake_runner,
            )
            integration.bind_table({"baseToken": "appABC", "tableId": "tblXYZ", "url": "https://example.feishu.cn/base/appABC"})
            result = integration.sync_lead({"leadId": "lead_1", "platform": "douyin", "title": "客户", "summary": "需要方案"})

        self.assertEqual(result["syncStatus"], "synced")
        self.assertEqual(result["recordId"], "rec123")

    def test_write_failure_keeps_pending_local_cache_without_sensitive_values(self) -> None:
        from core.feishu_integration import FeishuAcquisitionIntegration
        from core.paths import AppPaths

        def fake_runner(_args: list[str], **_kwargs):
            if _args[:3] == ["lark-cli", "auth", "status"]:
                return {"returncode": 0, "stdout": '{"identities":{"user":{"available":true,"status":"ready"}}}', "stderr": ""}
            return {"returncode": 1, "stdout": "", "stderr": "Bearer secret-token failed"}

        with tempfile.TemporaryDirectory() as temp_dir:
            integration = FeishuAcquisitionIntegration(
                AppPaths(base_path=temp_dir),
                command_resolver=lambda _name: "lark-cli",
                runner=fake_runner,
            )
            integration.bind_table({"baseToken": "appABC", "tableId": "tblXYZ", "url": "https://example.feishu.cn/base/appABC"})
            result = integration.sync_lead({"leadId": "lead_1", "platform": "douyin", "summary": "手机号 13800000000 Bearer secret-token"})
            cached = integration.pending_syncs()

        serialized = json.dumps({"result": result, "cached": cached}, ensure_ascii=False)
        self.assertEqual(result["syncStatus"], "sync_failed")
        self.assertEqual(cached[0]["leadId"], "lead_1")
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("13800000000", serialized)

    def test_acquisition_demo_flow_uses_pending_sync_when_feishu_unbound(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            flow = matrix.create_acquisition_demo_flow({"topic": "飞书线索", "leadSummary": "用户需要报价"})
            snapshot = matrix.acquisition_snapshot()

        self.assertEqual(flow["lead"]["syncStatus"], "pending_sync")
        self.assertEqual(snapshot["stats"]["pendingSync"], 1)
        self.assertIn("feishu", snapshot["integrations"])

    def test_loom_cli_exposes_integration_feishu_dry_run_commands(self) -> None:
        from loom_cli import dispatch

        cases = [
            (["integration", "feishu", "doctor", "--json", "--dry-run"], "GET", "/api/matrix/acquisition/feishu/doctor"),
            (["integration", "feishu", "status", "--json", "--dry-run"], "GET", "/api/matrix/acquisition/feishu/status"),
            (["integration", "feishu", "login", "--permission", "control", "--json", "--dry-run"], "POST", "/api/matrix/acquisition/feishu/login"),
            (["integration", "feishu", "bind-table", "--base-token", "appABC", "--table-id", "tblXYZ", "--permission", "control", "--json", "--dry-run"], "POST", "/api/matrix/acquisition/feishu/bind-table"),
            (["integration", "feishu", "test-write", "--permission", "control", "--json", "--dry-run"], "POST", "/api/matrix/acquisition/feishu/test-write"),
        ]

        for argv, method, endpoint in cases:
            with self.subTest(argv=argv):
                code, payload = dispatch(argv)

                self.assertEqual(code, 0)
                self.assertEqual(payload["data"]["method"], method)
                self.assertEqual(payload["data"]["endpoint"], endpoint)

    def test_ui_and_prompt_surface_include_feishu_sync_policy(self) -> None:
        page_path = os.path.join(REPO_ROOT, "src", "components", "acquisition", "AcquisitionWorkbenchPage.tsx")
        api_path = os.path.join(REPO_ROOT, "src", "services", "api.ts")
        skill_path = os.path.join(REPO_ROOT, "public", "skills", "loom-command-brain", "SKILL.md")

        with open(page_path, "r", encoding="utf-8") as handle:
            page = handle.read()
        with open(api_path, "r", encoding="utf-8") as handle:
            api = handle.read()
        with open(skill_path, "r", encoding="utf-8") as handle:
            skill = handle.read()

        for marker in [
            "data-acquisition-feishu-sync",
            "连接飞书",
            "扫码登录",
            "绑定线索表",
            "测试写入",
            "最近同步",
            "失败原因",
        ]:
            self.assertIn(marker, page)
        self.assertIn("feishuApi", api)
        self.assertIn("飞书线索表", skill)
        self.assertIn("先调用麓鸣集成检查", skill)
        self.assertIn("自动记录线索可以默认执行", skill)


if __name__ == "__main__":
    unittest.main()
