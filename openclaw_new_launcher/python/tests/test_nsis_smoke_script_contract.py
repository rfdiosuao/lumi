import os
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "smoke-test-tauri-nsis.ps1")


class NsisSmokeScriptContractTests(unittest.TestCase):
    def test_smoke_script_is_transactional_and_checks_packaged_bridge(self) -> None:
        self.assertTrue(os.path.exists(SCRIPT_PATH), "NSIS smoke script is missing")
        with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()

        for marker in (
            "Assert-ChildPath",
            "try {",
            "finally {",
            "Rename-Item -LiteralPath $productKey",
            "Rename-Item -LiteralPath $backupKey",
            "_up_\\python-runtime\\python.exe",
            'session.impl -ne "fastapi"',
            "/api/license/current",
            "/api/matrix/status",
            "/api/matrix/acquisition",
            "matrixStatus -ne 403",
            "acquisitionStatus -ne 403",
            "verify-release-secrets.ps1",
            "-SecretScanPath $resolvedSecretScanScript",
            "Remove-Item -LiteralPath $sessionPath -Force",
        ):
            self.assertIn(marker, source)

    def test_smoke_script_does_not_print_bridge_token(self) -> None:
        with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertNotIn("ConvertTo-Json $session", source)
        self.assertNotIn("Write-Output $session.token", source)


if __name__ == "__main__":
    unittest.main()
