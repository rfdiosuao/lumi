from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.newapi_account_manager import (
    ACCOUNT_SOURCE,
    NewApiAccountError,
    NewApiAccountManager,
    _classified_models_from_catalog,
    _choose_model,
    _extract_models,
    _flatten_model_catalog,
)
import core.newapi_account_manager as account_module
from core.license_manager import LicenseManager
from core.paths import AppPaths
from core.storage import read_json


class NewApiAccountManagerTests(unittest.TestCase):
    def test_nested_model_catalog_maps_are_flattened_and_classified(self) -> None:
        catalog = {
            "data": {
                "models": {
                    "qwen3.7-plus": {"owned_by": "heang"},
                    "gpt-4o": {"owned_by": "heang"},
                    "agnes-image-2.1-flash": {"type": "image"},
                    "agnes-video-v2.0": {"type": "video"},
                },
                "phone": {
                    "agnes-2.0-flash": {"type": "phone"},
                },
            }
        }

        models = _extract_models(catalog)
        classes = _classified_models_from_catalog(catalog)
        flat = _flatten_model_catalog(catalog)

        self.assertIn("qwen3.7-plus", models)
        self.assertIn("gpt-4o", models)
        self.assertIn("agnes-image-2.1-flash", classes["image"])
        self.assertIn("agnes-video-v2.0", classes["video"])
        self.assertIn("agnes-2.0-flash", flat)

    def test_newapi_user_models_map_response_keeps_multiple_text_models_without_phone_default(self) -> None:
        payload = {
            "success": True,
            "data": {
                "models": {
                    "qwen3.7-plus": {},
                    "qwen3.6-plus": {},
                    "deepseek-v3.2": {},
                    "agnes-2.0-flash": {},
                }
            },
        }

        classes = _classified_models_from_catalog(payload)

        self.assertEqual(
            classes["text"],
            ["qwen3.7-plus", "qwen3.6-plus", "deepseek-v3.2"],
        )
        self.assertNotIn("agnes-2.0-flash", classes["text"])

    def test_text_model_choice_never_uses_image_video_or_phone_fallback(self) -> None:
        chosen = _choose_model(
            [],
            "qwen3.7-plus",
            ["agnes-video-v2.0", "agnes-image-2.1-flash", "agnes-2.0-flash"],
        )

        self.assertEqual(chosen, "")

    def test_public_session_and_select_models_do_not_invent_qwen_when_catalog_has_no_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            manager = NewApiAccountManager(paths)
            manager._write_session({
                "source": ACCOUNT_SOURCE,
                "memberId": "newapi:test-user",
                "memberName": "user@example.invalid",
                "memberToken": "sk-test-token-not-real",
                "gatewayBaseUrl": "https://api.heang.top/v1",
                "gatewayImageBaseUrl": "https://api.heang.top/v1",
                "gatewayDefaultModel": "",
                "gatewayImageModel": "agnes-image-2.1-flash",
                "gatewayVideoDraftModel": "agnes-video-v2.0",
                "gatewayModels": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
                "gateway": {
                    "classifiedModels": {
                        "text": [],
                        "image": ["agnes-image-2.1-flash"],
                        "video": ["agnes-video-v2.0"],
                    },
                },
                "newApi": {
                    "baseUrl": "https://api.heang.top",
                    "account": "user@example.invalid",
                },
                "phoneAgent": {
                    "baseUrl": "https://api.heang.top/v1",
                    "apiKey": "sk-test-token-not-real",
                    "model": "agnes-2.0-flash",
                },
            })

            public_session = manager.public_session()
            self.assertEqual(public_session["models"]["text"], [])
            self.assertEqual(public_session["selectedModels"]["text"], "")

            with self.assertRaisesRegex(NewApiAccountError, "文本模型不在当前账号可用列表中"):
                manager.select_models(text_model="qwen3.7-plus")

    def test_login_creates_launcher_token_before_using_generic_agnes_only_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[
                    {
                        "name": "Default",
                        "key": "fake-generic-token-not-real",
                        "status": 1,
                        "remain_quota": 1000,
                    }
                ],
                create_token="fake-loom-token-not-real",
                model_by_token={
                    "fake-generic-token-not-real": ["agnes-2.0-flash"],
                    "fake-loom-token-not-real": ["qwen3.7-plus", "gpt-4o", "agnes-2.0-flash"],
                },
            )

            session = manager.login("user@example.invalid", "password-not-real", base_url="https://api.heang.top")

            self.assertEqual(session["memberToken"], "fake-loom-token-not-real")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertIn("gpt-4o", session["gateway"]["classifiedModels"]["text"])
            self.assertEqual(session["lease"]["tokenSource"], "created_launcher")

    def test_login_regenerates_launcher_token_when_existing_launcher_key_has_only_phone_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[
                    {
                        "name": "LOOM Launcher 1700000000",
                        "key": "fake-loom-old-token-not-real",
                        "status": 1,
                        "remain_quota": 1000,
                    }
                ],
                create_token="fake-loom-new-token-not-real",
                model_by_token={
                    "fake-loom-old-token-not-real": ["agnes-2.0-flash"],
                    "fake-loom-new-token-not-real": ["qwen3.7-plus", "MiniMax-M2.5", "agnes-2.0-flash"],
                },
            )

            session = manager.login("user@example.invalid", "password-not-real", base_url="https://api.heang.top")

            self.assertEqual(session["memberToken"], "fake-loom-new-token-not-real")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertIn("MiniMax-M2.5", session["gateway"]["classifiedModels"]["text"])
            self.assertEqual(session["lease"]["tokenSource"], "created_launcher_after_model_check")

    def test_login_skips_disabled_launcher_token_and_creates_fresh_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[
                    {
                        "name": "LOOM Launcher disabled",
                        "key": "fake-disabled-token-not-real",
                        "status": 2,
                        "remain_quota": 0,
                    }
                ],
                create_token="fake-loom-fresh-token-not-real",
                model_by_token={
                    "fake-disabled-token-not-real": ["agnes-2.0-flash"],
                    "fake-loom-fresh-token-not-real": ["qwen3.7-plus", "gpt-4o"],
                },
            )

            session = manager.login("user@example.invalid", "password-not-real", base_url="https://api.heang.top")

            self.assertEqual(session["memberToken"], "fake-loom-fresh-token-not-real")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertEqual(session["lease"]["tokenSource"], "created_launcher")

    def test_login_replaces_bridge_token_when_bridge_key_has_only_phone_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[],
                bridge_token="fake-bridge-token-not-real",
                bridge_models=["agnes-2.0-flash"],
                create_token="fake-loom-fresh-token-not-real",
                model_by_token={
                    "fake-bridge-token-not-real": ["agnes-2.0-flash"],
                    "fake-loom-fresh-token-not-real": ["qwen3.7-plus", "gpt-4o"],
                },
            )

            session = manager.login("user@example.invalid", "password-not-real", base_url="https://api.heang.top")

            self.assertEqual(session["memberToken"], "fake-loom-fresh-token-not-real")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertEqual(session["lease"]["tokenSource"], "created_launcher_after_model_check")

    def test_login_falls_back_to_generic_token_when_launcher_token_creation_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[
                    {
                        "name": "Default",
                        "key": "fake-generic-token-not-real",
                        "status": 1,
                        "remain_quota": 1000,
                    }
                ],
                create_fails=True,
                model_by_token={"fake-generic-token-not-real": ["agnes-2.0-flash"]},
            )

            session = manager.login("user@example.invalid", "password-not-real", base_url="https://api.heang.top")

            self.assertEqual(session["memberToken"], "fake-generic-token-not-real")
            self.assertEqual(session["lease"]["tokenSource"], "existing_fallback")
            self.assertEqual(session["phoneAgent"]["model"], "agnes-2.0-flash")

    def test_email_code_send_uses_newapi_verification_endpoint_without_returning_code_or_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            result = manager.send_email_code("user@example.invalid", base_url="https://api.heang.top")

            self.assertTrue(result["sent"])
            self.assertEqual(result["email"], "user@example.invalid")
            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/verification?email=user%40example.invalid")
            self.assertNotIn("123456", repr(result))
            self.assertNotIn("sk-test-token-not-real", repr(result))

    def test_email_code_login_send_uses_login_endpoint_not_register_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            result = manager.send_email_code(
                "user@example.invalid",
                base_url="https://api.heang.top",
                purpose="login",
            )

            self.assertTrue(result["sent"])
            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/openclaw/auth/email-code/send")
            self.assertEqual(manager.requests[0]["body"]["purpose"], "login")
            self.assertEqual(manager.requests[0]["body"]["scene"], "login")
            self.assertEqual(manager.requests[0]["body"]["type"], "login")
            self.assertEqual(manager.requests[0]["body"]["mode"], "login")
            self.assertEqual(manager.requests[0]["body"]["action"], "login")
            self.assertEqual(manager.requests[0]["body"]["authType"], "email_code_login")
            self.assertNotIn("/api/verification", manager.requests[0]["url"])

    def test_email_code_register_fallback_uses_register_scene_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            original_request_json = manager._request_json

            def request_json(opener, url, **kwargs):
                if "/api/verification?" in url:
                    raise NewApiAccountError("http_404")
                return original_request_json(opener, url, **kwargs)

            manager._request_json = request_json  # type: ignore[method-assign]
            result = manager.send_email_code(
                "user@example.invalid",
                base_url="https://api.heang.top",
                purpose="register",
            )

            self.assertTrue(result["sent"])
            body = manager.requests[-1]["body"]
            self.assertEqual(body["purpose"], "register")
            self.assertEqual(body["scene"], "register")
            self.assertEqual(body["type"], "register")
            self.assertEqual(body["mode"], "register")
            self.assertEqual(body["action"], "register")

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
            self.assertEqual(manager.synced_targets, ("openclaw", "opencode", "codex", "claude", "image", "desktop", "phone"))

            with open(manager.session_path, "r", encoding="utf-8") as file:
                raw_text = file.read()
            if os.name == "nt":
                self.assertNotIn("sk-test-token-not-real", raw_text)
                self.assertNotIn("sess-test-launcher-not-real", raw_text)

    def test_email_code_send_does_not_hide_newapi_business_errors_behind_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeBusinessErrorManager(AppPaths(temp_dir))

            with self.assertRaisesRegex(NewApiAccountError, "email domain"):
                manager.send_email_code("user@example.invalid", base_url="https://api.heang.top")

            self.assertEqual(len(manager.requests), 1)
            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/verification?email=user%40example.invalid")

    def test_refresh_regenerates_launcher_token_when_current_token_has_no_text_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LauncherTokenFakeManager(
                AppPaths(temp_dir),
                tokens=[],
                create_token="fake-loom-refresh-token-not-real",
                model_by_token={
                    "fake-old-token-not-real": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
                    "fake-loom-refresh-token-not-real": ["qwen3.7-plus", "gpt-4o", "gpt-image-1", "agnes-2.0-flash"],
                },
            )
            manager._write_session({
                "source": ACCOUNT_SOURCE,
                "memberToken": "fake-old-token-not-real",
                "gatewayImageAccessToken": "fake-old-token-not-real",
                "gatewayDefaultModel": "agnes-video-v2.0",
                "gatewayModels": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
                "gateway": {
                    "accessToken": "fake-old-token-not-real",
                    "imageAccessToken": "fake-old-token-not-real",
                    "defaultModel": "agnes-video-v2.0",
                    "models": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
                },
                "newApi": {
                    "baseUrl": "https://api.heang.top",
                    "userId": "u_123",
                    "account": "user@example.invalid",
                },
                "lease": {"tokenSource": "existing_launcher"},
                "phoneAgent": {
                    "apiKey": "fake-old-token-not-real",
                    "model": "agnes-2.0-flash",
                },
            })

            refreshed = manager.refresh_current()
            public_session = manager.public_session()

            self.assertEqual(refreshed["memberToken"], "fake-loom-refresh-token-not-real")
            self.assertEqual(refreshed["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertIn("gpt-4o", public_session["models"]["text"])
            self.assertNotIn("agnes-video-v2.0", public_session["models"]["text"])
            self.assertEqual(refreshed["lease"]["tokenSource"], "created_launcher_after_refresh_model_check")

    def test_register_with_email_code_builds_session_without_persisting_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))

            session = manager.register_with_email_code(
                "new@example.invalid",
                "secret123",
                "246810",
                base_url="https://api.heang.top",
            )
            public_session = manager.public_session()

            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/user/register")
            self.assertEqual(manager.requests[0]["body"]["password"], "secret123")
            self.assertEqual(manager.requests[0]["body"]["verification_code"], "246810")
            self.assertEqual(session["memberName"], "new@example.invalid")
            self.assertEqual(session["gatewayDefaultModel"], "qwen3.7-plus")
            self.assertNotIn("secret123", repr(session))
            self.assertNotIn("secret123", repr(public_session))

    def test_subscription_snapshot_reads_native_account_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = EmailCodeFakeManager(AppPaths(temp_dir))
            manager.login_with_email_code(
                "user@example.invalid",
                "654321",
                base_url="https://api.heang.top",
            )
            manager.requests.clear()

            snapshot = manager.subscription_snapshot()

            self.assertEqual(manager.requests[0]["url"], "https://api.heang.top/api/user/subscription")
            self.assertEqual(snapshot["mode"], "native")
            self.assertEqual(snapshot["plan"], "pro")
            self.assertEqual(snapshot["balance"], "1200")
            self.assertEqual(snapshot["usage"]["usedQuota"], "12")
            self.assertEqual(snapshot["purchaseUrl"], "https://api.heang.top/wallet")

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

    def test_logout_clears_managed_launcher_tokens(self) -> None:
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
                "gatewayModels": ["qwen3.7-plus", "gpt-image-1", "agnes-2.0-flash"],
                "memberToken": "test-token-not-real",
                "gatewayImageAccessToken": "test-token-not-real",
                "phoneAgent": {
                    "baseUrl": "https://api.heang.top/v1",
                    "apiKey": "test-token-not-real",
                    "model": "agnes-2.0-flash",
                },
            }
            manager._write_session(session)
            manager.sync_targets(session)

            self.assertTrue(manager.logout())

            self.assertFalse(os.path.exists(manager.session_path))
            self.assertEqual(read_json(paths.wire_current, {}), {})
            self.assertEqual(read_json(os.path.join(paths.launcher_dir, "phone-agent.json"), {}), {"llm": {}})
            desktop_config = read_json(os.path.join(paths.launcher_dir, "desktop-agent.json"), {})
            self.assertEqual(desktop_config.get("provider"), {})
            self.assertEqual(desktop_config.get("llm"), {})
            self.assertEqual(desktop_config.get("chatProvider", {}).get("config"), {})
            dumped = repr(read_json(paths.wire_current, {}))
            dumped += repr(read_json(os.path.join(paths.launcher_dir, "phone-agent.json"), {}))
            dumped += repr(desktop_config)
            self.assertNotIn("test-token-not-real", dumped)

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


