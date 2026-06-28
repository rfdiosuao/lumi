from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.paths import AppPaths
from core.storage import read_json
from core.wire_config import WireService, build_wire_from_session


def session_snapshot() -> dict:
    return {
        "source": "newapi_account",
        "memberId": "newapi:test-user",
        "memberName": "test@example.invalid",
        "gatewayBaseUrl": "https://api.heang.top/v1",
        "gatewayImageBaseUrl": "https://api.heang.top/v1",
        "gatewayDefaultModel": "qwen3.7-plus",
        "gatewayImageModel": "gpt-image-1",
        "gatewayVideoDraftModel": "agnes-video-v1",
        "gatewayModels": ["qwen3.7-plus", "gpt-4o", "gpt-image-1", "agnes-video-v1"],
        "memberToken": "sk-test-token-not-real",
        "gatewayImageAccessToken": "sk-test-token-not-real",
        "phoneAgent": {
            "baseUrl": "https://api.heang.top/v1",
            "apiKey": "sk-test-token-not-real",
            "model": "agnes-2.0-flash",
        },
        "gateway": {
            "classifiedModels": {
                "text": ["qwen3.7-plus", "gpt-4o"],
                "image": ["gpt-image-1"],
                "video": ["agnes-video-v1"],
            },
        },
    }


class WireServiceTests(unittest.TestCase):
    def test_sync_from_session_persists_public_wire_without_exposing_raw_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            result = service.sync_from_session(session_snapshot())
            public_wire = result["wire"]

            self.assertTrue(public_wire["ok"])
            self.assertEqual(public_wire["managedBy"], "heang_account")
            self.assertEqual(public_wire["provider"], "heang")
            self.assertEqual(public_wire["models"]["text"], "qwen3.7-plus")
            self.assertEqual(public_wire["models"]["phone"], "agnes-2.0-flash")
            self.assertNotIn("apiKey", json.dumps(public_wire))
            self.assertIn("tokenMasked", public_wire)

            with open(paths.wire_current, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            if os.name == "nt":
                self.assertNotIn("sk-test-token-not-real", raw_text)

    def test_sync_from_session_writes_managed_runtime_configs_and_keeps_video_locked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            result = service.sync_from_session(session_snapshot())
            targets = {item["target"]: item["ok"] for item in result["syncResults"]}

            self.assertTrue(targets["openclaw"])
            self.assertTrue(targets["phone"])
            self.assertTrue(targets["desktop"])
            self.assertTrue(targets["image"])

            auth_profiles = read_json(paths.auth_profiles, {})
            provider = auth_profiles["models"]["providers"]["member_gateway"]
            self.assertEqual(provider["managedBy"], "heang_account")
            self.assertEqual(provider["apiKey"], "sk-test-token-not-real")

            phone_config = read_json(os.path.join(paths.launcher_dir, "phone-agent.json"), {})
            self.assertEqual(phone_config["llm"]["managedBy"], "heang_account")
            self.assertEqual(phone_config["llm"]["model"], "agnes-2.0-flash")

            desktop_config = read_json(os.path.join(paths.launcher_dir, "desktop-agent.json"), {})
            self.assertEqual(desktop_config["provider"]["managedBy"], "heang_account")
            self.assertEqual(desktop_config["provider"]["model"], "qwen3.7-plus")

            image_config = read_json(paths.image_config, {})
            self.assertEqual(image_config["managedBy"], "heang_account")
            self.assertEqual(image_config["model"], "gpt-image-1")

            self.assertFalse(os.path.exists(paths.video_config))
            self.assertFalse(os.path.exists(paths.videoapi_config))

    def test_verify_and_rollback_use_current_and_last_good_wire(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = WireService(AppPaths(temp_dir))
            before = session_snapshot()
            after = {**session_snapshot(), "gatewayDefaultModel": "gpt-4o"}

            service.sync_from_session(before)
            service.sync_from_session(after)

            verified = service.verify()
            self.assertTrue(verified["ok"])

            rolled_back = service.rollback()
            self.assertEqual(rolled_back["wire"]["models"]["text"], "qwen3.7-plus")

    def test_sync_target_errors_are_redacted_before_returning_to_account_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            service = WireService(AppPaths(temp_dir), append_log=logs.append)
            secret = "s" + "k-" + "demo-secret"

            def fail_sync(_wire):
                raise RuntimeError(f"apiKey={secret}")

            service._sync_image = fail_sync
            results = service.apply_wire(build_wire_from_session(session_snapshot()), targets=("image",))
            dumped = repr(results) + repr(logs)

            self.assertNotIn(secret, dumped)
            self.assertIn("apiKey=[redacted]", dumped)

    def test_sync_custom_provider_writes_runtime_configs_without_exposing_raw_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            secret = "s" + "k-test-token-not-real"

            result = service.sync_custom_provider(
                provider="OpenAI 兼容",
                base_url="https://third.example/v1",
                api_key=secret,
                text_model="gpt-4o",
                image_model="gpt-image-1",
                phone_model="gpt-4o-mini",
                video_model="sora-draft",
            )
            public_wire = result["wire"]

            self.assertTrue(public_wire["ok"])
            self.assertEqual(public_wire["managedBy"], "custom_provider")
            self.assertEqual(public_wire["provider"], "OpenAI 兼容")
            self.assertEqual(public_wire["models"]["text"], "gpt-4o")
            self.assertEqual(public_wire["models"]["phone"], "gpt-4o-mini")
            self.assertEqual(public_wire["models"]["video"], "sora-draft")
            self.assertNotIn(secret, repr(public_wire))
            self.assertNotIn("apiKey", repr(public_wire))

            with open(paths.wire_current, "r", encoding="utf-8") as handle:
                raw_text = handle.read()
            if os.name == "nt":
                self.assertNotIn(secret, raw_text)

            auth_profiles = read_json(paths.auth_profiles, {})
            provider = auth_profiles["models"]["providers"]["custom_provider"]
            self.assertEqual(auth_profiles["models"]["primary"], "custom_provider")
            self.assertEqual(provider["managedBy"], "custom_provider")
            self.assertEqual(provider["defaultModel"], "gpt-4o")
            self.assertEqual(provider["apiKey"], secret)

            phone_config = read_json(os.path.join(paths.launcher_dir, "phone-agent.json"), {})
            self.assertEqual(phone_config["llm"]["managedBy"], "custom_provider")
            self.assertEqual(phone_config["llm"]["model"], "gpt-4o-mini")

            desktop_config = read_json(os.path.join(paths.launcher_dir, "desktop-agent.json"), {})
            self.assertEqual(desktop_config["provider"]["managedBy"], "custom_provider")
            self.assertEqual(desktop_config["provider"]["model"], "gpt-4o")

            self.assertFalse(os.path.exists(paths.video_config))
            self.assertFalse(os.path.exists(paths.videoapi_config))


if __name__ == "__main__":
    unittest.main()
