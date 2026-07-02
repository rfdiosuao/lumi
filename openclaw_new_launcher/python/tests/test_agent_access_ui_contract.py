from __future__ import annotations

import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AgentAccessUiContractTests(unittest.TestCase):
    def test_agent_access_entry_is_registered_without_long_copy(self) -> None:
        registry_path = os.path.join(ROOT, "src", "features", "registry.ts")
        page_path = os.path.join(ROOT, "src", "features", "pages.tsx")

        with open(registry_path, "r", encoding="utf-8") as handle:
            registry = handle.read()
        with open(page_path, "r", encoding="utf-8") as handle:
            pages = handle.read()

        self.assertTrue("Agent 接入" in registry or "开发者接入" in registry)
        self.assertRegex(registry, r"key:\s*'agentAccess'[\s\S]+?requiresLicense:\s*true")
        self.assertIn("agentAccess", pages)

    def test_agent_access_page_points_to_mcp_config(self) -> None:
        page_path = os.path.join(ROOT, "src", "components", "agentAccess", "AgentAccessPage.tsx")
        with open(page_path, "r", encoding="utf-8") as handle:
            page = handle.read()

        self.assertIn(".mcp.json", page)
        self.assertIn("loom_mcp.py", page)
        self.assertLess(page.count("<p"), 4)

    def test_agent_access_page_exposes_loom_command_brain_skill(self) -> None:
        page_path = os.path.join(ROOT, "src", "components", "agentAccess", "AgentAccessPage.tsx")
        with open(page_path, "r", encoding="utf-8") as handle:
            page = handle.read()

        self.assertIn("LOOM_COMMAND_BRAIN_SKILL_PATH", page)
        self.assertIn("loom-command-brain", page)
        self.assertIn("Skill", page)
        self.assertIn("复制 Skill 路径", page)


if __name__ == "__main__":
    unittest.main()
