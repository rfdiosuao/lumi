from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from api.routes_account import _account_response, _redact_secret_text
from api.routes_account import register_account_routes
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


class AccountRouteResponseTests(unittest.TestCase):
    def test_account_response_does_not_expose_session_secrets(self) -> None:
        response = _account_response(
            account={
                "loggedIn": True,
                "account": "user@example.com",
                "tokenMasked": "sk-***1234",
            },
            session={
                "memberToken": "sk-secret",
                "newApi": {"sessionCookie": "sid=secret"},
                "lastSyncResults": [
                    {"target": "image", "ok": True, "apiKey": "sk-secret"},
                    {"target": "openclaw", "ok": False, "error": "contains sk-secret"},
                ],
            },
            extra_sync_results=[{"target": "openclaw", "ok": True, "apiKey": "sk-secret"}],
        )

        dumped = repr(response)
        self.assertNotIn("member", response)
        self.assertNotIn("sk-secret", dumped)
        self.assertNotIn("sessionCookie", dumped)
        self.assertEqual(response["account"]["account"], "user@example.com")

    def test_error_text_redacts_secret_markers(self) -> None:
        secret = "s" + "k-" + "demo-secret"
        redacted = _redact_secret_text(f"failed with apiKey={secret}")

        self.assertNotIn(secret, redacted)
        self.assertIn("apiKey=[redacted]", redacted)

    def test_account_sync_uses_manager_wire_results_without_legacy_openclaw_bypass(self) -> None:
        app = FastAPI()
        manager = SimpleNamespace(
            refresh_current=lambda: {
                "lastSyncResults": [
                    {"target": "openclaw", "ok": True},
                    {"target": "phone", "ok": True},
                ],
            },
            public_session=lambda: {
                "loggedIn": True,
                "account": "user@example.invalid",
            },
        )

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

        def legacy_bypass():
            raise AssertionError("legacy OpenClaw direct sync should not be called")

        ctx = SimpleNamespace(
            auth_error=lambda _request: None,
            body=body,
            fastapi_json=fastapi_json,
            get_newapi_account_mgr=lambda: manager,
            append_log=lambda _text: None,
            sync_openclaw_models_from_api_profiles=legacy_bypass,
        )
        register_account_routes(app, ctx)
        client = TestClient(app)

        response = client.post("/api/account/sync")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["target"] for item in response.json()["syncResults"]],
            ["openclaw", "phone"],
        )

    def test_email_code_send_route_uses_bridge_manager_and_hides_sensitive_fields(self) -> None:
        app = FastAPI()
        calls = []

        def send_email_code(email: str, *, base_url: str = "") -> dict:
            calls.append((email, base_url))
            return {
                "sent": True,
                "email": email,
                "retryAfter": 60,
                "code": "123456",
                "token": "sk-route-secret",
            }

        manager = SimpleNamespace(send_email_code=send_email_code)
        register_account_routes(app, _ctx(manager))
        client = TestClient(app)

        response = client.post(
            "/api/account/email-code/send",
            json={"email": "user@example.invalid", "baseUrl": "https://api.heang.top"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(calls, [("user@example.invalid", "https://api.heang.top")])
        self.assertTrue(payload["sent"])
        self.assertNotIn("123456", repr(payload))
        self.assertNotIn("sk-route-secret", repr(payload))

    def test_email_code_login_route_returns_public_account_and_redacted_sync_results(self) -> None:
        app = FastAPI()
        calls = []

        def login_with_email_code(email: str, code: str, *, base_url: str = "") -> dict:
            calls.append((email, code, base_url))
            return {
                "lastSyncResults": [
                    {"target": "openclaw", "ok": True, "apiKey": "sk-route-secret"},
                    {"target": "phone", "ok": False, "error": "token=sk-route-secret"},
                ],
            }

        manager = SimpleNamespace(
            login_with_email_code=login_with_email_code,
            public_session=lambda: {
                "loggedIn": True,
                "account": "user@example.invalid",
                "tokenMasked": "sk-****cret",
            },
        )
        register_account_routes(app, _ctx(manager))
        client = TestClient(app)

        response = client.post(
            "/api/account/email-code/login",
            json={"email": "user@example.invalid", "code": "654321", "baseUrl": "https://api.heang.top"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(calls, [("user@example.invalid", "654321", "https://api.heang.top")])
        self.assertEqual(payload["account"]["account"], "user@example.invalid")
        self.assertNotIn("sk-route-secret", repr(payload))
        self.assertNotIn("apiKey", repr(payload["syncResults"]))
        self.assertIn("token=[redacted]", repr(payload))


def _ctx(manager):
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
        auth_error=lambda _request: None,
        body=body,
        fastapi_json=fastapi_json,
        get_newapi_account_mgr=lambda: manager,
        append_log=lambda _text: None,
    )


if __name__ == "__main__":
    unittest.main()
