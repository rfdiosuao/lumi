from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.routes_jobs import register_job_routes
from api.routes_phone import _public_store, register_phone_routes
from core.paths import AppPaths
from core.storage import read_json
from core.wire_config import WireService
from services.jobs import JobManager


class PhoneRouteSnapshotTests(unittest.TestCase):
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

    def test_phone_config_device_rejects_invalid_url_with_chinese_error(self) -> None:
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

            self.assertEqual(response.status_code, 400)
            self.assertIn("手机地址必须是 http:// 或 https:// 开头的完整地址", response.json()["error"])

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
