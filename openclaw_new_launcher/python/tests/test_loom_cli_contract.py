from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER_DIR = os.path.dirname(PYTHON_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


class LoomCliContractTests(unittest.TestCase):
    def test_status_command_returns_structured_json_payload(self) -> None:
        from loom_cli import dispatch

        with tempfile.TemporaryDirectory() as temp_dir:
            code, payload = dispatch(["status", "--json"], base_path=temp_dir)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "status")
        self.assertIn("data", payload)

    def test_commands_catalog_is_machine_readable(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["commands", "--json"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        catalog = payload["data"]
        self.assertEqual(catalog["schema"], "loom.cli.catalog.v1")
        self.assertGreaterEqual(catalog["commandCount"], 50)
        domains = {item["domain"] for item in catalog["domains"]}
        self.assertIn("account", domains)
        self.assertIn("media", domains)
        self.assertIn("matrix", domains)
        self.assertIn("--dry-run", json.dumps(catalog, ensure_ascii=False))

    def test_commands_catalog_teaches_codex_command_brain_workflow(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["commands", "--json"])

        self.assertEqual(code, 0)
        brain = payload["data"]["codexCommandBrain"]
        self.assertEqual(brain["schema"], "loom.codex_command_brain.v1")
        self.assertEqual(brain["roles"]["codex"], "Command Brain")
        self.assertEqual(brain["roles"]["singlePhone"], "Phone Worker")
        self.assertIn("matrix status", brain["workflows"]["matrixDispatch"])
        self.assertIn("matrix watch", brain["workflows"]["matrixDispatch"])
        self.assertIn("logs ledger", brain["workflows"]["matrixDispatch"])
        self.assertIn("phone adb-doctor", brain["recovery"]["adb"])
        self.assertIn("experience report", brain["experienceLoop"])

    def test_unknown_command_returns_structured_error(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["does-not-exist", "--json"])

        self.assertNotEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "unknown_command")
        self.assertIn("message", payload["error"])

    def test_admin_agent_install_is_denied_without_permission(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["agents", "install", "--component", "codex-desktop", "--json", "--dry-run"])

        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "permission_denied")

    def test_phone_read_dry_run_uses_fast_direct_read_path(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["phone", "read", "--prompt", "读取当前屏幕", "--json", "--dry-run"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/phone/read")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")
        self.assertNotIn("deep", json.dumps(payload, ensure_ascii=False).lower())

    def test_phone_read_screen_alias_uses_read_path(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["phone", "read-screen", "--json", "--dry-run"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/phone/read")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")

    def test_phone_adb_doctor_is_admin_repair_alias(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["phone", "adb-doctor", "--json", "--dry-run", "--permission", "admin"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["method"], "POST")
        self.assertEqual(payload["data"]["endpoint"], "/api/diagnostics/repair")
        self.assertEqual(payload["data"]["body"]["id"], "phone-adb")
        self.assertTrue(payload["data"]["body"]["confirmed"])

    def test_phone_adb_doctor_requires_admin_permission(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["phone", "adb-doctor", "--json", "--dry-run"])

        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "permission_denied")

    def test_phone_event_stream_wrappers_are_read_permission_dry_runs(self) -> None:
        from loom_cli import dispatch

        cases = [
            (
                ["phone", "events-start", "--device-id", "phone-1", "--max-sec", "3600", "--max-events", "0", "--json", "--dry-run"],
                "POST",
                "/api/phone/events/start",
            ),
            (
                ["phone", "events-status", "--device-id", "phone-1", "--json", "--dry-run"],
                "GET",
                "/api/phone/events/status?deviceId=phone-1",
            ),
            (
                ["phone", "events-stop", "--device-id", "phone-1", "--json", "--dry-run"],
                "POST",
                "/api/phone/events/stop",
            ),
        ]

        for argv, method, endpoint in cases:
            with self.subTest(argv=argv):
                code, payload = dispatch(argv)

                self.assertEqual(code, 0)
                self.assertEqual(payload["data"]["method"], method)
                self.assertEqual(payload["data"]["endpoint"], endpoint)

    def test_phone_quick_task_maps_simple_back_to_fast_action_path(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "quick-task",
                "--prompt",
                "返回上一页",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/phone/task")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")
        self.assertEqual(payload["data"]["body"]["action"], "back")

    def test_phone_run_task_alias_submits_phone_task(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "run-task",
                "--prompt",
                "read current page",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/phone/task")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")

    def test_phone_run_task_blocks_bulk_outreach_without_confirmation(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "run-task",
                "--prompt",
                "批量私信所有客户",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "safety_confirmation_required")

    def test_phone_quick_task_blocks_garbled_control_prompt(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "quick-task",
                "--prompt",
                "????????",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "safety_confirmation_required")

    def test_phone_template_task_passes_template_layer_to_bridge(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "template-task",
                "--template",
                "screen-summary",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/phone/task")
        self.assertEqual(payload["data"]["body"]["template"], "screen-summary")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")
        self.assertEqual(payload["data"]["body"]["executionLayer"], "template")
        self.assertNotIn("action", payload["data"]["body"])

    def test_phone_mutating_template_task_still_requires_control(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "phone",
                "template-task",
                "--template",
                "back",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "permission_denied")

    def test_cli_stdout_is_single_json_document(self) -> None:
        completed = subprocess.run(
            [sys.executable, os.path.join("python", "loom_cli.py"), "status", "--json"],
            cwd=LAUNCHER_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )

        self.assertEqual(completed.stderr.strip(), "")
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(payload["ok"])

    def test_cli_stdout_json_with_chinese_is_utf8(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        completed = subprocess.run(
            [
                sys.executable,
                os.path.join("python", "loom_cli.py"),
                "phone",
                "read-screen",
                "--json",
                "--dry-run",
            ],
            cwd=LAUNCHER_DIR,
            capture_output=True,
            env=env,
            timeout=10,
        )

        payload = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 0)
        self.assertIn("读取当前手机屏幕", payload["data"]["body"]["prompt"])

    def test_cli_writes_audit_to_user_data_not_source_tree(self) -> None:
        from loom_cli import dispatch

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"LOOM_AUDIT_DIR": temp_dir}):
                code, payload = dispatch(["status", "--json", "--bridge-token", "secret-token"])
                audit_path = os.path.join(temp_dir, "loom-cli-audit.jsonl")
                with open(audit_path, "r", encoding="utf-8") as handle:
                    audit = json.loads(handle.readline())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(audit["tool"], "cli:status")
        self.assertNotIn("secret-token", json.dumps(audit, ensure_ascii=False))

    def test_logs_tail_reads_user_audit_log(self) -> None:
        from loom_cli import dispatch

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"LOOM_AUDIT_DIR": temp_dir}):
                dispatch(["status", "--json"])
                code, payload = dispatch(["logs", "tail", "--limit", "5", "--json"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["path"].endswith("loom-cli-audit.jsonl"))
        self.assertGreaterEqual(len(payload["data"]["lines"]), 1)

    def test_matrix_status_dry_run_uses_matrix_endpoint(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["matrix", "status", "--json", "--dry-run"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["endpoint"], "/api/matrix/status")
        self.assertEqual(payload["data"]["method"], "GET")

    def test_matrix_status_reads_local_bridge_session_when_available(self) -> None:
        import loom_cli

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                return False

            def read(self) -> bytes:
                return b'{"devices":[],"tasks":[]}'

        captured: dict[str, str] = {}

        def fake_urlopen(request, timeout):
            headers = {key.lower(): value for key, value in request.header_items()}
            captured["url"] = request.full_url
            captured["token"] = headers.get("x-bridge-token", "")
            captured["timeout"] = str(timeout)
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = os.path.join(temp_dir, "session")
            os.makedirs(session_dir, exist_ok=True)
            with open(os.path.join(session_dir, "bridge-session.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema": "loom.bridge_session.v1",
                        "url": "http://127.0.0.1:18888",
                        "token": "local-session-token",
                    },
                    handle,
                )
            with patch.dict(os.environ, {"LOOM_BRIDGE_SESSION_DIR": session_dir}):
                with patch.object(loom_cli, "DEFAULT_BRIDGE_URL", ""), patch.object(loom_cli, "DEFAULT_BRIDGE_TOKEN", ""):
                    with patch("urllib.request.urlopen", fake_urlopen):
                        code, payload = loom_cli.dispatch(["matrix", "status", "--json"], base_path=temp_dir)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(captured["url"], "http://127.0.0.1:18888/api/matrix/status")
        self.assertEqual(captured["token"], "local-session-token")
        self.assertEqual(payload["data"]["result"]["devices"], [])

    def test_matrix_dispatch_requires_confirmation_for_bulk_outreach(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "matrix",
                "dispatch",
                "--prompt",
                "批量私信所有客户",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 3)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "safety_confirmation_required")

    def test_matrix_dispatch_dry_run_preserves_layered_execution_fields(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "matrix",
                "dispatch",
                "--device",
                "phone-a",
                "--prompt",
                "打开系统设置",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["endpoint"], "/api/matrix/dispatch")
        self.assertEqual(payload["data"]["body"]["executionLayer"], "template")
        self.assertEqual(payload["data"]["body"]["profile"], "fast")

    def test_matrix_watch_cancel_template_and_experience_commands_are_structured(self) -> None:
        from loom_cli import dispatch

        with tempfile.TemporaryDirectory() as temp_dir:
            commands = [
                ["matrix", "watch", "--campaign", "campaign_123", "--json", "--dry-run"],
                ["matrix", "cancel", "--campaign", "campaign_123", "--permission", "control", "--json", "--dry-run"],
                ["matrix", "retry", "--campaign", "campaign_123", "--permission", "control", "--json", "--dry-run"],
                ["matrix", "leads", "--limit", "5", "--json", "--dry-run"],
                [
                    "matrix",
                    "record-lead",
                    "--summary",
                    "用户询问套餐",
                    "--device",
                    "phone-a",
                    "--permission",
                    "control",
                    "--json",
                    "--dry-run",
                ],
                ["template", "run", "--template", "read-screen", "--device", "phone-a", "--json", "--dry-run"],
                ["experience", "report", "--json", "--dry-run"],
            ]
            payloads = [dispatch(command, base_path=temp_dir)[1] for command in commands]

        self.assertEqual(payloads[0]["data"]["endpoint"], "/api/matrix/watch?campaignId=campaign_123")
        self.assertEqual(payloads[1]["data"]["endpoint"], "/api/matrix/cancel")
        self.assertEqual(payloads[2]["data"]["endpoint"], "/api/matrix/retry")
        self.assertEqual(payloads[3]["data"]["endpoint"], "/api/matrix/leads?limit=5")
        self.assertEqual(payloads[4]["data"]["endpoint"], "/api/matrix/leads")
        self.assertEqual(payloads[4]["data"]["body"]["deviceId"], "phone-a")
        self.assertEqual(payloads[5]["data"]["endpoint"], "/api/matrix/template/run")
        self.assertEqual(payloads[6]["data"]["endpoint"], "/api/matrix/experience")

    def test_matrix_record_lead_dry_run_redacts_contact_like_values(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(
            [
                "matrix",
                "record-lead",
                "--summary",
                "用户询问套餐 13800000000 user@example.com Bearer secret-token",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ]
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertNotIn("13800000000", serialized)
        self.assertNotIn("user@example.com", serialized)
        self.assertNotIn("secret-token", serialized)

    def test_expanded_cli_domains_are_structured_and_redacted(self) -> None:
        from loom_cli import dispatch

        commands = [
            ["media", "image", "--prompt", "product photo", "--permission", "control", "--json", "--dry-run"],
            [
                "wire",
                "custom",
                "--base-url",
                "https://api.example.com/v1",
                "--api-key",
                "secret-value",
                "--text-model",
                "qwen",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ],
            [
                "agents",
                "model-apply",
                "--component",
                "codex-desktop",
                "--model",
                "qwen",
                "--permission",
                "control",
                "--json",
                "--dry-run",
            ],
            ["account", "subscription", "--json", "--dry-run"],
        ]
        payloads = [dispatch(command)[1] for command in commands]

        self.assertEqual(payloads[0]["data"]["endpoint"], "/api/image/generate/submit")
        self.assertEqual(payloads[1]["data"]["endpoint"], "/api/wire/custom")
        self.assertNotIn("secret-value", json.dumps(payloads[1], ensure_ascii=False))
        self.assertEqual(payloads[2]["data"]["endpoint"], "/api/components/model-config/apply")
        self.assertEqual(payloads[3]["data"]["endpoint"], "/api/account/subscription")

    def test_expanded_cli_admin_update_requires_admin_permission(self) -> None:
        from loom_cli import dispatch

        code, payload = dispatch(["settings", "update-do", "--permission", "read", "--json", "--dry-run"])

        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
