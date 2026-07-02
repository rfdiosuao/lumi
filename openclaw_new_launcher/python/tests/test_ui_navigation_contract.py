from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_FILE = os.path.join(REPO_ROOT, "src", "features", "registry.ts")
MATRIX_PAGE = os.path.join(REPO_ROOT, "src", "components", "matrix", "MatrixWorkbenchPage.tsx")


class UiNavigationContractTests(unittest.TestCase):
    def test_core_demo_pages_are_visible_but_locked_after_install(self) -> None:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        for key in ("creative", "workbench", "agentAccess", "capabilities"):
            self.assertRegex(source, rf"key:\s*'{key}'[\s\S]+?requiresLicense:\s*true")
        self.assertRegex(source, r"key:\s*'phone'[\s\S]+?visible:\s*HIDDEN")
        self.assertNotRegex(source, r"key:\s*'creative'[\s\S]+?visible:\s*false")
        self.assertNotRegex(source, r"key:\s*'workbench'[\s\S]+?visible:\s*false")
        self.assertNotRegex(source, r"key:\s*'agentAccess'[\s\S]+?visible:\s*false")
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


if __name__ == "__main__":
    unittest.main()
