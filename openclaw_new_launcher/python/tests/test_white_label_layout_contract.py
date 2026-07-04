import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
DOCS = ROOT / "docs"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class WhiteLabelLayoutContractTests(unittest.TestCase):
    def test_white_label_layout_tokens_exist(self):
        css = read_text(SRC / "styles" / "index.css")
        for token in [
            ".loom-white-page",
            ".loom-panel",
            ".loom-installer-shell",
            ".loom-account-layout",
            ".loom-subscription-frame",
            ".loom-matrix-shell",
        ]:
            self.assertIn(token, css)

    def test_core_pages_opt_into_white_label_layout(self):
        agent = read_text(SRC / "components" / "agents" / "AgentInstallerPage.tsx")
        account = read_text(SRC / "components" / "license" / "LicensePage.tsx")
        matrix = read_text(SRC / "components" / "matrix" / "MatrixWorkbenchPage.tsx")

        self.assertIn('data-white-label-layout="installer"', agent)
        self.assertIn("loom-installer-shell", agent)
        self.assertIn("loom-installer-stage", agent)

        self.assertIn('data-white-label-layout="account-subscription"', account)
        self.assertIn("loom-account-layout", account)
        self.assertIn("data-subscription-external-fallback", account)

        self.assertIn('data-white-label-layout="phone-matrix"', matrix)
        self.assertIn("loom-matrix-shell", matrix)
        self.assertIn("loom-matrix-layout", matrix)

    def test_sales_ppt_layout_blueprint_exists(self):
        doc = read_text(DOCS / "LOOM_WHITE_LABEL_SALES_PPT_LAYOUT.md")
        for marker in [
            "white-label-sales-deck",
            "pain-cost",
            "operating-model",
            "proof",
            "cta",
        ]:
            self.assertIn(marker, doc)


if __name__ == "__main__":
    unittest.main()
