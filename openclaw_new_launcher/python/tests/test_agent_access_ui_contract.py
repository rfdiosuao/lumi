from __future__ import annotations

import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AgentAccessUiContractTests(unittest.TestCase):
    def _page(self) -> str:
        page_path = os.path.join(ROOT, "src", "components", "agentAccess", "AgentAccessPage.tsx")
        with open(page_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_agent_access_route_is_registered_but_entry_lives_inside_agents(self) -> None:
        registry_path = os.path.join(ROOT, "src", "features", "registry.ts")
        page_path = os.path.join(ROOT, "src", "features", "pages.tsx")
        agent_page_path = os.path.join(ROOT, "src", "components", "agents", "AgentInstallerPage.tsx")

        with open(registry_path, "r", encoding="utf-8") as handle:
            registry = handle.read()
        with open(page_path, "r", encoding="utf-8") as handle:
            pages = handle.read()
        with open(agent_page_path, "r", encoding="utf-8") as handle:
            agent_page = handle.read()

        self.assertTrue("Agent 接入" in registry or "开发者接入" in registry)
        self.assertRegex(registry, r"key:\s*'agentAccess'[\s\S]+?requiresLicense:\s*true")
        self.assertRegex(registry, r"key:\s*'agentAccess'[\s\S]+?visible:\s*HIDDEN")
        self.assertIn("agentAccess", pages)
        self.assertIn("data-agent-access-inline", agent_page)
        self.assertIn("copyAgentAccessPrompt", agent_page)
        self.assertIn("buildOneShotAgentPrompt(buildMcpJson())", agent_page)

    def test_agent_access_page_points_to_mcp_config(self) -> None:
        page = self._page()

        self.assertIn(".mcp.json", page)
        self.assertIn("loom_mcp.py", page)
        self.assertLess(page.count("<p"), 4)

    def test_agent_access_page_exposes_cross_platform_skill_bootstrap(self) -> None:
        page = self._page()

        self.assertIn("LOOM_COMMAND_BRAIN_SKILL_PATH", page)
        self.assertIn("LOOM_COMMAND_BRAIN_SKILL_URLS", page)
        self.assertIn("/skills/loom-command-brain/SKILL.md", page)
        self.assertIn("loom-command-brain", page)
        self.assertIn("Skill 位置", page)
        self.assertIn("CODEX_HOME", page)
        self.assertIn("LOOM_HOME", page)
        self.assertIn("%USERPROFILE%\\\\.codex", page)
        self.assertIn("$HOME/.codex", page)
        self.assertIn("/Applications/LOOM.app/Contents/Resources", page)
        self.assertNotIn("D:\\Axiangmu\\AUSTART", page)

        public_skill_path = os.path.join(ROOT, "public", "skills", "loom-command-brain", "SKILL.md")
        self.assertTrue(os.path.exists(public_skill_path))
        with open(public_skill_path, "r", encoding="utf-8") as handle:
            public_skill = handle.read()
        self.assertIn("name: loom-command-brain", public_skill)
        self.assertIn("LOOM CLI/MCP", public_skill)
        self.assertIn("CODEX_HOME", public_skill)
        self.assertIn("LOOM_HOME", public_skill)
        self.assertIn("$HOME/.codex", public_skill)
        self.assertNotIn("D:\\Axiangmu\\AUSTART", public_skill)

    def test_agent_access_page_documents_encoding_and_tool_fallback(self) -> None:
        page = self._page()

        self.assertIn("UTF-8", page)
        self.assertIn("<meta charset=\"UTF-8\">", page)
        self.assertIn("Computer Use", page)
        self.assertIn("Node REPL", page)
        self.assertIn("LOOM CLI/MCP", page)
        self.assertIn("wire_api = \"chat\"", page)

    def test_agent_access_page_exposes_one_shot_bootstrap_prompt(self) -> None:
        page = self._page()

        self.assertIn("一条提示词接入", page)
        self.assertIn("buildOneShotAgentPrompt", page)
        self.assertIn("BEGIN_SKILL_URLS", page)
        self.assertIn("END_SKILL_URLS", page)
        self.assertIn("BEGIN_SKILL_MD", page)
        self.assertIn("END_SKILL_MD", page)
        self.assertIn("BEGIN_MCP_JSON", page)
        self.assertIn("END_MCP_JSON", page)
        self.assertIn("自动下载 Skill", page)
        self.assertIn("CopyOnlyBlock", page)
        self.assertIn("data-agent-one-shot-copy", page)
        self.assertIn("提示词正文不会展示在页面上", page)
        self.assertIn("高级配置", page)

    def test_agent_access_prompt_mentions_creative_to_phone_workflow(self) -> None:
        page = self._page()
        public_skill_path = os.path.join(ROOT, "public", "skills", "loom-command-brain", "SKILL.md")
        with open(public_skill_path, "r", encoding="utf-8") as handle:
            public_skill = handle.read()

        for source in (page, public_skill):
            self.assertIn("media image", source)
            self.assertIn("media video", source)
            self.assertIn("matrix dispatch", source)
            self.assertIn("Image-to-video-to-phone workflow", source)
            self.assertIn("read-only", source)
            self.assertIn("human confirmation", source)


if __name__ == "__main__":
    unittest.main()
