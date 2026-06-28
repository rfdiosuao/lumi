from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_PAGE = os.path.join(REPO_ROOT, "src", "components", "agents", "AgentInstallerPage.tsx")


class AgentInstallerPageContractTests(unittest.TestCase):
    def test_install_page_copy_is_readable_chinese_not_mojibake(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        mojibake_markers = tuple(chr(code) for code in (
            0x93C5,
            0x7F02,
            0x935A,
            0x9353,
            0x59AB,
            0x7039,
            0x7ECB,
            0x941C,
            0x95BF,
            0x4FD9,
            0x255C,
        ))
        for marker in mojibake_markers:
            self.assertNotIn(marker, source)

    def test_install_page_exposes_retry_and_log_panel_for_demo_flow(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-agent-log-panel", source)
        self.assertIn("data-agent-retry-button", source)
        self.assertIn("安装日志", source)
        self.assertIn("重试安装", source)

    def test_prepare_flow_installs_when_detection_finds_upgrade_available(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("needsInstallAfterDetect", source)
        self.assertIn("upgrade_available", source)
        self.assertIn("检测到需安装或升级，开始下载安装", source)

    def test_destructive_or_system_modifying_actions_are_confirmed(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("confirmPreflightRepair", source)
        self.assertIn("diagnosticsApi.repair({ confirmed: true })", source)
        self.assertIn("componentApi.install(component.id, { confirmed: true", source)


if __name__ == "__main__":
    unittest.main()
