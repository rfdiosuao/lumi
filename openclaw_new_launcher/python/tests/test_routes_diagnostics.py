from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.routes_diagnostics import register_diagnostics_routes


class DiagnosticsRouteTests(unittest.TestCase):
    def test_repair_requires_post_confirmation(self) -> None:
        app = FastAPI()
        calls: list[str] = []
        ctx = _test_context(calls)
        register_diagnostics_routes(app, ctx)
        client = TestClient(app)

        get_response = client.get("/api/diagnostics/repair")
        post_response = client.post("/api/diagnostics/repair", json={})

        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(post_response.status_code, 403)
        self.assertIn("环境修复需要确认", post_response.json()["error"])
        self.assertEqual(calls, [])

    def test_repair_runs_after_confirmation(self) -> None:
        app = FastAPI()
        calls: list[str] = []
        ctx = _test_context(calls)
        register_diagnostics_routes(app, ctx)
        client = TestClient(app)

        response = client.post("/api/diagnostics/repair", json={"confirmed": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["repair"])
        self.assertEqual(response.json()["diagnostics"]["summary"]["status"], "ok")


def _test_context(calls: list[str]) -> SimpleNamespace:
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

    class ProcessService:
        def repair_environment(self):
            calls.append("repair")
            return {"actions": [], "diagnostics": {"summary": {"status": "ok"}}}

    return SimpleNamespace(
        auth_error=lambda _request: None,
        body=body,
        fastapi_json=fastapi_json,
        get_process_svc=lambda: ProcessService(),
        append_runtime_checks=lambda diagnostics: diagnostics,
    )


if __name__ == "__main__":
    unittest.main()
