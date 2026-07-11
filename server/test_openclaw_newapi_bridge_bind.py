from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("openclaw_newapi_bridge.py")


def load_bridge():
    spec = importlib.util.spec_from_file_location("openclaw_newapi_bridge_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BindTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = load_bridge()
        self.tmp = tempfile.TemporaryDirectory()
        self.bridge.BIND_DB_PATH = str(Path(self.tmp.name) / "bind-tickets.db")
        self.bridge.DB_PATH = str(Path(self.tmp.name) / "one-api.db")
        self.original_launcher_token = self.bridge.handle_launcher_token
        self.original_send_code = self.bridge._send_login_email_code
        self.original_fetch_models = self.bridge.fetch_models
        self.original_request_json = self.bridge.request_json
        self.original_auth_failure_limit = self.bridge.AUTH_FAILURE_RATE_LIMIT
        self.original_public_api_base = self.bridge.PUBLIC_API_BASE
        self._init_newapi_db()

    def tearDown(self) -> None:
        self.bridge.handle_launcher_token = self.original_launcher_token
        self.bridge._send_login_email_code = self.original_send_code
        self.bridge.fetch_models = self.original_fetch_models
        self.bridge.request_json = self.original_request_json
        self.bridge.AUTH_FAILURE_RATE_LIMIT = self.original_auth_failure_limit
        self.bridge.PUBLIC_API_BASE = self.original_public_api_base
        self.tmp.cleanup()

    def _init_newapi_db(self) -> None:
        connection = sqlite3.connect(self.bridge.DB_PATH)
        try:
            connection.executescript(
                """
                create table users (
                    id integer primary key,
                    username text,
                    password text,
                    display_name text,
                    role integer,
                    status integer,
                    email text,
                    "group" text,
                    deleted_at datetime
                );
                create table tokens (
                    id integer primary key autoincrement,
                    user_id integer,
                    key varchar(128),
                    status integer default 1,
                    name text,
                    created_time integer,
                    accessed_time integer,
                    expired_time integer default -1,
                    remain_quota integer default 0,
                    unlimited_quota numeric,
                    model_limits_enabled numeric,
                    model_limits text,
                    allow_ips text default '',
                    used_quota integer default 0,
                    "group" text default '',
                    cross_group_retry numeric,
                    deleted_at datetime
                );
                create table options (
                    key text primary key,
                    value text
                );
                """
            )
            connection.execute(
                'insert into users(id, username, status, email, "group", deleted_at) values(42, ?, 1, ?, ?, null)',
                ("user@example.com", "user@example.com", "default"),
            )
            connection.execute(
                'insert into tokens(user_id, key, status, name, created_time, expired_time, remain_quota, unlimited_quota, model_limits_enabled, model_limits, "group", deleted_at) values(42, ?, 1, ?, 1, -1, 0, 1, 0, "", "default", null)',
                ("sk-test-secret-value", "LOOM test token"),
            )
            connection.commit()
        finally:
            connection.close()

    def stub_launcher_token(self, _body):
        return 200, {
            "success": True,
            "data": {
                "userId": "42",
                "account": "user@example.com",
                "key": "sk-test-secret-value",
                "tokenMasked": "sk-t***alue",
                "tokenId": 7,
                "tokenName": "OpenClaw Launcher",
                "source": "existing",
                "models": ["qwen3.7-plus", "agnes-2.0-flash"],
            },
        }

    def test_start_returns_ticket_without_raw_key(self):
        self.bridge.handle_launcher_token = self.stub_launcher_token

        status, payload = self.bridge.handle_bind_start({"username": "user@example.com", "password": "pw"})

        self.assertEqual(status, 200)
        data = payload["data"]
        self.assertTrue(data["ticket"].startswith("ocb_"))
        self.assertEqual(data["account"], "user@example.com")
        self.assertEqual(data["tokenMasked"], "sk-t***alue")
        self.assertIn("models", data)
        self.assertNotIn("key", data)

    def test_launcher_payload_does_not_reuse_limited_historical_token(self):
        connection = sqlite3.connect(self.bridge.DB_PATH)
        try:
            connection.execute("delete from tokens")
            connection.execute(
                'insert into tokens(user_id, key, status, name, created_time, expired_time, remain_quota, unlimited_quota, model_limits_enabled, model_limits, "group", deleted_at) values(42, ?, 1, ?, 1, -1, 0, 1, 1, "agnes-2.0-flash", "default", null)',
                ("sk-limited-old", "old user token"),
            )
            connection.commit()
        finally:
            connection.close()
        self.bridge.fetch_models = lambda token: ["qwen3.7-plus"] if token != "sk-limited-old" else ["agnes-2.0-flash"]

        self.assertIsNone(self.bridge.select_token("42"))
        status, payload = self.bridge.build_launcher_payload(user_id="42", account="user@example.com", group="default")

        self.assertEqual(status, 200)
        data = payload["data"]
        self.assertEqual(data["source"], "created")
        self.assertTrue(data["tokenName"].startswith("LOOM Launcher "))
        self.assertFalse(data["modelLimitsEnabled"])
        self.assertNotEqual(data["key"], "sk-limited-old")
        self.assertEqual(data["models"], ["qwen3.7-plus"])

    def test_launcher_payload_carries_account_group_and_session_cookie_for_one_request_login(self):
        self.bridge.fetch_models = lambda _token: ["qwen3.7-plus", "glm-5.2-coding", "agnes-2.0-flash"]

        status, payload = self.bridge.build_launcher_payload(
            user_id="42",
            account="user@example.com",
            group="pro",
            session_cookie="session=fake-session-not-real",
        )

        self.assertEqual(status, 200)
        data = payload["data"]
        self.assertEqual(data["userId"], "42")
        self.assertEqual(data["account"], "user@example.com")
        self.assertEqual(data["group"], "pro")
        self.assertEqual(data["sessionCookie"], "session=fake-session-not-real")
        self.assertEqual(data["models"], ["qwen3.7-plus", "glm-5.2-coding", "agnes-2.0-flash"])
        self.assertEqual(data["defaults"]["textModel"], "glm-5.2-coding")

    def test_launcher_payload_uses_configured_public_api_base(self):
        self.bridge.PUBLIC_API_BASE = "https://relay.example.com/openai/v1"
        self.bridge.fetch_models = lambda _token: ["qwen3.7-plus"]

        status, payload = self.bridge.build_launcher_payload(
            user_id="42",
            account="user@example.com",
            group="default",
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["api"]["baseUrl"], "https://relay.example.com/openai/v1")

    def test_launcher_payload_fails_closed_when_model_catalog_is_empty(self):
        self.bridge.fetch_models = lambda _token: []

        status, payload = self.bridge.build_launcher_payload(
            user_id="42",
            account="user@example.com",
            group="default",
        )

        self.assertEqual(status, 503)
        self.assertFalse(payload["success"])
        self.assertNotIn("sk-test-secret-value", repr(payload))

    def test_launcher_login_rejection_returns_401_without_token_lookup(self):
        self.bridge.request_json = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("invalid credentials"))

        status, payload = self.bridge.handle_launcher_token({
            "username": "user@example.com",
            "password": "wrong-password",
        })

        self.assertEqual(status, 401)
        self.assertFalse(payload["success"])
        self.assertIn("invalid credentials", payload["error"])

    def test_launcher_preserves_upstream_rate_limit_status(self):
        self.bridge.request_json = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            self.bridge.BridgeUpstreamError("too many requests", status_code=429)
        )

        status, payload = self.bridge.handle_launcher_token({
            "username": "user@example.com",
            "password": "password-not-real",
        })

        self.assertEqual(status, 429)
        self.assertIn("too many requests", payload["error"])
        self.assertFalse(self.bridge.auth_failure_limited("user@example.com", "password"))

    def test_launcher_login_rate_limits_repeated_failures_per_account(self):
        calls = []

        def reject_login(*_args, **_kwargs):
            calls.append(True)
            raise RuntimeError("invalid credentials")

        self.bridge.AUTH_FAILURE_RATE_LIMIT = 3
        self.bridge.request_json = reject_login
        body = {"username": "user@example.com", "password": "wrong-password"}

        statuses = [self.bridge.handle_launcher_token(body)[0] for _ in range(4)]

        self.assertEqual(statuses, [401, 401, 401, 429])
        self.assertEqual(len(calls), 3)

    def test_successful_launcher_login_clears_previous_failure_budget(self):
        calls = []

        def flaky_login(*_args, **_kwargs):
            calls.append(True)
            if len(calls) <= 2:
                raise RuntimeError("invalid credentials")
            return {
                "success": True,
                "data": {
                    "id": "42",
                    "username": "user@example.com",
                    "group": "default",
                },
            }

        self.bridge.AUTH_FAILURE_RATE_LIMIT = 3
        self.bridge.request_json = flaky_login
        self.bridge.fetch_models = lambda _token: ["qwen3.7-plus"]
        body = {"username": "user@example.com", "password": "password-not-real"}

        self.assertEqual(self.bridge.handle_launcher_token(body)[0], 401)
        self.assertEqual(self.bridge.handle_launcher_token(body)[0], 401)
        self.assertEqual(self.bridge.handle_launcher_token(body)[0], 200)
        self.assertFalse(self.bridge.auth_failure_limited("user@example.com", "password"))

    def test_auth_attempt_budget_is_atomic_under_concurrency(self):
        self.bridge.AUTH_FAILURE_RATE_LIMIT = 3
        results = []
        lock = threading.Lock()

        def reserve():
            allowed = self.bridge.reserve_auth_attempt("user@example.com", "password")
            with lock:
                results.append(allowed)

        threads = [threading.Thread(target=reserve) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 20)
        self.assertEqual(sum(1 for allowed in results if allowed), 3)

    def test_claim_returns_key_once(self):
        self.bridge.handle_launcher_token = self.stub_launcher_token
        _, start_payload = self.bridge.handle_bind_start({"username": "user@example.com", "password": "pw"})
        ticket = start_payload["data"]["ticket"]

        status, payload = self.bridge.handle_bind_claim({"ticket": ticket})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["key"], "sk-test-secret-value")

        status, payload = self.bridge.handle_bind_claim({"ticket": ticket})
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

    def test_concurrent_claim_only_returns_key_once(self):
        self.bridge.handle_launcher_token = self.stub_launcher_token
        _, start_payload = self.bridge.handle_bind_start({"username": "user@example.com", "password": "pw"})
        ticket = start_payload["data"]["ticket"]
        results = []
        lock = threading.Lock()

        def claim():
            result = self.bridge.handle_bind_claim({"ticket": ticket})
            with lock:
                results.append(result)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successes = [payload for status, payload in results if status == 200 and payload.get("data", {}).get("key")]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(results), 8)

    def test_expired_ticket_is_rejected(self):
        ticket = self.bridge.create_bind_ticket(
            {"success": True, "data": {"key": "sk-expired", "account": "expired@example.com"}},
            ttl_sec=-1,
        )["ticket"]

        status, payload = self.bridge.handle_bind_claim({"ticket": ticket})

        self.assertEqual(status, 410)
        self.assertIn("expired", payload["error"])

    def test_email_code_login_returns_launcher_payload_without_exposing_code(self):
        sent = {}

        def capture_code(email, code):
            sent["email"] = email
            sent["code"] = code

        self.bridge._send_login_email_code = capture_code
        self.bridge.fetch_models = lambda _token: ["qwen3.7-plus", "agnes-2.0-flash"]

        status, payload = self.bridge.handle_email_code_send({"email": "user@example.com", "purpose": "login"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["email"], "user@example.com")
        self.assertNotIn(sent["code"], repr(payload))

        status, payload = self.bridge.handle_email_code_login({"email": "user@example.com", "code": sent["code"]})
        self.assertEqual(status, 200)
        data = payload["data"]
        self.assertEqual(data["account"], "user@example.com")
        self.assertEqual(data["api"]["baseUrl"], "https://api.heang.top/v1")
        self.assertEqual(data["models"], ["qwen3.7-plus", "agnes-2.0-flash"])

        status, payload = self.bridge.handle_email_code_login({"email": "user@example.com", "code": sent["code"]})
        self.assertEqual(status, 400)
        self.assertIn("重新发送", payload["error"])

    def test_email_code_register_returns_managed_session_in_one_request(self):
        upstream_paths = []

        def register_user(opener, path, *, method="GET", body=None, headers=None, timeout=20):
            upstream_paths.append(path)
            self.assertEqual(method, "POST")
            if path == "/api/user/register":
                connection = sqlite3.connect(self.bridge.DB_PATH)
                try:
                    connection.execute(
                        'insert into users(id, username, status, email, "group", deleted_at) values(99, ?, 1, ?, ?, null)',
                        (body["email"], body["email"], "standard"),
                    )
                    connection.commit()
                finally:
                    connection.close()
                return {"success": True, "message": "registered"}
            if path == "/api/user/login":
                processor = next(
                    handler
                    for handler in opener.handlers
                    if isinstance(handler, self.bridge.urllib.request.HTTPCookieProcessor)
                )
                processor.cookiejar.set_cookie(self.bridge.http.cookiejar.Cookie(
                    version=0,
                    name="session",
                    value="fake-register-session-not-real",
                    port=None,
                    port_specified=False,
                    domain="127.0.0.1",
                    domain_specified=False,
                    domain_initial_dot=False,
                    path="/",
                    path_specified=True,
                    secure=False,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                ))
                return {
                    "success": True,
                    "data": {"id": "99", "username": body["username"], "group": "standard"},
                }
            raise AssertionError(f"unexpected upstream path: {path}")

        self.bridge.request_json = register_user
        self.bridge.fetch_models = lambda _token: ["qwen3.7-plus", "agnes-2.0-flash"]

        status, payload = self.bridge.handle_email_code_register({
            "email": "new@example.com",
            "username": "new@example.com",
            "password": "secret123",
            "code": "246810",
            "verification_code": "246810",
        })

        self.assertEqual(status, 200)
        data = payload["data"]
        self.assertEqual(data["account"]["id"], "99")
        self.assertEqual(data["account"]["email"], "new@example.com")
        self.assertEqual(data["account"]["plan"], "standard")
        self.assertEqual(data["api"]["baseUrl"], "https://api.heang.top/v1")
        self.assertEqual(data["models"], ["qwen3.7-plus", "agnes-2.0-flash"])
        self.assertEqual(data["sessionCookie"], "session=fake-register-session-not-real")
        self.assertEqual(upstream_paths, ["/api/user/register", "/api/user/login"])


if __name__ == "__main__":
    unittest.main()
