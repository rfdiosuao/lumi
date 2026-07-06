from __future__ import annotations

import json
import os
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
from api.routes_matrix import register_matrix_routes
from services.jobs import JobManager


class MatrixRouteContractTests(unittest.TestCase):
    def test_matrix_event_stream_returns_sse_status_and_events_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _app, client = _client(temp_dir)
            client.post("/api/matrix/device/register", json={"deviceId": "phone-a", "group": "demo", "online": True})

            response = client.get("/api/matrix/events/stream?once=1")

            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.headers["content-type"])
            self.assertIn("event: matrix", response.text)
            self.assertIn('"schema": "loom.matrix.stream.v1"', response.text)
            self.assertIn('"deviceId": "phone-a"', response.text)

    def test_matrix_dispatch_executes_direct_path_and_records_result_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_script(temp_dir, "openclaw-phone-vision.mjs")
            app, client = _client(temp_dir)

            registered = client.post(
                "/api/matrix/device/register",
                json={"deviceId": "phone-a", "group": "demo", "online": True},
            )
            self.assertEqual(registered.status_code, 200)

            with patch.dict(os.environ, {"LOOM_AUDIT_DIR": temp_dir}):
                submitted = client.post(
                    "/api/matrix/dispatch",
                    json={
                        "prompt": "读取当前屏幕",
                        "mode": "observe",
                        "profile": "fast",
                        "target": {"deviceIds": ["phone-a"]},
                    },
                )

                self.assertEqual(submitted.status_code, 202)
                payload = submitted.json()
                campaign_id = payload["task"]["campaignId"]
                job = _wait_for_job(client, payload["jobId"])

                ledger_path = os.path.join(temp_dir, "loom-task-ledger.jsonl")
                trace_path = os.path.join(temp_dir, "loom-action-trace.jsonl")
                with open(ledger_path, "r", encoding="utf-8") as handle:
                    ledger = json.loads(handle.readline())
                with open(trace_path, "r", encoding="utf-8") as handle:
                    trace = json.loads(handle.readline())

            self.assertEqual(job["status"], "succeeded")
            result = job["result"]
            self.assertTrue(result["success"])
            self.assertEqual(result["results"][0]["executionLayer"], "direct")
            self.assertIn("--device-id", result["results"][0]["stdoutPreview"])
            self.assertIn("phone-a", result["results"][0]["stdoutPreview"])

            watched = client.get(f"/api/matrix/watch?campaignId={campaign_id}")
            event_types = [event["type"] for event in watched.json()["events"]]
            self.assertIn("result", event_types)

            status = client.get("/api/matrix/status").json()
            self.assertFalse(status["devices"][0]["busy"])
            self.assertEqual(status["campaigns"][-1]["status"], "succeeded")
            self.assertEqual(ledger["source"], "bridge")
            self.assertEqual(ledger["tool"], "bridge:matrix.dispatch")
            self.assertEqual(ledger["actionTraceId"], trace["traceId"])

    def test_matrix_dispatch_streams_device_script_output_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_script(
                temp_dir,
                "openclaw-phone-agent.mjs",
                body=(
                    "import json, time\n"
                    "print('agent round 1: matrix live log', flush=True)\n"
                    "time.sleep(0.7)\n"
                    "print(json.dumps({'ok': True}, ensure_ascii=False), flush=True)\n"
                    "time.sleep(0.1)\n"
                ),
            )
            _app, client = _client(temp_dir)
            client.post("/api/matrix/device/register", json={"deviceId": "phone-a", "group": "demo", "online": True})

            submitted = client.post(
                "/api/matrix/dispatch",
                json={
                    "prompt": "执行一个需要 Agent 的真实手机任务",
                    "mode": "safe",
                    "profile": "fast",
                    "target": {"deviceIds": ["phone-a"]},
                },
            )

            self.assertEqual(submitted.status_code, 202)
            try:
                event = _wait_for_matrix_event(temp_dir, "matrix live log", timeout=0.45)
            finally:
                _wait_for_job(client, submitted.json()["jobId"], timeout=5.0)
            self.assertEqual(event["type"], "phone.events.phone.task.stdout")
            self.assertEqual(event["deviceId"], "phone-a")
            self.assertEqual(event["source"], "phone.task.stdout")

    def test_matrix_dispatch_safety_gate_returns_product_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_script(temp_dir, "openclaw-phone-vision.mjs")
            _app, client = _client(temp_dir)
            client.post("/api/matrix/device/register", json={"deviceId": "phone-a", "group": "demo", "online": True})

            response = client.post(
                "/api/matrix/dispatch",
                json={"prompt": "批量私信所有客户", "target": {"groups": ["demo"]}},
            )

            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "safety_confirmation_required")
            self.assertIn("确认", response.json()["error"])

    def test_matrix_leads_route_records_redacted_local_lead(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _app, client = _client(temp_dir)

            recorded = client.post(
                "/api/matrix/leads",
                json={
                    "summary": "用户询问套餐 13800000000 Bearer secret-token",
                    "deviceId": "phone-a",
                    "campaignId": "campaign_123",
                    "tags": ["演示"],
                    "token": "secret-token",
                },
            )
            listed = client.get("/api/matrix/leads?limit=5")

        self.assertEqual(recorded.status_code, 200)
        payload = recorded.json()
        serialized = json.dumps({"recorded": payload, "listed": listed.json()}, ensure_ascii=False)
        self.assertTrue(payload["lead"]["leadId"].startswith("lead_"))
        self.assertEqual(listed.json()["leads"][0]["deviceId"], "phone-a")
        self.assertNotIn("13800000000", serialized)
        self.assertNotIn("secret-token", serialized)

    def test_matrix_retry_route_dispatches_failed_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_script(temp_dir, "openclaw-phone-vision.mjs", return_code=1)
            _app, client = _client(temp_dir)
            client.post("/api/matrix/device/register", json={"deviceId": "phone-a", "group": "demo", "online": True})
            submitted = client.post(
                "/api/matrix/dispatch",
                json={"prompt": "读取当前屏幕", "mode": "observe", "target": {"deviceIds": ["phone-a"]}},
            )
            campaign_id = submitted.json()["task"]["campaignId"]
            _wait_for_job(client, submitted.json()["jobId"])

            _write_script(temp_dir, "openclaw-phone-vision.mjs", return_code=0)
            retried = client.post("/api/matrix/retry", json={"campaignId": campaign_id})
            retry_job = _wait_for_job(client, retried.json()["jobId"])

        self.assertEqual(retried.status_code, 202)
        self.assertEqual(retry_job["status"], "succeeded")
        retry_payload = retried.json()
        self.assertTrue(retry_payload["retry"]["retried"])
        self.assertEqual(retry_payload["retry"]["retryOf"], campaign_id)
        self.assertTrue(retry_payload["retry"]["task"]["campaignId"].startswith("campaign_"))


def _write_script(base_path: str, name: str, *, return_code: int = 0, body: str = "") -> None:
    scripts_dir = os.path.join(base_path, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    with open(os.path.join(scripts_dir, name), "w", encoding="utf-8") as handle:
        handle.write(body or (
            "import json, sys\n"
            "print(json.dumps({'argv': sys.argv[1:], 'ok': True}, ensure_ascii=False))\n"
            f"raise SystemExit({return_code})\n"
        ))


def _client(base_path: str) -> tuple[FastAPI, TestClient]:
    logs: list[str] = []
    job_mgr = JobManager(logs.append)
    app = FastAPI()
    ctx = _context(base_path, job_mgr, logs)
    register_matrix_routes(app, ctx)
    register_job_routes(app, ctx)
    return app, TestClient(app)


def _context(base_path: str, job_mgr: JobManager, logs: list[str]) -> SimpleNamespace:
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
        sanitize_text=lambda text: text,
    )


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


def _wait_for_matrix_event(base_path: str, needle: str, timeout: float = 1.0) -> dict:
    path = os.path.join(base_path, "matrix-events.jsonl")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if needle in str(event.get("message") or ""):
                        return event
        time.sleep(0.02)
    raise AssertionError(f"matrix event containing {needle!r} was not written")


if __name__ == "__main__":
    unittest.main()
