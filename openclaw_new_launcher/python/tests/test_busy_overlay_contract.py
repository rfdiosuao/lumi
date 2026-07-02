from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMON_FILE = os.path.join(REPO_ROOT, "src", "components", "common", "index.tsx")
AGENT_PAGE = os.path.join(REPO_ROOT, "src", "components", "agents", "AgentInstallerPage.tsx")
ACCOUNT_PAGE = os.path.join(REPO_ROOT, "src", "components", "license", "LicensePage.tsx")
PHONE_PAGE = os.path.join(REPO_ROOT, "src", "components", "phone", "PhoneDemoPage.tsx")


def _busy_overlay_source() -> str:
    with open(COMMON_FILE, "r", encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("export const BusyOverlay")
    end = source.index("export const SectionLabel", start)
    return source[start:end]


class BusyOverlayContractTests(unittest.TestCase):
    def test_busy_overlay_is_single_full_viewport_layer_without_local_blur(self) -> None:
        source = _busy_overlay_source()

        self.assertIn("createPortal", source)
        self.assertIn("document.body", source)
        self.assertIn("data-busy-overlay", source)
        self.assertIn("fixed inset-0", source)
        self.assertIn("z-[99940]", source)
        self.assertIn("pointer-events-auto", source)
        self.assertNotIn("backdrop-blur", source)
        self.assertNotIn("blur-[", source)
        self.assertNotIn("bg-gradient", source)

    def test_busy_overlay_does_not_change_page_layout_or_scroll_container(self) -> None:
        source = _busy_overlay_source()

        self.assertIn("role=\"status\"", source)
        self.assertIn("aria-live=\"polite\"", source)
        self.assertIn("data-busy-overlay-card", source)
        self.assertIn("max-h-[min(80vh,420px)]", source)
        self.assertIn("overflow-auto", source)
        self.assertIn("break-words", source)
        self.assertIn("whitespace-pre-wrap", source)
        self.assertNotIn("absolute inset-0", source)

    def test_install_account_and_phone_pages_use_shared_busy_overlay(self) -> None:
        for path in (AGENT_PAGE, ACCOUNT_PAGE, PHONE_PAGE):
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            self.assertIn("<BusyOverlay", source, path)

        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            phone_source = handle.read()
        self.assertIn("active={Boolean(busy)}", phone_source)
        self.assertNotIn("active={Boolean(blockingBusy)}", phone_source)


if __name__ == "__main__":
    unittest.main()
