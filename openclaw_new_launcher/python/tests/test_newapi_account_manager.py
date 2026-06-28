from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.newapi_account_manager import ACCOUNT_SOURCE, NewApiAccountManager
import core.newapi_account_manager as account_module
from core.license_manager import LicenseManager
from core.paths import AppPaths
from core.storage import read_json


class NewApiAccountManagerTests(unittest.TestCase):
    def test_email_code_send_uses_openclaw_auth_endpoint_without_returning_code_or_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            result = manager.send_email_code("user@example.invalid", base_url="https://api.heang.top")

            self.assertTrue(result["sent"])
            self.assertEqual(result["email"], "user@example.invalid")
            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/openclaw/auth/email-code/send")
            self.assertEqual(manager.requests[0]["body"]["email"], "user@example.invalid")
            self.assertNotIn("123456", repr(result))
            self.assertNotIn("sk-test-token-not-real", repr(result))

    def test_email_code_login_builds_protected_managed_session_and_syncs_wire(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            session = manager.login_with_email_code(
                "user@example.invalid",
                "654321",
                base_url="https://api.heang.top",
            )
            public_session = manager.public_session()

            self.assertEqual(session["memberName"], "user@example.invalid")
            self.assertEqual(session["memberToken"], "sk-test-token-not-real")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertEqual(session["gatewayImageModel"], "gpt-image-1")
            self.assertEqual(session["gatewayVideoDraftModel"], "agnes-video-v1")
            self.assertEqual(session["phoneAgent"]["model"], "agnes-2.0-flash")
            self.assertEqual(session["newApi"]["launcherToken"], "sess-test-launcher-not-real")
            self.assertEqual(public_session["account"], "user@example.invalid")
            self.assertNotIn("sk-test-token-not-real", repr(public_session))
            self.assertNotIn("sess-test-launcher-not-real", repr(public_session))
            self.assertEqual(manager.synced_targets, ("openclaw", "image", "desktop", "phone"))

            with open(manager.session_path, "r", encoding="utf-8") as file:
                raw_text = file.read()
            if os.name == "nt":
                self.assertNotIn("sk-test-token-not-real", raw_text)
                self.assertNotIn("sess-test-launcher-not-real", raw_text)

    def test_session_file_protects_secret_fields_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = NewApiAccountManager(AppPaths(temp_dir))
            session = {
                "source": ACCOUNT_SOURCE,
                "memberToken": "test-token-not-real",
                "gatewayImageAccessToken": "test-token-not-real",
                "gateway": {
                    "accessToken": "test-token-not-real",
                    "imageAccessToken": "test-token-not-real",
                },
                "newApi": {
                    "sessionCookie": "sid=secret-cookie",
                },
                "phoneAgent": {
                    "apiKey": "test-token-not-real",
                },
            }

            manager._write_session(session)
            with open(manager.session_path, "r", encoding="utf-8") as file:
                raw_text = file.read()
            loaded_raw = json.loads(raw_text)
            loaded_session = manager.current()

            if os.name == "nt":
                self.assertNotIn("test-token-not-real", raw_text)
                self.assertNotIn("sid=secret-cookie", raw_text)
                self.assertEqual(loaded_raw["memberToken"]["__loomSecret"], "dpapi")
            self.assertEqual(loaded_session["memberToken"], "test-token-not-real")
            self.assertEqual(loaded_session["newApi"]["sessionCookie"], "sid=secret-cookie")

    def test_default_sync_does_not_write_video_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = NewApiAccountManager(AppPaths(temp_dir))
            session = {
                "source": ACCOUNT_SOURCE,
                "gatewayBaseUrl": "https://api.heang.top/v1",
                "gatewayImageBaseUrl": "https://api.heang.top/v1",
                "gatewayDefaultModel": "qwen3.7-plus",
                "gatewayImageModel": "gpt-image-1",
                "gatewayVideoModel": "agnes-video-v1",
                "memberToken": "test-token-not-real",
                "gatewayImageAccessToken": "test-token-not-real",
                "phoneAgent": {
                    "baseUrl": "https://api.heang.top/v1",
                    "apiKey": "test-token-not-real",
                    "model": "agnes-2.0-flash",
                },
            }

            results = manager.sync_targets(session)

            self.assertIn("openclaw", [item["target"] for item in results])
            self.assertTrue(os.path.exists(AppPaths(temp_dir).wire_current))
            self.assertNotIn("video", [item["target"] for item in results])
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "video_config.json")))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "videoapi_config.json")))

    def test_select_models_writes_text_and_image_but_not_video_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = NewApiAccountManager(AppPaths(temp_dir))
            session = {
                "source": ACCOUNT_SOURCE,
                "gatewayBaseUrl": "https://api.heang.top/v1",
                "gatewayImageBaseUrl": "https://api.heang.top/v1",
                "gatewayDefaultModel": "qwen3.7-plus",
                "gatewayImageModel": "gpt-image-1",
                "gatewayVideoModel": "agnes-video-v1",
                "gatewayModels": ["qwen3.7-plus", "gpt-4o", "gpt-image-1", "seedream-image-v1", "agnes-video-v1"],
                "memberToken": "test-token-not-real",
                "gatewayImageAccessToken": "test-token-not-real",
                "gateway": {
                    "classifiedModels": {
                        "text": ["qwen3.7-plus", "gpt-4o"],
                        "image": ["gpt-image-1", "seedream-image-v1"],
                        "video": ["agnes-video-v1"],
                    }
                },
                "newApi": {
                    "modelClasses": {
                        "text": ["qwen3.7-plus", "gpt-4o"],
                        "image": ["gpt-image-1", "seedream-image-v1"],
                        "video": ["agnes-video-v1"],
                    }
                },
                "phoneAgent": {
                    "baseUrl": "https://api.heang.top/v1",
                    "apiKey": "test-token-not-real",
                    "model": "agnes-2.0-flash",
                },
            }
            manager._write_session(session)

            next_public = manager.select_models(
                text_model="gpt-4o",
                image_model="seedream-image-v1",
                video_model="agnes-video-v1",
            )

            self.assertEqual(next_public["selectedModels"]["text"], "gpt-4o")
            self.assertEqual(next_public["selectedModels"]["image"], "seedream-image-v1")
            self.assertEqual(next_public["selectedModels"]["videoDraft"], "agnes-video-v1")
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "video_config.json")))
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "videoapi_config.json")))

            auth_profiles = read_json(AppPaths(temp_dir).auth_profiles, {})
            provider = auth_profiles["models"]["providers"]["member_gateway"]
            self.assertEqual(provider["apiKey"], "test-token-not-real")
            self.assertEqual(provider["managedBy"], "heang_account")
            self.assertNotIn("gatewayVideoModel", provider)
            self.assertNotIn("videoModel", provider)
            self.assertTrue(os.path.exists(AppPaths(temp_dir).wire_current))

            models_json = read_json(os.path.join(temp_dir, "data", ".openclaw", "agents", "main", "agent", "models.json"), {})
            model_providers = models_json["providers"]
            self.assertEqual(len(model_providers), 1)
            model_provider = next(iter(model_providers.values()))
            self.assertEqual(model_provider["apiKey"], "test-token-not-real")
            self.assertNotIn("gatewayVideoModel", model_provider)
            self.assertNotIn("videoModel", model_provider)

            openclaw_config = read_json(AppPaths(temp_dir).openclaw_config, {})
            openclaw_providers = openclaw_config["models"]["providers"]
            self.assertEqual(len(openclaw_providers), 1)
            openclaw_provider = next(iter(openclaw_providers.values()))
            self.assertEqual(openclaw_provider["apiKey"], "test-token-not-real")
            self.assertNotIn("gatewayVideoModel", openclaw_provider)
            self.assertNotIn("videoModel", openclaw_provider)

    def test_license_manager_reads_protected_member_session_for_gateway_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            manager = NewApiAccountManager(paths)
            session = {
                "source": ACCOUNT_SOURCE,
                "memberId": "newapi:test-user",
                "memberName": "test@example.invalid",
                "gatewayBaseUrl": "https://api.heang.top/v1",
                "gatewayImageBaseUrl": "https://api.heang.top/v1",
                "gatewayDefaultModel": "qwen3.7-plus",
                "gatewayImageModel": "gpt-image-1",
                "gatewayVideoDraftModel": "agnes-video-v1",
                "gatewayModels": ["qwen3.7-plus", "gpt-image-1", "agnes-video-v1"],
                "memberToken": "test-token-not-real",
                "gatewayImageAccessToken": "test-token-not-real",
                "gateway": {
                    "accessToken": "test-token-not-real",
                    "imageAccessToken": "test-token-not-real",
                    "defaultModel": "qwen3.7-plus",
                    "imageModel": "gpt-image-1",
                    "videoDraftModel": "agnes-video-v1",
                    "models": ["qwen3.7-plus", "gpt-image-1", "agnes-video-v1"],
                },
            }

            manager._write_session(session)
            profile = LicenseManager(paths).current_gateway_profile()

            self.assertIsNotNone(profile)
            self.assertEqual(profile["apiKey"], "test-token-not-real")
            self.assertEqual(profile["imageApiKey"], "test-token-not-real")
            self.assertEqual(profile["defaultModel"], "qwen3.7-plus")
            self.assertEqual(profile["imageModel"], "gpt-image-1")
            self.assertEqual(profile["videoDraftModel"], "agnes-video-v1")
            self.assertNotIn("videoModel", profile)

    def test_sync_target_errors_are_redacted_before_storage_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs: list[str] = []
            manager = NewApiAccountManager(AppPaths(temp_dir), append_log=logs.append)
            secret = "s" + "k-" + "demo-secret"

            original_wire_service = account_module.WireService

            class FakeWireService:
                def __init__(self, *_args, **_kwargs):
                    pass

                def sync_from_session(self, _session, *, targets):
                    return {"syncResults": [{"target": targets[0], "ok": False, "error": "apiKey=[redacted]"}]}

            try:
                account_module.WireService = FakeWireService
                results = manager.sync_targets({"source": ACCOUNT_SOURCE}, targets=("image",))
            finally:
                account_module.WireService = original_wire_service
            dumped = repr(results) + repr(logs)

            self.assertNotIn(secret, dumped)
            self.assertIn("apiKey=[redacted]", dumped)