class LauncherTokenFakeManager(NewApiAccountManager):
    def __init__(
        self,
        paths: AppPaths,
        *,
        tokens: list[dict],
        create_token: str = "sk-created-token-not-real",
        create_fails: bool = False,
        bridge_token: str = "",
        bridge_models: list[str] | None = None,
        model_by_token: dict[str, list[str]] | None = None,
    ):
        super().__init__(paths)
        self.tokens = list(tokens)
        self.create_token = create_token
        self.create_fails = create_fails
        self.bridge_token = bridge_token
        self.bridge_models = bridge_models or []
        self.model_by_token = model_by_token or {}
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
        if url.endswith("/api/user/login"):
            return {
                "success": True,
                "data": {
                    "id": "u_123",
                    "username": (body or {}).get("username") or "user@example.invalid",
                    "email": "user@example.invalid",
                    "group": "standard",
                    "token": "user-session-token-not-real",
                },
            }
        if url.endswith("/api/openclaw/launcher-token"):
            if self.bridge_token:
                return {
                    "success": True,
                    "data": {
                        "source": "bridge",
                        "apiKey": self.bridge_token,
                        "models": self.bridge_models,
                    },
                }
            raise NewApiAccountError("http_404")
        if url.endswith("/api/user/self"):
            return {
                "success": True,
                "data": {
                    "id": "u_123",
                    "username": "user@example.invalid",
                    "email": "user@example.invalid",
                    "group": "standard",
                    "quota": 1000000,
                    "used_quota": 12,
                    "request_count": 34,
                },
            }
        if url.endswith("/api/token/?p=0&page_size=100"):
            return {"success": True, "data": self.tokens}
        if url.endswith("/api/token/") and method == "POST":
            if self.create_fails:
                raise NewApiAccountError("token_create_unavailable")
            token_name = (body or {}).get("name") or "LOOM Launcher test"
            created = {
                "name": token_name,
                "key": self.create_token,
                "status": 1,
                "unlimited_quota": True,
            }
            self.tokens.append(created)
            return {"success": True, "data": created}
        if url.endswith("/api/user/models"):
            return {"success": True, "data": {"models": {"agnes-2.0-flash": {}}}}
        if url.endswith("/v1/models"):
            auth = (headers or {}).get("Authorization", "")
            token = auth.replace("Bearer", "", 1).strip()
            models = self.model_by_token.get(token, ["agnes-2.0-flash"])
            return {"object": "list", "data": [{"id": model} for model in models]}
        raise AssertionError(f"unexpected request: {url}")

    def sync_targets(self, session, *, targets=("openclaw", "image", "desktop", "phone")):
        self.synced_targets = targets
        session["lastSyncResults"] = [{"target": "openclaw", "ok": True}]
        return session["lastSyncResults"]


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
        if "/api/verification?" in url:
            return {
                "success": True,
                "data": {
                    "sent": True,
                    "email": "user@example.invalid",
                    "retryAfter": 60,
                    "code": "123456",
                    "token": "sk-test-token-not-real",
                },
            }
        if url.endswith("/api/user/register"):
            return {
                "success": True,
                "message": "registered",
            }
        if url.endswith("/api/user/login"):
            username = (body or {}).get("username") or (body or {}).get("email") or "user@example.invalid"
            return {
                "success": True,
                "data": {
                    "id": "u_123",
                    "username": username,
                    "email": username,
                    "group": "standard",
                    "token": "user-session-token-not-real",
                },
            }
        if url.endswith("/api/user/self"):
            return {
                "success": True,
                "data": {
                    "id": "u_123",
                    "username": "new@example.invalid",
                    "email": "new@example.invalid",
                    "group": "standard",
                    "quota": 1000000,
                    "used_quota": 12,
                    "request_count": 34,
                },
            }
        if url.endswith("/api/openclaw/launcher-token"):
            return {
                "success": True,
                "data": {
                    "source": "bridge",
                    "apiKey": "sk-test-token-not-real",
                    "models": ["qwen3.7-plus", "gpt-4o", "gpt-image-1", "agnes-video-v1"],
                },
            }
        if url.endswith("/api/openclaw/auth/email-code/send"):
            return {
                "success": True,
                "data": {
                    "sent": True,
                    "email": body.get("email"),
                    "retryAfter": 60,
                },
            }
        if url.endswith("/api/openclaw/auth/email-code/login") or url.endswith("/api/openclaw/auth/email-code/register"):
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
        if url.endswith("/api/user/subscription"):
            return {
                "success": True,
                "data": {
                    "subscription": {
                        "plan": "pro",
                        "balance": 1200,
                        "expiresAt": "2026-12-31T00:00:00Z",
                        "purchaseUrl": "https://api.heang.top/wallet",
                    },
                    "usage": {
                        "usedQuota": 12,
                        "requestCount": 34,
                    },
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    def sync_targets(self, session, *, targets=("openclaw", "image", "desktop", "phone")):
        self.synced_targets = targets
        session["lastSyncResults"] = [{"target": "openclaw", "ok": True}]
        return session["lastSyncResults"]


class EmailCodeBusinessErrorManager(NewApiAccountManager):
    def __init__(self, paths: AppPaths):
        super().__init__(paths)
        self.requests: list[dict] = []

    def _request_json(self, opener, url, *, method="GET", body=None, headers=None, timeout=20):
        self.requests.append({
            "url": url,
            "method": method,
            "body": body or {},
            "headers": headers or {},
            "timeout": timeout,
        })
        if "/api/verification?" in url:
            raise NewApiAccountError("The administrator has enabled the email domain name whitelist")
        if "/api/openclaw/" in url:
            raise AssertionError("business errors from /api/verification must not fall back")
        raise AssertionError(f"unexpected request: {url}")


if __name__ == "__main__":
    unittest.main()
