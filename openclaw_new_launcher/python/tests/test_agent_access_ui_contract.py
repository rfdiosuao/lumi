from __future__ import annotations

import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AgentAccessUiContractTests(unittest.TestCase):
    def _page(self) -> str:
        page_path = os.path.join(ROOT, "src", "components", "agentAccess", "AgentAccessPage.tsx")
        with open(page_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _public_skill(self) -> str:
        public_skill_path = os.path.join(ROOT, "public", "skills", "loom-command-brain", "SKILL.md")
        with open(public_skill_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _public_workflows(self) -> str:
        public_workflows_path = os.path.join(
            ROOT, "public", "skills", "loom-command-brain", "references", "WORKFLOWS.md"
        )
        with open(public_workflows_path, "r", encoding="utf-8") as handle:
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
        self.assertIn("LOOM_CLI", page)
        self.assertIn("LOOM_CLI_DIR", page)
        self.assertLess(page.count("<p"), 4)

    def test_agent_access_page_exposes_cross_platform_skill_bootstrap(self) -> None:
        page = self._page()
        public_skill_path = os.path.join(ROOT, "public", "skills", "loom-command-brain", "SKILL.md")
        public_workflows_path = os.path.join(
            ROOT, "public", "skills", "loom-command-brain", "references", "WORKFLOWS.md"
        )

        self.assertIn("LOOM_COMMAND_BRAIN_SKILL_PATH", page)
        self.assertIn("LOOM_COMMAND_BRAIN_WORKFLOWS_PATH", page)
        self.assertIn("LOOM_COMMAND_BRAIN_SKILL_URLS", page)
        self.assertIn("LOOM_COMMAND_BRAIN_WORKFLOWS_URLS", page)
        self.assertIn("/skills/loom-command-brain/SKILL.md", page)
        self.assertIn("/skills/loom-command-brain/references/WORKFLOWS.md", page)
        self.assertIn("CODEX_HOME", page)
        self.assertIn("LOOM_CLI", page)
        self.assertIn("%USERPROFILE%\\\\.codex", page)
        self.assertIn("$HOME/.codex", page)
        self.assertIn("/Applications/LOOM.app/Contents/Resources", page)
        self.assertTrue(os.path.exists(public_skill_path))
        self.assertTrue(os.path.exists(public_workflows_path))

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

        self.assertIn("buildOneShotAgentPrompt", page)
        self.assertIn("BEGIN_SKILL_URLS", page)
        self.assertIn("END_SKILL_URLS", page)
        self.assertIn("BEGIN_WORKFLOWS_URLS", page)
        self.assertIn("END_WORKFLOWS_URLS", page)
        self.assertIn("BEGIN_SKILL_MD", page)
        self.assertIn("END_SKILL_MD", page)
        self.assertIn("BEGIN_WORKFLOWS_MD", page)
        self.assertIn("END_WORKFLOWS_MD", page)
        self.assertIn("BEGIN_MCP_JSON", page)
        self.assertIn("END_MCP_JSON", page)
        self.assertIn("data-agent-one-shot-copy", page)

    def test_agent_access_prompt_mentions_phone_cli_surface(self) -> None:
        sources = [self._page(), self._public_skill(), self._public_workflows()]

        for source in sources:
            self.assertIn("phone:agent", source)
            self.assertIn("phone:vision", source)
            self.assertIn("phone:video", source)
            self.assertIn("phone:image", source)
            self.assertIn("phone:image:edit", source)
            self.assertIn("phone:fleet", source)
            self.assertIn("phone:game", source)
            self.assertIn("phone:publish", source)
            self.assertIn("loom:phone:video", source)
            self.assertIn("events", source)
            self.assertIn("click_ref", source)
            self.assertTrue(
                "Android screen-capture consent prompt" in source
                or "Android MediaProjection consent prompt" in source
            )

    def test_agent_access_skill_text_has_no_mojibake_or_local_dev_paths(self) -> None:
        sources = [self._page(), self._public_skill(), self._public_workflows()]
        mojibake_markers = [
            "".join(chr(code) for code in codes)
            for codes in (
                (37902, 29808, 58931),
                (38328, 12517, 22717),
                (22994, 28057, 59336),
                (23092, 28355, 25643),
                (28729, 21578, 24387),
                (23138, 36346, 31220),
                (38329, 24658, 20785),
                (38331, 12834, 21904, 37736, 63),
            )
        ]
        forbidden = [
            r"D:\Axiangmu\AUSTART",
            r"C:\Users\Administrator",
            *mojibake_markers,
        ]

        for source in sources:
            for token in forbidden:
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
