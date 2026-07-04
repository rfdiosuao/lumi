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
        self._init_newapi_db()

    def tearDown(self) -> None:
        self.bridge.handle_launcher_token = self.original_launcher_token
        self.bridge._send_login_email_code = self.original_send_code
        self.bridge.fetch_models = self.original_fetch_models
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


if __name__ == "__main__":
    unittest.main()
