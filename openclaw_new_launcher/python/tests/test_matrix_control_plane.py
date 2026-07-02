from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


class MatrixControlPlaneTests(unittest.TestCase):
    def test_matrix_workbench_contains_phone_app_download_entry(self) -> None:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        page_path = os.path.join(repo_root, "src", "components", "matrix", "MatrixWorkbenchPage.tsx")
        with open(page_path, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("PHONE_AGENT_APK_URL", source)
        self.assertIn("PHONE_AGENT_QR_SRC", source)
        self.assertIn("data-matrix-phone-app-download", source)
        self.assertIn("phone-agent-apk-qr.svg", source)
        self.assertIn("下载手机端 App", source)

    def test_matrix_workbench_uses_event_source_for_live_updates(self) -> None:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        page_path = os.path.join(repo_root, "src", "components", "matrix", "MatrixWorkbenchPage.tsx")
        api_path = os.path.join(repo_root, "src", "services", "api.ts")
        with open(page_path, "r", encoding="utf-8") as handle:
            page = handle.read()
        with open(api_path, "r", encoding="utf-8") as handle:
            api = handle.read()

        self.assertIn("new EventSource", page)
        self.assertIn("matrixApi.eventsStreamUrl", page)
        self.assertIn("eventsStreamUrl", api)
        self.assertIn("/api/matrix/events/stream", api)

    def test_device_registry_redacts_tokens_and_tracks_runtime_fields(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            device = matrix.register_device(
                {
                    "deviceId": "phone-a",
                    "group": "demo",
                    "online": True,
                    "heartbeatAt": "2026-06-30T10:00:00+0800",
                    "currentScreenSummary": "微信首页",
                    "failureCount": 2,
                    "model": "agnes-2.0-flash",
                    "token": "secret-token",
                    "lumiLauncherSecret": "secret",
                }
            )
            status = matrix.status()

        serialized = json.dumps({"device": device, "status": status}, ensure_ascii=False)
        self.assertEqual(status["schema"], "loom.matrix.v1")
        self.assertEqual(status["devices"][0]["deviceId"], "phone-a")
        self.assertEqual(status["devices"][0]["group"], "demo")
        self.assertTrue(status["devices"][0]["online"])
        self.assertEqual(status["devices"][0]["currentScreenSummary"], "微信首页")
        self.assertEqual(status["devices"][0]["failureCount"], 2)
        self.assertEqual(status["devices"][0]["model"], "agnes-2.0-flash")
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("lumiLauncherSecret", serialized)

    def test_device_registry_marks_stale_heartbeat_offline_with_stream_fields(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        stale = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device(
                {
                    "deviceId": "phone-stale",
                    "online": True,
                    "heartbeatAt": stale,
                    "lastEventAt": stale,
                    "streamStatus": "connected",
                    "streamLatencyMs": 120,
                    "currentPackage": "com.demo",
                    "accessibilityRunning": True,
                    "screenOn": True,
                    "deviceLocked": False,
                    "runningTaskCount": 1,
                }
            )
            status = matrix.status()

        device = status["devices"][0]
        self.assertFalse(device["online"])
        self.assertEqual(device["streamStatus"], "offline")
        self.assertGreaterEqual(device["streamLatencyMs"], 30000)
        self.assertEqual(device["currentPackage"], "com.demo")
        self.assertTrue(device["accessibilityRunning"])
        self.assertTrue(device["screenOn"])
        self.assertFalse(device["deviceLocked"])
        self.assertEqual(device["runningTaskCount"], 1)

    def test_status_includes_saved_phone_config_devices_without_token_leak(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(base_path=temp_dir)
            os.makedirs(paths.launcher_dir, exist_ok=True)
            with open(os.path.join(paths.launcher_dir, "phone-agents.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "selectedDeviceId": "android-main",
                        "devices": [
                            {
                                "id": "android-main",
                                "name": "Android Phone",
                                "baseUrl": "http://192.168.1.13:9527",
                                "token": "phone-secret-token",
                                "album": "LOOM",
                                "lastSeenAt": "2026-07-01T12:00:00+08:00",
                            }
                        ],
                    },
                    handle,
                    ensure_ascii=False,
                )

            status = MatrixControlPlane(paths).status()

        self.assertEqual(status["summary"]["total"], 1)
        device = status["devices"][0]
        self.assertEqual(device["deviceId"], "android-main")
        self.assertEqual(device["name"], "Android Phone")
        self.assertEqual(device["source"], "phone-config")
        self.assertTrue(device["selected"])
        self.assertFalse(device["online"])
        self.assertFalse(device["busy"])
        self.assertEqual(device["model"], "agnes-2.0-flash")
        serialized = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("phone-secret-token", serialized)
        self.assertNotIn("192.168.1.13", serialized)

    def test_dispatch_creates_campaign_mission_device_tasks_steps_and_events(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device({"deviceId": "phone-a", "group": "demo", "online": True})
            task = matrix.dispatch(
                {
                    "title": "读屏",
                    "prompt": "读取当前屏幕",
                    "target": {"groups": ["demo"]},
                    "profile": "fast",
                    "mode": "observe",
                }
            )
            status = matrix.status()
            events = matrix.watch(task["campaignId"])

        self.assertTrue(task["campaignId"].startswith("campaign_"))
        self.assertTrue(task["missions"][0]["missionId"].startswith("mission_"))
        device_task = task["missions"][0]["deviceTasks"][0]
        self.assertEqual(device_task["deviceId"], "phone-a")
        self.assertEqual(device_task["executionLayer"], "direct")
        self.assertEqual([step["kind"] for step in device_task["steps"]], ["direct", "result"])
        self.assertEqual(status["devices"][0]["currentTaskId"], device_task["deviceTaskId"])
        self.assertEqual([event["type"] for event in events["events"][:3]], ["queued", "assigned", "running"])

    def test_template_and_agent_layers_are_selected_before_model_inference(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device({"deviceId": "phone-a", "group": "demo", "online": True})
            template_task = matrix.dispatch({"prompt": "打开系统设置", "target": {"deviceIds": ["phone-a"]}})
            agent_task = matrix.dispatch({"prompt": "完成一个复杂多步骤任务", "target": {"deviceIds": ["phone-a"]}, "mode": "full"})

        self.assertEqual(template_task["missions"][0]["deviceTasks"][0]["executionLayer"], "template")
        self.assertEqual(agent_task["missions"][0]["deviceTasks"][0]["executionLayer"], "agent")

    def test_safety_gate_requires_confirmation_for_bulk_outreach(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane, MatrixSafetyError

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device({"deviceId": "phone-a", "group": "demo", "online": True})
            with self.assertRaises(MatrixSafetyError) as raised:
                matrix.dispatch({"prompt": "批量私信所有客户并自动回复", "target": {"groups": ["demo"]}})

        self.assertEqual(raised.exception.code, "safety_confirmation_required")
        self.assertIn("确认", raised.exception.message)

    def test_experience_report_records_success_rate_without_sensitive_values(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device({"deviceId": "phone-a", "group": "demo", "online": True})
            task = matrix.dispatch(
                {
                    "prompt": "读取当前屏幕 sk-test-token",
                    "target": {"deviceIds": ["phone-a"]},
                }
            )
            device_task_id = task["missions"][0]["deviceTasks"][0]["deviceTaskId"]
            matrix.record_result(device_task_id, ok=True, duration_ms=321, failure_reason="")
            report = matrix.experience_report()

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["schema"], "loom.matrix.experience.v1")
        self.assertGreaterEqual(report["summary"]["total"], 1)
        self.assertEqual(report["summary"]["successRate"], 1.0)
        self.assertIn("templateSuggestions", report)
        self.assertNotIn("sk-test-token", serialized)

    def test_lead_records_are_local_structured_and_redacted(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            lead = matrix.record_lead(
                {
                    "source": "task",
                    "deviceId": "phone-a",
                    "campaignId": "campaign_123",
                    "deviceTaskId": "deviceTask_123",
                    "title": "客户线索",
                    "summary": "用户询问套餐，Bearer secret-token",
                    "status": "new",
                    "tags": ["demo", "需要跟进"],
                    "token": "secret-token",
                    "phone": "13800000000",
                }
            )
            listed = matrix.list_leads(limit=10)

        serialized = json.dumps({"lead": lead, "listed": listed}, ensure_ascii=False)
        self.assertEqual(lead["schema"], "loom.matrix.lead.v1")
        self.assertTrue(lead["leadId"].startswith("lead_"))
        self.assertEqual(listed["leads"][0]["deviceId"], "phone-a")
        self.assertEqual(listed["leads"][0]["tags"], ["demo", "需要跟进"])
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("13800000000", serialized)

    def test_retry_failed_campaign_creates_new_campaign_without_bypassing_safety(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            matrix.register_device({"deviceId": "phone-a", "group": "demo", "online": True})
            task = matrix.dispatch(
                {
                    "prompt": "读取当前屏幕",
                    "target": {"deviceIds": ["phone-a"]},
                    "mode": "observe",
                    "profile": "fast",
                }
            )
            device_task_id = task["missions"][0]["deviceTasks"][0]["deviceTaskId"]
            matrix.record_result(device_task_id, ok=False, duration_ms=123, failure_reason="设备离线")
            retried = matrix.retry_failed(task["campaignId"], {})
            events = matrix.watch(task["campaignId"])

        self.assertTrue(retried["retried"])
        self.assertEqual(retried["retryOf"], task["campaignId"])
        self.assertEqual(retried["task"]["retryOf"], task["campaignId"])
        retry_device_task = retried["task"]["missions"][0]["deviceTasks"][0]
        self.assertEqual(retry_device_task["deviceId"], "phone-a")
        self.assertEqual(retry_device_task["executionLayer"], "direct")
        self.assertIn("retry", [event["type"] for event in events["events"]])


if __name__ == "__main__":
    unittest.main()
