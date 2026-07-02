from __future__ import annotations

import os
import json
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.routes_jobs import register_job_routes
from api.routes_phone import (
    _phone_failure_result,
    _phone_event_sync_public,
    _phone_stdout_payload,
    _parse_phone_sse_events,
    _phone_event_matrix_patch,
    _phone_progress_result_fields_from_stdout,
    _public_store,
    _sanitize_cli_output,
    register_phone_routes,
)
from core.paths import AppPaths
from core.storage import read_json
from core.wire_config import WireService
from services.jobs import JobManager


class PhoneRouteSnapshotTests(unittest.TestCase):
    def test_phone_event_sse_parser_extracts_snapshot_events(self) -> None:
        text = "\n".join(
            [
                "id: 1",
                "event: snapshot",
                'data: {"schema":"apkclaw.event_stream.snapshot.v1","timestampMs":123,'
                '"status":{"accessibilityRunning":true,"currentPackage":"com.demo"},'
                '"metrics":{"totalMs":7},"tasks":[]}',
                "",
                ": keepalive",
                "",
            ]
        )

        events = _parse_phone_sse_events(text.splitlines())

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], "1")
        self.assertEqual(events[0]["event"], "snapshot")
        self.assertTrue(events[0]["data"]["status"]["accessibilityRunning"])
        self.assertEqual(events[0]["data"]["status"]["currentPackage"], "com.demo")

    def test_phone_event_snapshot_can_update_matrix_presence(self) -> None:
        patch = _phone_event_matrix_patch(
            {
                "event": "snapshot",
                "data": {
                    "schema": "apkclaw.event_stream.snapshot.v1",
                    "status": {
                        "accessibilityRunning": True,
                        "screenOn": True,
                        "currentPackage": "com.demo",
                    },
                    "metrics": {"totalMs": 11},
                    "tasks": [{"id": "task-1", "status": "running"}],
                },
            },
            {"id": "phone-1", "name": "Pixel 01", "group": "Lab"},
        )

        self.assertEqual(patch["deviceId"], "phone-1")
        self.assertEqual(patch["name"], "Pixel 01")
        self.assertTrue(patch["online"])
        self.assertIn("com.demo", patch["currentScreenSummary"])
        self.assertIn("stream", patch["lastResult"])

    def test_phone_event_snapshot_exposes_structured_task_state(self) -> None:
        patch = _phone_event_matrix_patch(
            {
                "event": "snapshot",
                "data": {
                    "schema": "apkclaw.event_stream.snapshot.v1",
                    "status": {
                        "accessibilityRunning": True,
                        "busy": True,
                        "currentTaskId": "task-1",
                    },
                    "metrics": {"totalMs": 21},
                    "tasks": [
                        {
                            "taskId": "task-1",
                            "status": "running",
                            "agentReport": {
                                "headline": "running: click settings",
                                "currentStep": "click_settings",
                                "needsCodex": True,
                            },
                        }
                    ],
                },
            },
            "phone-1",
        )

        self.assertTrue(patch["busy"])
        self.assertEqual(patch["currentTaskId"], "task-1")
        self.assertEqual(patch["currentStep"], "click_settings")
        self.assertEqual(patch["headline"], "running: click settings")
        self.assertTrue(patch["needsCodex"])

    def test_phone_stdout_promotes_agent_report_for_one_glance_status(self) -> None:
        stdout = json.dumps(
            {
                "data": {
                    "agentReport": {
                        "schema": "apkclaw.agent_report.v1",
                        "headline": "running: 等待登录页",
                        "currentStep": "wait_login",
                        "completed": False,
                        "needsCodex": False,
                    }
                }
            },
            ensure_ascii=False,
        )

        fields = _phone_progress_result_fields_from_stdout(stdout)

        self.assertEqual(fields["currentStep"], "wait_login")
        self.assertEqual(fields["agentReport"]["headline"], "running: 等待登录页")
        self.assertFalse(fields["agentReport"]["needsCodex"])

    def test_phone_stdout_payload_tolerates_log_lines_around_json(self) -> None:
        stdout = "\n".join(
            [
                "warmup log line",
                json.dumps(
                    {
                        "data": {
                            "agentReport": {
                                "schema": "apkclaw.agent_report.v1",
                                "headline": "running: wait",
                                "currentStep": "wait",
                                "completed": False,
                                "needsCodex": False,
                            }
                        }
                    }
                ),
                "tail log line",
            ]
        )

        payload = _phone_stdout_payload(stdout)
        fields = _phone_progress_result_fields_from_stdout(stdout)

        self.assertIn("data", payload)
        self.assertEqual(fields["currentStep"], "wait")
        self.assertEqual(fields["agentReport"]["headline"], "running: wait")

    def test_phone_agent_report_public_drops_prompt_preview_and_event_parameters(self) -> None:
        stdout = json.dumps(
            {
                "data": {
                    "agentReport": {
                        "schema": "apkclaw.agent_report.v1",
                        "status": "running",
                        "headline": "running: sk-secret-123456789",
                        "currentStep": "tool_call",
                        "completed": False,
                        "needsCodex": False,
                        "promptPreview": "sk-secret-123456789",
                        "lastEvent": {
                            "type": "tool_call",
                            "parameters": {"token": "sk-secret-123456789"},
                            "message": "Bearer abcdefghijklmnop",
                        },
                    }
                }
            }
        )

        fields = _phone_progress_result_fields_from_stdout(stdout)
        report = fields["agentReport"]
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("promptPreview", report)
        self.assertNotIn("parameters", report.get("lastEvent", {}))
        self.assertNotIn("sk-secret-123456789", serialized)

    def test_phone_event_sync_public_reports_state_staleness_and_restartability(self) -> None:
        process = SimpleNamespace(poll=lambda: 0)
        public = _phone_event_sync_public(
            {
                "process": process,
                "deviceId": "phone-1",
                "startedAt": "2026-07-02T10:00:00+0800",
                "finishedAt": "2026-07-02T10:01:00+0800",
                "eventCount": 3,
                "lastEventAt": 123.0,
                "lastHeartbeatAt": 120.0,
                "lastSummary": {"stoppedBy": "max_sec", "elapsedMs": 60000},
                "returncode": 0,
            }
        )

        self.assertFalse(public["running"])
        self.assertEqual(public["state"], "stopped")
        self.assertTrue(public["restartable"])
        self.assertFalse(public["stale"])
        self.assertEqual(public["lastEventAt"], 123.0)
        self.assertEqual(public["lastHeartbeatAt"], 120.0)
        self.assertEqual(public["stoppedBy"], "max_sec")

    def test_phone_failure_result_includes_codex_repair_report(self) -> None:
        result = _phone_failure_result(
            "phone.task",
            code="timeout",
            reason="phone task timed out",
            stdout="",
            stderr="",
            execution={"mode": "safe"},
            started_at=time.monotonic(),
        )

        self.assertTrue(result["agentReport"]["needsCodex"])
        self.assertEqual(result["agentReport"]["currentStep"], "failed")
        self.assertIn("fixHint", result["agentReport"])

    def test_phone_events_routes_start_and_report_sync_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys, time\n"
                    "print(json.dumps({'event':'snapshot','data':{'schema':'apkclaw.event_stream.snapshot.v1',"
                    "'status':{'accessibilityRunning':True,'currentPackage':'com.demo'},'metrics':{'totalMs':5},'tasks':[]}}), flush=True)\n"
                    "time.sleep(2)\n"
                )

            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            started = client.post("/api/phone/events/start", json={"maxSec": 2})
            status = client.get("/api/phone/events/status")
            stopped = client.post("/api/phone/events/stop")

            self.assertEqual(started.status_code, 200)
            self.assertTrue(started.json()["running"])
            self.assertEqual(status.status_code, 200)
            self.assertTrue(status.json()["running"])
            self.assertEqual(stopped.status_code, 200)
            self.assertFalse(stopped.json()["running"])

    def test_phone_config_save_auto_starts_event_sync_for_saved_device(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys, time\n"
                    "print(json.dumps({'event':'snapshot','deviceId':'phone-auto','data':{"
                    "'schema':'apkclaw.event_stream.snapshot.v1',"
                    "'status':{'online':True,'accessibilityRunning':True,'currentPackage':'com.demo'},"
                    "'metrics':{'totalMs':5},'tasks':[]}}), flush=True)\n"
                    "time.sleep(2)\n"
                )

            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            saved = client.post(
                "/api/phone/config/device",
                json={
                    "deviceId": "phone-auto",
                    "name": "Phone Auto",
                    "baseUrl": "192.168.1.88",
                    "token": "test-token",
                },
            )
            status = client.get("/api/phone/events/status?deviceId=phone-auto")
            stopped = client.post("/api/phone/events/stop", json={"deviceId": "phone-auto"})

            self.assertEqual(saved.status_code, 200)
            self.assertTrue(saved.json()["eventSync"]["started"])
            self.assertTrue(status.json()["running"])
            self.assertEqual(stopped.status_code, 200)

    def test_cli_output_sanitizer_redacts_json_and_bearer_secrets(self) -> None:
        ctx = SimpleNamespace(sanitize_text=lambda value: value)
        raw = '{"token":"secret-token","apiKey":"sk-demo-secret","headers":{"Authorization":"Bearer abcdefghijklmnop"}}'

        cleaned = _sanitize_cli_output(ctx, raw, kind="phone.task")

        self.assertNotIn("secret-token", cleaned)
        self.assertNotIn("sk-demo-secret", cleaned)
        self.assertNotIn("abcdefghijklmnop", cleaned)
        self.assertIn('"token": "[redacted]"', cleaned)
        self.assertIn('"apiKey": "[redacted]"', cleaned)
        self.assertIn('"Authorization": "[redacted]"', cleaned)

    def test_public_store_defaults_to_first_device_without_exposing_secrets(self) -> None:
        snapshot = _public_store(
            {
                "selectedDeviceId": "",
                "devices": [
                    {
                        "id": "pixel-01",
                        "name": "Pixel 01",
                        "baseUrl": "http://127.0.0.1:18080/",
                        "token": "secret-token",
                        "launcherId": "loom-test",
                        "launcherSecret": "secret-pairing",
                    }
                ],
            }
        )

        self.assertEqual(snapshot["selectedDeviceId"], "pixel-01")
        self.assertTrue(snapshot["configured"])
        self.assertEqual(snapshot["devices"][0]["baseUrl"], "http://127.0.0.1:18080")
        self.assertTrue(snapshot["devices"][0]["tokenAvailable"])
        self.assertTrue(snapshot["devices"][0]["paired"])
        self.assertNotIn("token", snapshot["devices"][0])
        self.assertNotIn("launcherSecret", snapshot["devices"][0])

    def test_phone_status_route_submits_phone_service_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-fleet.mjs"), "w", encoding="utf-8") as handle:
                handle.write("console.log('{\"results\":[]}');\n")

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            response = client.post("/api/phone/status")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["jobId"].startswith("job_"))
            self.assertEqual(payload["job"]["kind"], "phone.status")
            self.assertEqual(payload["job"]["type"], "phone.status")

    def test_phone_status_job_updates_matrix_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-fleet.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'selectedDeviceId': 'phone-1',"
                    "'results': [{"
                    "'ok': True,"
                    "'device': {'id': 'phone-1', 'name': 'Pixel 01'},"
                    "'status': {'online': True, 'accessibilityRunning': True, 'screenOn': True, 'deviceLocked': False}"
                    "}]"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/status")
            job = _wait_for_job(client, submitted.json()["jobId"])

            self.assertEqual(job["status"], "succeeded")
            from core.phone_matrix import MatrixControlPlane

            status = MatrixControlPlane(ctx.paths).status()
            self.assertEqual(status["summary"]["online"], 1)
            self.assertTrue(status["devices"][0]["online"])
            self.assertEqual(status["devices"][0]["deviceId"], "phone-1")
            self.assertIn("无障碍运行", status["devices"][0]["currentScreenSummary"])

    def test_phone_devices_route_submits_direct_job_without_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-fleet.mjs"), "w", encoding="utf-8") as handle:
                handle.write("import json, sys\nprint(json.dumps({'argv': sys.argv[1:], 'devices': []}, ensure_ascii=False))\n")

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/devices")

            self.assertEqual(submitted.status_code, 200)
            payload = submitted.json()
            self.assertEqual(payload["job"]["kind"], "phone.devices")
            job = _wait_for_job(client, payload["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(json.loads(job["result"]["stdout"])["argv"], ["list", "--json"])

    def test_phone_metrics_route_submits_agent_metrics_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({"
                    "'argv': sys.argv[1:],"
                    "'metrics': {"
                    "'taskCount': 3,"
                    "'successCount': 2,"
                    "'failureCount': 1,"
                    "'queueDepth': 1,"
                    "'cacheHitRate': 0.5,"
                    "'templateHitRate': 0.25,"
                    "'agentFallbackRate': 0.25"
                    "}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/metrics")

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["kind"], "phone.metrics")
            payload = json.loads(job["result"]["stdout"])
            self.assertEqual(payload["argv"][0], "metrics")
            self.assertIn("--json", payload["argv"])
            self.assertEqual(job["result"]["metrics"]["taskCount"], 3)
            self.assertEqual(job["result"]["metrics"]["queueDepth"], 1)

    def test_phone_config_device_saves_token_without_returning_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            storage: dict[str, dict] = {}
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs, storage)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post(
                "/api/phone/config/device",
                json={
                    "id": "pixel-01",
                    "name": "Pixel 01",
                    "baseUrl": "http://127.0.0.1:18080/",
                    "token": "secret-token",
                    "launcherId": "loom-test",
                    "launcherSecret": "secret-pairing",
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["configured"])
            self.assertEqual(payload["selectedDeviceId"], "pixel-01")
            self.assertEqual(payload["devices"][0]["baseUrl"], "http://127.0.0.1:18080")
            self.assertTrue(payload["devices"][0]["tokenAvailable"])
            self.assertNotIn("token", payload["devices"][0])
            self.assertNotIn("launcherSecret", payload["devices"][0])
            self.assertNotIn("secret-token", str(payload))

            stored = next(value for key, value in storage.items() if key.endswith("phone-agents.json"))
            self.assertEqual(stored["devices"][0]["token"], "secret-token")

    def test_phone_config_device_accepts_ip_only_and_defaults_port(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post(
                "/api/phone/config/device",
                json={"id": "phone-1", "baseUrl": "192.168.1.78", "token": "secret-token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["devices"][0]["baseUrl"], "http://192.168.1.78:9527")

    def test_phone_config_device_accepts_host_port_without_scheme(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post(
                "/api/phone/config/device",
                json={"id": "phone-1", "baseUrl": "127.0.0.1:18080", "token": "secret-token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["devices"][0]["baseUrl"], "http://127.0.0.1:18080")

    def test_phone_config_device_cleans_common_paste_mistakes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post(
                "/api/phone/config/device",
                json={"id": "phone-1", "baseUrl": " http:/192。168。1。78：9527／api/device/status ", "token": "secret-token"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["devices"][0]["baseUrl"], "http://192.168.1.78:9527")

    def test_phone_sync_model_route_runs_through_job_manager_without_secret_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _wire_context(temp_dir, job_mgr, logs, session=_session_snapshot())
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            response = client.post("/api/phone/sync-model")

            self.assertEqual(response.status_code, 200)
            submitted = response.json()
            self.assertTrue(submitted["jobId"].startswith("job_"))
            self.assertEqual(submitted["job"]["kind"], "phone.sync_model")

            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "succeeded")
            result = job["result"]
            self.assertEqual(result["wire"]["models"]["phone"], "agnes-2.0-flash")
            self.assertEqual(result["syncResults"][0]["target"], "phone")
            self.assertTrue(result["syncResults"][0]["ok"])
            self.assertNotIn("sk-test-token-not-real", repr(result))
            self.assertNotIn("apiKey", repr(result["wire"]))

            phone_config = read_json(os.path.join(temp_dir, "data", ".openclaw", "launcher", "phone-agent.json"), {})
            self.assertEqual(phone_config["llm"]["model"], "agnes-2.0-flash")

    def test_phone_sync_model_pushes_config_to_configured_phone_without_secret_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "assert sys.argv[1:3] == ['config-sync', '--json']\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'model': 'agnes-2.0-flash',"
                    "'phone': {'modelConfigured': True, 'modelReady': True}"
                    "}))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _wire_context(temp_dir, job_mgr, logs, session=_session_snapshot())
            ctx.paths = SimpleNamespace(base_path=temp_dir, launcher_dir=ctx.paths.launcher_dir, node_exe=sys.executable)
            os.makedirs(ctx.paths.launcher_dir, exist_ok=True)
            with open(os.path.join(ctx.paths.launcher_dir, "phone-agents.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "selectedDeviceId": "phone-1",
                        "devices": [
                            {
                                "id": "phone-1",
                                "baseUrl": "http://127.0.0.1:9527",
                                "token": "secret-phone-token",
                            }
                        ],
                    },
                    handle,
                )
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/sync-model").json()
            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "succeeded")
            self.assertTrue(job["result"]["phoneImport"]["attempted"])
            self.assertTrue(job["result"]["phoneImport"]["success"])
            self.assertEqual(job["result"]["phoneImport"]["model"], "agnes-2.0-flash")
            self.assertNotIn("sk-test-token-not-real", repr(job["result"]))
            self.assertNotIn("secret-phone-token", repr(job["result"]))

    def test_phone_sync_model_can_apply_existing_custom_wire_without_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            paths = AppPaths(temp_dir)
            secret = "s" + "k-custom-phone-test"
            WireService(paths).sync_custom_provider(
                provider="OpenAI 兼容",
                base_url="https://third.example/v1",
                api_key=secret,
                text_model="gpt-4o",
                phone_model="gpt-4o-mini",
                targets=(),
            )
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _wire_context(temp_dir, job_mgr, logs, session=None)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/sync-model").json()
            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["wire"]["managedBy"], "custom_provider")
            self.assertEqual(job["result"]["wire"]["models"]["phone"], "gpt-4o-mini")
            self.assertNotIn(secret, repr(job["result"]))

            phone_config = read_json(os.path.join(temp_dir, "data", ".openclaw", "launcher", "phone-agent.json"), {})
            self.assertEqual(phone_config["llm"]["model"], "gpt-4o-mini")

    def test_phone_sync_model_reports_clear_error_without_account_or_wire(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _wire_context(temp_dir, job_mgr, logs, session=None)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/sync-model").json()
            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "failed")
            self.assertIn("尚未登录中转站账号", job["error"])


    def test_phone_screenshot_job_omits_embedded_base64_from_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'filePath': 'C:/tmp/loom-frame.jpg',"
                    "'frame': {"
                    "'width': 1080,"
                    "'height': 2400,"
                    "'image': {'mime': 'image/jpeg', 'base64': 'AAAA' * 200},"
                    "'dataUrl': 'data:image/jpeg;base64,' + ('BBBB' * 200)"
                    "}"
                    "}))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/screenshot").json()
            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "succeeded")
            stdout = job["result"]["stdout"]
            self.assertIn("C:/tmp/loom-frame.jpg", stdout)
            self.assertIn("imageOmitted", stdout)
            self.assertNotIn("AAAA", stdout)
            self.assertNotIn("BBBB", stdout)
            self.assertNotIn("data:image/jpeg;base64", stdout)
            self.assertIn("metrics", job["result"])
            self.assertEqual(job["result"]["metrics"]["mode"], "screenshot")
            self.assertEqual(job["result"]["metrics"]["cacheHit"], False)
            self.assertEqual(job["result"]["cacheHit"], False)
            self.assertGreaterEqual(job["result"]["metrics"]["screenshotMs"], 0)

    def test_phone_screenshot_job_exposes_cached_frame_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'cached': True,"
                    "'filePath': 'C:/tmp/latest-fast-frame.jpg',"
                    "'frame': {'cached': True, 'imageOmitted': True}"
                    "}))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/screenshot").json()
            job = _wait_for_job(client, submitted["jobId"])

            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["metrics"]["mode"], "screenshot")
            self.assertEqual(job["result"]["metrics"]["cacheHit"], True)
            self.assertEqual(job["result"]["cacheHit"], True)
            self.assertEqual(job["result"]["metrics"]["screenshotMs"], 0)

    def test_phone_screenshot_reuses_recent_frame_for_same_screen_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            counter_path = os.path.join(temp_dir, "screenshot-count.txt")
            script_path = os.path.join(scripts_dir, "openclaw-phone-vision.mjs")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, os\n"
                    f"path = {counter_path!r}\n"
                    "try:\n"
                    "    count = int(open(path, 'r', encoding='utf-8').read())\n"
                    "except FileNotFoundError:\n"
                    "    count = 0\n"
                    "count += 1\n"
                    "open(path, 'w', encoding='utf-8').write(str(count))\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'screenHash': 'hash-same',"
                    "'filePath': 'C:/tmp/frame-' + str(count) + '.jpg',"
                    "'frame': {'screenHash': 'hash-same', 'cached': False, 'imageOmitted': True}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post("/api/phone/screenshot", json={"screenHash": "hash-same"}).json()
            first_job = _wait_for_job(client, first["jobId"])
            second = client.post("/api/phone/screenshot", json={"screenHash": "hash-same"}).json()
            second_job = _wait_for_job(client, second["jobId"])

            self.assertEqual(first_job["status"], "succeeded")
            self.assertEqual(second_job["status"], "succeeded")
            with open(counter_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "1")
            self.assertEqual(first_job["result"]["metrics"]["cacheHit"], False)
            self.assertEqual(second_job["result"]["metrics"]["cacheHit"], True)
            self.assertEqual(second_job["result"]["metrics"]["screenshotMs"], 0)
            self.assertEqual(second_job["result"]["metrics"]["screenHash"], "hash-same")
            self.assertEqual(first_job["result"]["mode"], "screenshot")
            self.assertEqual(second_job["result"]["mode"], "screenshot")
            self.assertEqual(second_job["result"]["currentStep"], "cache")

    def test_phone_screenshot_reuses_screen_hash_returned_by_previous_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            counter_path = os.path.join(temp_dir, "screenshot-count.txt")
            script_path = os.path.join(scripts_dir, "openclaw-phone-vision.mjs")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, os\n"
                    f"path = {counter_path!r}\n"
                    "try:\n"
                    "    count = int(open(path, 'r', encoding='utf-8').read())\n"
                    "except FileNotFoundError:\n"
                    "    count = 0\n"
                    "count += 1\n"
                    "open(path, 'w', encoding='utf-8').write(str(count))\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'filePath': 'C:/tmp/frame-' + str(count) + '.jpg',"
                    "'frame': {'screenHash': 'hash-from-frame', 'cached': False, 'imageOmitted': True}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post("/api/phone/screenshot", json={}).json()
            first_job = _wait_for_job(client, first["jobId"])
            second = client.post("/api/phone/screenshot", json={}).json()
            second_job = _wait_for_job(client, second["jobId"])

            self.assertEqual(first_job["status"], "succeeded")
            self.assertEqual(second_job["status"], "succeeded")
            with open(counter_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "1")
            self.assertEqual(first_job["result"]["metrics"]["cacheHit"], False)
            self.assertEqual(first_job["result"]["metrics"]["screenHash"], "hash-from-frame")
            self.assertEqual(second_job["result"]["cacheHit"], True)
            self.assertEqual(second_job["result"]["currentStep"], "cache")
            self.assertEqual(second_job["result"]["metrics"]["screenHash"], "hash-from-frame")

    def test_phone_screenshot_reuses_recent_read_hash_when_request_has_no_screen_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            counter_path = os.path.join(temp_dir, "screenshot-count.txt")
            script_path = os.path.join(scripts_dir, "openclaw-phone-vision.mjs")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, os, sys\n"
                    "argv = sys.argv[1:]\n"
                    "if argv[0] == 'read':\n"
                    "    print(json.dumps({'argv': argv, 'screenHash': 'hash-from-read'}, ensure_ascii=False))\n"
                    "else:\n"
                    f"    path = {counter_path!r}\n"
                    "    try:\n"
                    "        count = int(open(path, 'r', encoding='utf-8').read())\n"
                    "    except FileNotFoundError:\n"
                    "        count = 0\n"
                    "    count += 1\n"
                    "    open(path, 'w', encoding='utf-8').write(str(count))\n"
                    "    print(json.dumps({"
                    "'ok': True,"
                    "'screenHash': 'hash-from-read',"
                    "'filePath': 'C:/tmp/frame-' + str(count) + '.jpg',"
                    "'frame': {'screenHash': 'hash-from-read', 'cached': False, 'imageOmitted': True}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            read = client.post("/api/phone/read", json={"prompt": "read before screenshot"})
            self.assertEqual(read.status_code, 200)
            read_job = _wait_for_job(client, read.json()["jobId"])
            self.assertEqual(read_job["status"], "succeeded")

            first = client.post("/api/phone/screenshot", json={}).json()
            first_job = _wait_for_job(client, first["jobId"])
            second = client.post("/api/phone/screenshot", json={}).json()
            second_job = _wait_for_job(client, second["jobId"])

            self.assertEqual(first_job["status"], "succeeded")
            self.assertEqual(second_job["status"], "succeeded")
            with open(counter_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "1")
            self.assertEqual(first_job["result"]["metrics"]["cacheHit"], False)
            self.assertEqual(second_job["result"]["metrics"]["cacheHit"], True)
            self.assertEqual(second_job["result"]["metrics"]["screenshotMs"], 0)
            self.assertEqual(second_job["result"]["metrics"]["screenHash"], "hash-from-read")

    def test_phone_task_route_can_submit_full_access_agent_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "打开设置并返回当前页面标题", "mode": "full", "timeoutSec": 120, "maxRounds": 9},
            )

            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["job"]["kind"], "phone.task")
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            stdout = json.loads(job["result"]["stdout"])
            self.assertIn("--prompt", stdout["argv"])
            self.assertIn("打开设置并返回当前页面标题", stdout["argv"])
            self.assertIn("--mode", stdout["argv"])
            self.assertIn("full", stdout["argv"])
            self.assertIn("--max-rounds", stdout["argv"])
            self.assertIn("9", stdout["argv"])

    def test_phone_task_route_maps_fast_standard_deep_profiles_to_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            cases = [
                ("observe", "fast", "45", "4", "500"),
                ("safe", "fast", "120", "12", "500"),
                ("full", "fast", "300", "30", "500"),
                ("safe", "standard", "240", "12", "800"),
                ("full", "deep", "900", "30", "1200"),
            ]
            for mode, profile, timeout_sec, max_rounds, poll_ms in cases:
                with self.subTest(mode=mode, profile=profile):
                    submitted = client.post(
                        "/api/phone/task",
                        json={"prompt": "test", "mode": mode, "profile": profile},
                    )
                    self.assertEqual(submitted.status_code, 200)
                    job = _wait_for_job(client, submitted.json()["jobId"])
                    self.assertEqual(job["status"], "succeeded")
                    argv = json.loads(job["result"]["stdout"])["argv"]
                    if mode == "observe":
                        self.assertEqual(argv[0], "read")
                        self.assertIn("--fast-path", argv)
                        self.assertEqual(argv[argv.index("--fast-path") + 1], "observe_fast")
                        self.assertEqual(job["result"]["execution"]["budget"]["maxRounds"], 4)
                        self.assertEqual(job["result"]["execution"]["budget"]["timeoutSec"], 25)
                        continue
                    self.assertIn("--timeout-sec", argv)
                    self.assertEqual(argv[argv.index("--timeout-sec") + 1], timeout_sec)
                    self.assertIn("--max-rounds", argv)
                    self.assertEqual(argv[argv.index("--max-rounds") + 1], max_rounds)
                    self.assertIn("--poll-ms", argv)
                    self.assertEqual(argv[argv.index("--poll-ms") + 1], poll_ms)

    def test_phone_task_route_observe_mode_uses_direct_read_path_without_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('observe fast path should not use agent')\n")

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "读取当前屏幕，告诉我页面名称。", "mode": "observe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "direct")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "read")
            self.assertIn("读取当前屏幕，告诉我页面名称。", argv)

    def test_phone_task_observe_mode_reuses_last_screen_hash_for_incremental_observe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:], 'screenHash': 'hash-task-observe'}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('observe fast path should not use agent')\n")

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post(
                "/api/phone/task",
                json={"prompt": "read current screen", "mode": "observe", "profile": "fast"},
            )
            self.assertEqual(first.status_code, 200)
            first_job = _wait_for_job(client, first.json()["jobId"])
            self.assertEqual(first_job["status"], "succeeded")
            first_argv = json.loads(first_job["result"]["stdout"])["argv"]
            self.assertNotIn("--known-hash", first_argv)

            second = client.post(
                "/api/phone/task",
                json={"prompt": "read current screen again", "mode": "observe", "profile": "fast"},
            )
            self.assertEqual(second.status_code, 200)
            second_job = _wait_for_job(client, second.json()["jobId"])
            self.assertEqual(second_job["status"], "succeeded")
            second_argv = json.loads(second_job["result"]["stdout"])["argv"]
            self.assertIn("--known-hash", second_argv)
            self.assertEqual(second_argv[second_argv.index("--known-hash") + 1], "hash-task-observe")

    def test_phone_task_route_marks_template_layer_and_uses_small_step_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('template fast path should not use agent')\n")

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "读取当前页面并返回三个可见按钮",
                    "mode": "safe",
                    "profile": "fast",
                    "template": "screen-summary",
                },
            )

            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["job"]["kind"], "phone.task")
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "template")
            self.assertEqual(job["result"]["metrics"]["mode"], "template")
            self.assertEqual(job["result"]["mode"], "template")
            self.assertEqual(job["result"]["currentStep"], "collect")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "read")
            self.assertIn("--prompt", argv)
            self.assertIn("读取当前页面并返回三个可见按钮", argv)
            self.assertNotIn("--execution-layer", argv)

    def test_phone_task_screen_summary_template_reuses_last_screen_hash_for_incremental_observe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('screen-summary template should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:], 'screenHash': 'hash-template-read'}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post(
                "/api/phone/task",
                json={
                    "prompt": "summarize screen",
                    "mode": "safe",
                    "profile": "fast",
                    "template": "screen-summary",
                },
            )
            self.assertEqual(first.status_code, 200)
            first_job = _wait_for_job(client, first.json()["jobId"])
            self.assertEqual(first_job["status"], "succeeded")
            first_argv = json.loads(first_job["result"]["stdout"])["argv"]
            self.assertNotIn("--known-hash", first_argv)

            second = client.post(
                "/api/phone/task",
                json={
                    "prompt": "summarize screen again",
                    "mode": "safe",
                    "profile": "fast",
                    "template": "screen-summary",
                },
            )
            self.assertEqual(second.status_code, 200)
            second_job = _wait_for_job(client, second.json()["jobId"])
            self.assertEqual(second_job["status"], "succeeded")
            second_argv = json.loads(second_job["result"]["stdout"])["argv"]
            self.assertIn("--known-hash", second_argv)
            self.assertEqual(second_argv[second_argv.index("--known-hash") + 1], "hash-template-read")

    def test_phone_task_route_auto_promotes_known_simple_task_to_template_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('deterministic open-settings template should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "打开系统设置，停在设置首页后返回页面名称。", "mode": "safe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["job"]["progress"]["executionLayer"], "template")
            job = _wait_for_job(client, submitted.json()["jobId"])
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "action_fast")
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "open_app")
            self.assertEqual(body["packageName"], "com.android.settings")

    def test_phone_task_open_settings_template_preserves_top_level_observe_after_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('deterministic open-settings template should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "打开系统设置",
                    "mode": "safe",
                    "profile": "fast",
                    "template": "open-settings",
                    "observeAfter": False,
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "open_app")
            self.assertEqual(body["packageName"], "com.android.settings")
            self.assertEqual(body["observeAfter"], False)

    def test_phone_task_template_action_failure_falls_back_to_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'success': False,"
                    "'data': {"
                    "'mode': 'action_fast',"
                    "'errorCode': 'action_failed',"
                    "'error': 'open_app foreground verification failed',"
                    "'metrics': {'mode': 'action_fast', 'totalMs': 21, 'rounds': 0}"
                    "}"
                    "}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:], 'metrics': {'mode': 'agent_fallback', 'rounds': 1}}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "打开系统设置，停在设置首页后返回页面名称。", "mode": "safe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "agent")
            self.assertEqual(job["result"]["fallback"]["from"], "template/action_fast")
            self.assertEqual(job["result"]["fallback"]["errorCode"], "action_failed")
            self.assertEqual(job["result"]["metrics"]["mode"], "agent_fallback")
            self.assertEqual(job["result"]["currentStep"], "collect")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "run")
            self.assertIn("--execution-layer", argv)
            self.assertEqual(argv[argv.index("--execution-layer") + 1], "agent")

    def test_phone_task_route_auto_promotes_refresh_to_action_fast_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('deterministic refresh-screen template should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "refreshscreen", "mode": "safe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["job"]["progress"]["executionLayer"], "template")
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "action_fast")
            self.assertNotIn("--allow-unknown-target", argv)
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "scroll")
            self.assertEqual(body["direction"], "up")

    def test_phone_task_refresh_template_preserves_top_level_observe_after_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('deterministic refresh-screen template should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "refreshscreen",
                    "mode": "safe",
                    "profile": "fast",
                    "template": "refresh-screen",
                    "observeAfter": False,
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "scroll")
            self.assertEqual(body["direction"], "up")
            self.assertEqual(body["observeAfter"], False)

    def test_phone_task_refresh_template_action_failure_falls_back_to_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'success': False,"
                    "'data': {"
                    "'mode': 'action_fast',"
                    "'errorCode': 'action_failed',"
                    "'error': 'scroll gesture did not change screen',"
                    "'metrics': {'mode': 'action_fast', 'totalMs': 24, 'rounds': 0}"
                    "}"
                    "}, ensure_ascii=False))\n"
                )
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:], 'metrics': {'mode': 'agent_fallback', 'rounds': 1}}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "refreshscreen", "mode": "safe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "agent")
            self.assertEqual(job["result"]["fallback"]["from"], "template/action_fast")
            self.assertEqual(job["result"]["fallback"]["errorCode"], "action_failed")
            self.assertEqual(job["result"]["metrics"]["mode"], "agent_fallback")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "run")
            self.assertIn("--execution-layer", argv)
            self.assertEqual(argv[argv.index("--execution-layer") + 1], "agent")

    def test_phone_task_route_keeps_agent_layer_explicit_for_unmatched_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "打开应用后完成多步骤搜索任务", "mode": "full", "profile": "deep"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertIn("--execution-layer", argv)
            self.assertEqual(argv[argv.index("--execution-layer") + 1], "agent")
            self.assertIn("--step-timeout-sec", argv)

    def test_phone_task_job_result_exposes_layered_steps_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "打开应用后完成多步骤搜索任务", "mode": "safe", "profile": "fast"},
            )

            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["job"]["progress"]["executionLayer"], "agent")
            self.assertEqual(submitted.json()["job"]["progress"]["currentStep"], "prepare")

            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            execution = job["result"]["execution"]
            self.assertEqual(execution["layer"], "agent")
            self.assertEqual(execution["profile"], "fast")
            self.assertEqual(execution["budget"]["maxRounds"], 12)
            self.assertLessEqual(execution["budget"]["pollMs"], 500)
            self.assertIn("prepare", [step["id"] for step in execution["steps"]])
            self.assertIn("execute", [step["id"] for step in execution["steps"]])
            self.assertIn("collect", [step["id"] for step in execution["steps"]])

    def test_phone_screenshot_uses_low_resolution_cached_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/screenshot")

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertIn("--max-long-side", argv)
            self.assertLessEqual(int(argv[argv.index("--max-long-side") + 1]), 960)
            self.assertIn("--quality", argv)
            self.assertLessEqual(int(argv[argv.index("--quality") + 1]), 65)
            self.assertIn("--no-grid", argv)
            self.assertIn("--cache-ttl-ms", argv)

    def test_phone_task_route_rejects_unknown_performance_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post("/api/phone/task", json={"prompt": "test", "profile": "turbo"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("fast / standard / deep", response.json()["error"])

    def test_phone_read_route_uses_direct_vision_read_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('agent path should not be used')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/read", json={"prompt": "read only", "knownHash": "abc123"})

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "read")
            self.assertIn("--prompt", argv)
            self.assertIn("read only", argv)
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "observe_fast")
            self.assertIn("--known-hash", argv)
            self.assertEqual(argv[argv.index("--known-hash") + 1], "abc123")

    def test_phone_read_route_reuses_last_screen_hash_for_incremental_observe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('agent path should not be used')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:], 'screenHash': 'hash-one'}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post("/api/phone/read", json={"prompt": "read one"})
            self.assertEqual(first.status_code, 200)
            first_job = _wait_for_job(client, first.json()["jobId"])
            self.assertEqual(first_job["status"], "succeeded")
            first_argv = json.loads(first_job["result"]["stdout"])["argv"]
            self.assertNotIn("--known-hash", first_argv)

            second = client.post("/api/phone/read", json={"prompt": "read two"})
            self.assertEqual(second.status_code, 200)
            second_job = _wait_for_job(client, second.json()["jobId"])
            self.assertEqual(second_job["status"], "succeeded")
            second_argv = json.loads(second_job["result"]["stdout"])["argv"]
            self.assertIn("--known-hash", second_argv)
            self.assertEqual(second_argv[second_argv.index("--known-hash") + 1], "hash-one")

    def test_phone_read_route_promotes_observe_fast_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('agent path should not be used')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'screenHash': 'hash-selectors',"
                    "'selectors': ["
                    "{'nodeId': 'node-1', 'label': 'Search', 'actionBody': {'action': 'click_description', 'contentDescription': 'Search'}}"
                    "]"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post("/api/phone/read", json={"prompt": "read selectors"})
            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])

            self.assertEqual(job["status"], "succeeded")
            selectors = job["result"]["selectors"]
            self.assertEqual(selectors[0]["label"], "Search")
            self.assertEqual(selectors[0]["actionBody"]["action"], "click_description")
            self.assertEqual(selectors[0]["actionBody"]["contentDescription"], "Search")

    def test_phone_task_can_use_cached_read_selector_index_for_action_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('cached selector should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "if sys.argv[1] == 'read':\n"
                    "    print(json.dumps({"
                    "'screenHash': 'hash-selectors',"
                    "'selectors': ["
                    "{'nodeId': 'node-1', 'label': 'Search', 'actionBody': {'action': 'click_description', 'contentDescription': 'Search'}}"
                    "]"
                    "}, ensure_ascii=False))\n"
                    "else:\n"
                    "    print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            read = client.post("/api/phone/read", json={"prompt": "read selectors"})
            self.assertEqual(read.status_code, 200)
            read_job = _wait_for_job(client, read.json()["jobId"])
            self.assertEqual(read_job["status"], "succeeded")

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "tap cached selector", "mode": "safe", "profile": "fast", "selectorIndex": 0},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "direct")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_description")
            self.assertEqual(body["contentDescription"], "Search")

    def test_phone_task_cached_selector_index_does_not_require_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('cached selector should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "if sys.argv[1] == 'read':\n"
                    "    print(json.dumps({"
                    "'screenHash': 'hash-selectors',"
                    "'selectors': ["
                    "{'nodeId': 'node-1', 'label': 'Search', 'actionBody': {'action': 'click_description', 'contentDescription': 'Search'}}"
                    "]"
                    "}, ensure_ascii=False))\n"
                    "else:\n"
                    "    print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            read = client.post("/api/phone/read", json={"prompt": "read selectors"})
            self.assertEqual(read.status_code, 200)
            self.assertEqual(_wait_for_job(client, read.json()["jobId"])["status"], "succeeded")

            submitted = client.post("/api/phone/task", json={"mode": "safe", "profile": "fast", "selectorIndex": 0})

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_description")
            self.assertEqual(body["contentDescription"], "Search")

    def test_phone_task_cached_selector_index_survives_unchanged_incremental_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('cached selector should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "argv = sys.argv[1:]\n"
                    "if argv[0] == 'read' and '--known-hash' in argv:\n"
                    "    print(json.dumps({"
                    "'argv': argv,"
                    "'screenHash': 'hash-selectors',"
                    "'unchanged': True,"
                    "'cacheHit': True,"
                    "'summary': 'same screen'"
                    "}, ensure_ascii=False))\n"
                    "elif argv[0] == 'read':\n"
                    "    print(json.dumps({"
                    "'argv': argv,"
                    "'screenHash': 'hash-selectors',"
                    "'selectors': ["
                    "{'nodeId': 'node-1', 'label': 'Search', 'actionBody': {'action': 'click_description', 'contentDescription': 'Search'}}"
                    "]"
                    "}, ensure_ascii=False))\n"
                    "else:\n"
                    "    print(json.dumps({'argv': argv}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            first = client.post("/api/phone/read", json={"prompt": "read selectors"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(_wait_for_job(client, first.json()["jobId"])["status"], "succeeded")

            second = client.post("/api/phone/read", json={"prompt": "read selectors again"})
            self.assertEqual(second.status_code, 200)
            second_job = _wait_for_job(client, second.json()["jobId"])
            self.assertEqual(second_job["status"], "succeeded")
            second_argv = json.loads(second_job["result"]["stdout"])["argv"]
            self.assertIn("--known-hash", second_argv)
            self.assertEqual(second_argv[second_argv.index("--known-hash") + 1], "hash-selectors")

            submitted = client.post("/api/phone/task", json={"mode": "safe", "profile": "fast", "selectorIndex": 0})

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_description")
            self.assertEqual(body["contentDescription"], "Search")

    def test_phone_task_cached_selector_index_preserves_observe_after_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('cached selector should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "if sys.argv[1] == 'read':\n"
                    "    print(json.dumps({"
                    "'screenHash': 'hash-selectors',"
                    "'selectors': ["
                    "{'nodeId': 'node-1', 'label': 'Search', 'actionBody': {'action': 'click_description', 'contentDescription': 'Search'}}"
                    "]"
                    "}, ensure_ascii=False))\n"
                    "else:\n"
                    "    print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            read = client.post("/api/phone/read", json={"prompt": "read selectors"})
            self.assertEqual(read.status_code, 200)
            self.assertEqual(_wait_for_job(client, read.json()["jobId"])["status"], "succeeded")

            submitted = client.post(
                "/api/phone/task",
                json={"mode": "safe", "profile": "fast", "selectorIndex": 0, "observeAfter": False},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_description")
            self.assertEqual(body["contentDescription"], "Search")
            self.assertEqual(body["observeAfter"], False)

    def test_phone_task_direct_action_uses_action_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('direct action should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "back", "mode": "safe", "profile": "fast", "directAction": "back"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "direct")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "action_fast")
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "back")

    def test_phone_task_direct_action_preserves_top_level_observe_after_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('direct action should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "back", "mode": "safe", "profile": "fast", "directAction": "back", "observeAfter": False},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "back")
            self.assertEqual(body["observeAfter"], False)

    def test_phone_task_explicit_action_body_uses_action_fast_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('explicit action body should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "点击继续按钮",
                    "mode": "safe",
                    "profile": "fast",
                    "actionBody": {
                        "action": "click_text",
                        "text": "继续",
                        "targetLabel": "继续按钮",
                        "reason": "user explicitly requested one fast click",
                    },
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "direct")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "action_fast")
            self.assertNotIn("--allow-unknown-target", argv)
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_text")
            self.assertEqual(body["text"], "继续")
            self.assertIn("metrics", job["result"])
            self.assertEqual(job["result"]["metrics"]["mode"], "action_fast")
            self.assertEqual(job["result"]["metrics"]["rounds"], 0)
            self.assertGreaterEqual(job["result"]["metrics"]["totalMs"], 0)

    def test_phone_task_explicit_action_body_preserves_top_level_observe_after_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('explicit action body should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "mode": "safe",
                    "profile": "fast",
                    "observeAfter": False,
                    "actionBody": {
                        "action": "click_text",
                        "text": "Continue",
                    },
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            argv = json.loads(job["result"]["stdout"])["argv"]
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "click_text")
            self.assertEqual(body["text"], "Continue")
            self.assertEqual(body["observeAfter"], False)

    def test_phone_task_wait_element_action_body_normalizes_and_preserves_resource_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('wait element action body should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "wait for done page",
                    "mode": "safe",
                    "profile": "fast",
                    "actionBody": {
                        "action": "waitElement",
                        "resourceId": "com.example:id/done",
                        "timeoutMs": 1800,
                    },
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["executionLayer"], "direct")
            argv = json.loads(job["result"]["stdout"])["argv"]
            self.assertEqual(argv[0], "action")
            self.assertIn("--fast-path", argv)
            self.assertEqual(argv[argv.index("--fast-path") + 1], "action_fast")
            body = json.loads(argv[argv.index("--action-body") + 1])
            self.assertEqual(body["action"], "wait_element")
            self.assertEqual(body["resourceId"], "com.example:id/done")
            self.assertEqual(body["timeoutMs"], 1800)

    def test_phone_task_action_body_promotes_post_observe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('explicit action body should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'success': True,"
                    "'data': {"
                    "'mode': 'action_fast',"
                    "'action': 'click_text',"
                    "'currentStep': 'complete',"
                    "'events': [{'type': 'action_fast_completed', 'toolName': 'click_text', 'success': True}],"
                    "'screenHash': 'hash-after-action',"
                    "'summary': 'Settings page after click',"
                    "'currentPackage': 'com.android.settings',"
                    "'metrics': {'mode': 'action_fast', 'totalMs': 17, 'rounds': 0}"
                    "}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "点击设置",
                    "mode": "safe",
                    "profile": "fast",
                    "actionBody": {
                        "action": "click_text",
                        "text": "设置",
                        "targetLabel": "设置",
                        "reason": "single fast action with post observe",
                    },
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(job["result"]["screenHash"], "hash-after-action")
            self.assertEqual(job["result"]["summary"], "Settings page after click")
            self.assertEqual(job["result"]["currentPackage"], "com.android.settings")
            self.assertEqual(job["result"]["metrics"]["screenHash"], "hash-after-action")
            self.assertEqual(job["result"]["mode"], "action_fast")
            self.assertEqual(job["result"]["action"], "click_text")
            self.assertEqual(job["result"]["currentStep"], "complete")
            self.assertEqual(job["result"]["events"][0]["type"], "action_fast_completed")

    def test_phone_task_post_observe_hash_is_reused_by_next_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('fast paths should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "argv = sys.argv[1:]\n"
                    "if argv[0] == 'action':\n"
                    "    print(json.dumps({'success': True, 'data': {'screenHash': 'hash-after-action', 'summary': 'after action', 'metrics': {'mode': 'action_fast', 'rounds': 0}}}, ensure_ascii=False))\n"
                    "else:\n"
                    "    print(json.dumps({'argv': argv}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            action = client.post(
                "/api/phone/task",
                json={
                    "prompt": "点击设置",
                    "mode": "safe",
                    "profile": "fast",
                    "actionBody": {
                        "action": "click_text",
                        "text": "设置",
                        "targetLabel": "设置",
                        "reason": "single fast action with post observe",
                    },
                },
            )
            self.assertEqual(action.status_code, 200)
            action_job = _wait_for_job(client, action.json()["jobId"])
            self.assertEqual(action_job["status"], "succeeded")

            read = client.post("/api/phone/read", json={"prompt": "read after action"})
            self.assertEqual(read.status_code, 200)
            read_job = _wait_for_job(client, read.json()["jobId"])
            self.assertEqual(read_job["status"], "succeeded")
            argv = json.loads(read_job["result"]["stdout"])["argv"]
            self.assertIn("--known-hash", argv)
            self.assertEqual(argv[argv.index("--known-hash") + 1], "hash-after-action")

    def test_phone_task_failure_exposes_error_code_reason_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('direct failure should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "console.error('task_busy: another APKClaw job is running');\n"
                    "process.exit(2);\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "back", "mode": "safe", "profile": "fast", "directAction": "back"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "failed")
            result = job["result"]
            self.assertNotEqual(result["code"], 0)
            self.assertEqual(result["errorCode"], "task_busy")
            self.assertEqual(result["reason"], result["error"])
            self.assertEqual(result["metrics"]["mode"], "action_fast")
            self.assertEqual(result["mode"], "action_fast")
            self.assertEqual(result["currentStep"], "failed")
            self.assertEqual(result["metrics"]["rounds"], 0)
            self.assertGreaterEqual(result["metrics"]["totalMs"], 0)

    def test_phone_task_stdout_success_false_fails_job_with_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit('direct action should not use agent')\n")
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'success': False,"
                    "'data': {"
                    "'mode': 'action_fast',"
                    "'errorCode': 'action_failed',"
                    "'error': 'Text not found: Continue',"
                    "'metrics': {'mode': 'action_fast', 'totalMs': 19, 'rounds': 0}"
                    "}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={
                    "prompt": "点击继续",
                    "mode": "safe",
                    "profile": "fast",
                    "actionBody": {
                        "action": "click_text",
                        "text": "继续",
                        "targetLabel": "继续",
                        "reason": "single fast action",
                    },
                },
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "failed")
            result = job["result"]
            self.assertEqual(result["code"], "payload_failed")
            self.assertEqual(result["errorCode"], "action_failed")
            self.assertEqual(result["reason"], "Text not found: Continue")
            self.assertEqual(result["metrics"]["mode"], "action_fast")
            self.assertEqual(result["metrics"]["totalMs"], 19)

    def test_phone_task_result_promotes_queue_fields_from_agent_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-agent.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json\n"
                    "print(json.dumps({"
                    "'ok': True,"
                    "'taskId': 'task-1',"
                    "'currentStep': 'queued',"
                    "'queue': {"
                    "'queueMs': 120,"
                    "'queueDepth': 2,"
                    "'queuePosition': 1,"
                    "'currentTaskId': 'task-0',"
                    "'cancelRequested': False"
                    "},"
                    "'events': [{'type': 'queued', 'message': 'queued behind task-0'}],"
                    "'metrics': {'mode': 'agent', 'totalMs': 55, 'rounds': 1},"
                    "'final': {"
                    "'taskId': 'task-1',"
                    "'status': 'success',"
                    "'queueMs': 120,"
                    "'queueDepth': 2,"
                    "'queuePosition': 1,"
                    "'currentTaskId': 'task-0',"
                    "'cancelRequested': False,"
                    "'result': {"
                    "'success': True,"
                    "'answer': 'done',"
                    "'currentStep': 'complete',"
                    "'metrics': {'mode': 'agent', 'totalMs': 55, 'rounds': 1},"
                    "'events': [{'type': 'complete', 'message': 'done'}]"
                    "}"
                    "}"
                    "}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            submitted = client.post(
                "/api/phone/task",
                json={"prompt": "请执行一个复杂手机任务并返回结果", "mode": "safe", "profile": "standard"},
            )

            self.assertEqual(submitted.status_code, 200)
            job = _wait_for_job(client, submitted.json()["jobId"])
            self.assertEqual(job["status"], "succeeded")
            result = job["result"]
            self.assertEqual(result["queue"]["queueMs"], 120)
            self.assertEqual(result["queue"]["queueDepth"], 2)
            self.assertEqual(result["queue"]["queuePosition"], 1)
            self.assertEqual(result["queue"]["currentTaskId"], "task-0")
            self.assertFalse(result["queue"]["cancelRequested"])
            self.assertEqual(result["metrics"]["mode"], "agent")
            self.assertEqual(result["metrics"]["rounds"], 1)

    def test_phone_task_route_rejects_unknown_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            app = FastAPI()
            ctx = _test_context(temp_dir, JobManager(logs.append), logs)
            register_phone_routes(app, ctx)
            client = TestClient(app)

            response = client.post("/api/phone/task", json={"prompt": "test", "mode": "dangerous"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("模式", response.json()["error"])

    def test_phone_task_route_writes_task_ledger_action_trace_and_template_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            scripts_dir = os.path.join(temp_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "openclaw-phone-vision.mjs"), "w", encoding="utf-8") as handle:
                handle.write(
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv[1:]}, ensure_ascii=False))\n"
                )

            logs: list[str] = []
            job_mgr = JobManager(logs.append)
            app = FastAPI()
            ctx = _test_context(temp_dir, job_mgr, logs)
            register_phone_routes(app, ctx)
            register_job_routes(app, ctx)
            client = TestClient(app)

            with patch.dict(os.environ, {"LOOM_AUDIT_DIR": temp_dir}):
                submitted = client.post(
                    "/api/phone/task",
                    json={
                        "prompt": "读取当前页面 sk-test-token",
                        "mode": "safe",
                        "profile": "fast",
                        "template": "screen-summary",
                    },
                )
                self.assertEqual(submitted.status_code, 200)
                job = _wait_for_job(client, submitted.json()["jobId"])
                self.assertEqual(job["status"], "succeeded")

                ledger_path = os.path.join(temp_dir, "loom-task-ledger.jsonl")
                trace_path = os.path.join(temp_dir, "loom-action-trace.jsonl")
                optimizer_path = os.path.join(temp_dir, "loom-template-optimizer.json")
                with open(ledger_path, "r", encoding="utf-8") as handle:
                    ledger = json.loads(handle.readline())
                with open(trace_path, "r", encoding="utf-8") as handle:
                    trace = json.loads(handle.readline())
                with open(optimizer_path, "r", encoding="utf-8") as handle:
                    optimizer = json.load(handle)

        self.assertEqual(ledger["source"], "bridge")
        self.assertEqual(ledger["tool"], "bridge:phone.task")
        self.assertEqual(ledger["actionTraceId"], trace["traceId"])
        self.assertEqual(trace["taskId"], ledger["taskId"])
        self.assertIn("templateCandidate", ledger)
        self.assertGreaterEqual(len(optimizer["candidates"]), 1)
        serialized = json.dumps({"ledger": ledger, "trace": trace, "optimizer": optimizer}, ensure_ascii=False)
        self.assertNotIn("sk-test-token", serialized)


def _test_context(base_path: str, job_mgr: JobManager, logs: list[str], storage: dict[str, dict] | None = None) -> SimpleNamespace:
    storage = storage if storage is not None else {}

    async def body(request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def fastapi_json(data: dict, status_code: int = 200):
        payload = dict(data)
        payload["_meta"] = {"ok": 200 <= status_code < 400 and "error" not in payload, "status": status_code}
        return JSONResponse(status_code=status_code, content=payload)

    return SimpleNamespace(
        append_log=logs.append,
        auth_error=lambda _request: None,
        body=body,
        fastapi_json=fastapi_json,
        get_job_mgr=lambda: job_mgr,
        paths=SimpleNamespace(base_path=base_path, launcher_dir=base_path, node_exe=sys.executable),
        read_json=lambda path, default: storage.get(path, default),
        write_json=lambda path, data: storage.__setitem__(path, data),
        sanitize_text=lambda text: text,
    )


def _wire_context(base_path: str, job_mgr: JobManager, logs: list[str], session: dict | None) -> SimpleNamespace:
    paths = AppPaths(base_path)

    async def body(request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def fastapi_json(data: dict, status_code: int = 200):
        payload = dict(data)
        payload["_meta"] = {"ok": 200 <= status_code < 400 and "error" not in payload, "status": status_code}
        return JSONResponse(status_code=status_code, content=payload)

    manager = SimpleNamespace(current=lambda: session)
    return SimpleNamespace(
        append_log=logs.append,
        auth_error=lambda _request: None,
        body=body,
        fastapi_json=fastapi_json,
        get_job_mgr=lambda: job_mgr,
        get_newapi_account_mgr=lambda: manager,
        get_wire_svc=lambda: WireService(paths, logs.append),
        paths=paths,
        read_json=read_json,
        sanitize_text=lambda text: text,
        write_json=lambda path, data: None,
    )


def _session_snapshot() -> dict:
    return {
        "source": "newapi_account",
        "memberId": "newapi:test-user",
        "memberName": "test@example.invalid",
        "gatewayBaseUrl": "https://api.heang.top/v1",
        "gatewayDefaultModel": "qwen3.7-plus",
        "gatewayModels": ["qwen3.7-plus", "gpt-image-1"],
        "memberToken": "sk-test-token-not-real",
        "gateway": {
            "classifiedModels": {
                "text": ["qwen3.7-plus"],
                "image": ["gpt-image-1"],
                "video": [],
            },
        },
        "phoneAgent": {
            "apiKey": "sk-test-token-not-real",
            "model": "agnes-2.0-flash",
        },
    }


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        if response.status_code == 200:
            job = response.json()["job"]
            if job.get("status") in {"succeeded", "failed"}:
                return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job_id}")


if __name__ == "__main__":
    unittest.main()
