from __future__ import annotations

import importlib.util
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
        self.original_launcher_token = self.bridge.handle_launcher_token

    def tearDown(self) -> None:
        self.bridge.handle_launcher_token = self.original_launcher_token
        self.tmp.cleanup()

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


if __name__ == "__main__":
    unittest.main()
