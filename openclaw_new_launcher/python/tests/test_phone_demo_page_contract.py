from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHONE_PAGE = os.path.join(REPO_ROOT, "src", "components", "phone", "PhoneDemoPage.tsx")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")


class PhoneDemoPageContractTests(unittest.TestCase):
    def test_phone_demo_keeps_minimal_connection_config_entry(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("手机连接配置", source)
        self.assertIn("连接令牌", source)
        self.assertIn("保存并检测", source)
        self.assertIn("phoneApi.saveDevice", source)
        self.assertIn("tokenAvailable", source)
        self.assertIn("setPhoneToken('')", source)

    def test_phone_actions_are_disabled_until_connection_config_exists(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("const canUsePhone", source)
        self.assertIn("!canUsePhone", source)
        self.assertIn("请先保存手机地址和连接令牌", source)

    def test_phone_demo_exposes_bridge_owned_model_sync_action(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("同步模型到手机", source)
        self.assertIn("phoneApi.syncModel", source)
        self.assertIn("busy === 'syncModel'", source)
        self.assertNotIn("phone-agent.json", source)

    def test_phone_api_exposes_config_without_secret_echo(self) -> None:
        with open(API_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("PhoneConfigSnapshot", source)
        self.assertIn("config: ()", source)
        self.assertIn("saveDevice", source)
        self.assertIn("syncModel", source)
        self.assertIn("api('/api/phone/config')", source)
        self.assertIn("api('/api/phone/config/device', 'POST'", source)
        self.assertIn("api('/api/phone/sync-model', 'POST')", source)


if __name__ == "__main__":
    unittest.main()
