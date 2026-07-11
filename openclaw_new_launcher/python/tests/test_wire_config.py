from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.paths import AppPaths
from core.storage import read_json
from core.wire_config import WireConfigError, WireService, build_wire_from_session
from core.openclaw_model_sync import _text_model_ids, sync_openclaw_models_from_gateway_profile


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
    def test_default_text_model_prefers_glm52_coding_for_managed_accounts(self) -> None:
        session = {
            **session_snapshot(),
            "gatewayDefaultModel": "",
            "gateway": {
                "classifiedModels": {
                    "text": ["agnes-2.0-flash", "qwen3.7-plus", "glm-5.2-coding"],
                    "image": [],
                    "video": [],
                },
            },
        }

        wire = build_wire_from_session(session)

        self.assertEqual(wire["models"]["text"], "glm-5.2-coding")

    def test_openclaw_model_order_prefers_glm52_coding_when_no_explicit_default(self) -> None:
        models = _text_model_ids(["qwen3.7-plus", "glm-5.2-coding", "gpt-4o"])

        self.assertEqual(models[0], "glm-5.2-coding")

    def test_default_text_model_is_empty_when_managed_catalog_has_no_text_models(self) -> None:
        session = {
            **session_snapshot(),
            "gatewayDefaultModel": "",
            "gatewayModels": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
            "gateway": {
                "classifiedModels": {
                    "text": [],
                    "image": ["agnes-image-2.1-flash"],
                    "video": ["agnes-video-v2.0"],
                },
            },
        }

        wire = build_wire_from_session(session)

        self.assertEqual(wire["models"]["text"], "")
        self.assertEqual(wire["modelLists"]["text"], [])

    def test_agent_sync_reports_clear_error_when_managed_catalog_has_no_text_models(self) -> None:
        session = {
            **session_snapshot(),
            "gatewayDefaultModel": "",
            "gatewayModels": ["agnes-image-2.1-flash", "agnes-video-v2.0", "agnes-2.0-flash"],
            "gateway": {
                "classifiedModels": {
                    "text": [],
                    "image": ["agnes-image-2.1-flash"],
                    "video": ["agnes-video-v2.0"],
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            result = service.sync_from_session(session, targets=("openclaw", "opencode", "codex", "claude"))
            errors = {item["target"]: item.get("error", "") for item in result["syncResults"]}

            self.assertEqual(result["wire"]["models"]["text"], "")
            self.assertIn("没有可用文本模型", errors["openclaw"])
            self.assertIn("没有可用文本模型", errors["opencode"])
            self.assertIn("没有可用文本模型", errors["codex"])
            self.assertIn("没有可用文本模型", errors["claude"])
            self.assertFalse(os.path.exists(os.path.join(paths.data_dir, ".codex", "config.toml")))
            self.assertFalse(os.path.exists(os.path.join(paths.data_dir, ".opencode", "opencode.json")))

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
            self.assertTrue(targets["opencode"])
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

            opencode_config = read_json(os.path.join(paths.data_dir, ".opencode", "opencode.json"), {})
            self.assertEqual(opencode_config["model"], "loom/qwen3.7-plus")
            opencode_provider = opencode_config["provider"]["loom"]
            self.assertEqual(opencode_provider["options"]["apiKey"], "{env:LOOM_OPENCODE_API_KEY}")
            self.assertNotIn("sk-test-token-not-real", json.dumps(opencode_config))

            self.assertFalse(os.path.exists(paths.video_config))
            self.assertFalse(os.path.exists(paths.videoapi_config))

    def test_sync_from_session_writes_codex_and_claude_launcher_configs_without_exposing_raw_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            secret = session_snapshot()["memberToken"]

            result = service.sync_from_session(session_snapshot())
            targets = {item["target"]: item["ok"] for item in result["syncResults"]}

            self.assertTrue(targets["codex"])
            self.assertTrue(targets["claude"])

            codex_config = os.path.join(paths.data_dir, ".codex", "config.toml")
            claude_settings = os.path.join(paths.data_dir, ".claude", "settings.json")
            self.assertTrue(os.path.isfile(codex_config))
            self.assertTrue(os.path.isfile(claude_settings))

            with open(codex_config, "r", encoding="utf-8") as handle:
                codex_text = handle.read()
            with open(claude_settings, "r", encoding="utf-8") as handle:
                claude_text = handle.read()

            self.assertIn('model = "qwen3.7-plus"', codex_text)
            self.assertIn('model_provider = "heang"', codex_text)
            self.assertIn("[model_providers.heang]", codex_text)
            self.assertIn('env_key = "LOOM_CODEX_API_KEY"', codex_text)
            self.assertIn('wire_api = "responses"', codex_text)
            self.assertNotIn('wire_api = "chat"', codex_text)
            self.assertNotIn(secret, codex_text)

            user_codex_config = os.path.join(paths.data_dir, ".codex-user", "config.toml")
            self.assertTrue(os.path.isfile(user_codex_config))
            with open(user_codex_config, "r", encoding="utf-8") as handle:
                user_codex_text = handle.read()
            self.assertEqual(user_codex_text, codex_text)

            claude_config = json.loads(claude_text)
            self.assertEqual(claude_config["env"]["ANTHROPIC_MODEL"], "qwen3.7-plus")
            self.assertEqual(claude_config["env"]["ANTHROPIC_BASE_URL"], "https://api.heang.top")
            self.assertEqual(claude_config["env"]["ANTHROPIC_AUTH_TOKEN"], "{env:LOOM_CLAUDE_API_KEY}")
            self.assertEqual(claude_config["env"]["ANTHROPIC_API_KEY"], "{env:LOOM_CLAUDE_API_KEY}")
            self.assertNotIn(secret, claude_text)

    def test_codex_user_config_merge_preserves_existing_desktop_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            user_codex_config = os.path.join(paths.data_dir, ".codex-user", "config.toml")
            os.makedirs(os.path.dirname(user_codex_config), exist_ok=True)
            with open(user_codex_config, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "\n".join([
                        'model = "gpt-5.5"',
                        'model_reasoning_effort = "xinflo"',
                        'service_tier = "priority"',
                        'approval_policy = "never"',
                        'model_provider = "xinflo"',
                        "",
                        '[plugins."computer-use@openai-bundled"]',
                        "enabled = true",
                        "",
                        "[mcp_servers.node_repl]",
                        'command = "node_repl.exe"',
                        "",
                        "[model_providers.xinflo]",
                        'name = "xinflo"',
                        'base_url = "https://xinflo.com/v1"',
                        'env_key = "XINFLO_API_KEY"',
                        'wire_api = "responses"',
                        "",
                    ])
                )

            service = WireService(paths)
            service.sync_custom_provider(
                provider="xinflo",
                base_url="https://api.heang.top/v1",
                api_key="sk-test-token-not-real",
                text_model="qwen3.7-plus",
                targets=("codex",),
            )

            with open(user_codex_config, "r", encoding="utf-8") as handle:
                merged = handle.read()

            self.assertIn('model = "qwen3.7-plus"', merged)
            self.assertIn('model_provider = "xinflo"', merged)
            self.assertIn('model_reasoning_effort = "xinflo"', merged)
            self.assertIn('service_tier = "priority"', merged)
            self.assertIn('approval_policy = "never"', merged)
            self.assertIn('[plugins."computer-use@openai-bundled"]', merged)
            self.assertIn("[mcp_servers.node_repl]", merged)
            self.assertIn("[model_providers.xinflo]", merged)
            self.assertIn('base_url = "https://api.heang.top/v1"', merged)
            self.assertIn('env_key = "LOOM_CODEX_API_KEY"', merged)
            self.assertIn('wire_api = "responses"', merged)
            self.assertNotIn("sk-test-token-not-real", merged)

    def test_agent_env_keys_are_persisted_for_codex_claude_and_opencode_launches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            secret = session_snapshot()["memberToken"]

            with (
                mock.patch("core.wire_config._should_persist_user_env", return_value=True),
                mock.patch("core.wire_config._write_user_env_var") as write_env,
            ):
                service.sync_from_session(session_snapshot(), targets=("opencode", "codex", "claude"))

            calls = {(call.args[0], call.args[1]) for call in write_env.call_args_list}
            self.assertIn(("LOOM_OPENCODE_API_KEY", secret), calls)
            self.assertIn(("LOOM_CODEX_API_KEY", secret), calls)
            self.assertIn(("LOOM_CLAUDE_API_KEY", secret), calls)

    def test_agent_model_sync_clears_stale_model_env_without_deleting_api_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            stale_env = {
                "OPENAI_MODEL": "agnes-2.0-flash",
                "ANTHROPIC_MODEL": "agnes-2.0-flash",
                "OPENAI_API_KEY": "sk-user-key-should-stay",
            }

            with (
                mock.patch.dict(os.environ, stale_env, clear=False),
                mock.patch("core.wire_config._should_persist_user_env", return_value=True),
                mock.patch("core.wire_config._delete_user_env_var") as delete_env,
                mock.patch("core.wire_config._write_user_env_var"),
            ):
                service.sync_from_session(session_snapshot(), targets=("codex", "claude", "opencode"))

                self.assertNotIn("OPENAI_MODEL", os.environ)
                self.assertNotIn("ANTHROPIC_MODEL", os.environ)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-user-key-should-stay")

            deleted_names = {call.args[0] for call in delete_env.call_args_list}
            self.assertIn("OPENAI_MODEL", deleted_names)
            self.assertIn("ANTHROPIC_MODEL", deleted_names)
            self.assertNotIn("OPENAI_API_KEY", deleted_names)

    def test_openclaw_agent_model_config_writes_managed_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            service.sync_from_session(session_snapshot())

            status = service.sync_agent_model_config("openclaw-companion", model="gpt-4o")

            self.assertTrue(status["configured"])
            self.assertEqual(status["model"], "gpt-4o")
            self.assertEqual(status["configPath"], paths.openclaw_config)

            openclaw_config = read_json(paths.openclaw_config, {})
            primary = openclaw_config["agents"]["defaults"]["model"]["primary"]
            self.assertTrue(primary.endswith("/gpt-4o"))
            providers = openclaw_config["models"]["providers"]
            self.assertTrue(any(provider.get("baseUrl") == "https://api.heang.top/v1" for provider in providers.values()))

    def test_agent_model_config_write_failure_restores_previous_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            service.sync_from_session(session_snapshot())
            codex_config = os.path.join(paths.data_dir, ".codex", "config.toml")

            with open(codex_config, "r", encoding="utf-8") as handle:
                before = handle.read()

            with mock.patch("core.wire_config._atomic_write_text", side_effect=OSError("disk full")):
                with self.assertRaises(WireConfigError):
                    service.sync_agent_model_config("codex-desktop", model="gpt-4o")

            with open(codex_config, "r", encoding="utf-8") as handle:
                after = handle.read()
            self.assertEqual(after, before)

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

    def test_first_custom_provider_does_not_create_fake_last_good_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            service.sync_custom_provider(
                provider="custom",
                base_url="https://third.example/v1",
                api_key="sk-test-token-not-real",
                text_model="gpt-4o",
                targets=("codex",),
            )

            self.assertFalse(os.path.exists(paths.wire_last_good))
            with self.assertRaises(WireConfigError):
                service.rollback()

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

    def test_custom_provider_blank_phone_model_keeps_desktop_and_phone_models_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            result = service.sync_custom_provider(
                provider="custom",
                base_url="https://third.example/v1",
                api_key="sk-test-token-not-real",
                text_model="claude-3-5-sonnet",
                targets=("codex", "claude", "desktop", "phone"),
            )

            public_wire = result["wire"]
            self.assertEqual(public_wire["models"]["text"], "claude-3-5-sonnet")
            self.assertEqual(public_wire["models"]["phone"], "qwen3.7-plus")

            with open(os.path.join(paths.data_dir, ".codex", "config.toml"), "r", encoding="utf-8") as handle:
                codex_text = handle.read()
            with open(os.path.join(paths.data_dir, ".claude", "settings.json"), "r", encoding="utf-8") as handle:
                claude_text = handle.read()
            phone_config = read_json(os.path.join(paths.launcher_dir, "phone-agent.json"), {})

            self.assertIn('model = "claude-3-5-sonnet"', codex_text)
            self.assertNotIn('model = "agnes-2.0-flash"', codex_text)
            claude_env = json.loads(claude_text)["env"]
            self.assertEqual(claude_env["ANTHROPIC_MODEL"], "claude-3-5-sonnet")
            self.assertEqual(claude_env["ANTHROPIC_BASE_URL"], "https://third.example")
            self.assertEqual(phone_config["llm"]["model"], "qwen3.7-plus")

    def test_codex_model_config_rejects_phone_agent_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            service.sync_from_session(session_snapshot())

            with self.assertRaises(WireConfigError):
                service.sync_agent_model_config("codex-desktop", model="agnes-2.0-flash")

    def test_custom_provider_rejects_non_text_models_as_desktop_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = WireService(AppPaths(temp_dir))

            for invalid_model in ("agnes-2.0-flash", "agnes-image-2.1-flash", "agnes-video-v2.0"):
                with self.subTest(model=invalid_model):
                    with self.assertRaises(WireConfigError):
                        service.sync_custom_provider(
                            provider="custom",
                            base_url="https://third.example/v1",
                            api_key="sk-test-token-not-real",
                            text_model=invalid_model,
                            targets=("codex",),
                        )

    def test_codex_status_detects_user_config_model_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            service.sync_from_session(session_snapshot())
            user_codex_config = os.path.join(paths.data_dir, ".codex-user", "config.toml")
            with open(user_codex_config, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "\n".join([
                        "# Managed by LOOM.",
                        'model = "gpt-5.5"',
                        'model_provider = "loom"',
                        "",
                    ])
                )

            status = service.agent_model_config_status("codex-desktop")

            self.assertTrue(status["configured"])
            self.assertEqual(status["status"], "configured_with_warning")
            self.assertEqual(status["expectedModel"], "qwen3.7-plus")
            self.assertEqual(status["actualModel"], "qwen3.7-plus")
            self.assertEqual(status["userActualModel"], "gpt-5.5")
            self.assertFalse(status["userConfigSynchronized"])

    def test_codex_status_flags_phone_model_in_user_config_as_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            service.sync_from_session(session_snapshot())
            user_codex_config = os.path.join(paths.data_dir, ".codex-user", "config.toml")
            with open(user_codex_config, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    "\n".join([
                        "# stale bad model written by older LOOM builds",
                        'model = "agnes-2.0-flash"',
                        'model_provider = "heang"',
                        "",
                    ])
                )

            status = service.agent_model_config_status("codex-desktop")

            self.assertTrue(status["configured"])
            self.assertEqual(status["status"], "configured_with_warning")
            self.assertEqual(status["expectedModel"], "qwen3.7-plus")
            self.assertEqual(status["actualModel"], "qwen3.7-plus")
            self.assertEqual(status["userActualModel"], "agnes-2.0-flash")
            self.assertEqual(status["userInvalidModel"], "agnes-2.0-flash")
            self.assertFalse(status["userConfigSynchronized"])
            self.assertIn("用户 Codex", status["message"])

    def test_codex_managed_config_survives_user_config_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)
            managed_path = os.path.join(paths.data_dir, ".codex", "config.toml")
            user_path = os.path.join(paths.data_dir, ".codex-user", "config.toml")
            from core import wire_config as wire_module

            original_write = wire_module._write_text_with_backup

            def fail_user_write(path: str, text: str) -> str:
                if os.path.abspath(path) == os.path.abspath(user_path):
                    raise PermissionError("simulated locked user profile")
                return original_write(path, text)

            with mock.patch("core.wire_config._write_text_with_backup", side_effect=fail_user_write):
                result = service.sync_custom_provider(
                    provider="OpenAI compatible",
                    base_url="https://third.example/v1",
                    api_key="sk-test-token-not-real",
                    text_model="gpt-4o",
                    targets=("codex",),
                )

            target = result["syncResults"][0]
            self.assertTrue(target["ok"])
            self.assertTrue(os.path.isfile(managed_path))
            status = service.agent_model_config_status("codex-desktop")
            self.assertTrue(status["configured"])
            self.assertEqual(status["status"], "configured_with_warning")
            self.assertFalse(status["userConfigSynchronized"])
            self.assertIn("simulated locked user profile", status["userConfigWarning"])

    def test_codex_managed_config_survives_user_environment_registry_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            service = WireService(paths)

            with (
                mock.patch("core.wire_config._should_persist_user_env", return_value=True),
                mock.patch("core.wire_config._write_user_env_var", side_effect=PermissionError("simulated registry policy block")),
            ):
                result = service.sync_custom_provider(
                    provider="OpenAI compatible",
                    base_url="https://third.example/v1",
                    api_key="sk-test-token-not-real",
                    text_model="gpt-4o",
                    targets=("codex",),
                )

            target = result["syncResults"][0]
            self.assertTrue(target["ok"])
            status = service.agent_model_config_status("codex-desktop")
            self.assertTrue(status["configured"])
            self.assertEqual(status["status"], "configured_with_warning")
            self.assertFalse(status["environmentSynchronized"])
            self.assertIn("simulated registry policy block", status["environmentWarning"])

    def test_openclaw_model_sync_rejects_phone_only_model_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            ok = sync_openclaw_models_from_gateway_profile(
                paths,
                {
                    "baseUrl": "https://third.example/v1",
                    "apiKey": "sk-test-token-not-real",
                    "models": ["agnes-2.0-flash"],
                },
            )

            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