class EmailCodeFakeManager(NewApiAccountManager):
    def __init__(self, paths: AppPaths):
        super().__init__(paths)
        self.requests: list[dict] = []
        self.synced_targets: tuple[str, ...] | None = None

    def _request_json(self, opener, url, *, method="GET", body=None, headers=None, timeout=20):
        self.requests.append({
            "url": url,
            "method": method,
            "body": body or {},
            "headers": headers or {},
            "timeout": timeout,
        })
        if url.endswith("/api/openclaw/auth/email-code/send"):
            return {
                "success": True,
                "data": {
                    "sent": True,
                    "email": body.get("email"),
                    "retryAfter": 60,
                    "code": "123456",
                    "token": "sk-test-token-not-real",
                },
            }
        if url.endswith("/api/openclaw/auth/email-code/login"):
            return {
                "success": True,
                "data": {
                    "launcherToken": "sess-test-launcher-not-real",
                    "account": {
                        "id": "u_123",
                        "email": body.get("email"),
                        "name": "LOOM Tester",
                        "plan": "standard",
                    },
                    "quota": {
                        "remaining": 1000000,
                        "unit": "tokens",
                    },
                    "api": {
                        "baseUrl": "https://api.heang.top/v1",
                        "token": "sk-test-token-not-real",
                        "tokenMasked": "sk-****real",
                    },
                    "models": {
                        "text": ["qwen3.7-plus", "gpt-4o"],
                        "phone": ["agnes-2.0-flash"],
                        "image": ["gpt-image-1"],
                        "video": ["agnes-video-v1"],
                    },
                    "defaults": {
                        "textModel": "qwen3.7-plus",
                        "phoneModel": "agnes-2.0-flash",
                    },
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    def sync_targets(self, session, *, targets=("openclaw", "image", "desktop", "phone")):
        self.synced_targets = targets
        session["lastSyncResults"] = [{"target": "openclaw", "ok": True}]
        return session["lastSyncResults"]


if __name__ == "__main__":
    unittest.main()
