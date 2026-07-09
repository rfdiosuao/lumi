from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_FILE = os.path.join(REPO_ROOT, "src", "features", "registry.ts")
MATRIX_PAGE = os.path.join(REPO_ROOT, "src", "components", "matrix", "MatrixWorkbenchPage.tsx")
CAPABILITIES_PAGE = os.path.join(REPO_ROOT, "src", "components", "capabilities", "CapabilityCenterPage.tsx")
SIDEBAR_FILE = os.path.join(REPO_ROOT, "src", "components", "sidebar", "Sidebar.tsx")
TITLEBAR_FILE = os.path.join(REPO_ROOT, "src", "components", "window", "WindowTitlebar.tsx")


class UiNavigationContractTests(unittest.TestCase):
    def test_core_demo_pages_are_visible_but_locked_after_install(self) -> None:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        for key in ("creative", "workbench", "capabilities"):
            self.assertRegex(source, rf"key:\s*'{key}'[\s\S]+?requiresLicense:\s*true")
        self.assertRegex(source, r"key:\s*'phone'[\s\S]+?visible:\s*HIDDEN")
        self.assertRegex(source, r"key:\s*'agentAccess'[\s\S]+?visible:\s*HIDDEN")
        self.assertNotRegex(source, r"key:\s*'creative'[\s\S]+?visible:\s*false")
        self.assertNotRegex(source, r"key:\s*'workbench'[\s\S]+?visible:\s*false")
        self.assertNotRegex(source, r"key:\s*'capabilities'[\s\S]+?visible:\s*false")

    def test_matrix_workbench_uses_real_backend_data_without_demo_fallback(self) -> None:
        with open(MATRIX_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("matrixApi.status()", source)
        self.assertIn("matrixApi.watch()", source)
        self.assertIn("matrixApi.experience()", source)
        self.assertIn("matrix-empty-state", source)
        self.assertIn("composerDisabled = dispatching || !workers.length", source)
        self.assertNotIn("DEMO_WORKERS", source)
        self.assertNotIn("FALLBACK_EVENTS", source)
        self.assertNotIn("matrixDemoMode", source)
        self.assertNotIn("success: 128", source)

    def test_other_page_only_lists_unopened_capabilities(self) -> None:
        with open(CAPABILITIES_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("桌面 RPA", source)
        self.assertIn("平台发布", source)
        self.assertIn("任务库 / 定时任务", source)
        self.assertIn("主题配置", source)
        self.assertNotIn("图片生成", source)
        self.assertNotIn("视频生成", source)
        self.assertNotIn("CLI 自动化", source)
        self.assertNotIn("Agent 接入", source)

    def test_shell_distinguishes_acquisition_and_workbench_icons_and_uses_dark_titlebar(self) -> None:
        with open(SIDEBAR_FILE, "r", encoding="utf-8") as handle:
            sidebar = handle.read()
        with open(TITLEBAR_FILE, "r", encoding="utf-8") as handle:
            titlebar = handle.read()

        self.assertIn("if (key === 'acquisition') return 'target';", sidebar)
        self.assertIn("if (key === 'workbench') return 'matrix';", sidebar)
        self.assertIn("'target'", sidebar)
        self.assertIn("name === 'target'", sidebar)
        self.assertIn("bg-app-sidebar text-white", titlebar)
        self.assertIn("flex min-w-0 flex-1 items-stretch justify-end bg-app-sidebar", titlebar)
        self.assertIn("text-white/58 hover:bg-white/[0.07] hover:text-white", titlebar)
        self.assertIn("text-white/60 hover:bg-[#E81123] hover:text-white", titlebar)
        self.assertNotIn("flex-1 items-stretch justify-end bg-surface", titlebar)
        self.assertNotIn("text-text-muted", titlebar)
        self.assertNotIn("hover:bg-hover", titlebar)


if __name__ == "__main__":
    unittest.main()
